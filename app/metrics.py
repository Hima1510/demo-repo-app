"""Metrics: Prometheus counters/histograms plus a rolling 60s JSON summary
(CPU, memory, error rate, latency) matching the SRS Metric table."""
import threading
import time
from collections import deque

import psutil
from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds", "Request latency in seconds", ["path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
CPU = Gauge("app_cpu_percent", "Process CPU usage percent")
MEMORY = Gauge("app_memory_mb", "Process resident memory in MB")

_proc = psutil.Process()
_proc.cpu_percent(None)  # prime
_window = deque()  # (timestamp, status, duration_seconds)
_lock = threading.Lock()
WINDOW_SECONDS = 60


def record(method, path, status, duration):
    REQUESTS.labels(method, path, str(status)).inc()
    LATENCY.labels(path).observe(duration)
    now = time.time()
    with _lock:
        _window.append((now, status, duration))
        while _window and now - _window[0][0] > WINDOW_SECONDS:
            _window.popleft()


def snapshot():
    cpu = _proc.cpu_percent(None)
    mem = _proc.memory_info().rss / (1024 * 1024)
    CPU.set(cpu)
    MEMORY.set(mem)
    now = time.time()
    with _lock:
        recent = [r for r in _window if now - r[0] <= WINDOW_SECONDS]
    total = len(recent)
    errors = sum(1 for _, s, _ in recent if s >= 500)
    avg_ms = (sum(d for _, _, d in recent) / total * 1000) if total else 0.0
    return {
        "cpu": round(cpu, 2),
        "memory": round(mem, 2),
        "error_rate": round(errors / total, 4) if total else 0.0,
        "latency": round(avg_ms, 2),
        "requests_last_60s": total,
    }
