"""Recifix backend: Flask + MySQL.

Serves the existing static front end and a JSON API under /api.
"""
import hashlib
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, app, g, jsonify, redirect, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import mailer
from db import INTEGRITY_ERRORS, Database

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_FRONTEND_DIR = BACKEND_DIR.parent

MIN_PASSWORD = 8
MAX_PASSWORD = 128
RESET_TTL = timedelta(hours=1)
RESET_COOLDOWN_SECONDS = 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Used so that logging in with an unknown email takes as long as a real check.
_DUMMY_HASH = generate_password_hash("recifix-dummy-password")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class AttemptLimiter:
    """Process-local failed-login limiter (use Redis or similar if you run many workers)."""

    def __init__(self, max_attempts=5, window_seconds=900):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits = {}
        self._lock = threading.Lock()

    def _prune(self, key, now):
        self._hits[key] = [t for t in self._hits.get(key, []) if now - t < self.window]
        if not self._hits[key]:
            del self._hits[key]

    def retry_after(self, key) -> int:
        """Seconds until the key may try again (0 if not blocked)."""
        now = time.time()
        with self._lock:
            self._prune(key, now)
            hits = self._hits.get(key, [])
            if len(hits) >= self.max_attempts:
                return int(self.window - (now - hits[0])) + 1
            return 0

    def fail(self, key):
        with self._lock:
            self._hits.setdefault(key, []).append(time.time())

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)


# ---------- validation helpers ----------
class ValidationError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def clean_name(value):
    if not isinstance(value, str):
        raise ValidationError("Please enter your full name.", "fullname")
    name = " ".join(value.split())
    if not name:
        raise ValidationError("Please enter your full name.", "fullname")
    if len(name) > 100:
        raise ValidationError("Name must be 100 characters or fewer.", "fullname")
    return name


def clean_email(value):
    email = value.strip().lower() if isinstance(value, str) else ""
    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        raise ValidationError("Please enter a valid email address.", "email")
    return email


def clean_password(value, field="password"):
    if not isinstance(value, str) or len(value) < MIN_PASSWORD:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD} characters.", field)
    if len(value) > MAX_PASSWORD:
        raise ValidationError(f"Password must be {MAX_PASSWORD} characters or fewer.", field)
    return value


