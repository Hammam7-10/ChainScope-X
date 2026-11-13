import unittest

from app.main import app, health


class FoundationTests(unittest.TestCase):
    def test_health_payload(self):
        self.assertEqual(health(), {"status": "ok", "service": "chainscope-x"})

    def test_expected_routes_are_registered(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/", paths)
        self.assertIn("/health", paths)
        self.assertIn("/static", paths)

    def test_health_is_explicitly_a_get_route(self):
        route = next(route for route in app.routes if route.path == "/health")
        self.assertEqual(route.methods, {"GET"})


if __name__ == "__main__":
    unittest.main()
