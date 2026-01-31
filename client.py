"""Client for the UK Parliament Deposited Papers API.

API docs: https://depositedpapers-api.parliament.uk/index.html
Swagger:  https://depositedpapers-api.parliament.uk/swagger/v1/swagger.json
"""

import time
import logging
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://depositedpapers-api.parliament.uk"
API_PATH = "/api/DepositedPapers"
DEFAULT_PAGE_SIZE = 20
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubles each retry


class DepositedPapersClient:
    """Client for querying the UK Parliament Deposited Papers API."""

    def __init__(self, base_url=BASE_URL, page_size=DEFAULT_PAGE_SIZE):
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
        })

    def _get(self, path, params=None):
        """Make a GET request with retry logic."""
        url = f"{self.base_url}{path}"
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, params=params, timeout=90)
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

    def search(self, terms=None, deposited_from=None, deposited_to=None,
               house=None, order_by=None, department_ses_id=None,
               skip=0, take=None):
        """Search deposited papers.

        Args:
            terms: Free-text search across department, paper number, summary.
                   Must be 2–500 characters.
            deposited_from: Papers deposited on or after this date (YYYY-MM-DD).
            deposited_to: Papers deposited on or before this date (YYYY-MM-DD).
            house: Filter by house — "All", "Commons", or "Lords".
            order_by: Sort order — "Relevance", "CommitmentDateAsc",
                      or "CommitmentDateDesc".
            department_ses_id: Filter by depositing department ID.
            skip: Number of results to skip (pagination offset).
            take: Number of results to return per page.

        Returns:
            dict with keys: items, totalResults, links.
        """
        params = {
            "Skip": skip,
            "Take": take or self.page_size,
        }
        if terms:
            params["Terms"] = terms
        if deposited_from:
            params["DepositedFrom"] = deposited_from
        if deposited_to:
            params["DepositedTo"] = deposited_to
        if house:
            params["House"] = house
        if order_by:
            params["OrderBy"] = order_by
        if department_ses_id is not None:
            params["DepartmentSesId"] = department_ses_id

        return self._get(API_PATH, params=params)

    def get_paper(self, paper_id):
        """Get a single deposited paper by ID.

        Args:
            paper_id: The deposited paper ID (integer).

        Returns:
            dict with keys: value (paper detail), links.
        """
        return self._get(f"{API_PATH}/{paper_id}")

    def iter_all(self, terms=None, deposited_from=None, deposited_to=None,
                 house=None, order_by=None, department_ses_id=None):
        """Iterate over all deposited papers matching the query.

        Handles pagination automatically. Each yielded record is the inner
        ``value`` dict (the actual paper data), unwrapped from the
        ``{value, links}`` resource envelope.

        Args:
            terms: Free-text search.
            deposited_from: Start date (YYYY-MM-DD).
            deposited_to: End date (YYYY-MM-DD).
            house: "All", "Commons", or "Lords".
            order_by: "Relevance", "CommitmentDateAsc", "CommitmentDateDesc".
            department_ses_id: Depositing department ID.

        Yields:
            dict for each deposited paper (unwrapped from resource envelope).
        """
        skip = 0
        while True:
            data = self.search(
                terms=terms,
                deposited_from=deposited_from,
                deposited_to=deposited_to,
                house=house,
                order_by=order_by,
                department_ses_id=department_ses_id,
                skip=skip,
            )

            items = data.get("items") or []
            total = data.get("totalResults")
            if not items:
                break

            for item in items:
                # Each item is {value: {...}, links: [...]}
                yield item.get("value", item)

            skip += len(items)

            if total is not None:
                logger.info("  Progress: %d / %d", skip, total)
                if skip >= total:
                    break

            if len(items) < self.page_size:
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
