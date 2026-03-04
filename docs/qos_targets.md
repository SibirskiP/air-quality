# QoS Targets

- API response time: p95 < 200 ms
- Real-time processing delay: < 5s
- Availability target: 99.9% uptime

## Measurement approach

- Prometheus histogram `api_request_duration_seconds`
- Ingest delay gauge `sensor_gateway_delay_seconds`
- Service uptime from `up` metric in Prometheus