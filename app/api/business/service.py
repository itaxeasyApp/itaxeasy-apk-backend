from datetime import date, timedelta
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Business,
    BusinessSettings,
    BusinessStatus,
    FinancialYear,
    User,
)


def compute_current_fy(fy_start_month: int) -> tuple[str, str, str]:
    """Return (label, startDate, endDate) for the FY containing today."""
    today = date.today()
    start_year = today.year if today.month >= fy_start_month else today.year - 1
    start = date(start_year, fy_start_month, 1)
    end = date(start_year + 1, fy_start_month, 1) - timedelta(days=1)
    label = f"{start_year}-{start_year + 1}"
    return label, start.isoformat(), end.isoformat()


def _validate_for_active(name: Optional[str], pan: Optional[str], state: Optional[str]) -> None:
    """SRS Module 3: an ACTIVE business needs Business Name, PAN and State."""
    missing = []
    if not (name and name.strip()):
        missing.append("Business Name")
    if not (pan and pan.strip()):
        missing.append("PAN")
    if not (state and state.strip()):
        missing.append("State")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"To activate a business, please provide: {', '.join(missing)}.",
        )


class BusinessService:
    @classmethod
    async def list_businesses(cls, db: AsyncSession, user: User) -> List[Business]:
        result = await db.execute(
            select(Business)
            .where(Business.userId == user.id)
            .options(
                selectinload(Business.financial_years),
                selectinload(Business.settings),
            )
            .order_by(Business.createdAt.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_business(cls, db: AsyncSession, user: User, business_id: int) -> Business:
        result = await db.execute(
            select(Business)
            .where(Business.id == business_id, Business.userId == user.id)
            .options(
                selectinload(Business.financial_years),
                selectinload(Business.settings),
            )
        )
        business = result.scalars().first()
        if business is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Business not found."
            )
        return business

    @classmethod
    async def create_business(cls, db: AsyncSession, user: User, data) -> Business:
        if data.status == BusinessStatus.active:
            _validate_for_active(data.name, data.pan, data.stateCode)

        business = Business(
            userId=user.id,
            name=data.name.strip(),
            pan=data.pan,
            gstin=data.gstin,
            stateCode=data.stateCode,
            address=data.address,
            city=data.city,
            pincode=data.pincode,
            country=data.country or "India",
            currency=data.currency or "INR",
            fyStartMonth=data.fyStartMonth or 4,
            status=data.status,
        )
        db.add(business)
        await db.flush()  # assign id

        # System action (SRS Module 3 → Module 5): seed the current financial year.
        label, start_date, end_date = compute_current_fy(business.fyStartMonth)
        db.add(
            FinancialYear(
                businessId=business.id,
                label=label,
                startDate=start_date,
                endDate=end_date,
            )
        )

        # System action (SRS Module 3 → Module 4): "Create Default Business
        # Configuration". GST defaults ON if a GSTIN was supplied; the rest off.
        db.add(
            BusinessSettings(
                businessId=business.id,
                inventoryEnabled=False,
                gstRegistered=bool(business.gstin and business.gstin.strip()),
                multiBranch=False,
                manufacturing=False,
            )
        )

        await db.commit()
        return await cls.get_business(db, user, business.id)

    @classmethod
    async def update_business(
        cls, db: AsyncSession, user: User, business_id: int, data
    ) -> Business:
        business = await cls.get_business(db, user, business_id)

        # Compute the post-update values to validate activation correctly.
        new_name = data.name if data.name is not None else business.name
        new_pan = data.pan if data.pan is not None else business.pan
        new_state = data.stateCode if data.stateCode is not None else business.stateCode
        new_status = data.status if data.status is not None else business.status
        if new_status == BusinessStatus.active:
            _validate_for_active(new_name, new_pan, new_state)

        for field in (
            "name", "pan", "gstin", "stateCode",
            "address", "city", "pincode",
            "country", "currency", "fyStartMonth", "status",
        ):
            value = getattr(data, field)
            if value is not None:
                setattr(business, field, value.strip() if field == "name" else value)

        await db.commit()
        return await cls.get_business(db, user, business.id)

    # ── SRS Module 4 — Business Configuration ──────────────────────────────
    @classmethod
    async def _get_or_create_settings(
        cls, db: AsyncSession, business: Business
    ) -> BusinessSettings:
        """Return the business's settings row, creating a default if missing
        (covers businesses created before Module 4 existed)."""
        if business.settings is not None:
            return business.settings
        settings = BusinessSettings(
            businessId=business.id,
            inventoryEnabled=False,
            gstRegistered=bool(business.gstin and business.gstin.strip()),
            multiBranch=False,
            manufacturing=False,
        )
        db.add(settings)
        await db.flush()
        return settings

    @classmethod
    async def get_settings(
        cls, db: AsyncSession, user: User, business_id: int
    ) -> BusinessSettings:
        business = await cls.get_business(db, user, business_id)
        settings = await cls._get_or_create_settings(db, business)
        await db.commit()
        return settings

    @classmethod
    async def update_settings(
        cls, db: AsyncSession, user: User, business_id: int, data
    ) -> BusinessSettings:
        business = await cls.get_business(db, user, business_id)
        settings = await cls._get_or_create_settings(db, business)

        for field in ("inventoryEnabled", "gstRegistered", "multiBranch", "manufacturing"):
            value = getattr(data, field)
            if value is not None:
                setattr(settings, field, value)

        # SRS Module 4 rule: Manufacturing requires Inventory = YES.
        if settings.manufacturing and not settings.inventoryEnabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manufacturing can only be enabled when Inventory is enabled.",
            )

        await db.commit()
        await db.refresh(settings)
        return settings
