from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from aq_common.models import City, Measurement, SourceEnum, Station


def get_city_by_code(session, code: str) -> City | None:
    return session.scalar(select(City).where(City.code == code.upper()))


def get_or_create_station(session, city_id: int, name: str, source_key: str) -> Station:
    station = session.scalar(
        select(Station).where(Station.city_id == city_id, Station.source_station_key == source_key)
    )
    if station is not None:
        return station
    station = Station(city_id=city_id, name=name[:128], source_station_key=source_key[:128])
    session.add(station)
    session.flush()
    return station


def upsert_measurement(
    session,
    source: SourceEnum | str,
    city_id: int,
    station_id: int,
    pollutant: str,
    measured_at: datetime,
    received_at: datetime,
    value_raw: float | None,
    unit_raw: str | None,
    value_canonical: float | None,
    unit_canonical: str,
    conversion_mode: str | None,
) -> None:
    values = {
        "source": source.value if isinstance(source, SourceEnum) else source,
        "city_id": city_id,
        "station_id": station_id,
        "pollutant": pollutant.upper(),
        "measured_at": measured_at,
        "received_at": received_at,
        "value_raw": value_raw,
        "unit_raw": unit_raw,
        "value_canonical": value_canonical,
        "unit_canonical": unit_canonical,
        "conversion_mode": conversion_mode,
    }
    stmt = pg_insert(Measurement).values(**values).on_conflict_do_nothing(
        constraint="uq_measurement_dedup"
    )
    session.execute(stmt)
