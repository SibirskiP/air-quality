import json
import logging
from typing import Any

from prometheus_client import Counter, Gauge, start_http_server
import paho.mqtt.client as mqtt
from sqlalchemy import select

from aq_common.bootstrap import init_db, seed_base_data
from aq_common.database import SessionLocal, engine, wait_for_database
from aq_common.models import City, SourceEnum
from aq_common.repository import get_or_create_station, upsert_measurement
from aq_common.settings import settings
from aq_common.time_utils import now_utc, parse_iso_utc
from aq_common.units import CONVERSION_MODE, to_canonical


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sensor-gateway")

INGEST_EVENTS = Counter("sensor_gateway_ingest_total", "MQTT ingest events", ["status"])
INGEST_DELAY = Gauge("sensor_gateway_delay_seconds", "Ingest delay measured in seconds")


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


def process_payload(payload: dict[str, Any]) -> int:
    with SessionLocal() as db:
        city = db.scalar(select(City).where(City.code == payload["city_code"].upper()))
        if city is None:
            raise ValueError(f"Unknown city code: {payload['city_code']}")
        sensor_id = payload["sensor_id"]
        station_name = payload.get("station", "MQTT")
        station_key = f"IOT_{sensor_id}"
        station = get_or_create_station(db, city.id, station_name, station_key)

        measured_at = parse_iso_utc(payload["timestamp"])
        received_at = now_utc()
        delay = max(0.0, (received_at - measured_at).total_seconds())
        INGEST_DELAY.set(delay)

        metrics = payload.get("metrics", {})
        unit_map = payload.get("unit_map", {})
        inserted = 0
        for metric_name, metric_value in metrics.items():
            pollutant = normalize_pollutant(metric_name)
            raw_unit = unit_map.get(metric_name) or unit_map.get(metric_name.lower()) or "ug/m3"
            canonical_value, canonical_unit = to_canonical(pollutant, metric_value, raw_unit)
            upsert_measurement(
                session=db,
                source=SourceEnum.IOT,
                city_id=city.id,
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
            inserted += 1
        db.commit()
        return inserted


def on_connect(client: mqtt.Client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("Connected to MQTT broker, subscribing to %s", settings.mqtt_topic)
        client.subscribe(settings.mqtt_topic)
    else:
        logger.error("MQTT connection failed with code %s", rc)


def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        written = process_payload(payload)
        INGEST_EVENTS.labels(status="ok").inc()
        logger.info("Processed MQTT message topic=%s rows=%d", msg.topic, written)
    except Exception as exc:
        INGEST_EVENTS.labels(status="error").inc()
        logger.exception("Failed to process MQTT message: %s", exc)


def main() -> None:
    wait_for_database()
    init_db(engine)
    with SessionLocal() as db:
        seed_base_data(db)
        db.commit()
    start_http_server(settings.metrics_port)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(settings.mqtt_host, settings.mqtt_port, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
