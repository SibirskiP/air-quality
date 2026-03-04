# API Examples

## Register sensor

```bash
curl -X POST http://localhost:8000/api/v1/sensors/register \
  -H "Content-Type: application/json" \
  -d '{
    "city_code": "BIHAC",
    "station_name": "Nova cetvrt",
    "sensor_code": "usk-bihac-01"
  }'
```

## Authenticate sensor

```bash
curl -X POST http://localhost:8000/api/v1/sensors/auth \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_code": "usk-bihac-01",
    "api_key": "REPLACE_API_KEY"
  }'
```

## Ingest IoT measurement

```bash
curl -X POST http://localhost:8000/api/v1/ingest/iot \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer REPLACE_TOKEN" \
  -d '{
    "sensor_id": "usk-bihac-01",
    "city_code": "BIHAC",
    "station": "Nova cetvrt",
    "timestamp": "2026-03-02T10:00:00Z",
    "metrics": {
      "pm25": 28.1,
      "pm10": 44.2,
      "no2": 31.0,
      "so2": 8.0,
      "o3": 47.0,
      "co": 0.9
    },
    "unit_map": {
      "pm25": "ug/m3",
      "pm10": "ug/m3",
      "no2": "ug/m3",
      "so2": "ug/m3",
      "o3": "ug/m3",
      "co": "mg/m3"
    }
  }'
```

## Query measurements with conversion

```bash
curl "http://localhost:8000/api/v1/measurements?city=BIHAC&source=fhmz&unit_mode=converted&so2_unit=ppb&no2_unit=ppb&o3_unit=ppb"
```

