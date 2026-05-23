"""Authentication services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl, urlsplit

from fastapi import HTTPException, Request, status

from ruzsite.logging_config import setup_logging
from ruzsite.schemas.auth import SessionData, TelegramAuthRequest, TelegramUser
from ruzsite.settings import get_settings

setup_logging()
logger = logging.getLogger(__name__)
SESSION_COOKIE_NAME = "ruz_session"


def _b64decode_urlsafe(value: str) -> bytes:
    """Decode URL-safe base64 with implicit padding."""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _b64encode_urlsafe(value: bytes) -> str:
    """Encode URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _telegram_secret_key(bot_token: str) -> bytes:
    """Build Telegram Mini App verification key from the bot token."""
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def _parse_init_data(init_data: str) -> dict[str, str]:
    """Parse raw Telegram Mini App init data into a dictionary."""
    parsed = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    if "hash" not in parsed:
        logger.warning("Telegram initData is missing hash")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram initData hash is missing.",
        )
    return parsed


def verify_telegram_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int,
    now: int | None = None,
) -> TelegramUser:
    """Verify Telegram Mini App init data and return the signed user."""
    logger.debug("Verifying Telegram initData")
    parsed = _parse_init_data(init_data)
    received_hash = parsed.pop("hash")
    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(parsed.items(), key=lambda item: item[0])
    )
    calculated_hash = hmac.new(
        _telegram_secret_key(bot_token),
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        logger.warning("Telegram initData signature verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram initData signature is invalid.",
        )

    auth_date_raw = parsed.get("auth_date")
    if auth_date_raw is None:
        logger.warning("Telegram initData is missing auth_date")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram initData auth_date is missing.",
        )

    auth_date = int(auth_date_raw)
    current_time = int(time.time()) if now is None else now
    if auth_date > current_time or current_time - auth_date > max_age_seconds:
        logger.warning("Telegram initData is expired or from the future")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram initData is expired. Try reloading page.",
        )

    user_raw = parsed.get("user")
    if user_raw is None:
        logger.warning("Telegram initData is missing user payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram initData user payload is missing.",
        )

    telegram_user = TelegramUser.model_validate_json(user_raw)
    logger.info("Telegram initData verified for user ID %s", telegram_user.id)
    return telegram_user


async def extract_init_data(request: Request) -> str:
    """Read Telegram init data from a JSON request body."""
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        logger.warning("Telegram auth request used unsupported content type")
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Telegram auth endpoint only accepts JSON requests.",
        )

    body = await request.body()
    if not body:
        logger.warning("Telegram auth request is missing initData")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram initData was not provided.",
        )

    logger.debug("Reading Telegram initData from JSON request body")
    payload = TelegramAuthRequest.model_validate_json(body)
    if payload.init_data:
        return payload.init_data
    logger.warning("Telegram auth JSON request had no initData field")
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Telegram initData was not provided.",
    )


def _expected_origin(request: Request) -> str:
    """Build the expected origin, trusting forwarded headers only from proxies."""
    settings = get_settings()
    client_host = request.client.host if request.client else None
    expected_host = request.url.netloc
    expected_scheme = request.url.scheme

    if client_host in settings.trusted_proxy_ips:
        forwarded_host = request.headers.get("x-forwarded-host")
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_host:
            expected_host = forwarded_host.split(",", maxsplit=1)[0].strip()
        if forwarded_proto:
            expected_scheme = forwarded_proto.split(",", maxsplit=1)[0].strip()

    return f"{expected_scheme}://{expected_host}"


def _validate_request_provenance(
    request: Request,
    *,
    require_origin: bool,
    detail: str,
    request_name: str,
) -> None:
    """Reject requests whose Origin or Referer does not match the expected origin."""
    expected_origin = _expected_origin(request)
    candidate_headers = ("origin",) if require_origin else ("origin", "referer")

    for header_name in candidate_headers:
        header_value = request.headers.get(header_name)
        if not header_value:
            continue

        header_parts = urlsplit(header_value)
        if not header_parts.scheme or not header_parts.netloc:
            logger.warning(
                "%s has malformed %s header %s",
                request_name,
                header_name.title(),
                header_value,
            )
            break

        actual_origin = f"{header_parts.scheme}://{header_parts.netloc}"
        if hmac.compare_digest(actual_origin, expected_origin):
            return

        logger.warning(
            "Rejected %s from %s header %s; expected %s",
            request_name,
            header_name.title(),
            actual_origin,
            expected_origin,
        )
        break

    missing_header = "Origin" if require_origin else "Origin/Referer"
    logger.warning("%s is missing a valid %s header", request_name, missing_header)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
    )


def validate_same_origin(request: Request) -> None:
    """Reject cross-site auth requests based on the Origin header."""
    _validate_request_provenance(
        request,
        require_origin=True,
        detail="Telegram auth request origin is invalid.",
        request_name="Telegram auth request",
    )


def validate_same_origin_or_referer(request: Request) -> None:
    """Reject cross-site form posts based on the Origin or Referer header."""
    _validate_request_provenance(
        request,
        require_origin=False,
        detail="Settings request origin is invalid.",
        request_name="Settings request",
    )


def encode_session(session_data: SessionData, *, secret: str) -> str:
    """Create a signed session cookie value."""
    logger.debug(
        "Encoding session cookie for Telegram user ID %s",
        session_data.telegram_user_id,
    )
    payload = json.dumps(
        session_data.model_dump(exclude_none=True),
        separators=(",", ":"),
    ).encode("utf-8")
    payload_b64 = _b64encode_urlsafe(payload)
    signature = hmac.new(
        secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    )
    return f"{payload_b64}.{_b64encode_urlsafe(signature.digest())}"


def decode_session(
    cookie_value: str,
    *,
    secret: str,
    max_age_seconds: int,
    now: int | None = None,
) -> SessionData:
    """Verify and decode a signed session cookie."""
    try:
        payload_b64, signature_b64 = cookie_value.split(".", maxsplit=1)
    except ValueError as exc:
        logger.warning("Session cookie format is invalid")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session cookie format is invalid.",
        ) from exc

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    actual_signature = _b64decode_urlsafe(signature_b64)
    if not hmac.compare_digest(expected_signature, actual_signature):
        logger.warning("Session cookie signature verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session cookie signature is invalid.",
        )

    payload = _b64decode_urlsafe(payload_b64)
    session_data = SessionData.model_validate_json(payload)
    current_time = int(time.time()) if now is None else now
    if current_time - session_data.issued_at > max_age_seconds:
        logger.warning(
            "Session cookie expired for Telegram user ID %s",
            session_data.telegram_user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session cookie is expired. Try reloading page.",
        )
    logger.debug(
        "Decoded valid session cookie for Telegram user ID %s",
        session_data.telegram_user_id,
    )
    return session_data
