#!/usr/bin/env python3
"""
fetch_publications.py
Fetches publications for Rafael Ortiz III from NASA ADS.

Two queries are performed:
  1. ORCID query  â€” papers linked to ORCID 0000-0002-6150-833X
  2. Name query   â€” papers under author:"Ortiz, Rafael" in astronomy

Non-refereed papers are those that appear in the name query but NOT in the
ORCID query (i.e. preprints / arXiv submissions not yet linked to the ORCID).

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

ORCID      = "0000-0002-6150-833X"
AUTHOR_NAME = "Ortiz, Rafael"          # name-based search string
ADS_TOKEN  = os.environ.get("ADS_TOKEN", "")
ADS_API    = "https://api.adsabs.harvard.edu/v1/search/query"
OUTPUT     = os.path.join(os.path.dirname(__file__), "..", "publications.json")

FIELDS = [
    "title", "author", "year", "bibcode", "doi",
    "identifier", "citation_count", "doctype",
    "pub", "volume", "page", "abstract", "keyword",
]


def _query_ads(query: str, token: str, label: str) -> list[dict]:
    """Run a single ADS search and return docs."""
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "q":    query,
        "fl":   ",".join(FIELDS),
        "rows": 200,
        "sort": "date desc, bibcode desc",
    }
    resp = requests.get(ADS_API, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    docs = resp.json().get("response", {}).get("docs", [])
    print(f"Fetched {len(docs)} papers ({label}).")
    return docs


def fetch_papers(orcid: str, author_name: str, token: str) -> tuple[list[dict], list[dict]]:
    """
    Returns (orcid_docs, name_only_docs).
    name_only_docs are papers found by author name in astronomy collections but NOT by ORCID.
    """
    if not token:
        print("ERROR: ADS_TOKEN environment variable not set.", file=sys.stderr)
        print("Get your free token at: https://ui.adsabs.harvard.edu/user/settings/token",
              file=sys.stderr)
        sys.exit(1)

    orcid_docs = _query_ads(f"orcid:{orcid}", token, "ORCID")
    name_docs  = _query_ads(
        f'author:"{author_name}" collection:astronomy', token, "name search (astronomy collection)"
    )

    orcid_bibcodes = {d["bibcode"] for d in orcid_docs}
    name_only_docs = [d for d in name_docs if d["bibcode"] not in orcid_bibcodes]
    print(f"Non-ORCID (non-refereed) papers found: {len(name_only_docs)}")
    return orcid_docs, name_only_docs



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


def _doc_to_paper(d: dict, non_refereed_override: bool = False) -> dict:
    authors_raw = d.get("author") or []
    doi         = (d.get("doi") or [None])[0]
    arxiv       = arxiv_id(d.get("identifier") or [])
    journal_parts = [
        d.get("pub") or "",
        str(d.get("volume") or ""),
        (d.get("page") or [""])[0],
    ]
    journal = " ".join(p for p in journal_parts if p).strip()

    doctype  = d.get("doctype") or ""
    refereed = False if non_refereed_override else is_refereed(doctype)

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
        "non_refereed": non_refereed_override,
        "first_author": is_first_author(authors_raw),
        "abstract":     (d.get("abstract") or "")[:400],
        "keywords":     d.get("keyword") or [],
    }


def build_output(orcid_docs: list[dict], name_only_docs: list[dict]) -> dict:
    orcid_papers     = [_doc_to_paper(d, non_refereed_override=False) for d in orcid_docs]
    non_ref_papers   = [_doc_to_paper(d, non_refereed_override=True)  for d in name_only_docs]

    all_papers = orcid_papers + non_ref_papers

    # Stats over ORCID-linked papers only (mirrors existing behaviour)
    all_cites          = [p["citations"] for p in orcid_papers]
    first_author_cites = [p["citations"] for p in orcid_papers if p["first_author"]]
    refereed           = [p for p in orcid_papers if p["refereed"]]

    stats = {
        "total_papers":            len(orcid_papers),
        "refereed_papers":         len(refereed),
        "first_author_papers":     sum(1 for p in orcid_papers if p["first_author"]),
        "non_refereed_papers":     len(non_ref_papers),
        "total_citations":         sum(all_cites),
        "first_author_citations":  sum(first_author_cites),
        "h_index":                 compute_hindex(all_cites),
        "h_index_first_author":    compute_hindex(first_author_cites),
    }

    return {
        "meta": {
            "orcid":   ORCID,
            "updated": datetime.now(timezone.utc).isoformat(),
            "source":  "NASA ADS",
        },
        "stats":  stats,
        "papers": all_papers,
    }


def main():
    print(f"Fetching publications for ORCID: {ORCID}")
    orcid_docs, name_only_docs = fetch_papers(ORCID, AUTHOR_NAME, ADS_TOKEN)
    output = build_output(orcid_docs, name_only_docs)

    out_path = os.path.abspath(OUTPUT)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    s = output["stats"]
    print(f"\nðŸ“Š Stats:")
    print(f"  Total papers       : {s['total_papers']}")
    print(f"  Refereed           : {s['refereed_papers']}")
    print(f"  First-author       : {s['first_author_papers']}")
    print(f"  Non-refereed       : {s['non_refereed_papers']}")
    print(f"  Total citations    : {s['total_citations']}")
    print(f"  h-index            : {s['h_index']}")
    print(f"  h-index (1st auth) : {s['h_index_first_author']}")
    print(f"\nâœ… Written to: {out_path}")


if __name__ == "__main__":
    main()