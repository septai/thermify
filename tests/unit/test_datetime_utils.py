from __future__ import annotations

from datetime import UTC, datetime

from domain.datetime_utils import _parse_iso8601_utc, _parse_utc_iso8601


def test_parse_iso8601_utc_normalizes_z_suffix_to_utc() -> None:
    parsed = _parse_iso8601_utc("2026-05-12T14:01:33.891Z")

    assert parsed == datetime(2026, 5, 12, 14, 1, 33, 891000, tzinfo=UTC)


def test_parse_utc_iso8601_formats_milliseconds_and_z_suffix() -> None:
    formatted = _parse_utc_iso8601(datetime(2026, 5, 12, 14, 1, 33, 891000, tzinfo=UTC))

    assert formatted == "2026-05-12T14:01:33.891Z"
