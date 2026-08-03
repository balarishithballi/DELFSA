# Detection Engineering Lab — Architecture

## 1. Overall Architecture

Three logical planes on one Docker host: **Enterprise plane** (production services + users + data), **Attacker plane** (3-4 isolated networks), **SIEM plane** (collection→normalization→detection→correlation→storage→dashboard, fully separate pipeline stages as distinct containers, not one monolith). Planes connect only through explicitly whitelisted multi-homed bridge containers (reverse-proxy, log-shippers). Everything is Compose-orchestrated with per-phase profiles (idle, attack-scenario-N) so unused containers stay stopped rather than idle-consuming RAM.

> **Challenge to your brief**: don't build one "log-shipper" per host — use one shipper per network segment, not per-service, to cut container count and RAM while preserving segment-level provenance.

## 2. Network Topology

| Network | Subnet | Containers | Trust Boundary |
| :-- | :-- | :-- | :-- |
| `dmz_net` | 172.20.10.0/24 | reverse-proxy, web-server | Untrusted → semi-trusted edge |
| `internal_net` | 172.20.11.0/24 | rest-api, internal-api, samba, dns | Trusted, app tier |
| `db_net` | 172.20.12.0/24 | postgres-app, backup-server | Highest data sensitivity |
| `mgmt_net` | 172.20.13.0/24 | ssh-jump, monitoring-agent, patch-sim | Admin-only, no attacker reach |
| `dev_net` | 172.20.14.0/24 | git-service, dev-workstation, ci-runner | Semi-isolated, CI secrets live here |
| `siem_net` | 172.20.15.0/24 | shippers(rx side), normalizer, detection-engine, correlation-engine, redis, postgres-siem, grafana | Zero attacker reachability |
| `attacker_net_1` | 10.50.1.0/24 | kali (external recon/exploit) | Isolated, single egress via dmz_net exposed port only |
| `attacker_net_2` | 10.50.2.0/24 | kali (post-compromise pivot sim) | Reachable only after simulated foothold container attaches |
| `attacker_net_3` | 10.50.3.0/24 | kali (C2 sim, egress-only) | DNS/HTTP covert channel testing |
| `attacker_net_4` | 10.50.4.0/24 | kali (insider-threat sim) | Pre-attached to internal_net edge, no external hop |

**Rule**: an attacker container is never dual-homed onto siem_net, db_net, or mgmt_net under any scenario. Only shippers and the reverse-proxy are multi-homed bridges, and shippers are one-way (push-only, no listening ports facing the source segment).

## 3. Container Inventory

### Enterprise

- `reverse-proxy` (nginx/ubuntu)
- `web-server` (apache/ubuntu)
- `rest-api` (python:3.12-slim)
- `ftp-server` (debian)
- `ssh-jump` (ubuntu)
- `samba-server` (debian)
- `dns-server` (bind9/ubuntu)
- `internal-api` (python:3.12-slim)
- `backup-server` (debian)
- `git-service` (gitea or manual git+ssh on debian)
- `dev-workstation` (ubuntu)
- `ci-runner` (python:3.12-slim)
- `monitoring-agent` (ubuntu)


### Data

- `postgres-app` (official image — infra, not "vulnerable app")


### SIEM pipeline (each a distinct single-responsibility container)

- `log-collector/shipper` (per segment, ×6)
- `normalizer` (python:3.12-slim)
- `detection-engine` (python:3.12-slim, Sigma-rule evaluator)
- `correlation-engine` (python:3.12-slim)
- `redis` (official — message bus between stages)
- `postgres-siem` (official — normalized event store)
- `grafana` (official)


### Attacker

- `kali` ×3-4 (kalilinux/kali-rolling), one per attacker_net


### Background activity generators

- Separate lightweight sidecars, not baked into service containers (see §14)


## 4. Communication Matrix

| Source | Destination | Allowed? | Mechanism |
| :-- | :-- | :-- | :-- |
| attacker_net_1 | dmz_net (reverse-proxy:443) | Yes | Exposed port only |
| dmz_net | internal_net | Yes | reverse-proxy→rest-api explicit link |
| internal_net | db_net | Yes | rest-api/internal-api→postgres-app only |
| dmz_net | db_net | **No** | No route exists |
| attacker_net_* | siem_net | **No, never** | No shared network membership possible |
| attacker_net_* | mgmt_net | **No** | Separate network, no bridge container |
| mgmt_net | internal_net/db_net | Yes | ssh-jump only, key-based |
| dev_net | internal_net | Yes | ci-runner→internal-api only |
| all enterprise segments | siem_net | Yes | shipper push, one per segment |
| siem_net internal (shipper→normalizer→detection→correlation→storage) | — | Yes | Redis pub/sub or queue between each stage |