def pw_version(password_hash: str) -> str:
    """Fingerprint stored in the session so a password change signs out other devices."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def public_user(row: dict) -> dict:
    return {"id": row["id"], "name": row["full_name"], "email": row["email"]}


def create_app(overrides=None) -> Flask:
    load_dotenv(BACKEND_DIR / ".env")
    app = Flask(__name__, static_folder=None)

    secret = os.environ.get("SECRET_KEY", "").strip()
    if not secret and _env_bool("FLASK_DEBUG"):
        secret = secrets.token_hex(32)  # dev only: sessions reset on every restart

    app.config.update(
        SECRET_KEY=secret,
        DATABASE_URL=os.environ.get("DATABASE_URL", "mysql://recifix:password@127.0.0.1:3306/recifix"),
        BASE_URL=os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/"),
        FRONTEND_DIR=os.environ.get("FRONTEND_DIR", str(DEFAULT_FRONTEND_DIR)),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_env_bool("SESSION_COOKIE_SECURE"),
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        MAX_CONTENT_LENGTH=16 * 1024,
        SMTP_HOST=os.environ.get("SMTP_HOST", ""),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USER=os.environ.get("SMTP_USER", ""),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD", ""),
        SMTP_STARTTLS=_env_bool("SMTP_STARTTLS", True),
        MAIL_FROM=os.environ.get("MAIL_FROM", "Recifix <no-reply@localhost>"),
        MAILER=None,  # tests inject a callable(to, link)
    )
    if overrides:
        app.config.update(overrides)

    if not app.config["SECRET_KEY"]:
        raise RuntimeError(
            "SECRET_KEY is not set. Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_hex(32))"\n'
            "and put it in backend/.env (see .env.example)."
        )

    db = Database(app.config["DATABASE_URL"])
    app.extensions["db"] = db
    login_limiter = AttemptLimiter()
    app.extensions["login_limiter"] = login_limiter
    app.teardown_appcontext(db.close)

    # 🤖 OPTIMIZED RECIFIX ML CACHE SETUP
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b")
    recipes_cache = []
    tfidf_matrix = None

    # 🟢 WRAP IN AN APP CONTEXT SO EXTERNAL TOOLS (init_db.py) DON'T CRASH
    with app.app_context():
        try:
            query = """
                SELECT 
                    r.id, 
                    r.name AS title, 
                    r.image,
                    GROUP_CONCAT(REPLACE(REPLACE(i.match_spec, ';', ' '), '|', ' '), ' ') AS ingredients_blob
                FROM recipes r
                JOIN recipe_ingredients i ON r.id = i.recipe_id
                GROUP BY r.id, r.name, r.image
            """
            
            rows = db.all(query)
            if rows:
                recipes_cache = rows
                corpus = [r["ingredients_blob"] for r in rows]
                tfidf_matrix = vectorizer.fit_transform(corpus)
                app.logger.info("🤖 Recifix user taste-profile ML engine successfully loaded!")
        except Exception as e:
            app.logger.error(f"Recipe ML vectorizer initialization bypass: {e}")

    frontend = Path(app.config["FRONTEND_DIR"]).resolve()

    # ---------- plumbing ----------
    def error(message, status, field=None, **extra):
        body = {"error": message}
        if field:
            body["field"] = field
        body.update(extra)
        return jsonify(body), status

    @app.before_request
    def require_json_for_writes():
        # Browsers can't send application/json cross-site without a CORS preflight,
        # so this (plus SameSite=Lax cookies) blocks CSRF on the API.
        if request.path.startswith("/api/") and request.method in ("POST", "PATCH", "PUT", "DELETE"):
            if request.content_length and not request.is_json:
                return error("Requests must be sent as JSON.", 415)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")  # login page is framed by the landing page
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if request.path.startswith("/api/"):
            return error(exc.description or exc.name, exc.code)
        return exc

    @app.errorhandler(Exception)
    def unhandled(exc):
        app.logger.exception("Unhandled error")
        if request.path.startswith("/api/"):
            return error("Something went wrong. Please try again.", 500)
        return "Internal server error", 500

    def body_json():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValidationError("Invalid request.")
        return data

    @app.errorhandler(ValidationError)
    def validation_error(exc):
        return error(exc.message, 400, exc.field)

    def current_user():
        uid = session.get("user_id")
        if not uid:
            return None
        row = db.one("SELECT * FROM users WHERE id = %s", (uid,))
        if row is None or session.get("pv") != pw_version(row["password_hash"]):
            session.clear()
            return None
        return row

    def login_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return error("Please log in to continue.", 401)
            g.user = user
            return view(*args, **kwargs)

        return wrapper

    def start_session(user_row):
        session.clear()  # new session on every login (prevents fixation)
        session["user_id"] = user_row["id"]
        session["pv"] = pw_version(user_row["password_hash"])
        session.permanent = True

    # ---------- auth API ----------
    @app.post("/api/auth/signup")
    def signup():
        data = body_json()
        name = clean_name(data.get("fullname"))
        email = clean_email(data.get("email"))
        password = clean_password(data.get("password"))

        if db.one("SELECT id FROM users WHERE email = %s", (email,)):
            return error("An account with this email already exists. Try logging in.", 409, "email")

        now = fmt(utcnow())
        try:
            user_id, _ = db.execute(
                "INSERT INTO users (full_name, email, password_hash, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (name, email, generate_password_hash(password), now, now),
            )
            db.commit()
        except INTEGRITY_ERRORS:  # two signups racing on the same email
            return error("An account with this email already exists. Try logging in.", 409, "email")

        user = db.one("SELECT * FROM users WHERE id = %s", (user_id,))
        start_session(user)
        return jsonify({"ok": True, "user": public_user(user)}), 201

    @app.post("/api/auth/login")
    def login():
        data = body_json()
        email_raw = data.get("email")
        password = data.get("password")
        if not isinstance(email_raw, str) or not isinstance(password, str) or not email_raw.strip() or not password:
            return error("Enter your email and password.", 400)

        email = email_raw.strip().lower()[:254]
        key = f"{request.remote_addr}|{email}"
        wait = login_limiter.retry_after(key)
        if wait:
            resp = error("Too many failed attempts. Please try again later.", 429, retry_after=wait)
            resp[0].headers["Retry-After"] = str(wait)
            return resp

        user = db.one("SELECT * FROM users WHERE email = %s", (email,))
        if user:
            valid = check_password_hash(user["password_hash"], password)
        else:
            check_password_hash(_DUMMY_HASH, password)
            valid = False

        if not valid:
            login_limiter.fail(key)
            return error("Incorrect email or password.", 401)

        login_limiter.reset(key)
        start_session(user)
        return jsonify({"ok": True, "user": public_user(user)})

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/auth/me")
    @login_required
    def me():
        return jsonify({"user": public_user(g.user)})

    # ---------- forgot password (confirmed by emailed link) ----------
    @app.post("/api/auth/forgot-password")
    def forgot_password():
        data = body_json()
        email = clean_email(data.get("email"))
        new_password = clean_password(data.get("new_password"), "new_password")
        generic = jsonify(
            {
                "ok": True,
                "message": "If an account exists for that email, we've sent a link to confirm the new password.",
            }
        )

        now = utcnow()
        db.execute("DELETE FROM password_resets WHERE expires_at < %s", (fmt(now),))
        user = db.one("SELECT * FROM users WHERE email = %s", (email,))
        if user is None:
            db.commit()
            return generic

        recent = db.one(
            "SELECT id FROM password_resets WHERE user_id = %s AND created_at > %s",
            (user["id"], fmt(now - timedelta(seconds=RESET_COOLDOWN_SECONDS))),
        )
        if recent:  # avoid using this form to spam someone's inbox
            db.commit()
            return generic

        token = secrets.token_urlsafe(32)
        db.execute("DELETE FROM password_resets WHERE user_id = %s", (user["id"],))
        db.execute(
            "INSERT INTO password_resets (user_id, token_hash, new_password_hash, expires_at, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                user["id"],
                hashlib.sha256(token.encode()).hexdigest(),
                generate_password_hash(new_password),
                fmt(now + RESET_TTL),
                fmt(now),
            ),
        )
        db.commit()

        link = f"{app.config['BASE_URL']}/api/auth/confirm-reset?token={token}"
        send = app.config["MAILER"] or (lambda to, url: mailer.send_reset_email(app, to, url))
        send(user["email"], link)
        return generic

    @app.get("/api/auth/confirm-reset")
    def confirm_reset():
        token = request.args.get("token", "")
        row = db.one(
            "SELECT * FROM password_resets WHERE token_hash = %s AND expires_at > %s",
            (hashlib.sha256(token.encode()).hexdigest(), fmt(utcnow())),
        )
        if row is None:
            return redirect("/pages/login.html?reset=invalid")

        db.execute(
            "UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
            (row["new_password_hash"], fmt(utcnow()), row["user_id"]),
        )
        db.execute("DELETE FROM password_resets WHERE user_id = %s", (row["user_id"],))
        db.commit()
        return redirect("/pages/login.html?reset=success")

    # ---------- account API ----------
    @app.patch("/api/account")
    @login_required
    def update_account():
        data = body_json()
        if "name" not in data and "email" not in data:
            raise ValidationError("Nothing to update.")
        name = clean_name(data["name"]) if "name" in data else g.user["full_name"]
        email = clean_email(data["email"]) if "email" in data else g.user["email"]

        try:
            db.execute(
                "UPDATE users SET full_name = %s, email = %s, updated_at = %s WHERE id = %s",
                (name, email, fmt(utcnow()), g.user["id"]),
            )
            db.commit()
        except INTEGRITY_ERRORS:
            return error("That email is already used by another account.", 409, "email")

        user = db.one("SELECT * FROM users WHERE id = %s", (g.user["id"],))
        return jsonify({"ok": True, "user": public_user(user)})

    @app.post("/api/account/password")
    @login_required
    def change_password():
        data = body_json()
        current = data.get("current_password")
        if not isinstance(current, str) or not check_password_hash(g.user["password_hash"], current):
            return error("Your current password is incorrect.", 400, "current_password")
        new_password = clean_password(data.get("new_password"), "new_password")
        if new_password == current:
            return error("Choose a password different from your current one.", 400, "new_password")

        new_hash = generate_password_hash(new_password)
        db.execute(
            "UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
            (new_hash, fmt(utcnow()), g.user["id"]),
        )
        db.execute("DELETE FROM password_resets WHERE user_id = %s", (g.user["id"],))
        db.commit()

        user = db.one("SELECT * FROM users WHERE id = %s", (g.user["id"],))
        start_session(user)  # keeps this device signed in; other devices are signed out
        return jsonify({"ok": True})

    # ---------- recipes ----------
    from recipes import register_recipe_routes

    register_recipe_routes(app, db, login_required, error)

    # ---------- front end ----------
    def page(name):
        return send_from_directory(frontend, name)

    @app.get("/")
    @app.get("/index.html")
    def landing():
        return page("index.html")

    @app.get("/dashboard.html")
    def dashboard():
        if current_user() is None:
            return redirect("/pages/login.html")
        resp = page("dashboard.html")
        resp.headers["Cache-Control"] = "no-store"  # don't show it from cache after logout
        return resp

    @app.get("/<any(css,js,images,pages):folder>/<path:filename>")
    def assets(folder, filename):
        return send_from_directory(frontend / folder, filename)

# 🤖 RECIFIX PERSONALIZED HISTORY ML ENGINE ROUTE
    @app.route("/api/recipes/recommend", methods=["POST"])
    def recommend_recipes():
        nonlocal tfidf_matrix, recipes_cache, vectorizer
        
        if tfidf_matrix is None or not recipes_cache:
            return error("The recommendation matrix engine is currently empty or updating.", 503)

        uid = session.get("user_id")
        user_saved_keywords = []

        if uid:
            # Gathers the taste keywords from recipes the logged-in user has saved
            saved_query = """
                SELECT REPLACE(REPLACE(i.match_spec, ';', ' '), '|', ' ') AS clean_keywords
                FROM saved_recipes s
                JOIN recipe_ingredients i ON s.recipe_id = i.recipe_id
                WHERE s.user_id = %s
            """
            try:
                saved_rows = db.all(saved_query, (uid,))
                user_saved_keywords = [row["clean_keywords"] for row in saved_rows]
            except Exception as e:
                app.logger.error(f"Error fetching user saved history matrix: {e}")

        # Determine personalization state
        if user_saved_keywords:
            query_ingredients = " ".join(user_saved_keywords)
            is_personalized = True
        else:
            # Baseline fallback staples if user hasn't saved anything yet
            query_ingredients = "garlic onion olive oil salt pepper flour"
            is_personalized = False

        # Transform and calculate geometric cosine distance metrics
        user_vector = vectorizer.transform([query_ingredients])
        similarity_scores = cosine_similarity(user_vector, tfidf_matrix).flatten()

        scored_recipes = []
        for index, score in enumerate(similarity_scores):
            recipe = recipes_cache[index]
            
            # Exclude items they have already saved from cluttering their recommendations section
            if uid and is_personalized:
                already_saved = db.one("SELECT 1 FROM saved_recipes WHERE user_id = %s AND recipe_id = %s", (uid, recipe["id"]))
                if already_saved:
                    continue

            if score > 0.02:
                scored_recipes.append((score, recipe))

        # Sort from highest mathematical similarity down to lowest
        scored_recipes.sort(key=lambda x: x[0], reverse=True)

        top_matches = []
        for score, recipe in scored_recipes[:3]:
            top_matches.append({
                "id": recipe["id"],
                "title": recipe["title"],
                "image": recipe["image"], # Added this mapping value
                "match_percentage": int(round(float(score) * 100))
            })

        return jsonify({
            "recipes": top_matches, 
            "personalized": is_personalized
        })
        
    # FETCH FULL RECIPE DETAILS FOR THE MODAL VIEWER
    @app.route("/api/recipes/<int:recipe_id>", methods=["GET"])
    def get_recipe_details(recipe_id):
        # 1. Fetch primary recipe details
        recipe = db.one("SELECT id, name, description, image, prep_minutes, cook_minutes, servings, difficulty FROM recipes WHERE id = %s", (recipe_id,))
        if not recipe:
            return error("Recipe not found.", 404)

        # 2. Fetch linked structural ingredient listings with safe explicit tuple parameters
        ingredients = db.all("SELECT display FROM recipe_ingredients WHERE recipe_id = %s ORDER BY position", (recipe_id,))
        
        # 3. Fetch step-by-step procedures with safe explicit tuple parameters
        steps = db.all("SELECT body FROM recipe_steps WHERE recipe_id = %s ORDER BY position", (recipe_id,))

        # 🟢 SECURE FORMAT RETRIEVAL DEFENSE LAYER
        return jsonify({
            "id": int(recipe["id"]),
            "title": recipe["name"],
            "description": recipe["description"],
            "image": recipe["image"] or "images/intro-image.jpg",
            "prep_time": recipe["prep_minutes"] or 0,
            "cook_time": recipe["cook_minutes"] or 0,
            "servings": recipe["servings"] or 2,
            "difficulty": recipe["difficulty"] or "Easy",
            "ingredients": [i["display"] for i in ingredients] if ingredients else [],
            "steps": [s["body"] for s in steps] if steps else []
        })
    return app
