#!/usr/bin/env python3
"""Scrape deposited papers from the UK Parliament API.

Fetches metadata for deposited papers and optionally downloads attached files.
Results are saved as JSON (one file per run) and/or CSV.

Usage:
    python scraper.py --help
    python scraper.py --output data/papers.json
    python scraper.py --search "immigration" --date-from 2024-01-01 --format csv
    python scraper.py --download-files --output-dir data/
"""

import argparse
import csv
import json
import logging
import os
import re
import sys

from client import DepositedPapersClient

logger = logging.getLogger(__name__)


def flatten_paper(paper):
    """Flatten a paper record into a dict suitable for CSV output.

    The API response may nest file and member information. This function
    pulls the most useful fields to the top level.
    """
    flat = {}

    # Top-level scalar fields
    for key in ("id", "title", "dateDeposited", "dateCreated",
                "referenceNumber", "description", "house"):
        if key in paper:
            flat[key] = paper[key]

    # Depositing member (may be nested)
    member = paper.get("depositingMember") or paper.get("member") or {}
    if isinstance(member, dict):
        flat["memberName"] = member.get("name") or member.get("nameDisplayAs", "")
        flat["memberId"] = member.get("id", "")
    elif isinstance(member, str):
        flat["memberName"] = member

    # Files / attachments
    files = paper.get("files") or paper.get("attachments") or []
    if files:
        urls = []
        filenames = []
        for f in files:
            if isinstance(f, dict):
                url = f.get("url") or f.get("uri") or ""
                name = f.get("filename") or f.get("name") or ""
                urls.append(url)
                filenames.append(name)
            elif isinstance(f, str):
                urls.append(f)
        flat["fileUrls"] = "; ".join(urls)
        flat["fileNames"] = "; ".join(filenames)
        flat["fileCount"] = len(files)
    else:
        flat["fileUrls"] = ""
        flat["fileNames"] = ""
        flat["fileCount"] = 0

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
    # Ensure all keys are present
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
    """Download attached files for each paper."""
    files_dir = os.path.join(output_dir, "files")
    os.makedirs(files_dir, exist_ok=True)

    total_files = 0
    for paper in papers:
        paper_id = paper.get("id", "unknown")
        files = paper.get("files") or paper.get("attachments") or []
        for f in files:
            if isinstance(f, dict):
                url = f.get("url") or f.get("uri")
                name = f.get("filename") or f.get("name") or f"file_{total_files}"
            elif isinstance(f, str):
                url = f
                name = f"file_{total_files}"
            else:
                continue

            if not url:
                continue

            safe_name = sanitise_filename(name)
            dest = os.path.join(files_dir, f"{paper_id}_{safe_name}")
            if os.path.exists(dest):
                logger.debug("Skipping existing file: %s", dest)
                continue

            logger.info("Downloading %s -> %s", url, dest)
            try:
                client.download_file(url, dest)
                total_files += 1
            except Exception:
                logger.exception("Failed to download %s", url)

    logger.info("Downloaded %d files to %s", total_files, files_dir)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Scrape deposited papers from the UK Parliament API.",
    )
    parser.add_argument(
        "--search", "-s",
        dest="search_term",
        help="Free-text search term.",
    )
    parser.add_argument(
        "--date-from",
        help="Only include papers deposited on or after this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--date-to",
        help="Only include papers deposited on or before this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--member-id",
        type=int,
        help="Filter by depositing member ID.",
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
        help="Download attached files for each paper.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=20,
        help="Number of results per API request (default: 20, max: 100).",
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
    if args.search_term:
        logger.info("  Search term: %s", args.search_term)
    if args.date_from:
        logger.info("  Date from: %s", args.date_from)
    if args.date_to:
        logger.info("  Date to: %s", args.date_to)
    if args.member_id:
        logger.info("  Member ID: %s", args.member_id)

    papers = list(client.iter_all(
        search_term=args.search_term,
        date_from=args.date_from,
        date_to=args.date_to,
        member_id=args.member_id,
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