**Enforcement**: Docker network membership is the primary boundary; add iptables/nftables rules inside multi-homed containers as defense-in-depth, not as the sole control.

## 5. Data Flow

**Business data flows**:

```
dev_workstation → git-service (commits) → ci-runner (build) → internal-api (deploy config) → rest-api (serves to web-server) → postgres-app (persisted) → backup-server (scheduled dump) → samba (shared docs/exports)
```

**Attacker path (future)**:

```
dmz entry → internal pivot → db_net/samba data access → staged exfil via allowed egress protocol (DNS/HTTP/FTP) back toward attacker_net
```


## 6. Logging Pipeline

```
Service (raw log/stdout)
    ↓
Collector/Shipper (segment-local, tails + forwards, adds source metadata)
    ↓  [Redis queue]
Normalizer (parses raw → common schema, preserves raw_event_ref)
    ↓  [Redis queue]
Detection Engine (Sigma-rule match against normalized stream, tags MITRE technique/tactic, severity)
    ↓  [Redis queue]
Correlation Engine (groups related events → incident, assigns correlation_id/incident_id, applies asset-criticality weighting)
    ↓
Storage (postgres-siem: normalized events + raw archive reference; raw logs also archived separately, uncompressed, immutable path)
    ↓
Dashboard (Grafana, reads from postgres-siem)
```

Raw logs persist on a separate volume, never mutated — normalizer only reads them, detection/correlation never touch raw storage directly.

## 7. Event Processing Pipeline

Each stage is a single-responsibility, stateless-where-possible container communicating via Redis streams/queues (not direct HTTP calls) — this decouples throughput and lets you scale/replace any one stage without touching others. Detection engine loads Sigma rules from a mounted config volume (hot-reloadable). Correlation engine maintains short-lived state (sliding window) in Redis, not in-process memory, so it survives container restarts.

## 8. Asset Classification

| Asset | Tier | Rationale |
| :-- | :-- | :-- |
| postgres-app, backup-server | **Critical** | Customer/payroll data |
| internal-api, rest-api | **High** | Business logic, auth boundary |
| samba, git-service | **High** | IP, credentials, source code |
| reverse-proxy, web-server | **Medium** | Public-facing but stateless |
| dns-server, ftp-server | **Medium** | Supporting infra |
| dev-workstation, ci-runner | **Medium** | Pivot risk to git/internal |
| monitoring-agent, ssh-jump | **Low** individually / **High** if compromised | Admin trust |
| SIEM stack | **Critical** | Tampering = blind SOC |

**Incident priority** = f(detection_severity, asset_tier) — implement as a lookup matrix in correlation engine, not hardcoded per-rule.

## 9. Enterprise User Design

| User | Role | Access | Behavior Pattern |
| :-- | :-- | :-- | :-- |
| admin | Administrator | ssh-jump, all mgmt | Occasional SSH, config changes, patch approval |
| dev1/dev2 | Developer | git-service, dev-workstation, ci-runner | git push/pull, frequent, business-hours jitter |
| hr_user | HR | samba (HR share), rest-api (HR module) | Document access, low frequency |
| finance_user | Finance | samba (finance share), postgres via rest-api | Periodic report queries, month-end spikes |
| backup_svc | Service account | backup-server, db_net, samba | Scheduled, fixed-but-jittered cron, non-interactive |
| ci_bot | Service account | git-service, ci-runner, internal-api | Triggered by commits, bursty |
| monitor_svc | Service account | mgmt_net, all segments (read-only probes) | Constant low-volume health checks |
| guest | Guest | dmz_net web only | Sparse, unauthenticated browsing sim |

Each maps to realistic auth artifacts (SSH keys, samba credentials, API tokens) — fake but structurally valid, stored in the systems they'd realistically live in.

## 10. Enterprise Data Design

- **postgres-app**: customer table, employee/payroll table (fake PII, realistic schema)
- **git-service**: 2-3 fake repos with commit history, one containing an accidentally-committed fake API key (realistic secret-sprawl scenario)
- **samba shares**: HR docs, finance spreadsheets, IT configs — segmented by share permissions matching user table
- **backup-server**: tarball snapshots of db + samba, timestamped, some retained/some rotated
- **ssh-jump**: fake authorized_keys per user, realistic known_hosts
- **internal-api**: fake config files with fake internal API keys, fake service tokens

