"""Demo web service implemented with Python's standard library only."""
import json
import os
import threading
import time
from http import HTTPStatus
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from app import chaos, metrics

START_TIME = time.time()
INFRA_PATHS = {"/healthz", "/readyz", "/metrics", "/chaos", "/chaos/reset", "/api/stats"}
_items = [{"id": 1, "name": "first item"}]
_items_lock = threading.Lock()


def _json(data, status=200):
    return status, "application/json; charset=utf-8", json.dumps(data).encode("utf-8")


def _read_json(environ):
    try:
        size = min(max(int(environ.get("CONTENT_LENGTH") or 0), 0), 1_048_576)
        value = json.loads(environ["wsgi.input"].read(size) or b"{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError, UnicodeDecodeError):
        return {}


def _dispatch(method, path, environ):
    if path == "/" and method == "GET":
        return _json({
            "service": "demo-deploy-app",
            "message": "Hello from the Predictive Auto Deployment Platform demo app",
            "version": os.environ.get("APP_VERSION", "dev"),
            "endpoints": ["/healthz", "/readyz", "/version", "/api/items", "/api/stats", "/metrics", "/chaos"],
        })
    if path == "/healthz" and method == "GET":
        return _json({"status": "ok"})
    if path == "/readyz" and method == "GET":
        return _json({"status": "ready"})
    if path == "/version" and method == "GET":
        return _json({
            "version": os.environ.get("APP_VERSION", "dev"),
            "git_sha": os.environ.get("GIT_SHA", "unknown"),
            "uptime_seconds": round(time.time() - START_TIME, 1),
        })
    if path == "/api/items" and method == "GET":
        with _items_lock:
            return _json({"items": list(_items)})
    if path == "/api/items" and method == "POST":
        name = str(_read_json(environ).get("name", "")).strip()
        if not name:
            return _json({"error": "name is required"}, 400)
        with _items_lock:
            item = {"id": len(_items) + 1, "name": name}
            _items.append(item)
        return _json({"item": item}, 201)
    if path == "/api/stats" and method == "GET":
        return _json(metrics.snapshot())
    if path == "/metrics" and method == "GET":
        return 200, "text/plain; version=0.0.4; charset=utf-8", metrics.prometheus_text().encode("utf-8")
    if path == "/chaos" and method in {"GET", "POST"}:
        if not chaos.enabled():
            return _json({"error": "chaos endpoints disabled"}, 403)
        if method == "POST":
            return _json(chaos.apply(_read_json(environ)))
        return _json(chaos.current())
    if path == "/chaos/reset" and method == "POST":
        if not chaos.enabled():
            return _json({"error": "chaos endpoints disabled"}, 403)
        return _json(chaos.reset())
    known_paths = {
        "/", "/healthz", "/readyz", "/version", "/api/items", "/api/stats",
        "/metrics", "/chaos", "/chaos/reset",
    }
    if path in known_paths:
        return _json({"error": "method not allowed"}, 405)
    return _json({"error": "not found"}, 404)


def app(environ, start_response):
    """WSGI application callable, usable by the platform and stdlib server."""
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/")
    started = time.perf_counter()
    if path not in INFRA_PATHS and chaos.maybe_fail_or_delay():
        result = _json({"error": "injected failure"}, 500)
    else:
        result = _dispatch(method, path, environ)

    status, content_type, body = result
    metrics.record(method, path, status, time.perf_counter() - started)
    phrase = HTTPStatus(status).phrase
    start_response(f"{status} {phrase}", [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
    ])
    return [body]


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main():
    port = int(os.environ.get("PORT", "8080"))
    with make_server("0.0.0.0", port, app, server_class=_ThreadingWSGIServer) as server:
        print(f"Serving demo-deploy-app on 0.0.0.0:{port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
