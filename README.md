# Deposited Papers Scraper

Scrapes deposited paper records from the [UK Parliament Deposited Papers API](https://depositedpapers-api.parliament.uk/index.html).

Deposited papers are documents placed in the Libraries of the House of Commons or House of Lords, typically by government ministers in response to parliamentary questions or commitments.

## Setup

```
pip install -r requirements.txt
```

## Usage

Fetch all papers and save as JSON + CSV:

```
python scraper.py
```

Search by keyword:

```
python scraper.py --search "immigration"
```

Filter by date range:

```
python scraper.py --deposited-from 2024-01-01 --deposited-to 2024-12-31
```

Filter by house:

```
python scraper.py --house Commons
```

Also download attached documents:

```
python scraper.py --search "housing" --download-files
```

Output CSV only:

```
python scraper.py --format csv
```

### All options

```
python scraper.py --help
```

| Flag | Description |
|------|-------------|
| `--search`, `-s` | Free-text search across department, paper number, summary (2–500 chars) |
| `--deposited-from` | Papers deposited on or after this date (YYYY-MM-DD) |
| `--deposited-to` | Papers deposited on or before this date (YYYY-MM-DD) |
| `--house` | Filter by house: `All`, `Commons`, or `Lords` |
| `--order-by` | Sort order: `Relevance`, `CommitmentDateAsc`, `CommitmentDateDesc` |
| `--department-id` | Filter by depositing department ID |
| `--format`, `-f` | Output format: `json`, `csv`, or `both` (default: `both`) |
| `--output-dir`, `-o` | Output directory (default: `output/`) |
| `--download-files` | Download attached documents for each paper |
| `--page-size` | Results per API request (default: 20) |
| `--verbose`, `-v` | Verbose logging |

## Output

- `output/papers.json` — full API response data for each paper
- `output/papers.csv` — flattened records with key fields
- `output/files/` — downloaded attachments (when `--download-files` is used)

## Project structure

```
client.py      — API client with pagination and retry logic
scraper.py     — CLI entry point
```

## API reference

- [Deposited Papers API docs](https://depositedpapers-api.parliament.uk/index.html)
- [OpenAPI spec](https://depositedpapers-api.parliament.uk/swagger/v1/swagger.json)
- [UK Parliament Developer Hub](https://developer.parliament.uk/)

Data is available under the [Open Parliament Licence](https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/).
