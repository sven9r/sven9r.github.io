"""Refresh OpenAlex counts for the curated published papers in research.html.

Uses only public, keyless singleton DOI lookups. It never imports publications
or edits bibliographic text. Failed lookups preserve the last successful count.
API reference: https://help.openalex.org/api/get-single-entities/
"""

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s<>\"#?]+", re.I)
WORK_PATTERN = re.compile(r"https://openalex\.org/W[1-9]\d*")


def normalize_doi(value):
    if not isinstance(value, str):
        raise ValueError("DOI must be a string.")
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.I).lower()
    if not DOI_PATTERN.fullmatch(doi):
        raise ValueError(f"Invalid DOI: {value!r}")
    return doi


class PublicationParser(HTMLParser):
    """Locate only explicitly curated publication cards, never manuscripts."""

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.section_depth = 0
        self.section_count = 0
        self.pending = None
        self.publications = []
        self.offsets = [0] + [match.end() for match in re.finditer("\n", html)]
        self.feed(html)
        if self.section_depth or self.pending:
            raise ValueError("The published-paper section is not closed.")
        if self.section_count != 1 or not self.publications:
            raise ValueError("Expected one non-empty #publications section with DOI-labelled cards.")
        dois = [paper["doi"] for paper in self.publications]
        if len(dois) != len(set(dois)):
            raise ValueError("Published-paper cards contain a duplicate DOI.")

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "section":
            if values.get("id") == "publications":
                if self.section_depth:
                    raise ValueError("Nested #publications sections are not supported.")
                self.section_count += 1
                self.section_depth = 1
            elif self.section_depth:
                self.section_depth += 1
        if "data-doi" in values:
            if not self.section_depth or tag != "article" or "publication-card" not in values.get("class", "").split():
                raise ValueError("DOI metadata must belong to a published-paper article card.")
        if tag == "article" and self.section_depth and "publication-card" in values.get("class", "").split():
            if self.pending is not None:
                raise ValueError("Nested publication cards are not supported.")
            if not values.get("data-doi"):
                raise ValueError("A published-paper card is missing its data-doi attribute.")
            self.pending = {"doi": normalize_doi(values["data-doi"])}

    def handle_endtag(self, tag):
        if tag == "article" and self.pending is not None:
            line, column = self.getpos()
            self.pending["end_offset"] = self.offsets[line - 1] + column
            self.publications.append(self.pending)
            self.pending = None
        if tag == "section" and self.section_depth:
            self.section_depth -= 1


def read_publications(html):
    return PublicationParser(html).publications


def validate_record(record, expected_doi):
    if not isinstance(record, dict) or record.get("doi") != expected_doi:
        raise ValueError("Cached DOI does not exactly match its canonical key.")
    normalize_doi(expected_doi)
    if normalize_doi(expected_doi) != expected_doi:
        raise ValueError("Cached DOI keys must use canonical lowercase identifiers.")
    if not isinstance(record.get("openalex_id"), str) or not WORK_PATTERN.fullmatch(record["openalex_id"]):
        raise ValueError("OpenAlex work links must use https://openalex.org/W followed by digits.")
    count = record.get("cited_by_count")
    if type(count) is not int or count < 0:
        raise ValueError("Citation counts must be nonnegative integers.")
    captured = record.get("captured_at")
    if not isinstance(captured, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", captured):
        raise ValueError("Citation capture time must be a UTC ISO timestamp ending in Z.")
    try:
        datetime.strptime(captured, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError("Invalid citation capture timestamp.") from error
    return record


def load_cache(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("source") != "OpenAlex" or not isinstance(data.get("works"), dict):
        raise ValueError("Unsupported citation cache; expected OpenAlex schema_version 1.")
    return {doi: validate_record(record, doi) for doi, record in data["works"].items()}


def record_from_response(data, expected_doi, captured_at=None):
    if not isinstance(data, dict) or normalize_doi(data.get("doi")) != expected_doi:
        raise ValueError("OpenAlex returned a different or missing DOI.")
    record = {"doi": expected_doi, "openalex_id": data.get("id"), "cited_by_count": data.get("cited_by_count"), "captured_at": captured_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}
    return validate_record(record, expected_doi)


def fetch_record(doi, timeout=10, retries=1):
    request = Request("https://api.openalex.org/works/https://doi.org/" + quote(doi, safe="/"), headers={"Accept": "application/json", "User-Agent": "WebLabHomepage/1.0 (public citation metadata refresh)"})
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read(5_000_001)
            if len(payload) > 5_000_000:
                raise ValueError("OpenAlex response exceeded the expected size.")
            return record_from_response(json.loads(payload), doi), None
        except HTTPError as error:
            reason = f"HTTP {error.code}"
            retryable = error.code == 429 or error.code >= 500
        except (URLError, TimeoutError, OSError):
            reason, retryable = "network request failed", True
        except (ValueError, UnicodeError):
            reason, retryable = "invalid or mismatched OpenAlex response", False
        if not retryable or attempt == retries:
            return None, reason
        time.sleep(1)
    return None, "lookup failed"


def refresh(dois, existing, lookup=fetch_record, timeout=10, retries=1):
    records = dict(existing)
    summary = {"fetched": 0, "retained": 0, "unavailable": 0}
    errors = []
    for index, doi in enumerate(dois):
        if index:
            time.sleep(0.2)  # At most five singleton lookups/second, without keys.
        record, reason = lookup(doi, timeout=timeout, retries=retries)
        if record is not None:
            records[doi] = validate_record(record, doi)
            summary["fetched"] += 1
        else:
            summary["retained" if doi in existing else "unavailable"] += 1
            errors.append((doi, reason or "lookup failed"))
    return records, summary, errors


def write_cache(path, records):
    data = {"schema_version": 1, "source": "OpenAlex", "works": {doi: validate_record(record, doi) for doi, record in records.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".citations-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research", type=Path, default=ROOT / "research.html", help="Curated source HTML; only #publications cards are fetched.")
    parser.add_argument("--cache", type=Path, default=ROOT / "content/citations.json")
    parser.add_argument("--timeout", type=float, default=10, help="Per-request timeout in seconds (0.1–60).")
    parser.add_argument("--retries", type=int, choices=(0, 1, 2), default=1)
    args = parser.parse_args()
    try:
        if not 0.1 <= args.timeout <= 60:
            raise ValueError("--timeout must be between 0.1 and 60 seconds.")
        if args.research.suffix.lower() != ".html" or args.cache.suffix.lower() != ".json":
            raise ValueError("--research must be an HTML file and --cache must be a JSON file.")
        if args.cache.resolve() == args.research.resolve():
            raise ValueError("The cache must not overwrite the source HTML.")
        papers = read_publications(args.research.read_text(encoding="utf-8"))
        existing = load_cache(args.cache)
        records, summary, errors = refresh([paper["doi"] for paper in papers], existing, timeout=args.timeout, retries=args.retries)
        if summary["fetched"]:
            write_cache(args.cache, records)
        for doi, reason in errors:
            print(f"OpenAlex {doi}: {reason}; " + ("kept previous count." if doi in existing else "count unavailable."), file=sys.stderr)
        print(f"OpenAlex: {len(papers)} curated papers; {summary['fetched']} refreshed, {summary['retained']} retained, {summary['unavailable']} unavailable.")
        return 0 if summary["fetched"] or summary["retained"] else 1
    except (OSError, ValueError) as error:
        print(f"Citation refresh failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
