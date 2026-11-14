from datetime import UTC, datetime, time, timedelta

from jaguar_xiv_missao.config import Settings
from jaguar_xiv_missao.publishing.schedule import day_times, next_slot, slots_for_day


def cfg(**kw):
    return Settings(_env_file=None, **kw)


def test_auto_slots_are_spread_over_window():
    s = cfg(max_publish_per_day=3, publish_window_start="09:00", publish_window_end="21:00")
    assert day_times(s) == [time(9), time(15), time(21)]


def test_explicit_slots_capped_by_max_per_day():
    s = cfg(max_publish_per_day=2, publish_slots="18:00,12:00,21:00")
    assert day_times(s) == [time(12), time(18)]


def test_next_slot_skips_taken_and_past_and_converts_timezone():
    s = cfg(max_publish_per_day=2, publish_slots="12:00,18:00", publish_min_lead_minutes=30)
    now = datetime(2026, 11, 14, 14, 0, tzinfo=UTC)  # 11:00 em Brasília
    first = next_slot([], s, now)
    assert first == datetime(2026, 11, 14, 15, 0, tzinfo=UTC)  # 12:00 BRT
    second = next_slot([first], s, now)
    assert second == datetime(2026, 11, 14, 21, 0, tzinfo=UTC)  # 18:00 BRT
    third = next_slot([first, second], s, now)
    assert third == datetime(2026, 11, 15, 15, 0, tzinfo=UTC)


def test_lead_time_and_full_queue():
    s = cfg(max_publish_per_day=1, publish_slots="12:00", publish_queue_days=1)
    now = datetime(2026, 11, 14, 14, 50, tzinfo=UTC)  # 11:50 BRT: 12:00 está a < 30 min
    assert next_slot([], s, now) is None
    assert slots_for_day(now.date(), s)[0] > now - timedelta(days=1)
