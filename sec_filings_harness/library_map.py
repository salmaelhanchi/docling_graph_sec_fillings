"""Discover and summarize docling-graph usage options for the SEC harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

from docling_graph import PipelineConfig


CORE_OPTION_MATRIX: dict[str, tuple[Any, ...]] = {
    "backend": ("llm", "vlm"),
    "inference": ("local", "remote"),
    "processing_mode": ("one-to-one", "many-to-one"),
    "extraction_contract": ("direct", "staged", "delta"),
    "docling_config": ("ocr", "vision"),
    "structured_output": (True, False),
    "use_chunking": (True, False),
    "export_format": ("csv", "cypher"),
    "reverse_edges": (True, False),
    "dump_to_disk": (True, False, None),
}


def discover_pipeline_config_fields() -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for name, field in PipelineConfig.model_fields.items():
        annotation_args = get_args(field.annotation)
        fields.append(
            {
                "name": name,
                "annotation": str(field.annotation),
                "default": None if field.default is None else str(field.default),
                "literal_values": [str(value) for value in annotation_args]
                if annotation_args
                else [],
                "required": field.is_required(),
                "description": field.description or "",
            }
        )
    return fields


def sec_docling_graph_presets() -> list[dict[str, Any]]:
    """Curated option coverage that is realistic for large SEC filings."""

    return [
        {
            "name": "llm_direct_text_heavy",
            "backend": "llm",
            "inference": "remote",
            "processing_mode": "many-to-one",
            "extraction_contract": "direct",
            "docling_config": "ocr",
            "use_chunking": True,
            "structured_output": True,
        },
        {
            "name": "llm_staged_large_filing",
            "backend": "llm",
            "inference": "remote",
            "processing_mode": "many-to-one",
            "extraction_contract": "staged",
            "docling_config": "ocr",
            "use_chunking": True,
            "structured_output": True,
            "staged_tuning_preset": "standard",
        },
        {
            "name": "llm_delta_long_filing",
            "backend": "llm",
            "inference": "remote",
            "processing_mode": "many-to-one",
            "extraction_contract": "delta",
            "docling_config": "ocr",
            "use_chunking": True,
            "llm_batch_token_size": 2048,
            "delta_resolvers_enabled": True,
            "delta_resolvers_mode": "semantic",
        },
        {
            "name": "local_ollama_smoke",
            "backend": "llm",
            "inference": "local",
            "provider_override": "ollama",
            "model_override": "mistral:7b-instruct",
            "llm_overrides": {
                "connection": {
                    "base_url": "http://localhost:11434",
                },
                "generation": {
                    "temperature": 0.1,
                },
                "reliability": {
                    "timeout_s": 300,
                    "max_retries": 1,
                },
            },
            "processing_mode": "many-to-one",
            "extraction_contract": "direct",
            "use_chunking": True,
            "structured_output": False,
        },
    ]


def save_library_map(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "public_entrypoints": ["docling_graph.PipelineConfig", "docling_graph.run_pipeline"],
        "core_option_matrix": CORE_OPTION_MATRIX,
        "pipeline_config_fields": discover_pipeline_config_fields(),
        "sec_presets": sec_docling_graph_presets(),
        "notes": [
            "VLM only supports local inference.",
            "SEC URLs are accepted as URL inputs and downloaded by docling-graph before conversion.",
            "Remote LLM presets require the relevant provider API key.",
            "Local LLM presets require the local model server, such as Ollama or vLLM.",
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    output_path = Path("data") / "docling_graph_library_map.json"
    save_library_map(output_path)
    print(f"Saved docling-graph option map to {output_path}")


if __name__ == "__main__":
    main()
