from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models import BusinessStatus


class FinancialYearResponse(BaseModel):
    id: int
    label: str
    startDate: str
    endDate: str
    isClosed: bool

    class Config:
        from_attributes = True


class BusinessSettingsResponse(BaseModel):
    """SRS Module 4 — Business Configuration toggles."""

    inventoryEnabled: bool
    gstRegistered: bool
    multiBranch: bool
    manufacturing: bool

    class Config:
        from_attributes = True


class BusinessSettingsUpdateRequest(BaseModel):
    """Partial update of the Module 4 toggles (Business Configuration Wizard)."""

    inventoryEnabled: Optional[bool] = None
    gstRegistered: Optional[bool] = None
    multiBranch: Optional[bool] = None
    manufacturing: Optional[bool] = None


class BusinessResponse(BaseModel):
    id: int
    createdAt: datetime
    updatedAt: datetime
    userId: int
    name: str
    pan: Optional[str] = None
    gstin: Optional[str] = None
    stateCode: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    country: str
    currency: str
    fyStartMonth: int
    status: BusinessStatus
    financial_years: List[FinancialYearResponse] = []
    settings: Optional[BusinessSettingsResponse] = None

    class Config:
        from_attributes = True


class BusinessCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Trade Name (required)")
    pan: Optional[str] = None
    gstin: Optional[str] = None
    stateCode: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    country: str = "India"
    currency: str = "INR"
    fyStartMonth: int = Field(default=4, ge=1, le=12)
    # 'draft' = Save Draft; 'active' = Create Business (requires pan + state)
    status: BusinessStatus = BusinessStatus.draft


class BusinessUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    pan: Optional[str] = None
    gstin: Optional[str] = None
    stateCode: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    fyStartMonth: Optional[int] = Field(default=None, ge=1, le=12)
    status: Optional[BusinessStatus] = None
