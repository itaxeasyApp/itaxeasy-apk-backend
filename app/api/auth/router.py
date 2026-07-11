from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.schemas import (
    OtpSendRequest,
    OtpVerifyRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from app.api.auth.service import AuthService
from app.api.deps import get_current_user
from app.core import msg91
from app.core.config import settings
from app.core.database import get_db
from app.models import User

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/otp/send", status_code=status.HTTP_200_OK)
async def otp_send(payload: OtpSendRequest):
    """Have MSG91 generate and SMS an OTP to the given phone number."""
    # Test bypass: don't hit MSG91, the fixed TEST_OTP_CODE will be accepted.
    if settings.is_test_phone(payload.phone):
        return {"success": True, "message": "Test OTP active (no SMS sent)."}
    try:
        await msg91.send_otp(payload.phone)
    except msg91.Msg91Error as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not send OTP: {exc}",
        )
    return {"success": True, "message": "OTP sent."}


@router.post("/otp/resend", status_code=status.HTTP_200_OK)
async def otp_resend(payload: OtpSendRequest):
    """Re-trigger delivery of the active OTP via MSG91."""
    try:
        await msg91.resend_otp(payload.phone)
    except msg91.Msg91Error as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not resend OTP: {exc}",
        )
    return {"success": True, "message": "OTP resent."}


@router.post("/otp/verify", response_model=TokenResponse)
async def otp_verify(
    payload: OtpVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify the OTP or MSG91 Widget Access Token, then register (first time)
    or log in the user and return our own access + refresh tokens.
    """
    verified_phone = None
    # Test bypass: a configured test phone + the fixed TEST_OTP_CODE logs in
    # without contacting MSG91 (used when DLT/SMS isn't available).
    if payload.phone and payload.otp and settings.is_test_phone(payload.phone):
        if payload.otp != settings.TEST_OTP_CODE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not verify. Please request a new OTP.",
            )
        verified_phone = payload.phone
    elif payload.accessToken:
        try:
            verified_phone = await msg91.verify_widget_token(payload.accessToken)
        except msg91.Msg91Error as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token verification failed: {exc}",
            )
    else:
        if not payload.phone or not payload.otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either accessToken or phone + otp must be provided.",
            )
        # MSG91's SMS OTP is single-use, so don't burn it on a request that
        # authenticate_with_phone will reject anyway: a brand-new phone must
        # register WITH a full name. Check that BEFORE consuming the code, so
        # the app can collect the name and retry verify with the SAME still
        # -valid OTP. (The check in authenticate_with_phone remains the
        # authoritative guard for the test-phone and widget-token paths.)
        existing = await AuthService.get_user_by_phone(
            db, "+" + msg91.normalize_mobile(payload.phone)
        )
        if existing is None and (
            not payload.fullName or len(payload.fullName.strip()) < 3
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Full name (min 3 characters) is required to register.",
            )
        try:
            await msg91.verify_otp(payload.phone, payload.otp)
            verified_phone = payload.phone
        except msg91.Msg91Error:
            # Wrong / expired code → 400 so the app shows "request a new OTP".
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not verify. Please request a new OTP.",
            )

    phone_e164 = "+" + msg91.normalize_mobile(verified_phone)
    user, access_token, refresh_token, is_new = await AuthService.authenticate_with_phone(
        db,
        phone=phone_e164,
        full_name=payload.fullName,
        email=payload.email,
        device_info=payload.deviceInfo,
        ip_address=_client_ip(request),
    )
    return TokenResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        isNewUser=is_new,
        user=user,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Rotate a refresh token for a fresh access + refresh token pair."""
    user, access_token, refresh_token = await AuthService.refresh_tokens(
        db,
        raw_refresh=payload.refreshToken,
        device_info=None,
        ip_address=_client_ip(request),
    )
    return TokenResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        user=user,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Revoke a refresh-token session (SRS Module 2: Logout)."""
    await AuthService.logout(db, payload.refreshToken)
    return {"success": True, "message": "Logged out."}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile (SRS Module 2)."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit the authenticated user's profile (SRS Module 2: Edit Profile)."""
    return await AuthService.update_profile(db, current_user, payload)
