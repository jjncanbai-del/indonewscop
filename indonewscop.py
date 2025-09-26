#!/usr/bin/env python3
"""
indonewscop.py
---------------
CLI to take one or more news/article URLs, extract title, date, author(s), and content,
then save each as a Markdown file with YAML front-matter, plus append to a JSONL and CSV catalog.

Extraction uses trafilatura first, then falls back to newspaper3k.

Usage:
  python indonewscop.py URL1 URL2 ...
  python indonewscop.py --from-file urls.txt
  python indonewscop.py --output-dir ./articles --jsonl catalog.jsonl --csv catalog.csv URL...

Notes:
  * Please respect each site's Terms of Service and robots.txt.
  * This script won't bypass paywalls or authentication.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib import robotparser

import requests
import dateparser

# Primary extractor
import trafilatura

# Fallback extractor (optional)
try:
    from newspaper import Article
    NEWSPAPER_OK = True
except Exception:
    NEWSPAPER_OK = False


# Use a UA that reflects the repo name (replace <your-username> with your GitHub username if you like)
DEFAULT_UA = "Mozilla/5.0 (compatible; IndoNewsCop/1.0; +https://github.com/<your-username>/indonewscop)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": DEFAULT_UA, "Accept-Language": "en,*;q=0.5"})


def slugify(text, max_len=80):
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s\-_.]", "", text)
    text = re.sub(r"\s+", "-", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip("-_")
    return text or "untitled"


def read_urls_from_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]


def robots_allowed(url, user_agent=DEFAULT_UA, timeout=10):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        # If robots.txt is not reachable, default to True but be gentle
        return True


def fetch_with_trafilatura(url):
    downloaded = trafilatura.fetch_url(url, no_ssl=True)  # be forgiving on some sites
    if not downloaded:
        return None
    result_json = trafilatura.extract(
        downloaded,
        output_format="json",
        include_comments=False,
        with_metadata=True,
        favor_precision=True,
        include_links=False,
        json_output=True,
    )
    if not result_json:
        return None
    try:
        data = json.loads(result_json)
        # Normalize keys to our schema
        return {
            "url": url,
            "title": data.get("title"),
            "authors": data.get("author") or data.get("authors") or [],
            "date": data.get("date"),  # ISO string if available
            "text": data.get("text"),
            "sitename": data.get("sitename") or urlparse(url).netloc,
        }
    except Exception:
        return None


def fetch_with_newspaper(url):
    if not NEWSPAPER_OK:
        return None
    try:
        art = Article(url)
        art.download()
        art.parse()
        # Try NLP for keywords/authors if needed
        try:
            art.nlp()
        except Exception:
            pass
        dt = None
        if art.publish_date:
            # Convert datetime to ISO string
            dt = art.publish_date.astimezone(timezone.utc).isoformat()
        return {
            "url": url,
            "title": art.title or None,
            "authors": art.authors or [],
            "date": dt,
            "text": art.text or None,
            "sitename": urlparse(url).netloc,
        }
    except Exception:
        return None


def coalesce_article(url):
    # Try trafilatura first
    data = fetch_with_trafilatura(url)
    if data and data.get("title") and data.get("text"):
        return data

    # Fallback to newspaper3k
    fallback = fetch_with_newspaper(url)
    if fallback and fallback.get("title") and fallback.get("text"):
        # If trafilatura had some metadata we prefer (e.g., date), merge
        if data:
            for k in ("date", "authors", "sitename"):
                if not fallback.get(k) and data.get(k):
                    fallback[k] = data[k]
        return fallback

    # As a last resort return whatever we got from trafilatura
    return data or {"url": url}


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def save_markdown(record, out_dir):
    ensure_dir(out_dir)
    # Build filename: YYYY-MM-DD_title-slug.md (fallback to hash if no title)
    date_part = ""
    if record.get("date"):
        try:
            dt = dateparser.parse(record["date"])
            if dt:
                date_part = dt.strftime("%Y-%m-%d") + "_"
        except Exception:
            pass
    title = record.get("title") or record.get("sitename") or urlparse(record["url"]).netloc
    slug = slugify(title)
    if slug == "untitled":
        import hashlib
        slug = hashlib.sha1(record["url"].encode("utf-8")).hexdigest()[:10]
    fname = f"{date_part}{slug}.md"
    fpath = os.path.join(out_dir, fname)

    # YAML front-matter
    authors = record.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    fm = [
        "---",
        f'title: "{title.replace(chr(34), "\'")}"',
        f"url: {record.get('url','')}",
        f"site: {record.get('sitename','')}",
        f"date: {record.get('date') or ''}",
        "authors:",
    ] + [f"  - {a}" for a in authors] + ["---", ""]

    body = record.get("text") or ""
    content = "\n".join(fm) + body.strip() + "\n"
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    return fpath


def append_jsonl(record, jsonl_path):
    if not jsonl_path:
        return
    ensure_dir(os.path.dirname(jsonl_path) or ".")
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_csv(record, csv_path):
    if not csv_path:
        return
    ensure_dir(os.path.dirname(csv_path) or ".")
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "title", "date", "authors", "sitename", "text"])
        if not file_exists:
            writer.writeheader()
        row = dict(record)
        # ensure authors is a string in CSV
        if isinstance(row.get("authors"), (list, tuple)):
            row["authors"] = ", ".join(row["authors"])
        writer.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="Extract and save article metadata and content.")
    ap.add_argument("urls", nargs="*", help="Article URLs")
    ap.add_argument("--from-file", help="Path to a text file with one URL per line")
    ap.add_argument("--output-dir", default="./articles", help="Directory for Markdown files")
    ap.add_argument("--jsonl", default="./catalog.jsonl", help="Path to append JSONL catalog")
    ap.add_argument("--csv", default="./catalog.csv", help="Path to append CSV catalog")
    ap.add_argument("--delay", type=float, default=2.0, help="Seconds to sleep between requests")
    ap.add_argument("--skip-robots", action="store_true", help="Skip robots.txt check (at your own risk)")
    args = ap.parse_args()

    urls = list(args.urls)
    if args.from_file:
        urls.extend(read_urls_from_file(args.from_file))

    if not urls:
        print("No URLs provided. Pass URLs as arguments or with --from-file.", file=sys.stderr)
        sys.exit(2)

    ensure_dir(args.output_dir)

    for i, url in enumerate(urls, 1):
        if not args.skip_robots and not robots_allowed(url):
            print(f"[SKIP] Robots.txt disallows fetching: {url}", file=sys.stderr)
            continue

        print(f"[{i}/{len(urls)}] Fetching: {url}")
        record = coalesce_article(url) or {"url": url}

        # Basic normalization
        if not record.get("authors"):
            record["authors"] = []

        # Save artifacts
        md_path = save_markdown(record, args.output_dir)
        append_jsonl(record, args.jsonl)
        append_csv(record, args.csv)

        print(f"    ✓ Saved {md_path}")
        if i < len(urls):
            time.sleep(max(args.delay, 0.0))

    print("Done.")


if __name__ == "__main__":
    main()
