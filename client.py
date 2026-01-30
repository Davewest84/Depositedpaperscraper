"""Client for the UK Parliament Deposited Papers API.

API docs: https://depositedpapers-api.parliament.uk/index.html
"""

import time
import logging
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://depositedpapers-api.parliament.uk"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubles each retry


class DepositedPapersClient:
    """Client for querying the UK Parliament Deposited Papers API."""

    def __init__(self, base_url=BASE_URL, page_size=DEFAULT_PAGE_SIZE):
        self.base_url = base_url.rstrip("/")
        self.page_size = min(page_size, MAX_PAGE_SIZE)
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
        })

    def _get(self, path, params=None):
        """Make a GET request with retry logic."""
        url = f"{self.base_url}{path}"
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as exc:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    logger.warning(
                        "Request to %s failed (%s), retrying in %ds...",
                        url, exc, wait,
                    )
                    time.sleep(wait)
                else:
                    raise

    def search(self, search_term=None, date_from=None, date_to=None,
               member_id=None, skip=0, take=None):
        """Search deposited papers.

        Args:
            search_term: Free-text search string.
            date_from: Start date (YYYY-MM-DD).
            date_to: End date (YYYY-MM-DD).
            member_id: Filter by depositing member ID.
            skip: Number of results to skip (pagination offset).
            take: Number of results to return per page.

        Returns:
            dict with search results and pagination info.
        """
        params = {
            "Skip": skip,
            "Take": take or self.page_size,
        }
        if search_term:
            params["SearchTerm"] = search_term
        if date_from:
            params["DateFrom"] = date_from
        if date_to:
            params["DateTo"] = date_to
        if member_id:
            params["MemberId"] = member_id

        return self._get("/api/deposited-papers", params=params)

    def get_paper(self, paper_id):
        """Get a single deposited paper by ID.

        Args:
            paper_id: The deposited paper ID.

        Returns:
            dict with paper details.
        """
        return self._get(f"/api/deposited-papers/{paper_id}")

    def iter_all(self, search_term=None, date_from=None, date_to=None,
                 member_id=None):
        """Iterate over all deposited papers matching the query.

        Handles pagination automatically, yielding individual paper records.

        Args:
            search_term: Free-text search string.
            date_from: Start date (YYYY-MM-DD).
            date_to: End date (YYYY-MM-DD).
            member_id: Filter by depositing member ID.

        Yields:
            dict for each deposited paper.
        """
        skip = 0
        while True:
            data = self.search(
                search_term=search_term,
                date_from=date_from,
                date_to=date_to,
                member_id=member_id,
                skip=skip,
            )

            # The API may return results under different keys.
            # Try common patterns used by Parliament APIs.
            results = []
            if isinstance(data, list):
                results = data
            elif isinstance(data, dict):
                # Try known response shapes
                for key in ("results", "items", "depositedPapers", "value"):
                    if key in data:
                        results = data[key]
                        break
                else:
                    # If the dict itself looks like a paged response with
                    # a totalResults count, the items may be at the top level
                    # under a different key. Log and break.
                    logger.warning(
                        "Unexpected response shape at skip=%d: keys=%s",
                        skip, list(data.keys()),
                    )
                    break

            if not results:
                break

            yield from results

            skip += len(results)

            # Check if we've reached the end
            total = None
            if isinstance(data, dict):
                for key in ("totalResults", "total", "totalCount"):
                    if key in data:
                        total = data[key]
                        break

            if total is not None and skip >= total:
                break

            # Safety: if we got fewer results than requested, we're done
            if len(results) < self.page_size:
                break

    def download_file(self, file_url, dest_path):
        """Download a file from a deposited paper.

        Args:
            file_url: URL of the file to download.
            dest_path: Local path to save the file to.
        """
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(file_url, timeout=60, stream=True)
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                return
            except requests.exceptions.RequestException as exc:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    logger.warning(
                        "Download of %s failed (%s), retrying in %ds...",
                        file_url, exc, wait,
                    )
                    time.sleep(wait)
                else:
                    raise
