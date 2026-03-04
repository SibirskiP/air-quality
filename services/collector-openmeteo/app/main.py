from datetime import datetime, timezone
import logging
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from prometheus_client import Counter, Gauge, Histogram, start_http_server
import requests
from sqlalchemy import select

from aq_common.bootstrap import init_db, seed_base_data
from aq_common.config_loader import load_cities, load_collector_config
from aq_common.database import SessionLocal, engine, wait_for_database
from aq_common.models import City, CollectorRun, SourceEnum
from aq_common.repository import get_or_create_station, upsert_measurement
from aq_common.settings import settings
from aq_common.time_utils import now_utc
from aq_common.units import CONVERSION_MODE, to_canonical


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("collector-openmeteo")

COLLECTOR_RUNS = Counter("openmeteo_collector_runs_total", "Collector runs", ["status"])
COLLECTOR_ROWS = Counter("openmeteo_collector_rows_total", "Collector parsed rows")
COLLECTOR_DURATION = Histogram(
    "openmeteo_collector_duration_seconds",
    "Collector duration in seconds",
    buckets=(0.1, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 30),
)
COLLECTOR_LAST_SUCCESS = Gauge("openmeteo_last_success_timestamp", "Last success unix timestamp")


POLLUTANT_MAP = {
    "pm2_5": "PM2.5",
    "pm10": "PM10",
    "nitrogen_dioxide": "NO2",
    "sulphur_dioxide": "SO2",
    "ozone": "O3",
    "carbon_monoxide": "CO",
}


def parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def choose_current_hour_index(times: list[str]) -> int:
    if not times:
        return 0
    now = now_utc().replace(minute=0, second=0, microsecond=0)
    parsed = [parse_time(t) for t in times]
    # Prefer latest timestamp <= current hour. Fallback to closest timestamp.
    past_or_now = [i for i, t in enumerate(parsed) if t <= now]
    if past_or_now:
        return past_or_now[-1]
    closest_idx = min(range(len(parsed)), key=lambda i: abs((parsed[i] - now).total_seconds()))
    return closest_idx


def call_openmeteo(lat: float, lon: float, timeout: int) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(POLLUTANT_MAP.keys()),
        "timezone": "UTC",
        "forecast_days": 1,
    }
    response = requests.get(settings.open_meteo_url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def run_collector() -> None:
    cfg = load_collector_config().get("collectors", {}).get("openmeteo", {})
    timeout_seconds = int(cfg.get("timeout_seconds", 20))
    retries = int(cfg.get("retries", 3))
    started_at = now_utc()
    run_status = "success"
    rows = 0
    error_message = None
    begin = time.perf_counter()

    try:
        cities_cfg = load_cities()
        with SessionLocal() as db:
            for city_cfg in cities_cfg:
                city_code = city_cfg["code"].upper()
                city = db.scalar(select(City).where(City.code == city_code))
                if city is None:
                    logger.warning("City %s not found in DB, skipping", city_code)
                    continue
                station = get_or_create_station(
                    db,
                    city.id,
                    f"Open-Meteo {city_code}",
                    f"OPENMETEO_{city_code}",
                )
                payload = None
                last_exc = None
                for _ in range(retries):
                    try:
                        payload = call_openmeteo(float(city_cfg["lat"]), float(city_cfg["lon"]), timeout_seconds)
                        break
                    except Exception as exc:
                        last_exc = exc
                        time.sleep(1)
                if payload is None:
                    raise RuntimeError(f"Open-Meteo request failed for {city_code}: {last_exc}")

                hourly = payload.get("hourly", {})
                unit_map = payload.get("hourly_units", {})
                times = hourly.get("time", [])
                if not times:
                    continue
                idx = choose_current_hour_index(times)
                measured_at = parse_time(times[idx])
                received_at = now_utc()

                for field_name, pollutant in POLLUTANT_MAP.items():
                    values = hourly.get(field_name, [])
                    if idx >= len(values):
                        continue
                    raw_value = values[idx]
                    raw_unit = unit_map.get(field_name, "ug/m3")
                    canonical_value, canonical_unit = to_canonical(pollutant, raw_value, raw_unit)
                    upsert_measurement(
                        session=db,
                        source=SourceEnum.PUBLIC_API,
                        city_id=city.id,
                        station_id=station.id,
                        pollutant=pollutant,
                        measured_at=measured_at,
                        received_at=received_at,
                        value_raw=raw_value,
                        unit_raw=raw_unit,
                        value_canonical=canonical_value,
                        unit_canonical=canonical_unit,
                        conversion_mode=CONVERSION_MODE,
                    )
                    rows += 1
            db.add(
                CollectorRun(
                    collector_name="collector-openmeteo",
                    started_at=started_at,
                    finished_at=now_utc(),
                    status=run_status,
                    rows_parsed=rows,
                    error_message=error_message,
                )
            )
            db.commit()
        COLLECTOR_RUNS.labels(status="success").inc()
        COLLECTOR_ROWS.inc(rows)
        COLLECTOR_LAST_SUCCESS.set(time.time())
        logger.info("Open-Meteo collector run success rows=%s", rows)
    except Exception as exc:
        run_status = "error"
        error_message = str(exc)
        COLLECTOR_RUNS.labels(status="error").inc()
        logger.exception("Open-Meteo collector run failed: %s", exc)
        with SessionLocal() as db:
            db.add(
                CollectorRun(
                    collector_name="collector-openmeteo",
                    started_at=started_at,
                    finished_at=now_utc(),
                    status=run_status,
                    rows_parsed=rows,
                    error_message=error_message,
                )
            )
            db.commit()
    finally:
        COLLECTOR_DURATION.observe(time.perf_counter() - begin)


def main() -> None:
    wait_for_database()
    init_db(engine)
    with SessionLocal() as db:
        seed_base_data(db)
        db.commit()

    start_http_server(settings.metrics_port)
    schedule_cfg = load_collector_config().get("collectors", {}).get("openmeteo", {})
    interval = int(schedule_cfg.get("interval_minutes", settings.collector_interval_minutes))
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_collector, "interval", minutes=interval, next_run_time=datetime.now(timezone.utc))
    logger.info("collector-openmeteo started, interval=%s minutes", interval)
    scheduler.start()


if __name__ == "__main__":
    main()
