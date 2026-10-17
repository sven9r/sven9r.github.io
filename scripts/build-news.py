"""Rebuild the existing News block without touching the rest of the page."""

from html import escape
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "content" / "news.md"
TARGET_PATH = ROOT / "news.html"
START = "            <!-- NEWS_ITEMS_START: generated from content/news.md by scripts/build-news.js -->"
END = "            <!-- NEWS_ITEMS_END -->"


def parse_news(markdown):
    updates_start = markdown.find("\n## Updates")
    update_block = markdown[updates_start:] if updates_start != -1 else markdown
    entries = []
    for raw_line in update_block.splitlines():
        line = raw_line.strip()
        if not line.startswith(("- ", "* ")):
            continue
        parts = [part.strip() for part in line[2:].split("|")]
        if len(parts) < 3:
            raise ValueError(f"Invalid news line: {line}")
        datetime, label, *text_parts = parts
        text = " | ".join(text_parts)
        if not re.fullmatch(r"\d{4}(-(0[1-9]|1[0-2]))?", datetime):
            raise ValueError(f'Invalid date "{datetime}" in line: {line}')
        if not label or not text:
            raise ValueError(f"News label and text must not be empty: {line}")
        entries.append((datetime, label, text))
    if not entries:
        raise ValueError("No news entries found; existing news.html was left unchanged.")
    return entries


def render_news(markdown, html):
    entries = parse_news(markdown)
    if html.count(START) != 1 or html.count(END) != 1:
        raise ValueError("Expected one NEWS_ITEMS_START / NEWS_ITEMS_END pair; existing news.html was left unchanged.")
    start_index = html.index(START) + len(START)
    end_index = html.index(END)
    if end_index < start_index:
        raise ValueError("News markers are out of order; existing news.html was left unchanged.")
    rendered = "\n".join(
        f'            <p><time datetime="{escape(datetime)}">{escape(label)}</time>: {escape(text)}</p>'
        for datetime, label, text in entries
    )
    return html[:start_index] + "\n" + rendered + "\n" + html[end_index:], len(entries)


def main():
    try:
        html, count = render_news(SOURCE_PATH.read_text(encoding="utf-8"), TARGET_PATH.read_text(encoding="utf-8"))
        TARGET_PATH.write_text(html, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"News build failed: {error}", file=sys.stderr)
        return 1
    print(f"Updated news.html with {count} news entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
