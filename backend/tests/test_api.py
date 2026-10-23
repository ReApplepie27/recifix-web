import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("SMTP_HOST", None)

from app import create_app  # noqa: E402


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = []
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE_URL": f"sqlite:///{self.tmp.name}/test.db",
                "MAILER": lambda to, link: self.outbox.append((to, link)),
            }
        )
        with self.app.app_context():
            self.app.extensions["db"].init_schema()
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def signup(self, client=None, name="Maria Santos", email="maria@example.com", password="secret123"):
        return (client or self.client).post(
            "/api/auth/signup", json={"fullname": name, "email": email, "password": password}
        )

    def login(self, client=None, email="maria@example.com", password="secret123"):
        return (client or self.client).post("/api/auth/login", json={"email": email, "password": password})


class SignupTests(ApiTestCase):
    def test_signup_creates_account_and_logs_in(self):
        r = self.signup()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json["user"]["name"], "Maria Santos")
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json["user"]["email"], "maria@example.com")

    def test_password_is_hashed_not_stored(self):
        self.signup()
        with self.app.app_context():
            row = self.app.extensions["db"].one("SELECT password_hash FROM users")
        self.assertNotIn("secret123", row["password_hash"])
        self.assertTrue(row["password_hash"].startswith(("scrypt:", "pbkdf2:")))

    def test_email_normalised_and_unique(self):
        self.signup(email="Maria@Example.com ")
        r = self.signup(client=self.app.test_client(), email="maria@example.com")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json["field"], "email")

    def test_validation(self):
        bad = [
            {"fullname": "", "email": "a@b.co", "password": "secret123"},
            {"fullname": "A", "email": "not-an-email", "password": "secret123"},
            {"fullname": "A", "email": "a@b.co", "password": "short"},
            {"fullname": "A", "email": "a@b.co", "password": 12345678},
            {"fullname": ["x"], "email": "a@b.co", "password": "secret123"},
            {"fullname": "x" * 101, "email": "a@b.co", "password": "secret123"},
        ]
        for payload in bad:
            r = self.client.post("/api/auth/signup", json=payload)
            self.assertEqual(r.status_code, 400, payload)
            self.assertIn("error", r.json)

    def test_non_json_body_rejected(self):
        r = self.client.post("/api/auth/signup", data={"email": "a@b.co"})
        self.assertEqual(r.status_code, 415)


class LoginTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.signup()
        self.client = self.app.test_client()  # logged out

    def test_login_success_and_logout(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_login_is_case_insensitive_on_email(self):
        self.assertEqual(self.login(email="MARIA@example.com").status_code, 200)

    def test_wrong_password_and_unknown_user_look_identical(self):
        a = self.login(password="wrongpass1")
        b = self.login(email="nobody@example.com")
        self.assertEqual((a.status_code, a.json), (401, {"error": "Incorrect email or password."}))
        self.assertEqual((b.status_code, b.json), (401, {"error": "Incorrect email or password."}))

    def test_rate_limit_after_repeated_failures(self):
        for _ in range(5):
            self.assertEqual(self.login(password="wrongpass1").status_code, 401)
        r = self.login(password="wrongpass1")
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r.headers)
        # even the correct password is blocked during the lockout
        self.assertEqual(self.login().status_code, 429)

    def test_successful_login_resets_counter(self):
        for _ in range(4):
            self.login(password="wrongpass1")
        self.assertEqual(self.login().status_code, 200)
        for _ in range(4):
            self.assertEqual(self.login(password="wrongpass1").status_code, 401)

    def test_protected_routes_require_login(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.patch("/api/account", json={"name": "X"}).status_code, 401)
        self.assertEqual(self.client.post("/api/account/password", json={}).status_code, 401)


class AccountTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.signup()

    def test_update_name_and_email(self):
        r = self.client.patch("/api/account", json={"name": "  Maria  L. Santos ", "email": "New@Example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["user"], {"id": 1, "name": "Maria L. Santos", "email": "new@example.com"})
        self.assertEqual(self.login(self.app.test_client(), email="new@example.com").status_code, 200)

    def test_cannot_take_another_accounts_email(self):
        other = self.app.test_client()
        self.signup(client=other, name="Juan", email="juan@example.com")
        r = self.client.patch("/api/account", json={"email": "juan@example.com"})
        self.assertEqual(r.status_code, 409)

    def test_update_requires_a_field(self):
        self.assertEqual(self.client.patch("/api/account", json={}).status_code, 400)

    def test_change_password(self):
        r = self.client.post(
            "/api/account/password", json={"current_password": "secret123", "new_password": "brandnew456"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)  # this device stays signed in
        fresh = self.app.test_client()
        self.assertEqual(self.login(fresh, password="secret123").status_code, 401)
        self.assertEqual(self.login(fresh, password="brandnew456").status_code, 200)

    def test_change_password_signs_out_other_devices(self):
        other = self.app.test_client()
        self.login(other)
        self.assertEqual(other.get("/api/auth/me").status_code, 200)
        self.client.post("/api/account/password", json={"current_password": "secret123", "new_password": "brandnew456"})
        self.assertEqual(other.get("/api/auth/me").status_code, 401)

    def test_change_password_checks(self):
        wrong = self.client.post("/api/account/password", json={"current_password": "nope", "new_password": "brandnew456"})
        self.assertEqual((wrong.status_code, wrong.json["field"]), (400, "current_password"))
        short = self.client.post("/api/account/password", json={"current_password": "secret123", "new_password": "abc"})
        self.assertEqual(short.status_code, 400)
        same = self.client.post("/api/account/password", json={"current_password": "secret123", "new_password": "secret123"})
        self.assertEqual(same.status_code, 400)


class ForgotPasswordTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.signup()
        self.anon = self.app.test_client()

    def request_reset(self, email="maria@example.com", pw="resetpass99"):
        return self.anon.post("/api/auth/forgot-password", json={"email": email, "new_password": pw})

    def test_password_unchanged_until_link_is_opened(self):
        r = self.request_reset()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.outbox), 1)
        self.assertEqual(self.login(self.app.test_client(), password="secret123").status_code, 200)
        self.assertEqual(self.login(self.app.test_client(), password="resetpass99").status_code, 401)

    def test_confirm_link_applies_new_password_once(self):
        self.request_reset()
        link = self.outbox[0][1]
        path = re.sub(r"^https?://[^/]+", "", link)
        r = self.anon.get(path)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("reset=success"))
        self.assertEqual(self.login(self.app.test_client(), password="resetpass99").status_code, 200)
        self.assertEqual(self.login(self.app.test_client(), password="secret123").status_code, 401)
        # token is single-use
        again = self.anon.get(path)
        self.assertTrue(again.headers["Location"].endswith("reset=invalid"))

    def test_unknown_email_gets_same_response_and_no_mail(self):
        known = self.request_reset()
        unknown = self.request_reset(email="ghost@example.com")
        self.assertEqual((known.status_code, known.json), (unknown.status_code, unknown.json))
        self.assertEqual(len(self.outbox), 1)

    def test_invalid_or_expired_token(self):
        r = self.anon.get("/api/auth/confirm-reset?token=garbage")
        self.assertTrue(r.headers["Location"].endswith("reset=invalid"))
        self.request_reset()
        with self.app.app_context():
            self.app.extensions["db"].execute("UPDATE password_resets SET expires_at = '2000-01-01 00:00:00'")
            self.app.extensions["db"].commit()
        link_path = re.sub(r"^https?://[^/]+", "", self.outbox[0][1])
        self.assertTrue(self.anon.get(link_path).headers["Location"].endswith("reset=invalid"))

    def test_cooldown_prevents_email_spam(self):
        self.request_reset()
        self.request_reset()
        self.assertEqual(len(self.outbox), 1)

    def test_weak_new_password_rejected(self):
        self.assertEqual(self.request_reset(pw="123").status_code, 400)
        self.assertEqual(len(self.outbox), 0)

    def test_reset_signs_out_existing_sessions(self):
        self.request_reset()
        self.anon.get(re.sub(r"^https?://[^/]+", "", self.outbox[0][1]))
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)


class FrontendTests(ApiTestCase):
    def test_public_pages_served(self):
        for path in ("/", "/index.html", "/pages/login.html", "/pages/signup.html", "/css/style.css", "/js/script.js"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            r.close()

    def test_dashboard_requires_login(self):
        r = self.client.get("/dashboard.html")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/pages/login.html"))
        self.signup()
        ok = self.client.get("/dashboard.html")
        self.assertEqual(ok.status_code, 200)
        self.assertIn("no-store", ok.headers["Cache-Control"])
        ok.close()

    def test_backend_source_is_not_exposed(self):
        for path in ("/backend/app.py", "/backend/.env", "/app.py", "/js/../backend/app.py", "/pages/../backend/app.py"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


if __name__ == "__main__":
    unittest.main()
