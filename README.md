# demo-deploy-app

A small Flask service for testing the **Predictive Auto Deployment Platform**
(see the SRS). It satisfies the platform's repository requirements and gives
the pipeline, ML risk model, monitoring and rollback something real to work with.

## SRS requirement mapping

| SRS requirement | Where it is met |
|---|---|
| FR2 / Constraint 2.4 - repo must contain a Dockerfile | `Dockerfile` in the repo root |
| FR5 - run the test suite during the build | `tests/` (pytest). Run with `docker run --rm <image> pytest` |
| FR6 - build image from the Dockerfile | `docker build -t demo-deploy-app .` (port 8080, non-root, healthcheck) |
| FR7 / FR8 - commit and build metadata | Several source files + tests, so commits vary in files/lines changed |
| FR10 - deploy to isolated K8s namespace | `k8s/deployment.yaml`, `k8s/service.yaml` (no hard-coded namespace) |
| FR11 - CPU, memory, error rate, latency | `/metrics` (Prometheus) and `/api/stats` (JSON) |
| FR12 / FR13 - anomalies and auto-rollback | `/chaos` fault injection endpoints |
| NFR - rollback within ~30 s | Fast start-up, `/readyz` + `/healthz` probes, `revisionHistoryLimit: 5` |
| 4.3 / Appendix C - Python, Docker, K8s, Prometheus | Python 3.12, Flask, prometheus-client |

## Run locally

```bash
docker build -t demo-deploy-app --build-arg APP_VERSION=1.0.0 --build-arg GIT_SHA=$(git rev-parse --short HEAD) .
docker run --rm -p 8080:8080 demo-deploy-app
docker run --rm demo-deploy-app pytest        # run tests inside the image
```

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | Service info |
| `GET /healthz`, `GET /readyz` | Liveness / readiness probes |
| `GET /version` | App version, git SHA, uptime (tells you which release is live) |
| `GET/POST /api/items` | Tiny in-memory API (`{"name": "..."}`) |
| `GET /api/stats` | JSON: `cpu`, `memory`, `error_rate`, `latency` (rolling 60 s) |
| `GET /metrics` | Prometheus metrics |
| `GET/POST /chaos`, `POST /chaos/reset` | Fault injection (disable with `ENABLE_CHAOS=false`) |

## Test scenarios for your platform

1. **Healthy push** - change any file (e.g. the message in `app/main.py`), push. Expect: build, tests pass, low risk, deploy.
2. **Failing tests** - set `FAULTY_RELEASE = True` in `app/release.py`, push. Expect: `test_release_is_healthy` fails; a high risk score / blocked deployment.
3. **Anomaly after deploy** (tests pass, runtime degrades) - with a live deployment:
   ```bash
   python scripts/generate_traffic.py http://<app-url> 5 300 &
   curl -X POST http://<app-url>/chaos -H 'Content-Type: application/json' \
        -d '{"error_rate": 0.6, "latency_ms": 800}'
   ```
   Other knobs: `"cpu_burn": true`, `"memory_leak_mb": 150`. Expect the monitor to flag an anomaly and roll back.
   Reset with `curl -X POST http://<app-url>/chaos/reset`.
4. **Large commit** - add or edit many files in one push to exercise the "files/lines changed" features.
5. **Manual rollback** - push two healthy commits, then roll back from the dashboard; confirm with `GET /version`.

`.github/workflows/ci.yml` runs the same build + test steps on GitHub Actions.
