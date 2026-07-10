from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.form16.normalize import normalize_ocr_response
from app.core import ocr
from app.models import Form16Import, User


class Form16Service:
    @classmethod
    async def parse_only(
        cls,
        *,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> dict:
        """
        Proxy the PDF to the OCR service and normalize it. Does NOT persist —
        the result is returned for the user to review before saving. Shape:
        `{"data": <normalized>, "rawOcr": <raw OCR response>}`.
        """
        try:
            raw = await ocr.parse_form16_pdf(file_bytes, filename, content_type)
        except ocr.OcrError as exc:
            # OCR unreachable / timeout / upstream error → 502 with a clear message.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
            ) from exc

        normalized = normalize_ocr_response(raw, filename)
        # Fall back to "unknown" when the parser couldn't read the AY, and reflect
        # it back into the data (the AY is the eventual upsert key on save).
        normalized["assessmentYear"] = normalized.get("assessmentYear") or "unknown"
        return {"data": normalized, "rawOcr": raw}

    @classmethod
    async def save(
        cls,
        db: AsyncSession,
        user: User,
        *,
        data: dict,
        raw_ocr: Optional[dict],
    ) -> Form16Import:
        """
        Upsert a reviewed Form 16 under (user, assessment year, employer TAN).
        Re-submitting the same employer's form for the same year overwrites it;
        a different employer for the same year creates a new record.
        """
        assessment_year = data.get("assessmentYear") or "unknown"
        employer_tan = data.get("employerTan") or None
        data = {**data, "assessmentYear": assessment_year}

        record = await cls._get_by_ay_tan(db, user, assessment_year, employer_tan)
        if record is None:
            record = Form16Import(
                userId=user.id,
                assessmentYear=assessment_year,
                employerTan=employer_tan,
                data=data,
                rawOcr=raw_ocr,
            )
            db.add(record)
        else:
            record.data = data
            record.rawOcr = raw_ocr

        await db.commit()
        await db.refresh(record)
        return record

    @classmethod
    async def _get_by_ay_tan(
        cls,
        db: AsyncSession,
        user: User,
        assessment_year: str,
        employer_tan: Optional[str],
    ) -> Optional[Form16Import]:
        conditions = [
            Form16Import.userId == user.id,
            Form16Import.assessmentYear == assessment_year,
        ]
        if employer_tan is None:
            conditions.append(Form16Import.employerTan.is_(None))
        else:
            conditions.append(Form16Import.employerTan == employer_tan)
        result = await db.execute(select(Form16Import).where(*conditions))
        return result.scalars().first()

    @classmethod
    async def list_imports(cls, db: AsyncSession, user: User) -> List[Form16Import]:
        result = await db.execute(
            select(Form16Import)
            .where(Form16Import.userId == user.id)
            .order_by(Form16Import.assessmentYear.desc(), Form16Import.updatedAt.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_import(cls, db: AsyncSession, user: User, form16_id: int) -> Form16Import:
        result = await db.execute(
            select(Form16Import).where(
                Form16Import.id == form16_id, Form16Import.userId == user.id
            )
        )
        record = result.scalars().first()
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Form 16 not found."
            )
        return record

    @classmethod
    async def delete_import(cls, db: AsyncSession, user: User, form16_id: int) -> None:
        record = await cls.get_import(db, user, form16_id)
        await db.delete(record)
        await db.commit()