All fake data generated once at build time via seed scripts (not runtime-generated) for reproducibility across scenario resets.

## 11. Technology Choices

- **Official images for infra-only roles**: Redis, Postgres (both instances), Grafana — justified since these carry no intentional vulnerabilities and reinventing them wastes effort/RAM optimization time
- **Manual builds** (ubuntu/debian/python:3.12-slim/kali) for every service that is either attacker-facing or intentionally vulnerable
- **Sigma** as the detection rule format (portable, widely understood, decouples rule authorship from engine internals)
- **Redis Streams** over plain pub/sub between pipeline stages — gives replay/consumer-group semantics needed for correlation engine state recovery
- **Background traffic generators** as Python + schedule/cron with jitter, not full behavioral-simulation frameworks — keeps CPU/RAM low


## 12. Repository Structure

```
lab/
├── docker/
│   ├── networks/
│   └── compose/            (per-plane compose files + override profiles)
├── infrastructure/
│   ├── enterprise/
│   ├── siem/
│   └── attackers/
├── pipeline/
│   ├── collector/
│   ├── normalizer/
│   ├── detection-engine/
│   ├── correlation-engine/
│   └── schema/
├── rules/
│   └── sigma/
├── dashboards/
│   └── grafana/
├── attack-scenarios/
│   └── <tactic>/<technique>/
├── background-activity/
│   └── generators/<user-or-service>/
├── shared/
│   ├── base-images/
│   └── fake-data-seed/
├── scripts/
├── configs/
└── tests/
    ├── pipeline/
    └── network-isolation/
```


## 13. Resource Estimates

- **Idle**: ~3.6–4.3GB — reverse-proxy/web/api (~500MB combined), postgres-app+postgres-siem (~600MB combined, official images are heavier than manual slim builds), redis (~60MB), normalizer/detection/correlation (~150MB each ≈450MB), grafana (~250MB), 6 shippers (~40MB each ≈240MB), remaining enterprise services (~700MB combined). Fits <4.5GB with modest headroom.
- **Peak (attack scenario)**: ~5.8–6.9GB — adds active Kali container(s) (~600MB-1GB each, only 1-2 active simultaneously by design), spike in detection/correlation throughput (~+200-300MB transient). Fits <7GB target.
- **CPU idle**: 8-18% on 8 threads (background generators + shippers polling)
- **CPU peak**: 40-65% during active scan/exploit phases + correlation engine burst processing
- **Heaviest components**: dual Postgres instances (consider whether postgres-app and postgres-siem truly need separate containers vs. separate databases on one instance if RAM gets tight — flagged as an optimization tradeoff, not a hard recommendation).


## 14. Architectural Improvements Recommended

1. **Reconsider dual Postgres instances**: running postgres-app and postgres-siem as separate databases within one Postgres container (not one instance) saves ~250-300MB idle RAM while keeping logical separation — worth testing against your RAM budget before committing to two full containers.
2. **Decouple background-activity generators from service containers entirely** — run them as separate sidecar containers issuing traffic into services rather than baking cron into each service image; this keeps service images minimal/realistic and makes scenario toggling (stop generators, keep services) trivial.
3. **Add a network-tap layer** (single tcpdump/zeek sidecar on dmz_net + internal_net, not per-network) for NetFlow-style telemetry beyond host logs — high detection value for lateral movement/C2 discovery/exfil tactics, low RAM cost if scoped to two networks instead of all six.
4. **Enforce the "no attacker→SIEM" guarantee at two layers**: Docker network topology (primary) + iptables rule inside every multi-homed bridge container (defense-in-depth) — topology alone assumes no future misconfiguration ever dual-homes a container by accident.
5. **Version the event schema explicitly** (`schema_version` field) from day one — you will change the event model as detection rules mature, and retroactive migration of stored events is painful without it.
6. **Separate raw-log retention policy from normalized-event retention** — raw logs should have a longer/immutable retention path (compliance-realism) distinct from normalized events which correlation engine may prune/aggregate.
7. **Stage container startup with health-check dependencies** (compose depends_on + healthcheck, not implemented here per your no-code constraint, but architecturally: pipeline stages must come up in strict order — redis → normalizer → detection → correlation — before shippers start pushing, to avoid dropped events at cold start).
