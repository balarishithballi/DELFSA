# DELFSA — Distributed Enterprise Lab For Security Analysis

DELFSA is a Docker-based lab that stands up a small SIEM (Security Information and Event Management) pipeline alongside an isolated attacker node, so you can generate, detect, and correlate security events end-to-end on a single host.

This repository currently ships **Phase 1**: core infrastructure, the full SIEM pipeline, and an attacker container. The broader multi-segment enterprise network, background traffic generators, and Sigma-format rule packs described in [`DELFSA.md`](./DELFSA.md) are the target architecture for later phases.

## Architecture

Three logical planes, connected only through whitelisted bridge points:

- **Infrastructure plane** — Redis (message bus), Postgres (state), Elasticsearch + Kibana (log storage/search), Prometheus + Grafana (metrics/dashboards), and an Nginx reverse proxy fronting Kibana and Grafana.
- **SIEM pipeline plane** — a chain of single-responsibility services that move an event from raw log to actionable incident:

  ```
  log-shipper → normalizer → detection-engine → correlation-engine
  ```

  Stages communicate via Redis queues rather than direct calls, so any stage can be scaled or restarted independently.
- **Attacker plane** — a `kali` container on its own isolated, internal-only Docker network (`delfsa-attack-range`), started only when the `attack` profile is enabled. It never shares a network with the SIEM plane.

See [`DELFSA.md`](./DELFSA.md) for the full target network topology, communication matrix, asset classification, and planned architectural improvements.

### Pipeline stage details

| Stage | Responsibility |
| :-- | :-- |
| `log-shipper` | Watches `./logs` and pushes raw log lines onto a Redis queue with source metadata. |
| `normalizer` | Parses raw events into a common schema, preserving a reference to the raw event. |
| `detection-engine` | Evaluates normalized events against rules in `./rules` (hot-reloaded every 60s), tagging matches with severity and MITRE ATT&CK technique IDs. |
| `correlation-engine` | Groups related alerts (by source IP, host, or rule) within a sliding time window into incidents, using Redis sorted sets to track state so it survives restarts. |

## Prerequisites

- Docker
- Docker Compose v2 (the `docker compose` plugin)
- ~4.5 GB RAM free at idle, ~7 GB at peak (attacker container active)

## Getting started

```bash
# 1. Clone and enter the repo
git clone <this-repo-url>
cd SIEM-NETWORK-PROJECT

# 2. First-time setup: creates .env, host directories, builds images
./scripts/setup.sh

# 3. Edit .env and change every "change_me_*" password
nano .env

# 4. Start the core stack
./scripts/start.sh
```

`start.sh` brings up the stack and polls until services report healthy. Once running:

- **Kibana:** http://localhost:5601
- **Grafana:** http://localhost:3000 (default user/password come from `.env`)
- **Prometheus:** http://localhost:9090
- **Reverse proxy:** http://localhost:8080

### Adding the attacker node

The `kali` container is opt-in via a Compose profile so it isn't running (and consuming resources) by default:

```bash
docker compose --profile attack up -d kali
docker compose exec kali bash
```

Attack scenario playbooks are mounted read-only at `/attack-scenarios` inside the container.

### Stopping and cleaning up

```bash
./scripts/stop.sh       # stop all containers, keep data volumes
./scripts/cleanup.sh    # interactive: remove containers/networks, optionally volumes and images
./scripts/healthcheck.sh  # poll until all services report healthy (also called by start.sh)
```

## Configuration

All tunables live in `.env` (copy from `.env.example`). Key settings:

| Variable | Purpose |
| :-- | :-- |
| `REDIS_PASSWORD`, `POSTGRES_PASSWORD`, `GRAFANA_ADMIN_PASSWORD` | Change these before starting — defaults are placeholders. |
| `LOG_SHIPPER_WATCH_DIR`, `LOG_SHIPPER_POLL_INTERVAL` | Where the shipper looks for logs and how often it polls. |
| `CORRELATION_WINDOW_SECONDS`, `CORRELATION_THRESHOLD` | How many alerts within what window trigger an incident. |
| `INCIDENT_COOLDOWN_SECONDS` | Minimum time between repeated incidents for the same correlation key. |
| `KIBANA_PORT`, `GRAFANA_PORT`, `PROMETHEUS_PORT`, `REVERSE_PROXY_PORT` | Host port mappings. |

## Detection rules

Detection logic lives in `rules/baseline.yml` and is loaded by the detection engine at startup, then hot-reloaded every 60 seconds — new rule files dropped into `rules/` don't require a rebuild. Each rule declares a `match`, `contains`, or `regex` condition against a normalized event field, plus a severity and a MITRE ATT&CK technique ID. The baseline set covers things like failed SSH logins, root login attempts, HTTP 4xx/5xx patterns, SQL injection and directory traversal signatures in request paths, known scanner user agents, and sudo usage.

## Repository layout

```
.
├── configs/                # Nginx, Prometheus, Grafana provisioning, Redis template
├── docker/services/
│   ├── infrastructure/     # redis, postgres, elasticsearch, kibana, prometheus, grafana, reverse-proxy
│   ├── siem/                # log-shipper, normalizer, detection-engine, correlation-engine
│   └── attackers/kali/      # isolated attacker node
├── rules/                  # detection rule definitions (baseline.yml + extensions)
├── scripts/                # setup.sh, start.sh, stop.sh, cleanup.sh, healthcheck.sh
├── shared/python/           # delfsa_common.py — shared logging/Redis/heartbeat helpers used by pipeline services
├── docker-compose.yml
├── .env.example
└── DELFSA.md                # full architecture document (network topology, roadmap, etc.)
```

## Roadmap

Per `DELFSA.md`, planned next phases include the full multi-segment enterprise network (DMZ, internal, DB, management, and dev tiers), realistic fake enterprise data and user behavior generators, a network-tap/NetFlow sidecar, Sigma-format rule migration, and per-scenario Compose profiles for staged attack exercises.

## Security note

This lab intentionally contains vulnerable and misconfigured services for detection-engineering practice. Run it only in an isolated environment (e.g., an internal VM or sandboxed host), never on a network segment with production systems or exposed to the public internet.
