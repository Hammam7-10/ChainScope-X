import unittest

from app.main import app, health
from app.api.v1 import router as api_v1_router


class FoundationTests(unittest.TestCase):
    def test_health_payload(self):
        self.assertEqual(health(), {"status": "ok", "service": "chainscope-x"})

    def test_expected_routes_are_registered(self):
        paths = {getattr(route, "path", None) for route in app.routes}
        paths.update(getattr(route, "path", None) for route in api_v1_router.routes)
        self.assertIn("/", paths)
        self.assertIn("/health", paths)
        self.assertIn("/api/v1/analysis-runs", paths)
        self.assertIn("/static", paths)

    def test_health_is_explicitly_a_get_route(self):
        route = next(route for route in app.routes if getattr(route, "path", None) == "/health")
        self.assertEqual(route.methods, {"GET"})


if __name__ == "__main__":
    unittest.main()
