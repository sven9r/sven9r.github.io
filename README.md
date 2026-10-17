# Sven Weber personal website

A static academic homepage built with plain HTML, CSS, and minimal JavaScript. The source folder is the working copy; publish only the generated `dist/` folder.

## Edit and preview

Edit `index.html`, `about.html`, `research.html`, and `outreach.html` directly. News entries live in `content/news.md`; both `-` and `*` bullets are supported:

```text
* 2026-10 | October 2026 | Your update here.
```

Rebuild news with:

```bash
python3 scripts/build-news.py
```

The optional Node.js equivalent is `node scripts/build-news.js`. Both builders reject empty news, malformed dates and missing or duplicate markers before writing. Use the Python command if Node.js is unavailable. The existing news layout is preserved.

To preview the source:

```bash
python3 -m http.server 8000
```

Open http://localhost:8000. Stop the server with Ctrl+C.

## Prepare the public site

The preparation script uses Python 3 and Pillow (already available in the current environment). It copies only top-level HTML pages, `styles.css`, `script.js`, the optional `favicon.svg`, and assets referenced by HTML/CSS. It excludes unused pictures, Markdown sources, scripts, editor files, and history files. Keep private working material outside the public output.

```bash
python3 scripts/prepare-site.py --base-url https://sven9r.github.io
```

Use the actual public base URL, including a repository path if applicable. For example, a project Pages site may use `https://sven9r.github.io/Homepage`. The final custom-domain build will use `https://weblab.science` after that domain has been registered and configured.

The build writes `dist/` and preserves every original source file. Referenced JPEG/PNG copies are oriented from EXIF, resized to a maximum dimension of 1600 pixels, and exported without their original metadata. JPEG copies are compressed; originals remain available for future exports. Output HTML gains intrinsic image dimensions, deferred loading below the first image, canonical and social metadata. The output includes `sitemap.xml`, `robots.txt`, a simple 404 page and `.nojekyll`.

Only an empty directory or one marked by a prior successful build can be overwritten. A failed validation leaves an existing output intact. Use `--output PATH` for another generated output directory.

### CV review

The existing application-specific CV is blocked by default. Replace its HTML links with a reviewed public CV or remove the links before preparing a final release. For a provisional draft without a CV:

```bash
python3 scripts/prepare-site.py --base-url https://sven9r.github.io --omit-cv
```

`--omit-cv` removes CV links and files only from output. It does not decide what belongs in the eventual public CV. `--allow-application-cv` exists as an explicit override; use it only if that exact application document has been approved for public release.

### Review the output

```bash
python3 -m http.server 8000 --directory dist
```

Review the site at desktop and mobile widths, including the navigation, photographs and CV decision. Confirm publication and manuscript status, current affiliation, image permission, and any remaining content edits before launch. Preserve personal names and research claims only where supported by the user's material.

## Hosting and domain

Publish the contents of `dist/` to the existing GitHub Pages deployment repository or another static host. Do not upload this source directory wholesale. This preparation command does not create a repository, push changes, register a domain, or deploy the site.

Do not add a `CNAME` file for `weblab.science` until domain ownership and DNS are configured. Rebuild with the final base URL when switching from the temporary host to the custom domain, so canonical links, sitemap and social URLs match.

## Publication citation counts

The ten published papers remain a curated list in `research.html`. Each has a DOI attribute. OpenAlex citation counts are cached in `content/citations.json`; they do not change the bibliography or manuscript statuses.

Run `python3 scripts/update-citations.py`, then `python3 scripts/prepare-site.py --base-url https://sven9r.github.io`. The public build labels counts with OpenAlex and their retrieval date. Failed lookups retain the previous successful count.

The Pages workflow rebuilds on changes and refreshes counts weekly on Monday at 06:17 UTC. It publishes only `dist/`. No API key or paid service is required for these DOI lookups under the current OpenAlex policy. Historical journal impact factors are not currently populated.
