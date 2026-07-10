from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.form16.schemas import (
    Form16ListItem,
    Form16ParseResult,
    Form16Record,
    Form16SaveRequest,
)
from app.api.form16.service import Form16Service
from app.core.database import get_db
from app.models import Form16Import, User

router = APIRouter()


def _is_pdf(file: UploadFile) -> bool:
    if (file.content_type or "").lower() == "application/pdf":
        return True
    return (file.filename or "").lower().endswith(".pdf")


def _to_list_item(record: Form16Import) -> Form16ListItem:
    data = record.data or {}
    return Form16ListItem(
        id=record.id,
        assessmentYear=record.assessmentYear,
        employerTan=record.employerTan,
        createdAt=record.createdAt,
        updatedAt=record.updatedAt,
        employerName=data.get("employerName"),
        employeePan=data.get("employeePan"),
        grossSalary=data.get("grossSalary") or 0,
        totalTaxDeducted=data.get("totalTaxDeducted") or 0,
        confidence=data.get("confidence") or "low",
    )


@router.post("/parse", response_model=Form16ParseResult)
async def parse_form16(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Upload an employer-issued Form 16 PDF and extract it via the OCR service.
    This does NOT save anything — it returns the extracted data for the user to
    review, then the app persists it by POSTing to `/api/form16`.
    """
    if not _is_pdf(file):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only the official Form 16 PDF is accepted (no images).",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    return await Form16Service.parse_only(
        file_bytes=file_bytes,
        filename=file.filename or "Form16.pdf",
        content_type=file.content_type or "application/pdf",
    )


@router.post("", response_model=Form16Record, status_code=status.HTTP_201_CREATED)
async def save_form16(
    payload: Form16SaveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Persist a reviewed Form 16 for the signed-in user (one record per assessment
    year — re-submitting the same year overwrites it).
    """
    return await Form16Service.save(
        db,
        current_user,
        data=payload.data.model_dump(),
        raw_ocr=payload.rawOcr,
    )


@router.get("", response_model=List[Form16ListItem])
async def list_form16(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the user's stored Form 16s (one per employer per assessment year)."""
    records = await Form16Service.list_imports(db, current_user)
    return [_to_list_item(r) for r in records]


@router.get("/{form16_id}", response_model=Form16Record)
async def get_form16(
    form16_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a stored Form 16 by id."""
    return await Form16Service.get_import(db, current_user, form16_id)


@router.delete("/{form16_id}", status_code=status.HTTP_200_OK)
async def delete_form16(
    form16_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a stored Form 16 by id."""
    await Form16Service.delete_import(db, current_user, form16_id)
    return {"success": True, "message": "Deleted."}
