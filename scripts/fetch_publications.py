#!/usr/bin/env python3
"""
fetch_publications.py
Fetches publications for Rafael Ortiz III from NASA ADS using ORCID only.

Usage:
  export ADS_TOKEN="your_token_here"
  python scripts/fetch_publications.py

Requires: requests
  pip install requests
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

ORCID     = "0000-0002-6150-833X"
ADS_TOKEN = os.environ.get("ADS_TOKEN", "")
ADS_API   = "https://api.adsabs.harvard.edu/v1/search/query"
OUTPUT    = os.path.join(os.path.dirname(__file__), "..", "publications.json")

FIELDS = [
    "title", "author", "year", "bibcode", "doi",
    "identifier", "citation_count", "doctype",
    "pub", "volume", "page", "abstract", "keyword",
]


def fetch_papers(orcid: str, token: str) -> list[dict]:
    if not token:
        print("ERROR: ADS_TOKEN environment variable not set.", file=sys.stderr)
        print("Get your free token at: https://ui.adsabs.harvard.edu/user/settings/token",
              file=sys.stderr)
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "q":    f"orcid:{orcid}",
        "fl":   ",".join(FIELDS),
        "rows": 200,
        "sort": "date desc, bibcode desc",
    }
    resp = requests.get(ADS_API, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    docs = resp.json().get("response", {}).get("docs", [])
    print(f"Fetched {len(docs)} papers via ORCID {orcid}.")
    return docs


def arxiv_id(identifiers: list[str]) -> str | None:
    for i in identifiers or []:
        if i.startswith("arXiv:"):
            return i.replace("arXiv:", "")
    return None


def is_first_author(authors: list[str]) -> bool:
    if not authors:
        return False
    return "ortiz" in authors[0].lower()


def is_refereed(doctype: str) -> bool:
    return doctype in ("article", "inproceedings", "inbook", "book")


def compute_hindex(citation_counts: list[int]) -> int:
    counts = sorted(citation_counts, reverse=True)
    h = 0
    for i, c in enumerate(counts):
        if c >= i + 1:
            h = i + 1
        else:
            break
    return h


def doc_to_paper(d: dict) -> dict:
    authors_raw = d.get("author") or []
    doi         = (d.get("doi") or [None])[0]
    arxiv       = arxiv_id(d.get("identifier") or [])
    journal_parts = [
        d.get("pub") or "",
        str(d.get("volume") or ""),
        (d.get("page") or [""])[0],
    ]
    journal  = " ".join(p for p in journal_parts if p).strip()
    doctype  = d.get("doctype") or ""
    refereed = is_refereed(doctype)

    return {
        "title":        (d.get("title") or [""])[0],
        "authors":      authors_raw,
        "year":         int(d.get("year") or 0),
        "journal":      journal,
        "bibcode":      d.get("bibcode") or "",
        "doi":          doi,
        "arxiv":        arxiv,
        "citations":    d.get("citation_count") or 0,
        "doctype":      doctype,
        "refereed":     refereed,
        "first_author": is_first_author(authors_raw),
        "abstract":     (d.get("abstract") or "")[:400],
        "keywords":     d.get("keyword") or [],
    }


def build_output(docs: list[dict]) -> dict:
    papers = [doc_to_paper(d) for d in docs]

    all_cites          = [p["citations"] for p in papers]
    first_author_cites = [p["citations"] for p in papers if p["first_author"]]
    refereed           = [p for p in papers if p["refereed"]]
    first_author       = [p for p in papers if p["first_author"]]

    stats = {
        "total_papers":           len(papers),
        "refereed_papers":        len(refereed),
        "first_author_papers":    len(first_author),
        "total_citations":        sum(all_cites),
        "first_author_citations": sum(first_author_cites),
        "h_index":                compute_hindex(all_cites),
        "h_index_first_author":   compute_hindex(first_author_cites),
    }

    return {
        "meta": {
            "orcid":   ORCID,
            "updated": datetime.now(timezone.utc).isoformat(),
            "source":  "NASA ADS",
        },
        "stats":  stats,
        "papers": papers,
    }


def main():
    print(f"Fetching publications for ORCID: {ORCID}")
    docs   = fetch_papers(ORCID, ADS_TOKEN)
    output = build_output(docs)

    out_path = os.path.abspath(OUTPUT)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    s = output["stats"]
    print(f"\n📊 Stats:")
    print(f"  Total papers       : {s['total_papers']}")
    print(f"  Refereed           : {s['refereed_papers']}")
    print(f"  First-author       : {s['first_author_papers']}")
    print(f"  Total citations    : {s['total_citations']}")
    print(f"  h-index            : {s['h_index']}")
    print(f"  h-index (1st auth) : {s['h_index_first_author']}")
    print(f"\n✅ Written to: {out_path}")


if __name__ == "__main__":
    main()
