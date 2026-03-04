from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "dev")
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://airq:airq@localhost:5432/airq"
    )
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    metrics_port: int = int(os.getenv("METRICS_PORT", "9100"))
    mqtt_host: str = os.getenv("MQTT_HOST", "localhost")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_topic: str = os.getenv("MQTT_TOPIC", "airq/+/+")
    collector_interval_minutes: int = int(os.getenv("COLLECTOR_INTERVAL_MINUTES", "5"))
    fhmz_url: str = os.getenv(
        "FHMZ_URL", "https://www.fhmzbih.gov.ba/latinica/ZRAK/AQI-satne.php"
    )
    open_meteo_url: str = os.getenv(
        "OPEN_METEO_URL", "https://air-quality-api.open-meteo.com/v1/air-quality"
    )


settings = Settings()

