"""Small database layer.

Production target is MySQL via PyMySQL. SQLite is supported only so the test
suite can run without a MySQL server. All SQL in the app is written with %s
placeholders and standard syntax so it runs on both.
"""
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from flask import g

INTEGRITY_ERRORS = (sqlite3.IntegrityError,)
try:  # PyMySQL is only needed when talking to MySQL
    import pymysql
    import pymysql.cursors

    INTEGRITY_ERRORS += (pymysql.err.IntegrityError,)
except ImportError:  # pragma: no cover
    pymysql = None

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    new_password_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    meal_course TEXT NOT NULL,
    difficulty TEXT NOT NULL DEFAULT '',
    servings INTEGER NOT NULL DEFAULT 2,
    prep_minutes INTEGER, cook_minutes INTEGER, total_minutes INTEGER,
    time_notes TEXT NOT NULL DEFAULT '',
    allergen_text TEXT NOT NULL DEFAULT '',
    allergens_verified INTEGER NOT NULL DEFAULT 0,
    image TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    section TEXT,
    raw TEXT NOT NULL,
    display TEXT NOT NULL DEFAULT '',
    match_spec TEXT NOT NULL DEFAULT '',
    is_optional INTEGER NOT NULL DEFAULT 0,
    is_staple INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS recipe_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipe_tags (
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (recipe_id, kind, value)
);
CREATE TABLE IF NOT EXISTS saved_recipes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, recipe_id)
);
"""


def split_sql(text: str) -> list:
    """Split a schema file into statements. Comment lines are removed first, so a
    semicolon inside a comment can never be mistaken for the end of a statement."""
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


class Database:
    def __init__(self, url: str):
        parsed = urlparse(url)
        if parsed.scheme.startswith("mysql"):
            if pymysql is None:
                raise RuntimeError("PyMySQL is not installed. Run: pip install -r requirements.txt")
            self.kind = "mysql"
            self.mysql = {
                "host": parsed.hostname or "127.0.0.1",
                "port": parsed.port or 3306,
                "user": unquote(parsed.username or ""),
                "password": unquote(parsed.password or ""),
                "database": parsed.path.lstrip("/"),
            }
        elif parsed.scheme == "sqlite":
            self.kind = "sqlite"
            self.sqlite_path = url[len("sqlite:///"):]
        else:
            raise ValueError("DATABASE_URL must start with mysql:// or sqlite:///")

    # -- connection handling (one connection per request, stored on flask.g) --
    def _connect(self):
        if self.kind == "mysql":
            return pymysql.connect(
                **self.mysql,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=10,
            )
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def conn(self):
        if "db_conn" not in g:
            g.db_conn = self._connect()
        return g.db_conn

    def close(self, exc=None):
        conn = g.pop("db_conn", None)
        if conn is not None:
            try:
                if exc is not None:
                    conn.rollback()
            finally:
                conn.close()

    # -- queries --
    def _run(self, sql, params=()):
        if self.kind == "sqlite":
            sql = sql.replace("%s", "?")
        cur = self.conn().cursor()
        cur.execute(sql, params)
        return cur

    def one(self, sql, params=()):
        cur = self._run(sql, params)
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None

    def execute(self, sql, params=()):
        cur = self._run(sql, params)
        result = (cur.lastrowid, cur.rowcount)
        cur.close()
        return result

    def all(self, sql, params=()):
        cur = self._run(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        return rows

    def executemany(self, sql, seq):
        seq = list(seq)
        if not seq:
            return
        if self.kind == "sqlite":
            sql = sql.replace("%s", "?")
        cur = self.conn().cursor()
        cur.executemany(sql, seq)
        cur.close()

    def commit(self):
        self.conn().commit()

    # -- schema --
    def init_schema(self):
        conn = self.conn()
        if self.kind == "sqlite":
            conn.executescript(SQLITE_SCHEMA)
        else:
            sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
            cur = conn.cursor()
            for statement in split_sql(sql):
                cur.execute(statement)
            cur.close()
        conn.commit()