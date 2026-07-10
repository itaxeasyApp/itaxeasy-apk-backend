"""
Thin client for the standalone OCR service (the `OCR-` FastAPI app).

Form 16 extraction (YOLO + Tesseract + form16-parser) is intentionally kept out
of this process — we just proxy the uploaded PDF to `${OCR_BASE_URL}/api/parse_form16`
and hand the raw JSON back to the caller to normalize.
"""
import httpx

from app.core.config import settings


class OcrError(Exception):
    """Raised when the OCR service is unreachable, times out, or errors."""


def _extract_error(resp: httpx.Response) -> str | None:
    try:
        data = resp.json()
    except ValueError:
        return resp.text[:200] or None
    if isinstance(data, str):
        return data[:200]
    if isinstance(data, dict):
        for key in ("detail", "message", "error"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


async def parse_form16_pdf(
    file_bytes: bytes,
    filename: str,
    content_type: str = "application/pdf",
) -> dict:
    """POST the PDF to the OCR service's parse_form16 endpoint and return its JSON."""
    url = f"{settings.OCR_BASE_URL.rstrip('/')}/api/parse_form16"
    headers = {}
    if settings.OCR_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.OCR_API_TOKEN}"

    files = {"file": (filename, file_bytes, content_type)}

    try:
        async with httpx.AsyncClient(timeout=settings.OCR_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, files=files, headers=headers)
    except httpx.TimeoutException as exc:
        raise OcrError(
            "The OCR service timed out while reading the Form 16 PDF. Please try again."
        ) from exc
    except httpx.HTTPError as exc:
        raise OcrError(f"Could not reach the OCR service: {exc}") from exc

    if resp.status_code >= 400:
        detail = _extract_error(resp)
        raise OcrError(detail or f"OCR service returned HTTP {resp.status_code}.")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise OcrError("OCR service returned a non-JSON response.") from exc

    if not isinstance(payload, (dict, list)):
        raise OcrError("OCR service returned an unexpected response shape.")
    return payload if isinstance(payload, dict) else {"data": payload}
