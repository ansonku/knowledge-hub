import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase


class UserModelTests(TestCase):
    def test_uuid_and_default_role(self):
        user = get_user_model().objects.create_user(username="reader", email="reader@example.test")
        self.assertIsInstance(user.pk, uuid.UUID)
        self.assertEqual(user.role, "viewer")

    def test_email_is_unique(self):
        users = get_user_model().objects
        users.create_user(username="first", email="reader@example.test")
        with self.assertRaises(IntegrityError), transaction.atomic():
            users.create_user(username="second", email="reader@example.test")
