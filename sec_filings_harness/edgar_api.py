"""Small EDGAR client for discovering SEC filing document links.

The client uses official SEC JSON endpoints:
- https://www.sec.gov/files/company_tickers.json
- https://data.sec.gov/submissions/CIK##########.json
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests


SEC_DATA_BASE_URL = "https://data.sec.gov"
SEC_WWW_BASE_URL = "https://www.sec.gov"
FORMS = ("10-K", "10-Q", "20-F")
PERIODS = ("pre_2021", "post_2021")

DEFAULT_COMPANY_QUERIES: dict[str, tuple[str, ...]] = {
    "10-K": ("Apple Inc.", "Microsoft Corporation", "Amazon.com Inc."),
    "10-Q": ("Apple Inc.", "Microsoft Corporation", "Amazon.com Inc."),
    "20-F": (
        "Alibaba Group Holding Limited",
        "Toyota Motor Corporation",
        "ASML Holding N.V.",
        "Shell plc",
    ),
}


@dataclass(frozen=True)
class Company:
    cik: int
    ticker: str
    title: str

    @property
    def padded_cik(self) -> str:
        return f"{self.cik:010d}"


@dataclass(frozen=True)
class FilingLink:
    form: str
    period_bucket: str
    company_name: str
    ticker: str
    cik: int
    accession_number: str
    filing_date: str
    report_date: str
    primary_document: str
    document_url: str
    filing_detail_url: str
    source_endpoint: str


class EdgarClient:
    """Thin wrapper around SEC company ticker and submissions endpoints."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        request_delay_seconds: float = 0.2,
        timeout_seconds: int = 30,
    ) -> None:
        self.user_agent = user_agent or os.getenv(
            "SEC_USER_AGENT",
            "docling-graph-sec-harness/0.1 research@example.com",
        )
        self.request_delay_seconds = request_delay_seconds
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def get_json(self, url: str) -> Any:
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        response = self.session.get(url, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        time.sleep(self.request_delay_seconds)
        return response.json()

    def download_file(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        response = self.session.get(url, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        time.sleep(self.request_delay_seconds)
        destination.write_bytes(response.content)
        return destination

    def company_tickers(self) -> list[Company]:
        payload = self.get_json(f"{SEC_WWW_BASE_URL}/files/company_tickers.json")
        return [
            Company(
                cik=int(item["cik_str"]),
                ticker=str(item["ticker"]),
                title=str(item["title"]),
            )
            for item in payload.values()
        ]

    def search_companies(self, query: str, *, limit: int = 8) -> list[Company]:
        normalized = query.casefold()
        terms = [part for part in normalized.replace(".", " ").split() if part]
        matches: list[tuple[int, Company]] = []
        for company in self.company_tickers():
            haystack = f"{company.title} {company.ticker}".casefold()
            score = sum(1 for term in terms if term in haystack)
            if normalized in haystack:
                score += len(terms) + 2
            if score:
                matches.append((score, company))

        matches.sort(key=lambda item: (-item[0], item[1].title))
        return [company for _, company in matches[:limit]]

    def submissions(self, company: Company) -> dict[str, Any]:
        return self.get_json(f"{SEC_DATA_BASE_URL}/submissions/CIK{company.padded_cik}.json")

    def filing_rows(self, company: Company) -> list[dict[str, str]]:
        submission = self.submissions(company)
        endpoint = f"{SEC_DATA_BASE_URL}/submissions/CIK{company.padded_cik}.json"
        rows = _rows_from_recent(submission["filings"]["recent"], endpoint)

        for file_meta in submission.get("filings", {}).get("files", []):
            older_endpoint = f"{SEC_DATA_BASE_URL}/submissions/{file_meta['name']}"
            older = self.get_json(older_endpoint)
            rows.extend(_rows_from_recent(older, older_endpoint))

        return rows


def _rows_from_recent(recent: dict[str, list[Any]], endpoint: str) -> list[dict[str, str]]:
    fields = list(recent.keys())
    row_count = len(recent.get("accessionNumber", []))
    rows: list[dict[str, str]] = []
    for index in range(row_count):
        row = {field: str(recent[field][index] or "") for field in fields}
        row["source_endpoint"] = endpoint
        rows.append(row)
    return rows


def _period_match(filing_date: str, period_bucket: str) -> bool:
    parsed = date.fromisoformat(filing_date)
    split = date(2021, 1, 1)
    if period_bucket == "pre_2021":
        return parsed < split
    if period_bucket == "post_2021":
        return parsed >= split
    raise ValueError(f"Unsupported period bucket: {period_bucket}")


def _filing_link(company: Company, row: dict[str, str], period_bucket: str) -> FilingLink:
    accession = row["accessionNumber"]
    accession_no_dash = accession.replace("-", "")
    cik_path = str(company.cik)
    primary_document = row["primaryDocument"]
    base = f"{SEC_WWW_BASE_URL}/Archives/edgar/data/{cik_path}/{accession_no_dash}"
    return FilingLink(
        form=row["form"],
        period_bucket=period_bucket,
        company_name=company.title,
        ticker=company.ticker,
        cik=company.cik,
        accession_number=accession,
        filing_date=row["filingDate"],
        report_date=row.get("reportDate", ""),
        primary_document=primary_document,
        document_url=f"{base}/{primary_document}",
        filing_detail_url=f"{base}/{accession}-index.html",
        source_endpoint=row["source_endpoint"],
    )


def choose_filing(
    company: Company, rows: list[dict[str, str]], form: str, period_bucket: str
) -> FilingLink | None:
    candidates = [
        row
        for row in rows
        if row.get("form") == form
        and row.get("filingDate")
        and row.get("primaryDocument")
        and _period_match(row["filingDate"], period_bucket)
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda row: row["filingDate"], reverse=True)
    return _filing_link(company, candidates[0], period_bucket)


def discover_required_filings(
    *,
    client: EdgarClient | None = None,
    company_queries: dict[str, tuple[str, ...]] | None = None,
) -> tuple[list[FilingLink], dict[str, Any]]:
    """Find one pre-2021 and one post-2021 filing for 10-K, 10-Q, and 20-F."""

    client = client or EdgarClient()
    company_queries = company_queries or DEFAULT_COMPANY_QUERIES
    selected: list[FilingLink] = []
    search_log: dict[str, Any] = {"queries": {}, "missing": []}

    for form in FORMS:
        for period_bucket in PERIODS:
            found: FilingLink | None = None
            attempts: list[dict[str, Any]] = []
            for query in company_queries[form]:
                matches = client.search_companies(query)
                attempts.append(
                    {
                        "query": query,
                        "matches": [asdict(company) for company in matches],
                    }
                )
                for company in matches:
                    rows = client.filing_rows(company)
                    found = choose_filing(company, rows, form, period_bucket)
                    if found:
                        selected.append(found)
                        break
                if found:
                    break

            key = f"{form}:{period_bucket}"
            search_log["queries"][key] = attempts
            if not found:
                search_log["missing"].append({"form": form, "period_bucket": period_bucket})

    return selected, search_log


def save_filing_links(links: list[FilingLink], search_log: dict[str, Any], data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)

    json_path = data_dir / "sec_filing_links.json"
    json_path.write_text(
        json.dumps([asdict(link) for link in links], indent=2, sort_keys=True),
        encoding="utf-8",
    )

    csv_path = data_dir / "sec_filing_links.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(links[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(link) for link in links)

    (data_dir / "company_search_results.json").write_text(
        json.dumps(search_log, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_filing_links(path: Path) -> list[FilingLink]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [FilingLink(**item) for item in payload]


def filing_document_path(link: FilingLink, directory: Path) -> Path:
    safe_form = re.sub(r"[^A-Za-z0-9_.-]+", "_", link.form)
    safe_period = re.sub(r"[^A-Za-z0-9_.-]+", "_", link.period_bucket)
    safe_ticker = re.sub(r"[^A-Za-z0-9_.-]+", "_", link.ticker)
    safe_accession = re.sub(r"[^A-Za-z0-9_.-]+", "_", link.accession_number)
    suffix = Path(link.primary_document).suffix or ".html"
    return directory / f"{safe_form}_{safe_period}_{safe_ticker}_{safe_accession}{suffix}"


def materialize_filing_document(
    link: FilingLink,
    directory: Path,
    *,
    client: EdgarClient | None = None,
) -> Path:
    path = filing_document_path(link, directory)
    if path.exists() and path.stat().st_size > 0:
        return path
    client = client or EdgarClient()
    return client.download_file(link.document_url, path)
