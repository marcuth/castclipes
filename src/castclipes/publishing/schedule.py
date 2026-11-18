"""Fila de postagem: escolhe o próximo horário livre para agendar um corte."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..config import Settings


def _parse(value: str) -> time:
    hour, _, minute = value.strip().partition(":")
    return time(int(hour), int(minute or 0))


def day_times(settings: Settings) -> list[time]:
    """Horários do dia (hora local). Fixos em `publish_slots`, ou `max_publish_per_day`
    horários igualmente espaçados na janela (primeiro no início, último no fim)."""
    cap = max(1, settings.max_publish_per_day)
    if settings.publish_slots:
        return sorted({_parse(v) for v in settings.publish_slots})[:cap]
    start, end = _parse(settings.publish_window_start), _parse(settings.publish_window_end)
    a, b = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    if cap == 1 or b <= a:
        return [start]
    step = (b - a) / (cap - 1)
    return [time(*divmod(round(a + i * step), 60)) for i in range(cap)]


def slots_for_day(day: date, settings: Settings) -> list[datetime]:
    zone = ZoneInfo(settings.publish_timezone)
    return [datetime.combine(day, t, tzinfo=zone).astimezone(UTC) for t in day_times(settings)]


def next_slot(
    taken: Iterable[datetime], settings: Settings, now: datetime | None = None
) -> datetime | None:
    """Primeiro horário livre (UTC) com a antecedência mínima; None se a fila estiver cheia
    dentro de `publish_queue_days`."""
    now = now or datetime.now(UTC)
    earliest = now + timedelta(minutes=settings.publish_min_lead_minutes)
    busy = {t.astimezone(UTC).replace(second=0, microsecond=0) for t in taken}
    today = now.astimezone(ZoneInfo(settings.publish_timezone)).date()
    for offset in range(max(1, settings.publish_queue_days)):
        for slot in slots_for_day(today + timedelta(days=offset), settings):
            if slot >= earliest and slot not in busy:
                return slot
    return None
