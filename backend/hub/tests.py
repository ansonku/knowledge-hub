from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase


class HealthTests(TestCase):
    def test_public_health_with_database(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_database_failure_returns_generic_response(self):
        with patch("hub.views.connection.cursor", side_effect=OperationalError("private detail")):
            response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})

    def test_cannot_post(self):
        self.assertEqual(self.client.post("/api/health").status_code, 405)
