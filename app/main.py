"""Demo web service for the Predictive Auto Deployment Platform."""
import os
import threading
import time

from flask import Flask, Response, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import chaos, metrics

app = Flask(__name__)
START_TIME = time.time()

# Paths that must stay healthy even while faults are injected
INFRA_PATHS = {"/healthz", "/readyz", "/metrics", "/chaos", "/chaos/reset", "/api/stats"}

_items = [{"id": 1, "name": "first item"}]
_items_lock = threading.Lock()


@app.before_request
def _start():
    g.start = time.perf_counter()
    if request.path not in INFRA_PATHS and chaos.maybe_fail_or_delay():
        return jsonify(error="injected failure"), 500


@app.after_request
def _record(resp):
    path = request.url_rule.rule if request.url_rule else "unmatched"
    metrics.record(request.method, path, resp.status_code, time.perf_counter() - g.start)
    return resp


@app.get("/")
def index():
    return jsonify(
        service="demo-deploy-app",
        message="Hello from the Predictive Auto Deployment Platform demo app",
        version=os.environ.get("APP_VERSION", "dev"),
        endpoints=["/healthz", "/readyz", "/version", "/api/items", "/api/stats", "/metrics", "/chaos"],
    )


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.get("/readyz")
def readyz():
    return jsonify(status="ready")


@app.get("/version")
def version():
    return jsonify(
        version=os.environ.get("APP_VERSION", "dev"),
        git_sha=os.environ.get("GIT_SHA", "unknown"),
        uptime_seconds=round(time.time() - START_TIME, 1),
    )


@app.get("/api/items")
def list_items():
    with _items_lock:
        return jsonify(items=list(_items))


@app.post("/api/items")
def create_item():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify(error="name is required"), 400
    with _items_lock:
        item = {"id": len(_items) + 1, "name": name}
        _items.append(item)
    return jsonify(item), 201


@app.get("/api/stats")
def stats():
    """JSON summary of cpu / memory / error_rate / latency (SRS FR11)."""
    return jsonify(metrics.snapshot())


@app.get("/metrics")
def prom_metrics():
    metrics.snapshot()  # refresh gauges
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/chaos", methods=["GET", "POST"])
def chaos_control():
    if not chaos.enabled():
        return jsonify(error="chaos endpoints disabled"), 403
    if request.method == "POST":
        return jsonify(chaos.apply(request.get_json(silent=True) or {}))
    return jsonify(chaos.current())


@app.post("/chaos/reset")
def chaos_reset():
    if not chaos.enabled():
        return jsonify(error="chaos endpoints disabled"), 403
    return jsonify(chaos.reset())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
