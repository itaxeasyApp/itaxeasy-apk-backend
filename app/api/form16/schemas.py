from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class Form16Data(BaseModel):
    """
    The normalized Form 16 contract returned to the app and stored (as JSON) in
    `form16_imports.data`. Money fields default to 0 (OCR may not find every
    value); identity fields are optional strings.
    """

    fileName: Optional[str] = None
    assessmentYear: Optional[str] = None

    # Identity
    employerName: Optional[str] = None
    employerAddress: Optional[str] = None
    employerTan: Optional[str] = None
    employerPan: Optional[str] = None
    employeeName: Optional[str] = None
    employeeAddress: Optional[str] = None
    employeePan: Optional[str] = None
    phone: Optional[str] = None

    # Salary
    grossSalary: float = 0
    grossTotalIncome: float = 0
    salaryChargeable: float = 0
    standardDeduction: float = 0
    housePropertyIncome: float = 0
    otherIncome: float = 0

    # Chapter VI-A deductions
    section80C: float = 0
    section80D: float = 0
    section80CCD1B: float = 0
    chapterViaTotal: float = 0

    # Tax computation
    taxableIncome: float = 0
    taxOnTotalIncome: float = 0
    rebateUnderSection87A: float = 0
    surcharge: float = 0
    healthAndEducationCess: float = 0
    taxPayable: float = 0
    netTaxPayable: float = 0
    totalTaxDeducted: float = 0
    totalTaxDeposited: float = 0

    # Meta
    taxRegime: Optional[str] = None
    confidence: str = "low"
    warnings: List[str] = []
    # Full, cleanly-keyed Form 16 breakdown from the OCR extractor (every row).
    partA: Optional[dict] = None
    partB: Optional[dict] = None
    rawText: str = ""


class Form16ParseResult(BaseModel):
    """
    Result of extracting a PDF WITHOUT saving. Returned by POST /parse and shown
    to the user for review; the client posts it back to POST "" to persist.
    """

    data: Form16Data
    rawOcr: Optional[dict] = None


class Form16SaveRequest(BaseModel):
    """Persist a reviewed Form 16 (upsert by assessment year)."""

    data: Form16Data
    rawOcr: Optional[dict] = None


class Form16Record(BaseModel):
    """A stored Form 16 import (one per user per assessment year)."""

    id: int
    assessmentYear: str
    createdAt: datetime
    updatedAt: datetime
    data: Form16Data

    class Config:
        from_attributes = True


class Form16ListItem(BaseModel):
    """Lightweight list row — enough to render a per-employer picker."""

    id: int
    assessmentYear: str
    employerTan: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    employerName: Optional[str] = None
    employeePan: Optional[str] = None
    grossSalary: float = 0
    totalTaxDeducted: float = 0
    confidence: str = "low"
