from datetime import datetime
import re
import unicodedata

from bs4 import BeautifulSoup

from aq_common.config_loader import load_cities
from aq_common.time_utils import now_utc, parse_fhmz_datetime


def normalize_text(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_value).strip().upper()


def parse_numeric(text: str) -> float | None:
    txt = text.replace(",", ".").strip()
    if not txt or txt in {"-", "N/A", "#"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", txt)
    if not match:
        return None
    return float(match.group(0))


def build_city_alias_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for c in load_cities():
        code = c["code"].upper()
        out[normalize_text(code)] = code
        out[normalize_text(c["name"])] = code
        for alias in c.get("aliases", []):
            out[normalize_text(alias)] = code
    return out


def parse_pollutants(cells) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    idx = 0
    paired = ["SO2", "NO2", "O3", "PM10", "PM2.5"]
    for pollutant in paired:
        if idx >= len(cells):
            values[pollutant] = None
            continue
        cell = cells[idx]
        text = cell.get_text(" ", strip=True).replace("\xa0", " ").strip()
        colspan = int(cell.get("colspan", "1"))
        if colspan >= 2 and parse_numeric(text) is None:
            values[pollutant] = None
            idx += 1
            continue
        values[pollutant] = parse_numeric(text)
        idx += 1
        if idx < len(cells):
            idx += 1
    values["CO"] = parse_numeric(cells[idx].get_text(" ", strip=True)) if idx < len(cells) else None
    idx += 1
    values["H2S"] = parse_numeric(cells[idx].get_text(" ", strip=True)) if idx < len(cells) else None
    return values


def parse_fhmz_rows(html: str) -> tuple[datetime, list[dict]]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    subtitle = soup.select_one(".subtitle")
    measured_at = None
    if subtitle:
        measured_at = parse_fhmz_datetime(subtitle.get_text(" ", strip=True))
    if measured_at is None:
        measured_at = now_utc().replace(minute=0, second=0, microsecond=0)

    tables = soup.find_all("table")
    target = None
    for table in tables:
        if "SATNE VRIJEDNOSTI POLUTANATA" in table.get_text(" ", strip=True).upper():
            target = table
            break
    if target is None:
        raise RuntimeError("FHMZ table not found, schema changed")

    alias_map = build_city_alias_map()
    rows: list[dict] = []
    current_city_code = None

    for tr in target.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue

        first_text = tds[0].get_text(" ", strip=True).replace("\xa0", " ").strip()
        first_norm = normalize_text(first_text)
        has_rowspan = tds[0].get("rowspan") is not None
        is_city_row = has_rowspan or first_norm in alias_map

        if is_city_row:
            current_city_code = alias_map.get(first_norm)
            station_index = 1
        else:
            looks_like_unknown_city = (
                len(tds) >= 2
                and tds[0].find("a") is None
                and first_text == first_text.upper()
                and first_norm not in alias_map
            )
            if looks_like_unknown_city:
                current_city_code = None
                continue
            station_index = 0

        if not current_city_code:
            continue
        if station_index >= len(tds):
            continue

        station_name = tds[station_index].get_text(" ", strip=True).replace("\xa0", " ").strip()
        if not station_name:
            continue

        station_norm = normalize_text(station_name)
        if station_norm in {"LOKACIJA", "AQI", "POCETNA", "KVALITET ZRAKA"}:
            continue

        after_station = tds[station_index + 1 :]
        if len(after_station) < 2:
            continue

        pollutant_cells = after_station[1:]
        values = parse_pollutants(pollutant_cells)
        rows.append(
            {
                "city_code": current_city_code,
                "station_name": station_name,
                "measured_at": measured_at,
                "values": values,
            }
        )

    return measured_at, rows