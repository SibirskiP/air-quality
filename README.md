# Air Quality Monitoring BiH

## Quick start

1. Copy env file:
   - `cp .env.example .env`
2. Start full stack:
   - `docker compose up --build`
3. API docs:
   - `http://localhost:8000/docs`
4. Prometheus:
   - `http://localhost:9090`
5. Grafana:
   - `http://localhost:3000` (`admin/admin`)

## Verify

- Health:
  - `curl http://localhost:8000/api/v1/health`
- Metrics:
  - `curl http://localhost:8000/metrics`
- Tests:
  - `PYTHONPATH=services/common pytest -q tests`

## Services

- `api`: REST API + sensor onboarding + HTTP ingest
- `sensor-gateway`: MQTT subscriber ingest
- `collector-openmeteo`: public API collector
- `collector-fhmz`: FHMZ HTML scraper collector
- `processor`: comparison and alert generation

## Notes

- FHMZ data source is scraped from `AQI-satne.php`.
- Canonical comparison uses `ug/m3`.
- Gas display conversion supports `ppb` with fixed 25C/1atm model.
- Services have DB wait-retry logic and compose restart policy to reduce startup connection failures.
- API usage examples are in `docs/api_examples.md`.
