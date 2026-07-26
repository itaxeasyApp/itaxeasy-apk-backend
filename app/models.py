import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


# Enums
class UserGender(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"


class UserType(str, enum.Enum):
    normal = "normal"
    agent = "agent"
    admin = "admin"
    superadmin = "superadmin"


class BusinessStatus(str, enum.Enum):
    draft = "draft"  # "Save Draft" — not yet usable for accounting
    active = "active"  # fully created — unlocks accounting/GST/inventory


class User(Base):
    """
    Phase-1 user (SRS Module 1 & 2).

    Authentication is phone + MSG91 OTP only — there is no password column. The
    phone number is established and trusted when MSG91 verifies the OTP.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Legacy Firebase identity — kept nullable for older accounts; no longer set.
    firebaseUid = Column(String, unique=True, nullable=True, index=True)

    # SRS Module 1 / 2 fields
    phone = Column(String, nullable=False, unique=True)  # Mobile number (Mandatory)
    email = Column(String, unique=True, nullable=True)  # Optional in SRS Module 1
    fullName = Column(String, nullable=False)  # Min 3 chars (validated in schema)
    profilePhoto = Column(String, nullable=True)  # URL / path (Module 2, optional)
    timeZone = Column(String, nullable=False, server_default="Asia/Kolkata")  # Module 2
    language = Column(String, nullable=False, server_default="en")  # Module 2

    gender = Column(Enum(UserGender), nullable=True)
    verified = Column(Boolean, default=True, nullable=False)  # Phone verified via Firebase
    userType = Column(Enum(UserType), default=UserType.normal, nullable=False)

    # Personal KYC (OCR-scanned from PAN / Aadhaar) — all optional.
    panNumber = Column(String, nullable=True)      # PAN, uppercased ABCDE1234F
    aadhaarNumber = Column(String, nullable=True)  # 12 digits, no spaces
    fatherName = Column(String, nullable=True)     # from PAN
    dob = Column(String, nullable=True)            # ISO YYYY-MM-DD
    address = Column(Text, nullable=True)          # from Aadhaar (multiline)

    # Relationships
    sessions = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    otp_logs = relationship(
        "OtpLog", back_populates="user", cascade="all, delete-orphan"
    )
    businesses = relationship(
        "Business", back_populates="owner", cascade="all, delete-orphan"
    )
    form16_imports = relationship(
        "Form16Import", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User id={self.id} phone={self.phone}>"


class UserSession(Base):
    """
    SRS-required `user_sessions`. One row per issued refresh token.

    We store only a hash of the refresh token (never the raw value). Rotating or
    logging out revokes the row, which invalidates that refresh token.
    """

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    userId = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refreshTokenHash = Column(String, nullable=False, unique=True)
    deviceInfo = Column(String, nullable=True)
    ipAddress = Column(String, nullable=True)
    expiresAt = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<UserSession id={self.id} userId={self.userId} revoked={self.revoked}>"


class OtpLog(Base):
    """
    SRS-required `otp_logs`, repurposed as an AUDIT trail.

    Since the OTP itself is generated, sent and verified by MSG91, we don't store
    OTP codes. We record each successful verification for traceability/compliance.
    """

    __tablename__ = "otp_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    userId = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    phone = Column(String, nullable=False)
    firebaseUid = Column(String, nullable=True)  # legacy; unused with MSG91
    ipAddress = Column(String, nullable=True)
    purpose = Column(String, nullable=False, server_default="login")  # login | register

    user = relationship("User", back_populates="otp_logs")

    def __repr__(self):
        return f"<OtpLog id={self.id} phone={self.phone} purpose={self.purpose}>"


class Business(Base):
    """
    SRS Module 3 — Business (a.k.a. BillShield "company").

    Owned by a user (optional: a user may have zero or many businesses). The
    business is the server source of truth; the on-device BillShield engine
    scopes its local books by this id.
    """

    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    userId = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # SRS Module 3 fields
    name = Column(String, nullable=False)  # Trade Name (required)
    pan = Column(String, nullable=True)  # required when status=active (validated in schema)
    gstin = Column(String, nullable=True)  # GSTIN (optional)
    stateCode = Column(String, nullable=True)  # State (required when active)
    address = Column(String, nullable=True)  # Street / building address (optional)
    city = Column(String, nullable=True)  # City / town (optional)
    pincode = Column(String, nullable=True)  # Postal PIN code (optional)
    country = Column(String, nullable=False, server_default="India")
    currency = Column(String, nullable=False, server_default="INR")
    fyStartMonth = Column(Integer, nullable=False, server_default="4")  # 4 = April

    status = Column(Enum(BusinessStatus), nullable=False, default=BusinessStatus.draft)

    owner = relationship("User", back_populates="businesses")
    financial_years = relationship(
        "FinancialYear", back_populates="business", cascade="all, delete-orphan"
    )
    settings = relationship(
        "BusinessSettings",
        back_populates="business",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Business id={self.id} name={self.name} status={self.status}>"


class BusinessSettings(Base):
    """
    SRS Module 4 — Business Configuration (`business_settings`).

    Four yes/no toggles that reshape the whole app (the "Layer-2" gating that
    decides which menus/reports BillShield shows for an ACTIVE business):
      - inventoryEnabled: show Items/Stock/Warehouses; invoices use an item grid
        that moves stock. If False, only services (no stock).
      - gstRegistered: show GST Returns/Dashboard/Reports.
      - multiBranch: enable Branch Master/Transfers/Reports (SRS Module 6).
      - manufacturing: enable BOM/Production/etc. — REQUIRES inventoryEnabled.

    One row per business (1:1). Seeded with defaults when a business is created
    (SRS Module 3 "System Action: Create Default Business Configuration").
    """

    __tablename__ = "business_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    businessId = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    inventoryEnabled = Column(Boolean, nullable=False, server_default="false")
    gstRegistered = Column(Boolean, nullable=False, server_default="false")
    multiBranch = Column(Boolean, nullable=False, server_default="false")
    manufacturing = Column(Boolean, nullable=False, server_default="false")

    business = relationship("Business", back_populates="settings")

    def __repr__(self):
        return (
            f"<BusinessSettings businessId={self.businessId} "
            f"inventory={self.inventoryEnabled} gst={self.gstRegistered}>"
        )


class Form16Import(Base):
    """
    A user's extracted Form 16, one row per (user, assessment year).

    The uploaded PDF is proxied to the OCR service, normalized, and upserted here.
    Re-uploading the same assessment year updates the existing row. The original
    PDF is NOT stored. Rather than exploding every field into its own column, the
    whole normalized Form 16 is kept as a JSON blob (`data`), with the full raw
    OCR response in `rawOcr` so fields can be re-mapped later without re-uploading.
    Only `userId` + `assessmentYear` are real columns — they form the upsert key.
    """

    __tablename__ = "form16_imports"
    __table_args__ = (
        # One row per employer per assessment year (a taxpayer can have several
        # employers in a year → several Form 16s for the same AY).
        UniqueConstraint(
            "userId", "assessmentYear", "employerTan", name="uq_form16_user_ay_tan"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updatedAt = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    userId = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessmentYear = Column(String, nullable=False)  # e.g. "2025-26"
    employerTan = Column(String, nullable=True)  # deductor TAN — part of the upsert key

    data = Column(JSONB, nullable=False)  # normalized Form 16 fields (Form16Data)
    rawOcr = Column(JSONB, nullable=True)  # full raw OCR response for re-mapping

    user = relationship("User", back_populates="form16_imports")

    def __repr__(self):
        return (
            f"<Form16Import id={self.id} userId={self.userId} "
            f"ay={self.assessmentYear} tan={self.employerTan}>"
        )


class FinancialYear(Base):
    """SRS Module 5 storage, seeded on business creation (financial_years)."""

    __tablename__ = "financial_years"

    id = Column(Integer, primary_key=True, autoincrement=True)
    createdAt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    businessId = Column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label = Column(String, nullable=False)  # e.g. "2026-2027"
    startDate = Column(String, nullable=False)  # ISO date (YYYY-MM-DD)
    endDate = Column(String, nullable=False)
    isClosed = Column(Boolean, nullable=False, server_default="false")

    business = relationship("Business", back_populates="financial_years")

    def __repr__(self):
        return f"<FinancialYear id={self.id} label={self.label}>"
