"""Fault injection so the platform's anomaly detection and auto-rollback can be
tested on demand. Controlled via POST /chaos (disable with ENABLE_CHAOS=false)."""
import os
import random
import threading
import time

from app import release

_state = {"error_rate": 0.0, "latency_ms": 0, "cpu_burn": False, "memory_leak_mb": 0}
_leak = []
_lock = threading.Lock()
MAX_LEAK_MB = 200


def enabled():
    return os.environ.get("ENABLE_CHAOS", "true").lower() == "true"


def _burn():
    while _state["cpu_burn"]:
        sum(i * i for i in range(20000))


def apply(new):
    with _lock:
        if "error_rate" in new:
            _state["error_rate"] = min(max(float(new["error_rate"]), 0.0), 1.0)
        if "latency_ms" in new:
            _state["latency_ms"] = min(max(int(new["latency_ms"]), 0), 10000)
        if "memory_leak_mb" in new:
            target = min(max(int(new["memory_leak_mb"]), 0), MAX_LEAK_MB)
            while len(_leak) < target:
                _leak.append(bytearray(1024 * 1024))
            while len(_leak) > target:
                _leak.pop()
            _state["memory_leak_mb"] = target
        if "cpu_burn" in new:
            want = bool(new["cpu_burn"])
            if want and not _state["cpu_burn"]:
                _state["cpu_burn"] = True
                threading.Thread(target=_burn, daemon=True).start()
            elif not want:
                _state["cpu_burn"] = False
    return dict(_state)


def reset():
    return apply({"error_rate": 0, "latency_ms": 0, "memory_leak_mb": 0, "cpu_burn": False})


def current():
    return dict(_state)


def effective():
    """Faults to apply to a request: runtime chaos plus the faulty-release switch."""
    err, lat = _state["error_rate"], _state["latency_ms"]
    if release.FAULTY_RELEASE:
        err, lat = max(err, 0.5), max(lat, 800)
    return err, lat


def maybe_fail_or_delay():
    """Returns True if this request should fail with a 500."""
    err, lat = effective()
    if lat:
        time.sleep(lat / 1000.0)
    return err > 0 and random.random() < err
