"""Build or run docling-graph jobs for SEC filing links."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from docling_graph import PipelineConfig, run_pipeline

from sec_filings_harness.edgar_api import EdgarClient, FilingLink, load_filing_links, materialize_filing_document
from sec_filings_harness.library_map import sec_docling_graph_presets
from sec_filings_harness.sec_template import SecFilingDocument


def build_pipeline_config(
    link: FilingLink,
    preset: dict[str, Any],
    output_root: Path,
    *,
    source: str | Path | None = None,
    debug: bool = False,
) -> PipelineConfig:
    config_data = dict(preset)
    preset_name = config_data.pop("name")
    output_dir = output_root / preset_name / f"{link.form}_{link.period_bucket}_{link.ticker}"
    return PipelineConfig(
        source=source or link.document_url,
        template=SecFilingDocument,
        output_dir=output_dir,
        dump_to_disk=True,
        debug=debug,
        export_docling=True,
        export_docling_json=True,
        export_markdown=True,
        **config_data,
    )


def build_plan(links: list[FilingLink], output_root: Path) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for link in links:
        for preset in sec_docling_graph_presets():
            if preset["backend"] == "vlm" and preset.get("inference") == "remote":
                continue
            config = build_pipeline_config(link, preset, output_root)
            plan.append(
                {
                    "filing": asdict(link),
                    "preset": preset["name"],
                    "config": config.to_metadata_config_dict(),
                }
            )
    return plan


def provider_ready(config: PipelineConfig) -> bool:
    provider = config.provider_override or config.models.llm.remote.provider
    if config.backend == "llm" and config.inference == "remote":
        env_name = f"{provider.upper()}_API_KEY"
        return bool(os.getenv(env_name))
    return True


def run_jobs(links: list[FilingLink], output_root: Path, *, limit: int | None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    count = 0
    client = EdgarClient()
    source_dir = output_root.parent / "source_documents"
    for link in links:
        local_source: Path | None = None
        for preset in sec_docling_graph_presets():
            if limit is not None and count >= limit:
                return results

            if local_source is None:
                local_source = materialize_filing_document(link, source_dir, client=client)

            config = build_pipeline_config(
                link,
                preset,
                output_root,
                source=local_source,
                debug=True,
            )
            result: dict[str, Any] = {
                "form": link.form,
                "period_bucket": link.period_bucket,
                "ticker": link.ticker,
                "preset": preset["name"],
                "output_dir": str(config.output_dir),
                "source_path": str(local_source),
            }
            if not provider_ready(config):
                result["status"] = "skipped_missing_provider_key"
                results.append(result)
                continue

            try:
                context = run_pipeline(config)
                result.update(
                    {
                        "status": "ok",
                        "nodes": context.knowledge_graph.number_of_nodes(),
                        "edges": context.knowledge_graph.number_of_edges(),
                    }
                )
            except Exception as exc:
                result.update({"status": "error", "error": str(exc)})

            results.append(result)
            count += 1

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare or run docling-graph SEC filing jobs.")
    parser.add_argument("--links", type=Path, default=Path("data") / "sec_filing_links.json")
    parser.add_argument("--output-root", type=Path, default=Path("outputs") / "sec_filings")
    parser.add_argument("--plan-out", type=Path, default=Path("data") / "docling_graph_sec_run_plan.json")
    parser.add_argument("--run", action="store_true", help="Actually run docling-graph jobs.")
    parser.add_argument("--limit", type=int, default=None, help="Limit actual runs.")
    args = parser.parse_args()

    links = load_filing_links(args.links)
    plan = build_plan(links, args.output_root)
    args.plan_out.parent.mkdir(parents=True, exist_ok=True)
    args.plan_out.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Saved {len(plan)} planned docling-graph jobs to {args.plan_out}")

    if args.run:
        results = run_jobs(links, args.output_root, limit=args.limit)
        result_path = args.plan_out.with_name("docling_graph_sec_run_results.json")
        result_path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Saved run results to {result_path}")


if __name__ == "__main__":
    main()
