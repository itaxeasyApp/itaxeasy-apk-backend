"""
MSG91 OTP integration (https://control.msg91.com).

Uses the dedicated OTP product at /api/v5/otp: MSG91 generates, delivers and stores
the code, so this process never holds it. MSG91_TEMPLATE_ID must therefore name a
template from the panel's **SendOTP -> Templates** section, NOT SMS -> Templates —
the two products keep separate template registries and an SMS template id handed to
the OTP endpoint is rejected as "Invalid Template".

An earlier version of this docstring described a local OTP cache delivered over the
v5 Flow API. That is not what the code below does, and believing it costs real
debugging time. Anything claimed here must be true of the functions underneath.

A caution that shapes the error handling: this endpoint answers {"type": "success"}
with a request_id even when it has rejected the request outright — verified against a
deliberately invalid authkey, and against templates the panel simultaneously recorded
as 400s in its API Failed Logs. A 200 from send_otp() therefore means "MSG91 accepted
the HTTP call", never "the SMS is on its way". Genuine delivery can only be confirmed
from the delivery report (see delivery_status) or the panel's OTP logs.
"""
import datetime as _dt
import time as _time

import httpx

from app.core.config import settings



class Msg91Error(Exception):
    """Raised when MSG91 returns an error (bad config, etc.)."""


def normalize_mobile(phone: str) -> str:
    """
    Convert any Indian phone input to MSG91's expected `91XXXXXXXXXX` form
    (country code, no '+'). Accepts '+91 98765 43210', '9876543210', etc.
    """
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if len(digits) > 10 and digits.startswith("91"):
        return digits
    return "91" + digits[-10:]


def _require_config() -> None:
    if not settings.MSG91_AUTH_KEY:
        raise Msg91Error(
            "MSG91 is not configured on the server "
            "(MSG91_AUTH_KEY missing)."
        )
    # A blank template id is NOT a usable default. India's DLT regime requires a
    # registered template on every message, so MSG91 pauses a template-less send with
    # error 211 ("Template Id Missing") and never delivers it — while still answering
    # the API call with {"type": "success"}. Refusing here turns weeks of silent
    # non-delivery into an immediate, readable 502 on the very first request.
    if not settings.MSG91_TEMPLATE_ID:
        raise Msg91Error(
            "MSG91 is not configured on the server (MSG91_TEMPLATE_ID missing). "
            "Set it to a DLT-registered template from the panel's SendOTP section."
        )


def _check_response(resp: httpx.Response, fallback: str) -> dict:
    """MSG91 OTP API returns 200 with {"type": "success"|"error", "message": ...}."""
    try:
        data = resp.json()
    except ValueError:
        raise Msg91Error(f"{fallback} (unexpected response: {resp.text[:200]})")
    if isinstance(data, dict) and data.get("type") == "success":
        return data
    message = data.get("message") if isinstance(data, dict) else None
    raise Msg91Error(str(message or fallback))


async def send_otp(phone: str) -> str:
    """Send an OTP via MSG91's dedicated SendOTP API."""
    _require_config()
    mobile = normalize_mobile(phone)

    # Build query parameters. template_id is unconditional — _require_config has
    # already guaranteed it is set, because there is no global fallback template to
    # degrade to (an earlier comment here claimed otherwise; it was wrong, and that
    # claim is why the field sat commented out in .env while nothing was delivered).
    params = {
        "mobile": mobile,
        "authkey": settings.MSG91_AUTH_KEY,
        "otp_length": settings.MSG91_OTP_LENGTH,
        "expiry": settings.MSG91_OTP_EXPIRY_MINUTES,
        "template_id": settings.MSG91_TEMPLATE_ID,
    }

    # Optional 6-char DLT header. Blank falls back to the header bound to the
    # template, which is the usual case.
    if settings.MSG91_SENDER_ID:
        params["sender"] = settings.MSG91_SENDER_ID

    url = f"{settings.MSG91_BASE_URL}/otp"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, params=params)

    data = _check_response(resp, "Could not send OTP. Please try again.")
    # Return the request ID from MSG91
    return str(data.get("request_id", ""))


async def verify_otp(phone: str, otp: str) -> None:
    """Verify the OTP using MSG91's verify API."""
    _require_config()
    mobile = normalize_mobile(phone)

    params = {
        "mobile": mobile,
        "otp": otp,
        "authkey": settings.MSG91_AUTH_KEY,
    }

    url = f"{settings.MSG91_BASE_URL}/otp/verify"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)

    # MSG91 returns type="success" on successful verification, or type="error" with "message"
    _check_response(resp, "Invalid or expired OTP. Please try again.")


