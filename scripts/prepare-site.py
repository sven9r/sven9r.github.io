"""Create a small, allowlisted static site. Originals are never modified."""

import argparse
from collections import deque
from datetime import datetime
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import json
import importlib.util
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUFFIXES = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".webm", ".mp3", ".ogg"}
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
CSS_IMPORT = re.compile(r"@import\s+['\"]([^'\"]+)['\"]", re.I)
APPLICATION_CV = re.compile(r"(?:smnk|application|bewerbung|cover.?letter|research.?statement|teaching.?statement)", re.I)
MARKER = ".site-build.json"


def citation_helpers():
    spec = importlib.util.spec_from_file_location("homepage_citations", Path(__file__).with_name("update-citations.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_citation_badges(text, records):
    helpers = citation_helpers()
    papers = helpers.read_publications(text)
    for paper in reversed(papers):
        record = records.get(paper["doi"])
        if record is None:
            continue  # Unavailable is different from a verified zero count.
        helpers.validate_record(record, paper["doi"])
        captured = datetime.strptime(record["captured_at"], "%Y-%m-%dT%H:%M:%SZ")
        date = captured.strftime("%Y-%m-%d")
        month = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[captured.month - 1]
        label = f"{captured.day} {month} {captured.year}"
        count = record["cited_by_count"]
        noun = "citation" if count == 1 else "citations"
        badge = f'  <p class="citation-count"><a href="{escape(record["openalex_id"], quote=True)}" target="_blank" rel="noopener noreferrer">{count:,} {noun} · OpenAlex</a> <span class="citation-count__date">· checked <time datetime="{date}">{label}</time></span></p>\n          '
        offset = paper["end_offset"]
        text = text[:offset] + badge + text[offset:]
    return text


class PublicationYearParser(HTMLParser):
    """Read the visible year from each curated published-paper card."""

    def __init__(self, text, dois):
        super().__init__(convert_charrefs=True)
        self.dois = set(dois)
        self.normalize_doi = citation_helpers().normalize_doi
        self.current_doi = None
        self.in_year = False
        self.year_text = []
        self.years = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "article" and values.get("data-doi"):
            doi = self.normalize_doi(values["data-doi"])
            if doi in self.dois:
                self.current_doi = doi
        if tag == "p" and self.current_doi and "publication-meta" in values.get("class", "").split():
            self.in_year = True
            self.year_text = []

    def handle_data(self, data):
        if self.in_year:
            self.year_text.append(data)

    def handle_endtag(self, tag):
        if tag == "p" and self.in_year:
            label = "".join(self.year_text).strip()
            if not re.fullmatch(r"\d{4}", label) or self.current_doi in self.years:
                raise ValueError(f"Expected one four-digit publication year for {self.current_doi}.")
            self.years[self.current_doi] = int(label)
            self.in_year = False
        if tag == "article":
            self.current_doi = None


def validate_journal_metric(doi, record, publication_year):
    if not isinstance(record, dict):
        raise ValueError(f"Journal metric for {doi} must be an object.")
    for field in ("journal", "source_label"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f"Journal metric for {doi} needs a non-empty {field}.")
    for field in ("publication_year", "jif_year"):
        if type(record.get(field)) is not int or record[field] != publication_year:
            raise ValueError(f"Journal metric {field} for {doi} must match its visible publication year ({publication_year}).")
    jif = record.get("jif")
    if type(jif) not in (int, float) or not math.isfinite(jif) or jif <= 0:
        raise ValueError(f"Journal impact factor for {doi} must be a positive finite number.")
    source_url = record.get("source_url")
    if not isinstance(source_url, str):
        raise ValueError(f"Journal metric for {doi} needs an HTTPS source URL.")
    try:
        url = urlsplit(source_url)
    except ValueError as error:
        raise ValueError(f"Malformed journal metric source URL for {doi}.") from error
    if url.scheme != "https" or not url.hostname or url.username or url.password or re.search(r"\s", source_url):
        raise ValueError(f"Journal metric for {doi} needs an HTTPS source URL without credentials or whitespace.")
    try:
        url.port  # Reject malformed ports, even when a hostname was parsed.
    except ValueError as error:
        raise ValueError(f"Malformed journal metric source URL for {doi}.") from error
    verified = record.get("verified_on")
    if not isinstance(verified, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", verified):
        raise ValueError(f"Journal metric verified_on for {doi} must be YYYY-MM-DD.")
    try:
        datetime.strptime(verified, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError(f"Invalid journal metric verified_on date for {doi}.") from error
    return record


def load_journal_metrics(path, text):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError(f"Invalid JSON in journal metrics file {path.name}.") from error
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1 or not isinstance(data.get("works"), dict):
        raise ValueError("Journal metrics need schema_version 1 and a works object keyed by DOI.")
    helpers = citation_helpers()
    papers = helpers.read_publications(text)
    dois = {paper["doi"] for paper in papers}
    years = PublicationYearParser(text, dois).years
    records = {}
    for doi, record in data["works"].items():
        if helpers.normalize_doi(doi) != doi or doi not in dois:
            raise ValueError(f"Journal metric DOI must exactly match a curated published-paper DOI: {doi!r}")
        if doi not in years:
            raise ValueError(f"Missing visible publication year for journal metric DOI {doi}.")
        records[doi] = validate_journal_metric(doi, record, years[doi])
    return records


def render_journal_metrics(text, records):
    if not records:
        return text
    helpers = citation_helpers()
    papers = helpers.read_publications(text)
    years = PublicationYearParser(text, (paper["doi"] for paper in papers)).years
    for paper in reversed(papers):
        doi = paper["doi"]
        record = records.get(doi)
        if record is None:
            continue
        if doi not in years:
            raise ValueError(f"Missing visible publication year for journal metric DOI {doi}.")
        validate_journal_metric(doi, record, years[doi])
        value = format(record["jif"], ".15g")
        label = f'{record["jif_year"]} journal impact factor: {value}'
        provenance = f'Source: {record["source_label"]}; verified {record["verified_on"]}'
        badge = f'  <p class="journal-impact"><a href="{escape(record["source_url"], quote=True)}" target="_blank" rel="noopener noreferrer" title="{escape(provenance, quote=True)}">{escape(label)}</a> <span class="journal-impact__source">· {escape(record["source_label"])}</span></p>\n          '
        offset = paper["end_offset"]
        text = text[:offset] + badge + text[offset:]
    return text


def is_cv_reference(reference):
    url = urlsplit(reference.strip())
    path = Path(unquote(url.path))
    return not url.scheme and not url.netloc and path.suffix.lower() == ".pdf" and ("cv" in path.parts or "cv" in path.stem.lower())


def omit_cv_links(text):
    anchor = re.compile(r"<a\b[^>]*\bhref\s*=\s*(['\"])(.*?)\1[^>]*>[\s\S]*?</a\s*>", re.I)

    def strip_item(match):
        link = anchor.fullmatch(match.group(1).strip())
        return "" if link and is_cv_reference(link.group(2)) else match.group(0)

    text = re.sub(r"<li\b[^>]*>\s*(<a\b[^>]*>[\s\S]*?</a\s*>)\s*</li\s*>", strip_item, text, flags=re.I)
    return anchor.sub(lambda match: "" if is_cv_reference(match.group(2)) else match.group(0), text)


def local_path(reference, owner):
    """Return a contained source path; external/data/fragment URLs need no copy."""
    url = urlsplit(reference.strip())
    if url.scheme or url.netloc or not url.path:
        return None
    relative = unquote(url.path)
    path = (ROOT / relative.lstrip("/") if relative.startswith("/") else owner.parent / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Reference escapes the project: {reference} in {owner.relative_to(ROOT)}")
    rel = path.relative_to(ROOT)
    if any(part.startswith(".") for part in rel.parts) or any(part in {"scripts", "content", "dist"} for part in rel.parts):
        raise ValueError(f"Source/editor file is referenced: {rel}")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"Referenced file type is not approved for publishing: {rel}")
    if path.suffix.lower() == ".html" and path.parent != ROOT:
        raise ValueError(f"Only top-level HTML pages are approved: {rel}")
    if path.suffix.lower() == ".js" and path != ROOT / "script.js":
        raise ValueError(f"Only the site's script.js is approved: {rel}")
    if not path.is_file():
        raise ValueError(f"Missing local asset: {rel} (from {owner.relative_to(ROOT)})")
    return path


class PageParser(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.references = []
        self.images = []
        self.title = ""
        self.description = ""
        self.in_title = False
        self.line_offsets = [0]
        for match in re.finditer("\n", source):
            self.line_offsets.append(match.end())
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and values.get("name", "").lower() == "description":
            self.description = values.get("content", "")
        for name in ("src", "href", "poster"):
            if values.get(name):
                self.references.append(values[name])
        if values.get("srcset"):
            self.references.extend(part.strip().split()[0] for part in values["srcset"].split(",") if part.strip())
        if values.get("style"):
            self.references.extend(match[1] for match in CSS_URL.findall(values["style"]))
        if tag == "img":
            line, column = self.getpos()
            offset = self.line_offsets[line - 1] + column
            self.images.append((offset, self.get_starttag_text(), attrs))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def collect_sources(allow_application_cv, omit_cv=False):
    pages = sorted(path for path in ROOT.glob("*.html") if not path.name.startswith("."))
    if ROOT / "index.html" not in pages:
        raise ValueError("The homepage index.html is missing.")
    queue = deque(pages + [ROOT / "styles.css", ROOT / "script.js"])
    if (ROOT / "favicon.svg").is_file():
        queue.append(ROOT / "favicon.svg")
    sources, parsers = set(), {}
    while queue:
        path = queue.popleft()
        if path in sources:
            continue
        if not path.is_file():
            raise ValueError(f"Missing site file: {path.relative_to(ROOT)}")
        if path.suffix.lower() == ".pdf" and APPLICATION_CV.search(path.name) and not allow_application_cv:
            raise ValueError(f"Application-specific document cannot be published: {path.relative_to(ROOT)}. Replace the link with a reviewed public CV, remove it, or explicitly use --allow-application-cv.")
        sources.add(path)
        references = []
        if path.suffix.lower() == ".html":
            parsers[path] = PageParser(path.read_text(encoding="utf-8"))
            references = parsers[path].references
        elif path.suffix.lower() == ".css":
            css = path.read_text(encoding="utf-8")
            references = [match[1] for match in CSS_URL.findall(css)] + CSS_IMPORT.findall(css)
        for reference in references:
            if omit_cv and is_cv_reference(reference):
                continue
            target = local_path(reference, path)
            if target is not None:
                queue.append(target)
    return pages, sources, parsers


def copy_asset(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        shutil.copyfile(source, target)
        return
    with Image.open(source) as original:
        if source.suffix.lower() == ".png" and getattr(original, "is_animated", False):
            raise ValueError(f"Animated PNG needs an explicit export: {source.relative_to(ROOT)}")
        image = ImageOps.exif_transpose(original)
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        image.info.clear()
        if source.suffix.lower() in {".jpg", ".jpeg"}:
            image.convert("RGB").save(target, "JPEG", quality=82, optimize=True, progressive=True, exif=b"")
        else:
            image.save(target, "PNG", optimize=True)


def public_url(base, path):
    relative = path.relative_to(ROOT).as_posix()
    return base + ("/" if relative == "index.html" else "/" + quote(relative, safe="/"))


def output_html(source, parser, stage, base, omit_cv=False, citation_records=None, journal_metrics=None):
    text = source.read_text(encoding="utf-8")
    for index, (offset, original, attrs) in reversed(list(enumerate(parser.images))):
        values = dict(attrs)
        image_path = local_path(values.get("src", ""), source)
        if image_path and (stage / image_path.relative_to(ROOT)).is_file():
            try:
                with Image.open(stage / image_path.relative_to(ROOT)) as image:
                    values.setdefault("width", str(image.width))
                    values.setdefault("height", str(image.height))
            except (OSError, ValueError):
                pass  # SVG and remote images may not have raster dimensions.
        values.setdefault("decoding", "async")
        if index:
            values.setdefault("loading", "lazy")
        replacement = "<img" + "".join(" " + key if value is None else f' {key}="{escape(value, quote=True)}"' for key, value in values.items()) + ">"
        text = text[:offset] + replacement + text[offset + len(original):]
    if omit_cv:
        text = omit_cv_links(text)
    if source.name == "research.html":
        text = render_citation_badges(text, citation_records or {})
        text = render_journal_metrics(text, journal_metrics or {})
    # Updated assets and the public CV must not reuse an older browser copy.
    for asset, attribute in (("styles.css", "href"), ("script.js", "src"), ("cv/Sven_Weber_CV_public.pdf", "href")):
        if not (stage / asset).is_file():
            continue
        version = sha256((stage / asset).read_bytes()).hexdigest()[:12]
        text = text.replace(f'{attribute}="{asset}"', f'{attribute}="{asset}?v={version}"')
    canonical = public_url(base, source)
    # Source pages remain unchanged; deployment metadata belongs to this build.
    text = re.sub(r'\s*<link\b(?=[^>]*\brel=[\'\"]canonical[\'\"])[^>]*>', "", text, flags=re.I)
    text = re.sub(r'\s*<meta\b(?=[^>]*\bproperty=[\'\"]og:[^\'\"]+[\'\"])[^>]*>', "", text, flags=re.I)
    metadata = [f'<link rel="canonical" href="{escape(canonical, quote=True)}">', '<meta property="og:type" content="website">', f'<meta property="og:title" content="{escape(parser.title.strip(), quote=True)}">', f'<meta property="og:description" content="{escape(parser.description, quote=True)}">', f'<meta property="og:url" content="{escape(canonical, quote=True)}">']
    if (stage / "favicon.svg").exists() and not re.search(r'rel=[\'\"](?:shortcut )?icon[\'\"]', text, re.I):
        metadata.append('<link rel="icon" href="favicon.svg" type="image/svg+xml">')
    if not re.search(r"</head\s*>", text, re.I):
        raise ValueError(f"Missing closing head in {source.name}")
    return re.sub(r"</head\s*>", lambda match: "    " + "\n    ".join(metadata) + "\n  </head>", text, count=1, flags=re.I)


def build(base, output, allow_application_cv, omit_cv=False):
    url = urlsplit(base)
    if url.scheme not in {"https", "http"} or not url.netloc or url.query or url.fragment or url.username or url.password:
        raise ValueError("--base-url must be a public http(s) URL without credentials, query or fragment.")
    base = base.rstrip("/")
    output = output.resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        raise ValueError("Output must not replace the project or one of its ancestors.")
    if output.exists() and (not output.is_dir() or (any(output.iterdir()) and not (output / MARKER).is_file())):
        raise ValueError(f"Refusing to overwrite a non-generated output directory: {output}")
    pages, sources, parsers = collect_sources(allow_application_cv, omit_cv)
    citation_records = {}
    journal_metrics = {}
    if ROOT / "research.html" in parsers:
        helpers = citation_helpers()
        research_text = (ROOT / "research.html").read_text(encoding="utf-8")
        helpers.read_publications(research_text)
        citation_records = helpers.load_cache(ROOT / "content/citations.json")
        journal_metrics = load_journal_metrics(ROOT / "content/journal-metrics.json", research_text)
    if output in sources or any(source.is_relative_to(output) for source in sources):
        raise ValueError("Output contains a source file; choose a separate build directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".site-build-", dir=output.parent) as temporary:
        stage = Path(temporary)
        for source in sorted(sources):
            if source.suffix.lower() != ".html":
                copy_asset(source, stage / source.relative_to(ROOT))
        for source in pages:
            (stage / source.name).write_text(output_html(source, parsers[source], stage, base, omit_cv, citation_records, journal_metrics), encoding="utf-8")
        sitemap = ElementTree.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
        for page in pages:
            if page.name != "404.html":
                ElementTree.SubElement(ElementTree.SubElement(sitemap, "url"), "loc").text = public_url(base, page)
        ElementTree.ElementTree(sitemap).write(stage / "sitemap.xml", encoding="utf-8", xml_declaration=True)
        (stage / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
        (stage / ".nojekyll").touch()
        (stage / "404.html").write_text('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex"><title>Page not found | Sven Weber</title></head><body><main><h1>Page not found</h1><p>The page may have moved.</p><p><a href="' + escape(base + "/", quote=True) + '">Return to the homepage</a></p></main></body></html>\n', encoding="utf-8")
        files = sorted(path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file())
        (stage / MARKER).write_text(json.dumps({"base_url": base, "cv_omitted": omit_cv, "files": files}, indent=2) + "\n", encoding="utf-8")
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(stage, output)
    source_bytes = sum(path.stat().st_size for path in sources)
    output_bytes = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    print(f"Prepared {len(pages)} pages in {output}")
    print(f"Referenced source: {source_bytes / 1000000:.2f} MB; public output: {output_bytes / 1000000:.2f} MB")
    if omit_cv:
        print("Draft mode: CV links and documents were omitted from output; source links remain unchanged.")
    print("Publish only this output directory. No domain registration or DNS changes were made.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://sven9r.github.io")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--allow-application-cv", action="store_true", help="Explicitly permit a linked application-specific PDF; prefer a reviewed public CV.")
    parser.add_argument("--omit-cv", action="store_true", help="Prepare a provisional draft without CV links or documents; source remains unchanged.")
    args = parser.parse_args()
    try:
        if args.allow_application_cv and args.omit_cv:
            raise ValueError("Choose either --omit-cv or --allow-application-cv, not both.")
        build(args.base_url, args.output, args.allow_application_cv, args.omit_cv)
    except (OSError, ValueError) as error:
        print(f"Site preparation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
