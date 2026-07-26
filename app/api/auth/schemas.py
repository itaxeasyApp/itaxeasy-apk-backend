import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import UserGender, UserType

_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_AADHAAR_RE = re.compile(r"^\d{12}$")


class UserResponse(BaseModel):
    id: int
    createdAt: datetime
    updatedAt: datetime
    phone: str
    email: Optional[EmailStr] = None
    fullName: str
    profilePhoto: Optional[str] = None
    timeZone: str
    language: str
    gender: Optional[UserGender] = None
    panNumber: Optional[str] = None
    aadhaarNumber: Optional[str] = None
    fatherName: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    verified: bool
    userType: UserType

    class Config:
        from_attributes = True


class OtpSendRequest(BaseModel):
    """Ask the backend to have MSG91 send an OTP to this phone."""

    phone: str = Field(..., description="Indian mobile (E.164 +91… or 10 digits)")


class OtpVerifyRequest(BaseModel):
    """
    Verify the OTP the user typed, or the MSG91 SendOTP Widget access token.
    On success, the backend registers (first time, `fullName` required) or
    logs the user in.
    """

    phone: Optional[str] = Field(default=None, description="Same phone the OTP was sent to")
    otp: Optional[str] = Field(default=None, min_length=4, max_length=8, description="Code from SMS")
    accessToken: Optional[str] = Field(default=None, description="JWT access token from MSG91 SendOTP Widget")
    fullName: Optional[str] = Field(
        default=None, min_length=3, description="Required on first-time registration"
    )
    email: Optional[EmailStr] = None
    deviceInfo: Optional[str] = Field(default=None, description="Optional device label")


class RefreshRequest(BaseModel):
    refreshToken: str


class ProfileUpdateRequest(BaseModel):
    fullName: Optional[str] = Field(default=None, min_length=3)
    email: Optional[EmailStr] = None
    profilePhoto: Optional[str] = None
    timeZone: Optional[str] = None
    language: Optional[str] = None
    gender: Optional[UserGender] = None
    # Personal KYC (OCR-scanned)
    panNumber: Optional[str] = None
    aadhaarNumber: Optional[str] = None
    fatherName: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None

    @field_validator("panNumber")
    @classmethod
    def _validate_pan(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().upper()
        if not _PAN_RE.match(v):
            raise ValueError("Invalid PAN format (expected ABCDE1234F).")
        return v

    @field_validator("aadhaarNumber")
    @classmethod
    def _validate_aadhaar(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        digits = re.sub(r"\s", "", v)
        if not _AADHAAR_RE.match(digits):
            raise ValueError("Aadhaar number must be exactly 12 digits.")
        return digits

    @field_validator("dob")
    @classmethod
    def _validate_dob(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Date of birth must be ISO format YYYY-MM-DD.")
        return v


class TokenResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "bearer"
    isNewUser: bool = False
    user: UserResponse
