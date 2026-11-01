"""
accounts/tests/test_auth.py

Phase 1 test suite — covers all authentication endpoints.
Uses Django's TestCase + DRF's APIClient.
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from apps.accounts.models import UserRole, OrganizerProfile, AttendeeProfile

User = get_user_model()


class AttendeeRegistrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("attendee-register")
        self.valid_payload = {
            "email": "attendee@test.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "phone_number": "+254712345678",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }

    def test_successful_registration_returns_201_and_tokens(self):
        response = self.client.post(self.url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["role"], UserRole.ATTENDEE)

    def test_registration_creates_attendee_profile(self):
        self.client.post(self.url, self.valid_payload, format="json")
        user = User.objects.get(email="attendee@test.com")
        self.assertTrue(AttendeeProfile.objects.filter(user=user).exists())

    def test_duplicate_email_returns_400(self):
        self.client.post(self.url, self.valid_payload, format="json")
        response = self.client.post(self.url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_mismatch_returns_400(self):
        payload = {**self.valid_payload, "password_confirm": "WrongPass123!"}
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weak_password_returns_400(self):
        payload = {**self.valid_payload, "password": "123", "password_confirm": "123"}
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_email_returns_400(self):
        payload = {**self.valid_payload}
        del payload["email"]
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class OrganizerRegistrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("organizer-register")
        self.valid_payload = {
            "email": "organizer@test.com",
            "first_name": "John",
            "last_name": "Smith",
            "phone_number": "+254799000000",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "organization_name": "Nairobi Events Ltd",
            "bio": "We organize the best events in Nairobi.",
            "website": "https://nairobievents.co.ke",
        }

    def test_organizer_registration_returns_201_not_approved(self):
        response = self.client.post(self.url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["user"]["is_approved"])
        self.assertEqual(response.data["user"]["role"], UserRole.ORGANIZER)

    def test_organizer_profile_created(self):
        self.client.post(self.url, self.valid_payload, format="json")
        user = User.objects.get(email="organizer@test.com")
        self.assertTrue(OrganizerProfile.objects.filter(user=user).exists())
        profile = OrganizerProfile.objects.get(user=user)
        self.assertEqual(profile.organization_name, "Nairobi Events Ltd")

    def test_organizer_does_not_receive_tokens(self):
        """Organizers must be approved first — no instant login."""
        response = self.client.post(self.url, self.valid_payload, format="json")
        self.assertNotIn("access", response.data)


class LoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("login")
        self.user = User.objects.create_user(
            email="user@test.com",
            password="SecurePass123!",
            first_name="Test",
            last_name="User",
        )

    def test_valid_login_returns_tokens_and_user(self):
        response = self.client.post(
            self.url,
            {"email": "user@test.com", "password": "SecurePass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["role"], UserRole.ATTENDEE)

    def test_login_embeds_role_in_token(self):
        """Decode the access token and confirm role is in the payload."""
        import jwt
        from django.conf import settings
        response = self.client.post(
            self.url,
            {"email": "user@test.com", "password": "SecurePass123!"},
            format="json",
        )
        access = response.data["access"]
        payload = jwt.decode(access, options={"verify_signature": False})
        self.assertEqual(payload["role"], UserRole.ATTENDEE)
        self.assertIn("full_name", payload)
        self.assertIn("email", payload)

    def test_wrong_password_returns_401(self):
        response = self.client.post(
            self.url,
            {"email": "user@test.com", "password": "wrongpassword"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_nonexistent_user_returns_401(self):
        response = self.client.post(
            self.url,
            {"email": "ghost@test.com", "password": "SecurePass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post(
            self.url,
            {"email": "user@test.com", "password": "SecurePass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class LogoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="user@test.com",
            password="SecurePass123!",
            first_name="Test",
            last_name="User",
        )
        login_response = self.client.post(
            reverse("login"),
            {"email": "user@test.com", "password": "SecurePass123!"},
            format="json",
        )
        self.access = login_response.data["access"]
        self.refresh = login_response.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def test_logout_blacklists_refresh_token(self):
        response = self.client.post(
            reverse("logout"), {"refresh": self.refresh}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_blacklisted_token_cannot_refresh(self):
        self.client.post(reverse("logout"), {"refresh": self.refresh}, format="json")
        response = self.client.post(
            reverse("token-refresh"), {"refresh": self.refresh}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_without_token_returns_400(self):
        response = self.client.post(reverse("logout"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="profile@test.com",
            password="SecurePass123!",
            first_name="Profile",
            last_name="User",
        )
        login = self.client.post(
            reverse("login"),
            {"email": "profile@test.com", "password": "SecurePass123!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    def test_get_own_profile(self):
        response = self.client.get(reverse("my-profile"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "profile@test.com")

    def test_patch_own_profile(self):
        response = self.client.patch(
            reverse("my-profile"),
            {"first_name": "Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Updated")

    def test_cannot_change_role_via_profile_update(self):
        response = self.client.patch(
            reverse("my-profile"),
            {"role": UserRole.SUPER_ADMIN},
            format="json",
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, UserRole.ATTENDEE)

    def test_unauthenticated_profile_access_returns_401(self):
        self.client.credentials()
        response = self.client.get(reverse("my-profile"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password(self):
        response = self.client.post(
            reverse("change-password"),
            {
                "current_password": "SecurePass123!",
                "new_password": "NewSecurePass456!",
                "new_password_confirm": "NewSecurePass456!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewSecurePass456!"))

    def test_wrong_current_password_blocked(self):
        response = self.client.post(
            reverse("change-password"),
            {
                "current_password": "WRONGPASSWORD",
                "new_password": "NewSecurePass456!",
                "new_password_confirm": "NewSecurePass456!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PermissionTests(TestCase):
    """Verify role-based access control is enforced."""

    def setUp(self):
        self.client = APIClient()
        self.attendee = User.objects.create_user(
            email="attendee@test.com", password="Pass123!",
            first_name="A", last_name="T",
        )
        self.admin = User.objects.create_superuser(
            email="admin@test.com", password="AdminPass123!",
            first_name="Super", last_name="Admin",
        )

    def _login(self, user):
        response = self.client.post(
            reverse("login"),
            {"email": user.email, "password": "Pass123!" if not user.is_superuser else "AdminPass123!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_attendee_cannot_access_admin_user_list(self):
        self._login(self.attendee)
        response = self.client.get(reverse("admin-user-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_access_admin_user_list(self):
        self._login(self.admin)
        response = self.client.get(reverse("admin-user-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unauthenticated_cannot_access_admin(self):
        self.client.credentials()
        response = self.client.get(reverse("admin-user-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
