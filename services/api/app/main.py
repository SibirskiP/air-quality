from datetime import datetime, timezone
import time
from typing import Any
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from aq_common.bootstrap import init_db, seed_base_data
from aq_common.database import SessionLocal, engine, wait_for_database
from aq_common.models import (
    Alert,
    AlertStatus,
    AuthAudit,
    City,
    Comparison,
    Measurement,
    RefreshSnapshot,
    Sensor,
    SourceEnum,
)
from aq_common.security import create_access_token, decode_token, generate_api_key, hash_api_key, verify_api_key
from aq_common.time_utils import now_utc, parse_iso_utc
from aq_common.units import CONVERSION_MODE, from_canonical, to_canonical


REQUEST_COUNT = Counter(
    "api_requests_total",
    "Total API requests",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "api_request_duration_seconds",
    "API request latency in seconds",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1, 2, 5),
)
INGEST_COUNT = Counter("iot_ingest_total", "IoT ingest events", ["status"])


app = FastAPI(title="Air Quality Monitoring API", version="0.1.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class SensorRegisterRequest(BaseModel):
    city_code: str
    station_name: str = "Default"
    sensor_code: str | None = None


class SensorAuthRequest(BaseModel):
    sensor_code: str
    api_key: str


class IoTIngestRequest(BaseModel):
    sensor_id: str = Field(..., alias="sensor_id")
    city_code: str
    station: str
    timestamp: str
    metrics: dict[str, float | None]
    unit_map: dict[str, str]


class SnapshotCaptureRequest(BaseModel):
    city_code: str
    pollutant: str
    from_ts: str | None = None
    to_ts: str | None = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def normalize_pollutant(name: str) -> str:
    key = name.strip().lower().replace("_", "").replace(".", "")
    mapping = {
        "pm25": "PM2.5",
        "pm10": "PM10",
        "no2": "NO2",
        "so2": "SO2",
        "o3": "O3",
        "co": "CO",
        "h2s": "H2S",
    }
    return mapping.get(key, name.upper())


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return authorization.split(" ", 1)[1]


def current_sensor(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Sensor:
    token = extract_bearer_token(authorization)
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    sensor_code = payload.get("sub")
    if not sensor_code:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    sensor = db.scalar(select(Sensor).where(Sensor.sensor_code == sensor_code, Sensor.active.is_(True)))
    if sensor is None:
        raise HTTPException(status_code=401, detail="Sensor not active")
    return sensor


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    method = request.method
    path = request.url.path
    REQUEST_COUNT.labels(method=method, path=path, status_code=str(response.status_code)).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(elapsed)
    return response


@app.on_event("startup")
def startup() -> None:
    wait_for_database()
    init_db(engine)
    with SessionLocal() as db:
        seed_base_data(db)
        db.commit()


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def ui_home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/v1/sensors/register")
def register_sensor(payload: SensorRegisterRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    city = db.scalar(select(City).where(City.code == payload.city_code.upper()))
    if city is None:
        raise HTTPException(status_code=404, detail="City not found")
    station_key = f"{city.code}_{payload.station_name.strip().upper().replace(' ', '_')}"
    from aq_common.repository import get_or_create_station

    station = get_or_create_station(db, city.id, payload.station_name, station_key)
    sensor_code = payload.sensor_code or f"{city.code.lower()}-{station.id}-{int(time.time())}"
    existing = db.scalar(select(Sensor).where(Sensor.sensor_code == sensor_code))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Sensor code already exists")
    api_key = generate_api_key()
    sensor = Sensor(
        city_id=city.id,
        station_id=station.id,
        sensor_code=sensor_code,
        api_key_hash=hash_api_key(api_key),
        active=True,
    )
    db.add(sensor)
    db.commit()
    return {"sensor_code": sensor_code, "api_key": api_key}


@app.post("/api/v1/sensors/auth")
def auth_sensor(payload: SensorAuthRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    sensor = db.scalar(select(Sensor).where(Sensor.sensor_code == payload.sensor_code))
    if sensor is None:
        db.add(AuthAudit(sensor_code=payload.sensor_code, success=False, reason="sensor_not_found"))
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_api_key(payload.api_key, sensor.api_key_hash):
        db.add(AuthAudit(sensor_code=payload.sensor_code, success=False, reason="bad_api_key"))
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    db.add(AuthAudit(sensor_code=payload.sensor_code, success=True, reason="ok"))
    db.commit()
    token = create_access_token(sensor.sensor_code)
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/v1/ingest/iot")
def ingest_iot(
    payload: IoTIngestRequest,
    sensor: Sensor = Depends(current_sensor),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.sensor_id != sensor.sensor_code:
        raise HTTPException(status_code=403, detail="Sensor mismatch")
    measured_at = parse_iso_utc(payload.timestamp)
    received_at = now_utc()
    from aq_common.repository import get_or_create_station, upsert_measurement

    station_key = f"IOT_{sensor.sensor_code}"
    station = get_or_create_station(db, sensor.city_id, payload.station, station_key)
    written = 0
    for metric_name, metric_value in payload.metrics.items():
        pollutant = normalize_pollutant(metric_name)
        raw_unit = payload.unit_map.get(metric_name) or payload.unit_map.get(metric_name.lower()) or "ug/m3"
        canonical_value, canonical_unit = to_canonical(pollutant, metric_value, raw_unit)
        upsert_measurement(
            session=db,
            source=SourceEnum.IOT,
            city_id=sensor.city_id,
            station_id=station.id,
            pollutant=pollutant,
            measured_at=measured_at,
            received_at=received_at,
            value_raw=metric_value,
            unit_raw=raw_unit,
            value_canonical=canonical_value,
            unit_canonical=canonical_unit,
            conversion_mode=CONVERSION_MODE,
        )
        written += 1
    db.commit()
    INGEST_COUNT.labels(status="ok").inc()
    return {"status": "ok", "written": written}


@app.get("/api/v1/cities")
def list_cities(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    cities = db.scalars(select(City).where(City.enabled.is_(True)).order_by(City.code)).all()
    return [
        {"code": c.code, "name": c.name, "lat": c.lat, "lon": c.lon, "enabled": c.enabled}
        for c in cities
    ]


def requested_unit_for_pollutant(pollutant: str, params: dict[str, str | None]) -> str:
    key_map = {
        "SO2": "so2_unit",
        "NO2": "no2_unit",
        "O3": "o3_unit",
        "PM10": "pm10_unit",
        "PM2.5": "pm25_unit",
        "CO": "co_unit",
    }
    key = key_map.get(pollutant)
    if not key:
        return "ug/m3"
    return params.get(key) or "ug/m3"


def latest_value_for_source(
    db: Session,
    city_id: int,
    pollutant: str,
    source: str,
    from_dt: datetime | None,
    to_dt: datetime | None,
) -> float | None:
    stmt = (
        select(Measurement.value_canonical)
        .where(
            Measurement.city_id == city_id,
            Measurement.pollutant == pollutant,
            Measurement.source == source,
            Measurement.value_canonical.is_not(None),
        )
        .order_by(Measurement.measured_at.desc())
    )
    if from_dt:
        stmt = stmt.where(Measurement.measured_at >= from_dt)
    if to_dt:
        stmt = stmt.where(Measurement.measured_at <= to_dt)
    return db.scalar(stmt.limit(1))


@app.post("/api/v1/snapshots/capture")
def capture_snapshot(payload: SnapshotCaptureRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    city = db.scalar(select(City).where(City.code == payload.city_code.upper()))
    if city is None:
        raise HTTPException(status_code=404, detail="City not found")
    pollutant = normalize_pollutant(payload.pollutant)
    from_dt = parse_iso_utc(payload.from_ts) if payload.from_ts else None
    to_dt = parse_iso_utc(payload.to_ts) if payload.to_ts else None

    fhmz = latest_value_for_source(db, city.id, pollutant, SourceEnum.FHMZ.value, from_dt, to_dt)
    openm = latest_value_for_source(db, city.id, pollutant, SourceEnum.PUBLIC_API.value, from_dt, to_dt)
    delta = abs(float(fhmz) - float(openm)) if fhmz is not None and openm is not None else None

    snap = RefreshSnapshot(
        city_id=city.id,
        pollutant=pollutant,
        snapshot_at=now_utc(),
        fhmz_value=float(fhmz) if fhmz is not None else None,
        openmeteo_value=float(openm) if openm is not None else None,
        delta_abs=delta,
        unit="ug/m3",
    )
    db.add(snap)
    db.commit()
    return {
        "id": snap.id,
        "city": city.code,
        "pollutant": snap.pollutant,
        "snapshot_at": snap.snapshot_at.isoformat(),
        "fhmz_value": snap.fhmz_value,
        "openmeteo_value": snap.openmeteo_value,
        "delta_abs": snap.delta_abs,
        "unit": snap.unit,
    }


@app.get("/api/v1/snapshots")
def list_snapshots(
    city: str,
    pollutant: str,
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    norm_pollutant = normalize_pollutant(pollutant)
    stmt = (
        select(RefreshSnapshot, City.code)
        .join(City, City.id == RefreshSnapshot.city_id)
        .where(City.code == city.upper(), RefreshSnapshot.pollutant == norm_pollutant)
        .order_by(RefreshSnapshot.snapshot_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "id": s.id,
            "city": city_code,
            "pollutant": s.pollutant,
            "snapshot_at": s.snapshot_at.isoformat(),
            "fhmz_value": s.fhmz_value,
            "openmeteo_value": s.openmeteo_value,
            "delta_abs": s.delta_abs,
            "unit": s.unit,
        }
        for s, city_code in rows
    ]


@app.get("/api/v1/measurements")
def list_measurements(
    city: str | None = Query(default=None),
    source: str | None = Query(default=None),
    pollutant: str | None = Query(default=None),
    from_ts: str | None = Query(default=None, alias="from"),
    to_ts: str | None = Query(default=None, alias="to"),
    unit_mode: str = Query(default="canonical"),
    so2_unit: str | None = Query(default=None),
    no2_unit: str | None = Query(default=None),
    o3_unit: str | None = Query(default=None),
    pm10_unit: str | None = Query(default=None),
    pm25_unit: str | None = Query(default=None),
    co_unit: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(Measurement, City.code).join(City, City.id == Measurement.city_id)
    filters = []
    if city:
        filters.append(City.code == city.upper())
    if source:
        filters.append(Measurement.source == source)
    if pollutant:
        filters.append(Measurement.pollutant == normalize_pollutant(pollutant))
    if from_ts:
        filters.append(Measurement.measured_at >= parse_iso_utc(from_ts))
    if to_ts:
        filters.append(Measurement.measured_at <= parse_iso_utc(to_ts))
    if filters:
        stmt = stmt.where(and_(*filters))
    stmt = stmt.order_by(Measurement.measured_at.desc()).limit(limit)
    rows = db.execute(stmt).all()
    params = {
        "so2_unit": so2_unit,
        "no2_unit": no2_unit,
        "o3_unit": o3_unit,
        "pm10_unit": pm10_unit,
        "pm25_unit": pm25_unit,
        "co_unit": co_unit,
    }
    result = []
    for m, city_code in rows:
        out_value = m.value_canonical
        out_unit = m.unit_canonical
        if unit_mode == "raw":
            out_value = m.value_raw
            out_unit = m.unit_raw
        elif unit_mode == "converted":
            target = requested_unit_for_pollutant(m.pollutant, params)
            out_value = from_canonical(m.pollutant, m.value_canonical, target)
            out_unit = target
        result.append(
            {
                "id": m.id,
                "source": m.source,
                "city": city_code,
                "station_id": m.station_id,
                "pollutant": m.pollutant,
                "measured_at": m.measured_at.astimezone(timezone.utc).isoformat(),
                "value": out_value,
                "unit": out_unit,
                "raw_value": m.value_raw,
                "raw_unit": m.unit_raw,
                "canonical_value": m.value_canonical,
                "canonical_unit": m.unit_canonical,
            }
        )
    return result


@app.get("/api/v1/comparisons")
def list_comparisons(
    city: str | None = Query(default=None),
    pollutant: str | None = Query(default=None),
    from_ts: str | None = Query(default=None, alias="from"),
    to_ts: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(Comparison, City.code).join(City, City.id == Comparison.city_id)
    filters = []
    if city:
        filters.append(City.code == city.upper())
    if pollutant:
        filters.append(Comparison.pollutant == normalize_pollutant(pollutant))
    if from_ts:
        filters.append(Comparison.measured_at >= parse_iso_utc(from_ts))
    if to_ts:
        filters.append(Comparison.measured_at <= parse_iso_utc(to_ts))
    if filters:
        stmt = stmt.where(and_(*filters))
    rows = db.execute(stmt.order_by(Comparison.measured_at.desc()).limit(limit)).all()
    return [
        {
            "id": c.id,
            "city": city_code,
            "pollutant": c.pollutant,
            "measured_at": c.measured_at.isoformat(),
            "openmeteo_value": c.openmeteo_value,
            "fhmz_value": c.fhmz_value,
            "delta_abs": c.delta_abs,
            "delta_pct": c.delta_pct,
            "unit": c.unit_canonical,
        }
        for c, city_code in rows
    ]


@app.get("/api/v1/alerts")
def list_alerts(
    city: str | None = Query(default=None),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(Alert, City.code).join(City, City.id == Alert.city_id)
    filters = []
    if city:
        filters.append(City.code == city.upper())
    if status:
        filters.append(Alert.status == status)
    if severity:
        filters.append(Alert.severity == severity)
    if filters:
        stmt = stmt.where(and_(*filters))
    rows = db.execute(stmt.order_by(Alert.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": a.id,
            "city": city_code,
            "pollutant": a.pollutant,
            "measured_at": a.measured_at.isoformat(),
            "threshold_value": a.threshold_value,
            "observed_value": a.observed_value,
            "severity": a.severity,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
            "closed_at": a.closed_at.isoformat() if a.closed_at else None,
        }
        for a, city_code in rows
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
