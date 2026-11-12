"""Small durable state store; every API secret remains inside HAOS /data."""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import providers

# New sources are always added disabled: an upgrade never starts outbound
# calls the owner has not chosen.
DEFAULT = {
    "setup_complete": False,
    "sports": {name: name == "jolpica" for name in providers.SPORTS},
    "epg": {name: False for name in providers.EPG},
    "options": {"thesportsdb_sports": list(providers.THESPORTSDB_SPORTS),
                "openligadb_leagues": list(providers.OPENLIGADB_LEAGUES)},
    "keys": {},
    "schedule": ["04:00", "12:00", "17:00"],
    "github": {"owner": "jimmyfazz", "repository": "", "branch": "main", "token": "", "enabled": False},
    "publication_approvals": [],
}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._db() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS kv (name TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots (
                  product TEXT PRIMARY KEY, updated_at TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL,
                  provider TEXT NOT NULL, state TEXT NOT NULL, details TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS jobs_recent ON jobs(id DESC);
                CREATE TABLE IF NOT EXISTS requests (
                  provider TEXT NOT NULL, utc_day TEXT NOT NULL, count INTEGER NOT NULL,
                  PRIMARY KEY(provider,utc_day));
            """)
        if not self._get("config"):
            self._put("config", DEFAULT)

    @contextmanager
    def _db(self):
        c = sqlite3.connect(str(self.path), timeout=10)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def _get(self, name):
        with self._lock, self._db() as db:
            row = db.execute("SELECT data FROM kv WHERE name=?", (name,)).fetchone()
            return json.loads(row[0]) if row else None

    def _put(self, name, obj):
        with self._lock, self._db() as db:
            db.execute("INSERT INTO kv(name,data) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET data=excluded.data", (name, json.dumps(obj, separators=(",", ":"))))
            db.commit()

    def config(self):
        # Carry new source defaults into pre-existing v0.1 installations; do not
        # re-enable or overwrite saved provider choices or credentials.
        stored = self._get("config") or {}
        config = json.loads(json.dumps(DEFAULT))
        for key, value in stored.items():
            if key in config:
                if isinstance(config[key], dict) and isinstance(value, dict):
                    config[key].update(value)
                else:
                    config[key] = value
        return config

    def configure(self, update):
        """Update selected top-level values; nested dict updates retain other provider keys."""
        with self._lock:
            config = self.config()
            for key, value in update.items():
                if key not in DEFAULT:
                    raise ValueError("Unknown configuration field")
                if isinstance(config[key], dict) and isinstance(value, dict):
                    config[key].update(value)
                else:
                    config[key] = value
            self._put("config", config)
            return config

    def snapshot(self, product):
        with self._lock, self._db() as db:
            row = db.execute("SELECT updated_at,data FROM snapshots WHERE product=?", (product,)).fetchone()
            return {"updated_at": row[0], "data": json.loads(row[1])} if row else None

    def save_snapshot(self, product, data):
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._db() as db:
            db.execute("INSERT INTO snapshots(product,updated_at,data) VALUES(?,?,?) ON CONFLICT(product) DO UPDATE SET updated_at=excluded.updated_at,data=excluded.data", (product, utcnow(), encoded))
            db.commit()

    def job(self, provider, state, details=""):
        # Never call with credentials, source URLs containing credentials, or raw response bodies.
        details = str(details)[:350]
        with self._lock, self._db() as db:
            db.execute("INSERT INTO jobs(time,provider,state,details) VALUES(?,?,?,?)", (utcnow(), provider, state, details))
            db.execute("DELETE FROM jobs WHERE id NOT IN (SELECT id FROM jobs ORDER BY id DESC LIMIT 300)")
            db.commit()

    def recent_jobs(self, limit=20):
        with self._lock, self._db() as db:
            return [dict(x) for x in db.execute("SELECT time,provider,state,details FROM jobs ORDER BY id DESC LIMIT ?", (limit,))]

    def increment(self, provider, limit):
        """Conservative call accounting: reserve a unit before attempting network IO."""
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock, self._db() as db:
            old = db.execute("SELECT count FROM requests WHERE provider=? AND utc_day=?", (provider, day)).fetchone()
            count = old[0] if old else 0
            if count >= limit:
                raise RuntimeError("Configured daily call budget exhausted")
            db.execute("INSERT INTO requests(provider,utc_day,count) VALUES(?,?,1) ON CONFLICT(provider,utc_day) DO UPDATE SET count=count+1", (provider, day))
            db.commit()
            return count + 1

    def usage(self):
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock, self._db() as db:
            return {r[0]: r[1] for r in db.execute("SELECT provider,count FROM requests WHERE utc_day=?", (day,))}
