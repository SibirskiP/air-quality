from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso_utc(ts: str) -> datetime:
    value = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_fhmz_datetime(text: str) -> datetime | None:
    pattern = r"(\d{1,2})\.(\d{1,2})\.(\d{4})\.\s*u\s*(\d{1,2})"
    match = re.search(pattern, text)
    if not match:
        return None
    day, month, year, hour = match.groups()
    local_dt = datetime(
        int(year),
        int(month),
        int(day),
        int(hour),
        0,
        0,
        tzinfo=ZoneInfo("Europe/Sarajevo"),
    )
    return local_dt.astimezone(timezone.utc)
