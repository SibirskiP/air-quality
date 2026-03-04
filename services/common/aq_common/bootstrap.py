from sqlalchemy import select

from aq_common.config_loader import load_cities
from aq_common.models import Base, City, Station


def init_db(engine) -> None:
    Base.metadata.create_all(bind=engine)


def seed_base_data(session) -> None:
    cities_cfg = load_cities()
    for city_cfg in cities_cfg:
        code = city_cfg["code"].upper()
        city = session.scalar(select(City).where(City.code == code))
        if city is None:
            city = City(
                code=code,
                name=city_cfg["name"],
                enabled=True,
                lat=float(city_cfg["lat"]),
                lon=float(city_cfg["lon"]),
            )
            session.add(city)
            session.flush()
        default_station_key = f"{code}_DEFAULT"
        station = session.scalar(
            select(Station).where(
                Station.city_id == city.id, Station.source_station_key == default_station_key
            )
        )
        if station is None:
            session.add(
                Station(
                    city_id=city.id,
                    name="Default",
                    source_station_key=default_station_key,
                )
            )
    session.flush()