async def resend_otp(phone: str, channel: str = "text") -> None:
    """Resend a fresh OTP via MSG91's retry API."""
    _require_config()
    mobile = normalize_mobile(phone)

    params = {
        "mobile": mobile,
        "authkey": settings.MSG91_AUTH_KEY,
        "retrytype": "voice" if channel == "voice" else "text",
    }

    url = f"{settings.MSG91_BASE_URL}/otp/retry"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)

    _check_response(resp, "Could not resend OTP. Please try again.")


# --------------------------------------------------------------------------- #
# SendOTP Widget — the route that actually delivers.
#
# send_otp() above talks to /api/v5/otp, which sends under OUR DLT header and is
# therefore paused by the operators with error 211 until the Entity/PE ID is mapped
# to `quarki` in the MSG91 panel. The widget sends under MSG91's own registered
# entity, so it works today. Verified end to end: three sends to a real handset all
# arrived, while seven through /api/v5/otp never left `Pending`.
#
# Unlike /api/v5/otp, this endpoint can be trusted when it says success — a disabled
# token gets a real 401 AuthenticationFailure rather than a cheerful {"type":
# "success"}, which is what makes error handling here meaningful at all.
# --------------------------------------------------------------------------- #

# reqId returned by the widget on send, needed again on verify. Bill-Shill's client
# posts {phone, otp} and never sees a reqId, so the mapping is held here rather than
# widening the app's API contract. In-process and single-instance by design: a reqId
# is worthless after MSG91's 15-minute expiry, so losing the map on restart costs a
# user one "request a new OTP", not a broken account. If this backend is ever scaled
# past one pm2 instance, move it to Redis or have the client echo the reqId back.
_WIDGET_REQUESTS: dict[str, tuple[str, float]] = {}
_WIDGET_REQ_TTL_SECONDS = 15 * 60


def _require_widget_config() -> None:
    if not settings.widget_configured:
        raise Msg91Error(
            "MSG91 widget is not configured on the server "
            "(MSG91_WIDGET_ID / MSG91_WIDGET_TOKEN missing)."
        )


def _widget_check(resp: httpx.Response) -> str:
    """
    Widget responses carry the payload in `message`: a reqId on send, an access
    token on verify, and the human-readable reason on failure.
    """
    try:
        data = resp.json()
    except ValueError:
        raise Msg91Error(f"Unexpected response from MSG91 ({resp.text[:200]})")

    if not isinstance(data, dict):
        raise Msg91Error(f"Unexpected response from MSG91 ({resp.text[:200]})")

    if data.get("type") == "success" and not data.get("hasError"):
        return str(data.get("message", ""))

    # e.g. "Web requests are not allowed for this widget." when the widget is set to
    # Mobile-only, or "AuthenticationFailure" on a disabled token.
    raise Msg91Error(str(data.get("message") or "Could not complete the OTP request."))


def _remember_request(mobile: str, req_id: str) -> None:
    now = _time.monotonic()
    # Opportunistic sweep — this map only ever holds in-flight logins.
    for key, (_, expires) in list(_WIDGET_REQUESTS.items()):
        if expires <= now:
            _WIDGET_REQUESTS.pop(key, None)
    _WIDGET_REQUESTS[mobile] = (req_id, now + _WIDGET_REQ_TTL_SECONDS)


def _recall_request(mobile: str) -> str | None:
    entry = _WIDGET_REQUESTS.get(mobile)
    if not entry:
        return None
    req_id, expires = entry
    if expires <= _time.monotonic():
        _WIDGET_REQUESTS.pop(mobile, None)
        return None
    return req_id


async def send_widget_otp(phone: str) -> str:
    """Send an OTP through the SendOTP widget. Returns MSG91's reqId."""
    _require_widget_config()
    mobile = normalize_mobile(phone)

    payload = {
        "widgetId": settings.MSG91_WIDGET_ID,
        "tokenAuth": settings.MSG91_WIDGET_TOKEN,
        "identifier": mobile,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://control.msg91.com/api/v5/widget/sendOtp",
            headers={"Content-Type": "application/json"},
            json=payload,
        )

    req_id = _widget_check(resp)
    _remember_request(mobile, req_id)
    return req_id


