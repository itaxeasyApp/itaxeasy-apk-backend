"""ProfileUpdateRequest validates & normalizes the OCR-scanned KYC fields."""
import pytest
from pydantic import ValidationError

from app.api.auth.schemas import ProfileUpdateRequest, UserResponse


def test_accepts_and_uppercases_valid_pan():
    req = ProfileUpdateRequest(panNumber="abcde1234f")
    assert req.panNumber == "ABCDE1234F"


def test_rejects_malformed_pan():
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(panNumber="XYZ123")


def test_strips_spaces_from_aadhaar():
    req = ProfileUpdateRequest(aadhaarNumber="1234 5678 9012")
    assert req.aadhaarNumber == "123456789012"


def test_rejects_short_aadhaar():
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(aadhaarNumber="12345")


def test_partial_patch_leaves_other_fields_none():
    req = ProfileUpdateRequest(fatherName="Ramesh Kumar")
    assert req.fatherName == "Ramesh Kumar"
    assert req.panNumber is None
    assert req.aadhaarNumber is None
    assert req.dob is None


def test_user_response_exposes_kyc_fields():
    fields = UserResponse.model_fields
    for name in ("panNumber", "aadhaarNumber", "fatherName", "dob", "address"):
        assert name in fields
