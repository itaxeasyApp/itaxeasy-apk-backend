"""The User profile carries the OCR-scanned KYC fields (SRS personal profile)."""
from app.models import User


def test_user_has_kyc_columns():
    for col in ("panNumber", "aadhaarNumber", "fatherName", "dob", "address"):
        assert hasattr(User, col), f"User model is missing KYC column: {col}"
