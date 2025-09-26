# IndoNewsCop

A tiny CLI to extract **title, date, author(s), and full text** from article URLs and save them as Markdown with YAML front-matter, plus a JSONL and CSV catalog.

Repo name aligned: `indonewscop`

## Quickstart

```bash
pip install -r requirements.txt
python indonewscop.py "https://www.example.com/news/article"                       --output-dir ./articles                       --jsonl ./catalog.jsonl                       --csv ./catalog.csv
```

You can also pass a file of URLs (one per line):

```bash
python indonewscop.py --from-file urls.txt
```

Respect sites’ **Terms of Service** and **robots.txt**. This tool won’t bypass paywalls or authentication.

## Outputs

- `articles/YYYY-MM-DD_title-slug.md` with YAML front-matter:
  - `title`, `url`, `site`, `date`, `authors`
- `catalog.jsonl` one JSON record per article
- `catalog.csv` spreadsheet-friendly

## Options

- `--delay` seconds between requests (default 2.0)
- `--skip-robots` skip robots.txt checks (not recommended)

## Cloud usage (GitHub Codespaces example)

1. Push this folder to your repo `indonewscop`.
2. GitHub → Code → Create codespace.
3. In the codespace terminal:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python indonewscop.py --from-file urls.txt --output-dir ./articles --jsonl ./catalog.jsonl --csv ./catalog.csv
```

Download your results from the Codespaces file explorer.
