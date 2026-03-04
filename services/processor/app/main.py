from datetime import datetime, timedelta, timezone
import logging
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from prometheus_client import Counter, Histogram, start_http_server
from sqlalchemy import and_, func, select

from aq_common.bootstrap import init_db, seed_base_data
from aq_common.config_loader import load_collector_config, load_thresholds
from aq_common.database import SessionLocal, engine, wait_for_database
from aq_common.models import Alert, AlertStatus, AlertSeverity, CollectorRun, Comparison, Measurement, SourceEnum
from aq_common.settings import settings
from aq_common.time_utils import now_utc


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("processor")

PROCESSOR_RUNS = Counter("processor_runs_total", "Processor run count", ["status"])
COMPARISON_ROWS = Counter("processor_comparisons_total", "Comparison rows written")
ALERT_ROWS = Counter("processor_alert_events_total", "Alert events", ["action"])
PROCESSOR_DURATION = Histogram(
    "processor_duration_seconds",
    "Processor run duration in seconds",
    buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 3, 5, 10),
)


def calculate_severity(value: float, warning: float, critical: float) -> str | None:
    if value >= critical:
        return AlertSeverity.CRITICAL.value
    if value >= warning:
        return AlertSeverity.WARNING.value
    return None


def upsert_comparisons(db) -> int:
    window_start = now_utc() - timedelta(hours=24)
    bucket = func.date_trunc("hour", Measurement.measured_at).label("bucket")
    q = (
        select(
            Measurement.city_id,
            Measurement.pollutant,
            bucket,
            Measurement.source,
            func.avg(Measurement.value_canonical).label("avg_val"),
        )
        .where(
            Measurement.source.in_([SourceEnum.FHMZ.value, SourceEnum.PUBLIC_API.value]),
            Measurement.value_canonical.is_not(None),
            Measurement.measured_at >= window_start,
        )
        .group_by(Measurement.city_id, Measurement.pollutant, bucket, Measurement.source)
    )
    rows = db.execute(q).all()
    grouped: dict[tuple[int, str, datetime], dict[str, float]] = {}
    for city_id, pollutant, measured_bucket, source, avg_val in rows:
        key = (city_id, pollutant, measured_bucket)
        grouped.setdefault(key, {})
        grouped[key][source] = float(avg_val)

    inserted = 0
    for (city_id, pollutant, measured_at), data in grouped.items():
        if SourceEnum.FHMZ.value not in data or SourceEnum.PUBLIC_API.value not in data:
            continue
        fhmz_value = data[SourceEnum.FHMZ.value]
        openmeteo_value = data[SourceEnum.PUBLIC_API.value]
        delta_abs = abs(fhmz_value - openmeteo_value)
        base = max(openmeteo_value, 1e-9)
        delta_pct = (delta_abs / base) * 100.0
        existing = db.scalar(
            select(Comparison).where(
                Comparison.city_id == city_id,
                Comparison.pollutant == pollutant,
                Comparison.measured_at == measured_at,
            )
        )
        if existing is None:
            db.add(
                Comparison(
                    city_id=city_id,
                    station_id=None,
                    pollutant=pollutant,
                    measured_at=measured_at,
                    openmeteo_value=openmeteo_value,
                    fhmz_value=fhmz_value,
                    delta_abs=delta_abs,
                    delta_pct=delta_pct,
                    unit_canonical="ug/m3",
                )
            )
            inserted += 1
    return inserted


def process_alerts(db) -> int:
    thresholds = load_thresholds()
    window_start = now_utc() - timedelta(hours=6)
    q = (
        select(Measurement)
        .where(
            Measurement.value_canonical.is_not(None),
            Measurement.measured_at >= window_start,
        )
        .order_by(Measurement.measured_at.desc())
    )
    rows = db.scalars(q).all()
    updated = 0
    for m in rows:
        th = thresholds.get(m.pollutant)
        if not th:
            continue
        warning = float(th.get("warning", 0))
        critical = float(th.get("critical", warning))
        severity = calculate_severity(float(m.value_canonical), warning, critical)

        open_alert = db.scalar(
            select(Alert).where(
                Alert.city_id == m.city_id,
                Alert.station_id == m.station_id,
                Alert.pollutant == m.pollutant,
                Alert.status == AlertStatus.OPEN.value,
            )
        )
        if severity:
            if open_alert is None:
                db.add(
                    Alert(
                        city_id=m.city_id,
                        station_id=m.station_id,
                        pollutant=m.pollutant,
                        measured_at=m.measured_at,
                        threshold_value=critical if severity == AlertSeverity.CRITICAL.value else warning,
                        observed_value=float(m.value_canonical),
                        severity=severity,
                        status=AlertStatus.OPEN.value,
                    )
                )
                ALERT_ROWS.labels(action="open").inc()
                updated += 1
            else:
                open_alert.severity = severity
                open_alert.observed_value = float(m.value_canonical)
                open_alert.measured_at = m.measured_at
                updated += 1
        elif open_alert is not None:
            open_alert.status = AlertStatus.CLOSED.value
            open_alert.closed_at = now_utc()
            ALERT_ROWS.labels(action="close").inc()
            updated += 1
    return updated


def run_processor() -> None:
    start = time.perf_counter()
    started_at = now_utc()
    comparisons = 0
    alerts_changed = 0
    status = "success"
    err = None
    try:
        with SessionLocal() as db:
            comparisons = upsert_comparisons(db)
            alerts_changed = process_alerts(db)
            db.add(
                CollectorRun(
                    collector_name="processor",
                    started_at=started_at,
                    finished_at=now_utc(),
                    status=status,
                    rows_parsed=comparisons + alerts_changed,
                    error_message=None,
                )
            )
            db.commit()
        PROCESSOR_RUNS.labels(status="success").inc()
        COMPARISON_ROWS.inc(comparisons)
        logger.info("processor success comparisons=%s alerts=%s", comparisons, alerts_changed)
    except Exception as exc:
        status = "error"
        err = str(exc)
        PROCESSOR_RUNS.labels(status="error").inc()
        logger.exception("processor failed: %s", exc)
        with SessionLocal() as db:
            db.add(
                CollectorRun(
                    collector_name="processor",
                    started_at=started_at,
                    finished_at=now_utc(),
                    status=status,
                    rows_parsed=comparisons + alerts_changed,
                    error_message=err,
                )
            )
            db.commit()
    finally:
        PROCESSOR_DURATION.observe(time.perf_counter() - start)


def main() -> None:
    wait_for_database()
    init_db(engine)
    with SessionLocal() as db:
        seed_base_data(db)
        db.commit()

    start_http_server(settings.metrics_port)
    cfg = load_collector_config().get("processor", {})
    interval = int(cfg.get("interval_minutes", settings.collector_interval_minutes))
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_processor, "interval", minutes=interval, next_run_time=datetime.now(timezone.utc))
    logger.info("processor started interval=%s minutes", interval)
    scheduler.start()


if __name__ == "__main__":
    main()
