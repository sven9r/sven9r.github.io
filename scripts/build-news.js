// Optional Node.js equivalent of build-news.py. Both accept '-' and '*' bullets.
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const start = "            <!-- NEWS_ITEMS_START: generated from content/news.md by scripts/build-news.js -->";
const end = "            <!-- NEWS_ITEMS_END -->";

function escapeHtml(value) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
}

function parseNews(markdown) {
  const updatesStart = markdown.indexOf("\n## Updates");
  const updateBlock = updatesStart === -1 ? markdown : markdown.slice(updatesStart);
  const entries = updateBlock.split(/\r?\n/).map((line) => line.trim())
    .filter((line) => line.startsWith("- ") || line.startsWith("* "))
    .map((line) => {
      const parts = line.slice(2).split("|").map((part) => part.trim());
      if (parts.length < 3) throw new Error(`Invalid news line: ${line}`);
      const [datetime, label, ...textParts] = parts;
      const text = textParts.join(" | ");
      if (!/^\d{4}(-(0[1-9]|1[0-2]))?$/.test(datetime)) throw new Error(`Invalid date "${datetime}" in line: ${line}`);
      if (!label || !text) throw new Error(`News label and text must not be empty: ${line}`);
      return { datetime, label, text };
    });
  if (!entries.length) throw new Error("No news entries found; existing news.html was left unchanged.");
  return entries;
}

function renderNews(markdown, html) {
  const entries = parseNews(markdown);
  if (html.split(start).length !== 2 || html.split(end).length !== 2) {
    throw new Error("Expected one NEWS_ITEMS_START / NEWS_ITEMS_END pair; existing news.html was left unchanged.");
  }
  const startIndex = html.indexOf(start) + start.length;
  const endIndex = html.indexOf(end);
  if (endIndex < startIndex) throw new Error("News markers are out of order; existing news.html was left unchanged.");
  const rendered = entries.map(({ datetime, label, text }) =>
    `            <p><time datetime="${escapeHtml(datetime)}">${escapeHtml(label)}</time>: ${escapeHtml(text)}</p>`
  ).join("\n");
  return { html: html.slice(0, startIndex) + "\n" + rendered + "\n" + html.slice(endIndex), count: entries.length };
}

if (require.main === module) {
  try {
    const result = renderNews(fs.readFileSync(path.join(root, "content/news.md"), "utf8"), fs.readFileSync(path.join(root, "news.html"), "utf8"));
    fs.writeFileSync(path.join(root, "news.html"), result.html);
    console.log(`Updated news.html with ${result.count} news entries.`);
  } catch (error) {
    console.error(`News build failed: ${error.message}`);
    process.exitCode = 1;
  }
}

module.exports = { parseNews, renderNews };
