from datetime import datetime, timezone
import logging
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from prometheus_client import Counter, Gauge, Histogram, start_http_server
import requests
from sqlalchemy import select

from aq_common.bootstrap import init_db, seed_base_data
from aq_common.config_loader import load_collector_config
from aq_common.database import SessionLocal, engine, wait_for_database
from aq_common.fhmz_parser import normalize_text, parse_fhmz_rows
from aq_common.models import City, CollectorRun, SourceEnum
from aq_common.repository import get_or_create_station, upsert_measurement
from aq_common.settings import settings
from aq_common.time_utils import now_utc
from aq_common.units import CONVERSION_MODE, to_canonical


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("collector-fhmz")

SCRAPE_RUNS = Counter("fhmz_scrape_runs_total", "FHMZ scrape runs", ["status"])
SCRAPE_ROWS = Counter("fhmz_rows_parsed_total", "FHMZ parsed rows total")
SCRAPE_DURATION = Histogram(
    "fhmz_scrape_duration_seconds",
    "FHMZ scrape duration in seconds",
    buckets=(0.1, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 30),
)
LAST_SUCCESS = Gauge("fhmz_last_success_timestamp", "Last successful FHMZ scrape timestamp")



def run_collector() -> None:
    cfg = load_collector_config().get("collectors", {}).get("fhmz", {})
    timeout_seconds = int(cfg.get("timeout_seconds", 20))
    retries = int(cfg.get("retries", 3))
    started_at = now_utc()
    rows_inserted = 0
    status = "success"
    err = None
    begin = time.perf_counter()
    try:
        response_text = None
        last_exc = None
        for _ in range(retries):
            try:
                response = requests.get(settings.fhmz_url, timeout=timeout_seconds)
                response.raise_for_status()
                response_text = response.text
                break
            except Exception as exc:
                last_exc = exc
                time.sleep(1)
        if response_text is None:
            raise RuntimeError(f"FHMZ request failed: {last_exc}")

        _, parsed_rows = parse_fhmz_rows(response_text)
        with SessionLocal() as db:
            for row in parsed_rows:
                city = db.scalar(select(City).where(City.code == row["city_code"]))
                if city is None:
                    continue
                station_key = (
                    f"FHMZ_{row['city_code']}_"
                    f"{normalize_text(row['station_name']).replace(' ', '_')[:64]}"
                )
                station = get_or_create_station(db, city.id, row["station_name"], station_key)
                for pollutant, raw_value in row["values"].items():
                    canonical_value, canonical_unit = to_canonical(pollutant, raw_value, "ug/m3")
                    upsert_measurement(
                        session=db,
                        source=SourceEnum.FHMZ,
                        city_id=city.id,
                        station_id=station.id,
                        pollutant=pollutant,
                        measured_at=row["measured_at"],
                        received_at=now_utc(),
                        value_raw=raw_value,
                        unit_raw="ug/m3",
                        value_canonical=canonical_value,
                        unit_canonical=canonical_unit,
                        conversion_mode=CONVERSION_MODE,
                    )
                    rows_inserted += 1

            db.add(
                CollectorRun(
                    collector_name="collector-fhmz",
                    started_at=started_at,
                    finished_at=now_utc(),
                    status=status,
                    rows_parsed=rows_inserted,
                    error_message=err,
                )
            )
            db.commit()

        SCRAPE_RUNS.labels(status="success").inc()
        SCRAPE_ROWS.inc(rows_inserted)
        LAST_SUCCESS.set(time.time())
        logger.info("FHMZ scrape success rows=%s", rows_inserted)
    except Exception as exc:
        status = "error"
        err = str(exc)
        SCRAPE_RUNS.labels(status="error").inc()
        logger.exception("FHMZ scrape failed: %s", exc)
        with SessionLocal() as db:
            db.add(
                CollectorRun(
                    collector_name="collector-fhmz",
                    started_at=started_at,
                    finished_at=now_utc(),
                    status=status,
                    rows_parsed=rows_inserted,
                    error_message=err,
                )
            )
            db.commit()
    finally:
        SCRAPE_DURATION.observe(time.perf_counter() - begin)


def main() -> None:
    wait_for_database()
    init_db(engine)
    with SessionLocal() as db:
        seed_base_data(db)
        db.commit()

    start_http_server(settings.metrics_port)
    cfg = load_collector_config().get("collectors", {}).get("fhmz", {})
    interval = int(cfg.get("interval_minutes", settings.collector_interval_minutes))
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_collector, "interval", minutes=interval, next_run_time=datetime.now(timezone.utc))
    logger.info("collector-fhmz started, interval=%s minutes", interval)
    scheduler.start()


if __name__ == "__main__":
    main()
