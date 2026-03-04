from aq_common.time_utils import parse_fhmz_datetime


def test_parse_fhmz_datetime_converts_to_utc():
    # 2.3.2026 19h in Sarajevo (CET, UTC+1) should be 18:00 UTC.
    dt = parse_fhmz_datetime("2.3.2026. u 19 h")
    assert dt is not None
    assert dt.hour == 18
    assert dt.minute == 0

