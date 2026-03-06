#!/usr/bin/env python3
"""
fetch_arxiv.py
Fetches astro-ph papers authored by "Ortiz, Rafael" from the arXiv API,
mirroring the search: author=Ortiz, Rafael | classification: astro-ph | include_cross_list: True

No API token required.

Usage:
    python scripts/fetch_arxiv.py

Requires: requests
    pip install requests

Output: arxiv_preprints.json (repo root, alongside publications.json)
"""

import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

# Mirrors: author=Ortiz, Rafael AND cat:astro-ph.* (cross-list included by default in arXiv API)
AUTHOR_QUERY = "Ortiz, Rafael"
CATEGORY     = "astro-ph"
MAX_RESULTS  = 200
ARXIV_API    = "https://export.arxiv.org/api/query"
OUTPUT       = os.path.join(os.path.dirname(__file__), "..", "arxiv_preprints.json")

NS = {
    "atom":       "http://www.w3.org/2005/Atom",
    "arxiv":      "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


def fetch_all_entries() -> list[ET.Element]:
    """Fetch all results in batches of 50 (arXiv recommends <= 100 per request)."""
    all_entries = []
    batch_size  = 50
    start       = 0

    while True:
        params = {
            "search_query": f'au:"{AUTHOR_QUERY}" AND cat:{CATEGORY}.*',
            "start":        start,
            "max_results":  batch_size,
            "sortBy":       "submittedDate",
            "sortOrder":    "descending",
        }
        print(f"  Fetching records {start + 1}–{start + batch_size}…")
        resp = requests.get(ARXIV_API, params=params, timeout=30)
        resp.raise_for_status()

        root    = ET.fromstring(resp.text)
        entries = root.findall("atom:entry", NS)
        all_entries.extend(entries)

        total_str = root.findtext("opensearch:totalResults", default="0", namespaces=NS)
        total     = int(total_str)

        if start == 0:
            print(f"  arXiv reports {total} total results for: au:\"{AUTHOR_QUERY}\" AND cat:{CATEGORY}.*")

        start += len(entries)
        if start >= total or not entries:
            break

    return all_entries


def parse_entry(entry: ET.Element) -> dict:
    raw_id   = entry.findtext("atom:id", default="", namespaces=NS)
    arxiv_id = raw_id.replace("http://arxiv.org/abs/", "").replace("https://arxiv.org/abs/", "").strip()

    title = (entry.findtext("atom:title", default="", namespaces=NS) or "").replace("\n", " ").strip()

    authors = [
        a.findtext("atom:name", default="", namespaces=NS)
        for a in entry.findall("atom:author", NS)
    ]

    published = entry.findtext("atom:published", default="", namespaces=NS)
    updated   = entry.findtext("atom:updated",   default="", namespaces=NS)
    year      = int(published[:4]) if published else 0

    summary = (entry.findtext("atom:summary", default="", namespaces=NS) or "").replace("\n", " ").strip()

    categories = [t.get("term", "") for t in entry.findall("atom:category", NS)]
    primary_el = entry.find("arxiv:primary_category", NS)
    primary    = primary_el.get("term", "") if primary_el is not None else ""

    doi     = entry.findtext("arxiv:doi",         default=None, namespaces=NS)
    jref    = entry.findtext("arxiv:journal_ref", default=None, namespaces=NS)
    comment = entry.findtext("arxiv:comment",     default=None, namespaces=NS)

    # First-author check: "Ortiz" in first listed author name
    first_author = bool(authors) and "ortiz" in authors[0].lower()

    # Cross-list flag: primary category is NOT astro-ph.* but paper appears via cross-list
    is_crosslist = not primary.startswith("astro-ph") if primary else False

    return {
        "arxiv_id":         arxiv_id,
        "title":            title,
        "authors":          authors,
        "year":             year,
        "published":        published,
        "updated":          updated,
        "abstract":         summary[:400],
        "categories":       categories,
        "primary_category": primary,
        "is_crosslist":     is_crosslist,
        "doi":              doi,
        "journal_ref":      jref,
        "comment":          comment,
        "first_author":     first_author,
        "arxiv_url":        f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url":          f"https://arxiv.org/pdf/{arxiv_id}",
    }


def build_output(entries: list[ET.Element]) -> dict:
    papers       = [parse_entry(e) for e in entries]
    first_author = [p for p in papers if p["first_author"]]
    published    = [p for p in papers if p["journal_ref"] or p["doi"]]
    crosslist    = [p for p in papers if p["is_crosslist"]]

    return {
        "meta": {
            "author_query": AUTHOR_QUERY,
            "category":     CATEGORY,
            "cross_list":   True,
            "updated":      datetime.now(timezone.utc).isoformat(),
            "source":       "arXiv API",
        },
        "stats": {
            "total_preprints":        len(papers),
            "first_author_preprints": len(first_author),
            "published_preprints":    len(published),
            "crosslist_preprints":    len(crosslist),
        },
        "papers": papers,
    }


def main():
    print(f'Querying arXiv for: au:"{AUTHOR_QUERY}" AND cat:{CATEGORY}.* (cross-list included)')
    entries = fetch_all_entries()

    if not entries:
        print("No entries found. Check your query or network connection.")
        return

    output   = build_output(entries)
    out_path = os.path.abspath(OUTPUT)

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    s = output["stats"]
    print(f"\n📊 Stats:")
    print(f"  Total preprints       : {s['total_preprints']}")
    print(f"  First-author          : {s['first_author_preprints']}")
    print(f"  With journal ref/DOI  : {s['published_preprints']}")
    print(f"  Cross-listed          : {s['crosslist_preprints']}")
    print(f"\n✅ Written to: {out_path}")


if __name__ == "__main__":
    main()
