# IMPLEMENTATION_PLAN.md - Air Quality Monitoring BiH (FHMZ + Open-Meteo + IoT)

## 1. Sažetak
Cilj je isporučiti sistem koji:
- prikuplja podatke iz `Open-Meteo` i `FHMZ` (scraping, bez API-ja),
- prima IoT podatke u realnom vremenu preko MQTT,
- upoređuje vrijednosti po gradu/polutantu/vremenu,
- detektuje prekoračenja i generiše alarme,
- izlaže REST API,
- radi u lokalnom Kubernetes klasteru (Minikube),
- ima potpuni monitoring (Prometheus + Grafana + Alertmanager),
- dokazuje QoS ciljeve (`p95 < 200ms`, kašnjenje obrade `< 5s`).

## 2. Zaključani stack
- Jezik: `Python 3.12`
- API: `FastAPI`
- Broker: `Mosquitto (MQTT)`
- DB: `PostgreSQL`
- ORM/migracije: `SQLAlchemy` + `Alembic`
- Kolektori: `requests` + `BeautifulSoup4` + `lxml`
- Scheduler: `APScheduler`
- Monitoring: `Prometheus`, `Grafana`, `Alertmanager`
- Deploy: `Docker`, `Kubernetes`, `Minikube`
- Performanse: `k6`

## 3. Arhitektura servisa
- `sensor-gateway`: registracija/autentifikacija senzora + MQTT ingest.
- `collector-openmeteo`: periodično dohvaća Open-Meteo AQ podatke.
- `collector-fhmz`: periodično dohvaća i parsira `AQI-satne.php`.
- `processor`: normalizacija, poređenje, alarmiranje.
- `api`: REST upiti za mjerenja, poređenja, alarme, health.
- `postgres`: skladištenje podataka.
- `prometheus`, `grafana`, `alertmanager`: observability.

## 4. Jedinice i konverzije (zaključano)
- Model: `Raw + Canonical`.
- Canonical: `ug/m3`.
- Konverzija gasova u `ppb` (fixed 25C, 1 atm): `ppb = ug/m3 * 24.45 / MW`.

## 5. Konfiguracija i checklist
Detaljna checklist implementacije se nalazi u `README.md` i kodnim artefaktima po fazama.
