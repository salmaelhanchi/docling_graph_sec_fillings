"""Pydantic extraction template for SEC annual and quarterly filings."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def edge(label: str, **kwargs: Any) -> Any:
    if "default" not in kwargs and "default_factory" not in kwargs:
        kwargs["default"] = ...
    return Field(json_schema_extra={"edge_label": label}, **kwargs)


class CompanyIdentity(BaseModel):
    model_config = ConfigDict(graph_id_fields=["name"], extra="ignore")

    name: str = Field(description="Registrant legal name.")
    cik: str | None = Field(default=None, description="SEC central index key if present.")
    ticker: str | None = Field(default=None, description="Ticker symbol if present.")
    jurisdiction: str | None = Field(default=None, description="State or country of incorporation.")
    sic: str | None = Field(default=None, description="SIC code or industry label if present.")


class FilingPeriod(BaseModel):
    model_config = ConfigDict(is_entity=False, extra="ignore")

    fiscal_year: str | None = Field(default=None, description="Fiscal year covered by the filing.")
    period_end_date: str | None = Field(
        default=None, description="Period end date in ISO format when available."
    )
    filing_date: str | None = Field(
        default=None, description="SEC filing date in ISO format when available."
    )


class BusinessSegment(BaseModel):
    model_config = ConfigDict(graph_id_fields=["name"], extra="ignore")

    name: str = Field(description="Business segment, product line, or geography.")
    description: str | None = Field(default=None, description="Concise segment description.")
    revenue: str | None = Field(
        default=None, description="Reported revenue amount with unit and currency."
    )


class RiskFactor(BaseModel):
    model_config = ConfigDict(graph_id_fields=["name"], extra="ignore")

    name: str = Field(description="Short name for the risk factor.")
    category: str | None = Field(
        default=None, description="Risk category, such as market, legal, cyber, or liquidity."
    )
    description: str | None = Field(
        default=None, description="Specific risk described by management."
    )


class FinancialMetric(BaseModel):
    model_config = ConfigDict(graph_id_fields=["name"], extra="ignore")

    name: str = Field(description="Financial metric name, such as revenue, net income, or assets.")
    value: str | None = Field(default=None, description="Reported value with unit and currency.")
    period: str | None = Field(default=None, description="Period associated with the metric.")


class SecFilingDocument(BaseModel):
    """Root model for extracting graph-ready facts from SEC filings."""

    model_config = ConfigDict(graph_id_fields=["accession_number"], extra="ignore")

    accession_number: str = Field(
        description="SEC accession number, or document accession if visible."
    )
    form_type: str = Field(description="SEC form type, for example 10-K, 10-Q, or 20-F.")
    title: str | None = Field(default=None, description="Document title.")
    company: CompanyIdentity | None = edge(
        "FILED_BY",
        default=None,
        description="Registrant that filed this SEC document.",
    )
    period: FilingPeriod | None = edge(
        "COVERS_PERIOD",
        default=None,
        description="Fiscal period covered by this filing.",
    )
    business_segments: list[BusinessSegment] = edge(
        "DESCRIBES_SEGMENT",
        default_factory=list,
        description="Major business segments, product groups, or geographies discussed.",
    )
    risk_factors: list[RiskFactor] = edge(
        "DISCLOSES_RISK",
        default_factory=list,
        description="Material risk factors disclosed in the filing.",
    )
    financial_metrics: list[FinancialMetric] = edge(
        "REPORTS_METRIC",
        default_factory=list,
        description="Key financial metrics reported in the filing.",
    )
