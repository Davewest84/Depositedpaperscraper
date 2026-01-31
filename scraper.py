#!/usr/bin/env python3
"""Scrape deposited papers from the UK Parliament API.

Fetches metadata for deposited papers and optionally downloads attached
documents. Results are saved as JSON and/or CSV.

Usage:
    python scraper.py --help
    python scraper.py --search "immigration"
    python scraper.py --search "health" --deposited-from 2024-01-01 --format csv
    python scraper.py --download-files --output-dir data/
"""

import argparse
import csv
import json
import logging
import os
import re

from client import DepositedPapersClient

logger = logging.getLogger(__name__)


# Fields from DepositedPaperSummary / DepositedPaperDetail schemas
SCALAR_FIELDS = [
    "paperNumber",
    "title",
    "dateUpdated",
    "indexerNotes",
    "notes",
]


def flatten_paper(paper):
    """Flatten a paper record into a dict suitable for CSV output."""
    flat = {}

    for key in SCALAR_FIELDS:
        if key in paper:
            flat[key] = paper[key]

    # houses is a list of strings like ["Commons", "Lords"]
    houses = paper.get("houses") or []
    flat["houses"] = "; ".join(str(h) for h in houses)

    # corporateAuthors is a list of strings
    authors = paper.get("corporateAuthors") or []
    flat["corporateAuthors"] = "; ".join(str(a) for a in authors)

    # depositingDepartments is a list of strings
    depts = paper.get("depositingDepartments") or []
    flat["depositingDepartments"] = "; ".join(str(d) for d in depts)

    # attachedDocuments is only available from the detail endpoint,
    # not the search/list endpoint, so omit it. Instead add a direct
    # link to the paper on the parliament website.
    paper_id = paper.get("paperId")
    if paper_id is not None:
        flat["url"] = (
            f"https://depositedpapers.parliament.uk/depositedpaper/"
            f"{paper_id}/details"
        )
    else:
        flat["url"] = ""

    return flat


def sanitise_filename(name, max_len=80):
    """Turn an arbitrary string into a safe filename."""
    name = re.sub(r'[^\w\s\-.]', '', name)
    name = re.sub(r'\s+', '_', name).strip('_')
    return name[:max_len] if name else "unnamed"


def save_json(papers, path):
    """Save papers list as JSON."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=2, ensure_ascii=False, default=str)
    logger.info("Saved %d papers to %s", len(papers), path)


def save_csv(papers, path):
    """Save flattened paper records as CSV."""
    if not papers:
        logger.warning("No papers to save.")
        return

    flat_rows = [flatten_paper(p) for p in papers]
    fieldnames = list(flat_rows[0].keys())
    for row in flat_rows:
        for k in row:
            if k not in fieldnames:
                fieldnames.append(k)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_rows)
    logger.info("Saved %d papers to %s", len(flat_rows), path)


def download_files(client, papers, output_dir):
    """Download attached documents for each paper."""
    files_dir = os.path.join(output_dir, "files")
    os.makedirs(files_dir, exist_ok=True)

    total_files = 0
    for paper in papers:
        paper_id = paper.get("paperId", "unknown")
        docs = paper.get("attachedDocuments") or []
        for doc_url in docs:
            if not doc_url or not isinstance(doc_url, str):
                continue

            # Use the last segment of the URL as filename
            url_filename = doc_url.rstrip("/").rsplit("/", 1)[-1]
            safe_name = sanitise_filename(url_filename) or f"file_{total_files}"
            dest = os.path.join(files_dir, f"{paper_id}_{safe_name}")
            if os.path.exists(dest):
                logger.debug("Skipping existing file: %s", dest)
                continue

            logger.info("Downloading %s -> %s", doc_url, dest)
            try:
                client.download_file(doc_url, dest)
                total_files += 1
            except Exception:
                logger.exception("Failed to download %s", doc_url)

    logger.info("Downloaded %d files to %s", total_files, files_dir)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Scrape deposited papers from the UK Parliament API.",
    )
    parser.add_argument(
        "--search", "-s",
        dest="terms",
        help=(
            "Free-text search across depositing department, paper number, "
            "and summary (2–500 chars)."
        ),
    )
    parser.add_argument(
        "--deposited-from",
        help="Papers deposited on or after this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--deposited-to",
        help="Papers deposited on or before this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--house",
        choices=["All", "Commons", "Lords"],
        help="Filter by house.",
    )
    parser.add_argument(
        "--order-by",
        choices=["Relevance", "CommitmentDateAsc", "CommitmentDateDesc"],
        help="Sort order for results.",
    )
    parser.add_argument(
        "--department-id",
        type=int,
        dest="department_ses_id",
        help="Filter by depositing department ID.",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "csv", "both"],
        default="both",
        help="Output format (default: both).",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="output",
        help="Directory for output files (default: output/).",
    )
    parser.add_argument(
        "--download-files",
        action="store_true",
        help="Download attached documents for each paper.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=20,
        help="Number of results per API request (default: 20).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    client = DepositedPapersClient(page_size=args.page_size)

    logger.info("Fetching deposited papers...")
    if args.terms:
        logger.info("  Terms: %s", args.terms)
    if args.deposited_from:
        logger.info("  Deposited from: %s", args.deposited_from)
    if args.deposited_to:
        logger.info("  Deposited to: %s", args.deposited_to)
    if args.house:
        logger.info("  House: %s", args.house)

    papers = list(client.iter_all(
        terms=args.terms,
        deposited_from=args.deposited_from,
        deposited_to=args.deposited_to,
        house=args.house,
        order_by=args.order_by,
        department_ses_id=args.department_ses_id,
    ))

    logger.info("Fetched %d papers.", len(papers))

    if not papers:
        logger.warning("No papers found. Exiting.")
        return

    os.makedirs(args.output_dir, exist_ok=True)

    if args.format in ("json", "both"):
        save_json(papers, os.path.join(args.output_dir, "papers.json"))

    if args.format in ("csv", "both"):
        save_csv(papers, os.path.join(args.output_dir, "papers.csv"))

    if args.download_files:
        download_files(client, papers, args.output_dir)

    logger.info("Done.")


if __name__ == "__main__":
    main()
