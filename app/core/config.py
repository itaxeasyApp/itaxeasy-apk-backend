from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "itaxeasy-apk-backend"
    ENVIRONMENT: str = "local"

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/itaxeasy"

    # JWT (our own session tokens issued AFTER MSG91 verifies the phone OTP)
    JWT_SECRET: str = "supersecretjwtkeyforitaxeasyapkbackend"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 60  # 60 days

    # MSG91 OTP (https://control.msg91.com)
    # The backend proxies OTP send/verify to MSG91's OTP API; MSG91 generates,
    # delivers (DLT SMS) and stores the OTP, so we never hold the code ourselves.
    MSG91_AUTH_KEY: str = ""
    MSG91_TEMPLATE_ID: str = ""
    MSG91_SENDER_ID: str = ""  # optional 6-char DLT header (blank = template default)
    MSG91_OTP_EXPIRY_MINUTES: int = 5
    MSG91_OTP_LENGTH: int = 6
    MSG91_BASE_URL: str = "https://control.msg91.com/api/v5"

    # ------------------------------- OCR service ------------------------------ #
    # Form 16 extraction is delegated to the standalone OCR service (the `OCR-`
    # FastAPI app that runs YOLO + Tesseract + form16-parser). This backend
    # proxies the uploaded PDF to `${OCR_BASE_URL}/api/parse_form16`, normalizes
    # the response, and persists it — the heavy ML never runs in this process.
    OCR_BASE_URL: str = "https://ocr.itaxeasy.com"
    OCR_API_TOKEN: str = ""  # optional bearer for the OCR service (blank = none)
    OCR_TIMEOUT_SECONDS: float = 120.0  # parsing a scanned PDF can be slow

    # ----------------------------- Test OTP bypass ---------------------------- #
    # For testing without sending a real SMS (e.g. when DLT isn't set up). When
    # enabled, listed phones skip MSG91 entirely: /otp/send is a no-op and
    # /otp/verify accepts TEST_OTP_CODE. NEVER enable in production.
    TEST_OTP_ENABLED: bool = False
    TEST_OTP_CODE: str = "123456"
    # Comma-separated phones (E.164 "+919636286581" or bare "9636286581").
    TEST_PHONES: str = ""

    @property
    def test_phones_normalized(self) -> set[str]:
        """Test phones reduced to their last 10 digits for robust matching."""
        out: set[str] = set()
        for raw in self.TEST_PHONES.split(","):
            digits = "".join(c for c in raw if c.isdigit())
            if len(digits) >= 10:
                out.add(digits[-10:])
        return out

    def is_test_phone(self, phone: str) -> bool:
        if not self.TEST_OTP_ENABLED:
            return False
        digits = "".join(c for c in (phone or "") if c.isdigit())
        return len(digits) >= 10 and digits[-10:] in self.test_phones_normalized

    @property
    def is_local(self) -> bool:
        return self.ENVIRONMENT == "local"

    # Read .env file if it exists
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