async def verify_widget_otp(phone: str, otp: str) -> None:
    """
    Check `otp` against the widget request opened by send_widget_otp for this phone.

    Raises Msg91Error on a wrong or expired code, or when no send is on record — the
    caller turns any of these into "request a new OTP", which is the right advice in
    every one of those cases.
    """
    _require_widget_config()
    mobile = normalize_mobile(phone)

    req_id = _recall_request(mobile)
    if not req_id:
        raise Msg91Error("No OTP request is active for this number.")

    payload = {
        "widgetId": settings.MSG91_WIDGET_ID,
        "tokenAuth": settings.MSG91_WIDGET_TOKEN,
        "reqId": req_id,
        "otp": otp,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://control.msg91.com/api/v5/widget/verifyOtp",
            headers={"Content-Type": "application/json"},
            json=payload,
        )

    _widget_check(resp)
    # Single-use: a verified code must not open a second session.
    _WIDGET_REQUESTS.pop(mobile, None)


async def delivery_status(phone: str, days: int = 1) -> list[dict]:
    """
    Recent OTP delivery rows for `phone`, newest first, straight from MSG91's report.

    This is the only honest answer to "did the SMS actually go out". send_otp() cannot
    tell you — see the module docstring — so when a user reports never receiving a
    code, ask here instead of trusting the send call's 200.

    Rows worth reading: `status` ("Pending" means queued and NOT delivered),
    `pauseReason` (e.g. "code: 211" = template id missing, or the DLT entity is not
    mapped to the header in the MSG91 panel), `credit` (None = nothing was ever
    charged, so nothing was ever carried) and `DLT_TE_ID` (the DLT template id, None
    when the template is unregistered).

    Returns [] rather than raising when the report is empty or unavailable: this is a
    diagnostic, and it must never be the reason a login request fails. Note the report
    lags sends by several minutes, so an empty list shortly after a send is not proof
    of anything.
    """
    _require_config()
    mobile = normalize_mobile(phone)

    # MSG91 rejects windows wider than 3 days ("Duration exceeds, allowed limit is 3").
    end = _dt.datetime.now(_dt.timezone.utc).date()
    start = end - _dt.timedelta(days=min(max(days, 1), 3) - 1)

    payload = {
        "page": 1,
        "pageSize": 50,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.MSG91_BASE_URL}/report/logs/p/otp",
                headers={
                    "authkey": settings.MSG91_AUTH_KEY,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        rows = resp.json().get("data") or []
    except (httpx.HTTPError, ValueError, AttributeError):
        return []

    return [r for r in rows if isinstance(r, dict) and str(r.get("telNum")) == mobile]


async def verify_widget_token(access_token: str) -> str:
    """
    Verify the MSG91 SendOTP Widget access token and return the verified mobile number.
    """
    _require_config()

    headers = {
        "Content-Type": "application/json",
        "authkey": settings.MSG91_AUTH_KEY,
    }

    payload = {
        "authkey": settings.MSG91_AUTH_KEY,
        "access-token": access_token,
    }

    url = "https://control.msg91.com/api/v5/widget/verifyAccessToken"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code != 200:
        raise Msg91Error(
            f"MSG91 verification returned status code {resp.status_code}: {resp.text[:200]}"
        )

    try:
        data = resp.json()
    except ValueError:
        raise Msg91Error(f"Invalid JSON response from MSG91: {resp.text[:200]}")

    if isinstance(data, dict):
        if data.get("type") == "error":
            message = data.get("message", "Token verification failed")
            raise Msg91Error(str(message))

        # Extract mobile number from response (can be in data.mobile, data.data.mobile, etc.)
        mobile = None
        inner_data = data.get("data")
        if isinstance(inner_data, dict):
            mobile = inner_data.get("mobile") or inner_data.get("phone")
        elif isinstance(inner_data, str) and inner_data.isdigit():
            mobile = inner_data

        if not mobile:
            mobile = data.get("mobile") or data.get("phone")

        if mobile:
            return str(mobile)

        # Success fallback scan
        if data.get("type") == "success" or data.get("status") == "success":
            import re
            numbers = re.findall(r"\b\d{10,12}\b", resp.text)
            if numbers:
                return numbers[0]

        raise Msg91Error(
            f"Could not extract verified mobile number from MSG91 response: {resp.text[:200]}"
        )
    else:
        raise Msg91Error(
            f"Unexpected response format from MSG91: {resp.text[:200]}"
        )


