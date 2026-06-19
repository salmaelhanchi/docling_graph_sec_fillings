"""CLI entrypoint for retrieving SEC filing links into the data folder."""

from __future__ import annotations

import argparse
from pathlib import Path

from sec_filings_harness.edgar_api import EdgarClient, discover_required_filings, save_filing_links


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch SEC filing document links.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--user-agent",
        default=None,
        help="SEC User-Agent. Prefer setting SEC_USER_AGENT='name email@example.com'.",
    )
    args = parser.parse_args()

    client = EdgarClient(user_agent=args.user_agent)
    links, search_log = discover_required_filings(client=client)
    if len(links) != 6:
        missing = search_log.get("missing", [])
        raise SystemExit(f"Expected 6 links but found {len(links)}. Missing: {missing}")

    save_filing_links(links, search_log, args.data_dir)
    print(f"Saved {len(links)} filing links to {args.data_dir / 'sec_filing_links.json'}")
    for link in links:
        print(
            f"{link.form:4} {link.period_bucket:9} {link.ticker:5} "
            f"{link.filing_date} {link.document_url}"
        )


if __name__ == "__main__":
    main()
