"""The sign-up admin shows removal requests that came from a phone that does not own the sign-up, so the owner can act."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from talks.models import AppSignup
from talks.tests_fix_admin import PLAIN_STATIC


@override_settings(STORAGES=PLAIN_STATIC)  # admin pages link their stylesheets; tests have no collected static files
class SignupRemovalRequestAdminTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser("owner", "owner@example.com", "a-long-test-password"))
        self.asked = AppSignup.objects.create(email="asked@example.com", removal_requested_at=timezone.now())
        AppSignup.objects.create(email="quiet@example.com")

    def test_the_list_shows_the_request_and_can_be_narrowed_to_them(self):
        page = self.client.get("/admin/talks/appsignup/")
        self.assertContains(page, "Removal asked")
        only = self.client.get("/admin/talks/appsignup/?removal_requested_at__isempty=0")
        self.assertContains(only, "asked@example.com")
        self.assertNotContains(only, "quiet@example.com")

    def test_clearing_the_request_keeps_the_sign_up(self):
        res = self.client.post("/admin/talks/appsignup/", {"action": "clear_removal_request", "_selected_action": [self.asked.pk]}, follow=True)
        self.assertEqual(res.status_code, 200)
        self.asked.refresh_from_db()
        self.assertIsNone(self.asked.removal_requested_at)
        self.assertEqual(AppSignup.objects.count(), 2)  # nothing was deleted
