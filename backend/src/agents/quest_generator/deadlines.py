"""Quest deadline helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_TIMEZONE = timezone(timedelta(hours=9))
DEFAULT_SURPRISE_DURATION_MINUTES = 120
MIN_SURPRISE_DURATION_MINUTES = 1
MAX_SURPRISE_DURATION_MINUTES = 24 * 60


def coerce_surprise_duration_minutes(value: object) -> int:
    """돌발 퀘스트 제한 시간을 안전한 분 단위 정수로 바꿉니다.

    사용자가 문자열이나 너무 큰 값을 넣어도 서버가 정한 1분~24시간 범위 안으로 보정합니다.
    """
    if isinstance(value, bool):
        return DEFAULT_SURPRISE_DURATION_MINUTES
    if isinstance(value, int):
        minutes = value
    elif isinstance(value, str) and value.strip().isdecimal():
        minutes = int(value.strip())
    else:
        return DEFAULT_SURPRISE_DURATION_MINUTES
    return max(MIN_SURPRISE_DURATION_MINUTES, min(MAX_SURPRISE_DURATION_MINUTES, minutes))


def surprise_duration_minutes_from_payload(payload: dict[str, Any]) -> int:
    """요청 payload에서 돌발 퀘스트 제한 시간 옵션을 읽습니다.

    옵션이 없으면 기본값을 반환해서 기존 요청도 그대로 동작하게 합니다.
    """
    options = payload.get("quest_generation_options")
    if not isinstance(options, dict):
        return DEFAULT_SURPRISE_DURATION_MINUTES
    return coerce_surprise_duration_minutes(options.get("surprise_duration_minutes"))


def _next_midnight(generated_at: datetime) -> datetime:
    next_day = generated_at.date() + timedelta(days=1)
    return datetime.combine(next_day, datetime.min.time(), tzinfo=generated_at.tzinfo)


def _next_monday_midnight(generated_at: datetime) -> datetime:
    days_until_next_monday = (7 - generated_at.weekday()) % 7
    if days_until_next_monday == 0:
        days_until_next_monday = 7
    target_day = generated_at.date() + timedelta(days=days_until_next_monday)
    return datetime.combine(target_day, datetime.min.time(), tzinfo=generated_at.tzinfo)


def quest_deadline(
    quest_type: str,
    generated_at: datetime | None = None,
    timezone_name: str = "Asia/Seoul",
    surprise_duration_minutes: int | str | None = None,
) -> tuple[str, str]:
    """퀘스트 타입에 맞는 생성 시각과 만료 시각을 ISO 문자열로 반환합니다.

    daily는 다음 자정, weekly는 다음 월요일 자정, surprise는 생성 시각 기준 제한 시간 뒤로 계산합니다.
    """
    generated = generated_at or datetime.now(DEFAULT_TIMEZONE)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=DEFAULT_TIMEZONE)
    else:
        generated = generated.astimezone(DEFAULT_TIMEZONE)

    if quest_type == "surprise":
        duration_minutes = coerce_surprise_duration_minutes(surprise_duration_minutes)
        expires_at = generated + timedelta(minutes=duration_minutes)
    elif quest_type == "weekly":
        expires_at = _next_monday_midnight(generated)
    else:
        expires_at = _next_midnight(generated)

    return generated.isoformat(timespec="seconds"), expires_at.isoformat(timespec="seconds")