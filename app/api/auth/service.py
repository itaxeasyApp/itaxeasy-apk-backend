import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import OtpLog, User, UserSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuthService:
    # ------------------------------------------------------------------ #
    # Token helpers                                                       #
    # ------------------------------------------------------------------ #
    @staticmethod
    def create_access_token(user_id: int) -> str:
        payload = {
            "sub": str(user_id),
            "type": "access",
            "exp": _now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            "iat": _now(),
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def decode_access_token(token: str) -> Optional[int]:
        try:
            payload = jwt.decode(
                token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
            )
            if payload.get("type") != "access":
                return None
            user_id = payload.get("sub")
            return int(user_id) if user_id else None
        except (jwt.PyJWTError, ValueError):
            return None

    @staticmethod
    def _hash_refresh_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    async def _issue_session(
        cls,
        db: AsyncSession,
        user: User,
        device_info: Optional[str],
        ip_address: Optional[str],
    ) -> str:
        """Create a new refresh-token session row, return the RAW refresh token."""
        raw = secrets.token_urlsafe(48)
        session = UserSession(
            userId=user.id,
            refreshTokenHash=cls._hash_refresh_token(raw),
            deviceInfo=device_info,
            ipAddress=ip_address,
            expiresAt=_now() + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
            revoked=False,
        )
        db.add(session)
        return raw

    # ------------------------------------------------------------------ #
    # Lookups                                                            #
    # ------------------------------------------------------------------ #
    @classmethod
    async def get_user_by_id(cls, db: AsyncSession, user_id: int) -> Optional[User]:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    @classmethod
    async def get_user_by_phone(cls, db: AsyncSession, phone: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.phone == phone))
        return result.scalars().first()

    # ------------------------------------------------------------------ #
    # Phone OTP login / registration (SRS Module 1: Send/Verify OTP)      #
    # ------------------------------------------------------------------ #
    @classmethod
    async def authenticate_with_phone(
        cls,
        db: AsyncSession,
        phone: str,
        full_name: Optional[str],
        email: Optional[str],
        device_info: Optional[str],
        ip_address: Optional[str],
    ) -> Tuple[User, str, str, bool]:
        """
        Register-or-login a user whose phone OTP has just been verified by MSG91.

        The caller (router) must have already confirmed the OTP with MSG91 before
        invoking this — reaching here means the phone number is trusted.

        Returns (user, access_token, raw_refresh_token, is_new_user).
        """
        is_new_user = False
        user = await cls.get_user_by_phone(db, phone)

        if user is None:
            # First-time registration — full name is required (SRS: min 3 chars)
            if not full_name or len(full_name.strip()) < 3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Full name (min 3 characters) is required to register.",
                )
            user = User(
                phone=phone,
                email=email,
                fullName=full_name.strip(),
                verified=True,
            )
            db.add(user)
            await db.flush()  # assign user.id before creating dependent rows
            is_new_user = True

        # Audit log of this verification (otp_logs)
        db.add(
            OtpLog(
                userId=user.id,
                phone=phone,
                ipAddress=ip_address,
                purpose="register" if is_new_user else "login",
            )
        )

        raw_refresh = await cls._issue_session(db, user, device_info, ip_address)
        await db.commit()
        await db.refresh(user)

        access_token = cls.create_access_token(user.id)
        return user, access_token, raw_refresh, is_new_user

    # ------------------------------------------------------------------ #
    # Refresh / logout                                                  #
    # ------------------------------------------------------------------ #
    @classmethod
    async def _get_active_session(
        cls, db: AsyncSession, raw_refresh: str
    ) -> Optional[UserSession]:
        token_hash = cls._hash_refresh_token(raw_refresh)
        result = await db.execute(
            select(UserSession).where(UserSession.refreshTokenHash == token_hash)
        )
        session = result.scalars().first()
        if session is None or session.revoked:
            return None
        expires_at = session.expiresAt
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < _now():
            return None
        return session

    @classmethod
    async def refresh_tokens(
        cls,
        db: AsyncSession,
        raw_refresh: str,
        device_info: Optional[str],
        ip_address: Optional[str],
    ) -> Tuple[User, str, str]:
        session = await cls._get_active_session(db, raw_refresh)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token. Please sign in again.",
            )

        user = await cls.get_user_by_id(db, session.userId)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists."
            )

        # Rotate: revoke the used token, issue a fresh one
        session.revoked = True
        new_refresh = await cls._issue_session(db, user, device_info, ip_address)
        await db.commit()

        access_token = cls.create_access_token(user.id)
        return user, access_token, new_refresh

    @classmethod
    async def logout(cls, db: AsyncSession, raw_refresh: str) -> None:
        session = await cls._get_active_session(db, raw_refresh)
        if session is not None:
            session.revoked = True
            await db.commit()

    # ------------------------------------------------------------------ #
    # Profile (SRS Module 2)                                             #
    # ------------------------------------------------------------------ #
    @classmethod
    async def update_profile(cls, db: AsyncSession, user: User, data) -> User:
        if data.email is not None and data.email != user.email:
            existing = await db.execute(
                select(User).where(User.email == data.email, User.id != user.id)
            )
            if existing.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email address already in use.",
                )

        for field in (
            "fullName",
            "email",
            "profilePhoto",
            "timeZone",
            "language",
            "gender",
            "panNumber",
            "aadhaarNumber",
            "fatherName",
            "dob",
            "address",
        ):
            value = getattr(data, field)
            if value is not None:
                setattr(user, field, value)

        await db.commit()
        await db.refresh(user)
        return user
