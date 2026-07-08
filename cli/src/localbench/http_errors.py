from __future__ import annotations

import json

import httpx


def raise_for_status_with_body(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        detail = response_error_detail(response)
        if not detail:
            raise
        raise httpx.HTTPStatusError(
            f"{error} ({detail})",
            request=error.request,
            response=error.response,
        ) from error


def response_error_detail(response: httpx.Response) -> str:
    payload = _json_object(response)
    if payload:
        code = _text(payload.get("code"))
        message = _text(payload.get("message")) or _text(payload.get("error")) or _text(payload.get("detail"))
        if code and message:
            return f"{code}: {message}"
        return code or message or _json_summary(payload)
    text = response.text.strip()
    return text[:500]


def _json_object(response: httpx.Response) -> dict[str, object]:
    try:
        parsed = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _json_summary(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))[:500]
