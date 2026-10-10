"""Pydantic schemas for the Execution 02 financial summary workflow."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.db.models.enums import (
    FinancialInclusionRule,
    FinancialItemCategory,
    FinancialItemKind,
)


class FinancialSummaryCreateRequest(BaseModel):
    company_id: int
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)

    submitted_revenue: Decimal | None = Field(default=None, ge=0)
    submitted_expenses: Decimal | None = Field(default=None, ge=0)
    closing_bank_balance: Decimal | None = None
    closing_cash_balance: Decimal | None = None
    outstanding_debts: Decimal | None = Field(default=None, ge=0)
    customer_receivables: Decimal | None = Field(default=None, ge=0)
    manager_notes: str | None = Field(default=None, max_length=5000)
    bank_statement_reference: str | None = Field(default=None, max_length=255)


class FinancialSummaryUpdateRequest(BaseModel):
    """All fields optional; only a draft / correction-required version may change."""

    submitted_revenue: Decimal | None = Field(default=None, ge=0)
    submitted_expenses: Decimal | None = Field(default=None, ge=0)
    closing_bank_balance: Decimal | None = None
    closing_cash_balance: Decimal | None = None
    outstanding_debts: Decimal | None = Field(default=None, ge=0)
    customer_receivables: Decimal | None = Field(default=None, ge=0)
    manager_notes: str | None = Field(default=None, max_length=5000)
    bank_statement_reference: str | None = Field(default=None, max_length=255)


class FinancialItemCreateRequest(BaseModel):
    """A special item value.

    Either reference a ``definition_id`` (the rules are snapshotted from it), or
    supply the snapshot fields directly for an ad-hoc item.
    """

    definition_id: int | None = None
    amount: Decimal
    currency: str | None = Field(default=None, max_length=8)
    reason: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)

    # Ad-hoc snapshot fields (ignored when definition_id is given).
    code: str | None = Field(default=None, max_length=60)
    name_ar: str | None = Field(default=None, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    category: FinancialItemCategory | None = None
    kind: FinancialItemKind | None = None
    inclusion_rule: FinancialInclusionRule | None = None
    decision_reference: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _adhoc_needs_a_name(self) -> "FinancialItemCreateRequest":
        if self.definition_id is None and not (self.name_ar or self.name_en):
            raise ValueError("An ad-hoc item needs at least a name.")
        return self


class FinancialItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    definition_id: int | None = None
    code: str
    name_ar: str
    name_en: str
    category: str
    kind: str
    inclusion_rule: str
    decision_reference: str | None = None
    amount: Decimal
    currency: str
    reason: str | None = None
    notes: str | None = None


class FinancialBankAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    content_type: str | None
    size_bytes: int | None
    created_at: datetime


class FinancialSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_id: int
    company_id: int
    company_name_ar: str | None = None
    company_name_en: str | None = None
    period_year: int | None = None
    period_month: int | None = None
    version_number: int
    status: str
    currency: str
    corrects_version_id: int | None = None
    submitted_revenue: Decimal | None
    submitted_expenses: Decimal | None
    effective_revenue: Decimal | None
    effective_expenses: Decimal | None
    calculated_result: Decimal | None
    closing_bank_balance: Decimal | None
    closing_cash_balance: Decimal | None
    calculated_total_cash: Decimal | None
    outstanding_debts: Decimal | None
    customer_receivables: Decimal | None
    manager_notes: str | None = None
    bank_statement_reference: str | None = None
    return_note: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    created_by_id: int | None = None
    items: list[FinancialItemOut] = []
    bank_attachments: list[FinancialBankAttachmentOut] = []


class FinancialPeriodOut(BaseModel):
    id: int
    company_id: int
    company_name_ar: str | None = None
    company_name_en: str | None = None
    period_year: int
    period_month: int
    currency: str
    effective_version_id: int | None = None
    versions: list[FinancialSummaryOut] = []


class FinancialReviewReturnRequest(BaseModel):
    """Accountant returns a summary; the note is mandatory (spec AC-08)."""

    note: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def _note_is_not_blank(self) -> "FinancialReviewReturnRequest":
        if not self.note.strip():
            raise ValueError("A note is required when returning a summary for correction.")
        return self


class FinancialItemDefinitionCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z][a-z0-9_]*$")
    name_ar: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    description_ar: str | None = Field(default=None, max_length=2000)
    description_en: str | None = Field(default=None, max_length=2000)
    category: FinancialItemCategory = FinancialItemCategory.OTHER
    kind: FinancialItemKind = FinancialItemKind.OTHER
    inclusion_rule: FinancialInclusionRule = FinancialInclusionRule.INCLUDED
    is_active: bool = True
    decision_reference: str | None = Field(default=None, max_length=120)


class FinancialItemDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    code: str
    name_ar: str
    name_en: str
    description_ar: str | None = None
    description_en: str | None = None
    category: str
    kind: str
    inclusion_rule: str
    is_active: bool
    decision_reference: str | None = None


__all__ = [
    "FinancialSummaryCreateRequest",
    "FinancialSummaryUpdateRequest",
    "FinancialItemCreateRequest",
    "FinancialItemOut",
    "FinancialBankAttachmentOut",
    "FinancialSummaryOut",
    "FinancialPeriodOut",
    "FinancialReviewReturnRequest",
    "FinancialItemDefinitionCreateRequest",
    "FinancialItemDefinitionOut",
]
