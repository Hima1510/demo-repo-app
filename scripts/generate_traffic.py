#!/usr/bin/env python3
"""Send steady traffic to the app so the platform has live metrics to monitor.

Usage: python scripts/generate_traffic.py http://localhost:8080 [rps] [seconds]
"""
import sys
import time
import urllib.error
import urllib.request

base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
rps = float(sys.argv[2]) if len(sys.argv) > 2 else 5
duration = int(sys.argv[3]) if len(sys.argv) > 3 else 60
paths = ["/", "/api/items", "/version"]

ok = err = 0
end = time.time() + duration
i = 0
while time.time() < end:
    try:
        urllib.request.urlopen(base + paths[i % len(paths)], timeout=5).read()
        ok += 1
    except (urllib.error.URLError, TimeoutError):
        err += 1
    i += 1
    time.sleep(1 / rps)
print(f"done: {ok} ok, {err} errors")
