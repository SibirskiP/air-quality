"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_city_code"),
    )
    op.create_index("ix_cities_code", "cities", ["code"], unique=False)

    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("source_station_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.UniqueConstraint("city_id", "source_station_key", name="uq_station_source"),
    )

    op.create_table(
        "sensors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("sensor_code", sa.String(length=64), nullable=False),
        sa.Column("api_key_hash", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.UniqueConstraint("sensor_code", name="uq_sensor_code"),
    )

    op.create_table(
        "measurements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("pollutant", sa.String(length=32), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value_raw", sa.Float(), nullable=True),
        sa.Column("unit_raw", sa.String(length=32), nullable=True),
        sa.Column("value_canonical", sa.Float(), nullable=True),
        sa.Column("unit_canonical", sa.String(length=32), nullable=True),
        sa.Column("conversion_mode", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.UniqueConstraint(
            "source", "station_id", "pollutant", "measured_at", name="uq_measurement_dedup"
        ),
    )
    op.create_index("ix_measurement_city_time", "measurements", ["city_id", "measured_at"], unique=False)
    op.create_index(
        "ix_measurement_source_time", "measurements", ["source", "measured_at"], unique=False
    )
    op.create_index(
        "ix_measurement_pollutant_time", "measurements", ["pollutant", "measured_at"], unique=False
    )

    op.create_table(
        "comparisons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("pollutant", sa.String(length=32), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("openmeteo_value", sa.Float(), nullable=False),
        sa.Column("fhmz_value", sa.Float(), nullable=False),
        sa.Column("delta_abs", sa.Float(), nullable=False),
        sa.Column("delta_pct", sa.Float(), nullable=False),
        sa.Column("unit_canonical", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.UniqueConstraint("city_id", "pollutant", "measured_at", name="uq_comparison_dedup"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("pollutant", sa.String(length=32), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
    )
    op.create_index("ix_alert_status_created", "alerts", ["status", "created_at"], unique=False)

    op.create_table(
        "collector_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("collector_name", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rows_parsed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "auth_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sensor_code", sa.String(length=64), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("auth_audit")
    op.drop_table("collector_runs")
    op.drop_index("ix_alert_status_created", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("comparisons")
    op.drop_index("ix_measurement_pollutant_time", table_name="measurements")
    op.drop_index("ix_measurement_source_time", table_name="measurements")
    op.drop_index("ix_measurement_city_time", table_name="measurements")
    op.drop_table("measurements")
    op.drop_table("sensors")
    op.drop_table("stations")
    op.drop_index("ix_cities_code", table_name="cities")
    op.drop_table("cities")

