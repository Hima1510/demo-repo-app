"""Small standard-library metrics collector for JSON and Prometheus output."""
import threading
import time
from collections import defaultdict, deque

WINDOW_SECONDS = 60
_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)
_window = deque()
_lock = threading.Lock()
_requests = defaultdict(int)
_durations = defaultdict(lambda: {"count": 0, "sum": 0.0, "buckets": [0] * len(_BUCKETS)})
_cpu_sample_lock = threading.Lock()
_last_cpu_wall = time.monotonic()
_last_cpu_seconds = time.process_time()


def _cpu_percent():
    """Estimate process CPU use using Python's standard library."""
    global _last_cpu_wall, _last_cpu_seconds
    wall = time.monotonic()
    cpu = time.process_time()
    with _cpu_sample_lock:
        elapsed = wall - _last_cpu_wall
        used = cpu - _last_cpu_seconds
        _last_cpu_wall, _last_cpu_seconds = wall, cpu
    return max(0.0, used) / elapsed * 100 if elapsed > 0 else 0.0


def _memory_mb():
    """Read resident memory from Linux procfs without a third-party package."""
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def record(method, path, status, duration):
    now = time.time()
    key = (method, path, str(status))
    with _lock:
        _requests[key] += 1
        histogram = _durations[path]
        histogram["count"] += 1
        histogram["sum"] += duration
        for index, bound in enumerate(_BUCKETS):
            if duration <= bound:
                histogram["buckets"][index] += 1
        _window.append((now, status, duration))
        while _window and now - _window[0][0] > WINDOW_SECONDS:
            _window.popleft()


def snapshot():
    cpu = _cpu_percent()
    memory = _memory_mb()
    now = time.time()
    with _lock:
        recent = [row for row in _window if now - row[0] <= WINDOW_SECONDS]
    total = len(recent)
    errors = sum(1 for _, status, _ in recent if status >= 500)
    average_ms = sum(duration for _, _, duration in recent) / total * 1000 if total else 0.0
    return {
        "cpu": round(cpu, 2),
        "memory": round(memory, 2),
        "error_rate": round(errors / total, 4) if total else 0.0,
        "latency": round(average_ms, 2),
        "requests_last_60s": total,
    }


def prometheus_text():
    current = snapshot()
    lines = [
        "# HELP http_requests_total HTTP requests",
        "# TYPE http_requests_total counter",
    ]
    with _lock:
        requests = list(_requests.items())
        durations = list(_durations.items())
    for (method, path, status), count in requests:
        lines.append(
            f'http_requests_total{{method="{_escape(method)}",path="{_escape(path)}",status="{status}"}} {count}'
        )

    lines.extend((
        "# HELP http_request_duration_seconds Request latency in seconds",
        "# TYPE http_request_duration_seconds histogram",
    ))
    for path, histogram in durations:
        for bound, count in zip(_BUCKETS, histogram["buckets"]):
            lines.append(
                f'http_request_duration_seconds_bucket{{path="{_escape(path)}",le="{bound}"}} {count}'
            )
        lines.append(
            f'http_request_duration_seconds_bucket{{path="{_escape(path)}",le="+Inf"}} {histogram["count"]}'
        )
        lines.append(f'http_request_duration_seconds_sum{{path="{_escape(path)}"}} {histogram["sum"]:.6f}')
        lines.append(f'http_request_duration_seconds_count{{path="{_escape(path)}"}} {histogram["count"]}')

    lines.extend((
        "# HELP app_cpu_percent Process CPU use percent",
        "# TYPE app_cpu_percent gauge",
        f"app_cpu_percent {current['cpu']}",
        "# HELP app_memory_mb Process resident memory in MB",
        "# TYPE app_memory_mb gauge",
        f"app_memory_mb {current['memory']}",
    ))
    return "\n".join(lines) + "\n"


def _escape(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
