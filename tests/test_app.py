"""Dependency-free tests for the WSGI app."""
import io
import json
import unittest

from app import chaos, release
from app.main import app


def request(path, method="GET", data=None):
    body = json.dumps(data).encode("utf-8") if data is not None else b""
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/json",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8080",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.StringIO(),
        "wsgi.multithread": True,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }
    result = {}

    def start_response(status, headers):
        result["status"] = int(status.split()[0])
        result["headers"] = dict(headers)

    result["body"] = b"".join(app(environ, start_response))
    result["json"] = json.loads(result["body"]) if "json" in result["headers"].get("Content-Type", "") else None
    return result


class AppTests(unittest.TestCase):
    def setUp(self):
        chaos.reset()
        release.FAULTY_RELEASE = False

    def tearDown(self):
        chaos.reset()

    def test_index(self):
        response = request("/")
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["json"]["service"], "demo-deploy-app")

    def test_health_and_ready(self):
        self.assertEqual(request("/healthz")["json"], {"status": "ok"})
        self.assertEqual(request("/readyz")["json"], {"status": "ready"})

    def test_version(self):
        body = request("/version")["json"]
        self.assertTrue({"version", "git_sha", "uptime_seconds"} <= body.keys())

    def test_items_create_and_list(self):
        created = request("/api/items", "POST", {"name": "demo"})
        self.assertEqual(created["status"], 201)
        names = [item["name"] for item in request("/api/items")["json"]["items"]]
        self.assertIn("demo", names)

    def test_items_validation(self):
        self.assertEqual(request("/api/items", "POST", {})["status"], 400)

    def test_stats_has_required_metrics(self):
        request("/")
        body = request("/api/stats")["json"]
        self.assertTrue({"cpu", "memory", "error_rate", "latency"} <= body.keys())

    def test_prometheus_metrics(self):
        request("/")
        text = request("/metrics")["body"].decode("utf-8")
        self.assertIn("http_requests_total", text)
        self.assertIn("http_request_duration_seconds", text)

    def test_injected_errors_show_in_error_rate(self):
        request("/chaos", "POST", {"error_rate": 1.0})
        for _ in range(5):
            self.assertEqual(request("/")["status"], 500)
        self.assertEqual(request("/healthz")["status"], 200)
        self.assertGreater(request("/api/stats")["json"]["error_rate"], 0)

    def test_chaos_reset(self):
        request("/chaos", "POST", {"error_rate": 1.0})
        request("/chaos/reset", "POST")
        self.assertEqual(request("/")["status"], 200)

    def test_release_is_healthy(self):
        self.assertFalse(release.FAULTY_RELEASE)


if __name__ == "__main__":
    unittest.main()
