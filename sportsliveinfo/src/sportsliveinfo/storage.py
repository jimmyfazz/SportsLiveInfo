"""Small durable state store; every API secret remains inside HAOS /data."""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import providers

# New sources are always added disabled: an upgrade never starts outbound
# calls the owner has not chosen.
DEFAULT = {
    "setup_complete": False,
    "sports": {name: name == "jolpica" for name in providers.SPORTS},
    "epg": {name: False for name in providers.EPG},
    "options": {"thesportsdb_sports": list(providers.THESPORTSDB_SPORTS),
                "openligadb_leagues": list(providers.OPENLIGADB_DEFAULT_LEAGUES)},
    "keys": {},
    "schedule": ["04:00", "12:00", "17:00"],
    # Separate public *data* destination, not the private Home Assistant App repository.
    # Credentials and publication approval remain unset on installation.
    "github": {"owner": "jimmyfazz", "repository": "LiveSports-EPG", "branch": "main",
               "token": "", "enabled": False, "auto_publish": False},
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
                CREATE TABLE IF NOT EXISTS scheduler_slots (
                  slot TEXT PRIMARY KEY, claimed_at TEXT NOT NULL);
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
        # Older installs saved an empty repository placeholder. Populate only
        # that placeholder for the original owner; never change an explicitly
        # configured alternative owner, repo, publishing flag, key or token.
        target = config.get("github")
        if (isinstance(target, dict) and target.get("owner") == "jimmyfazz"
                and not target.get("repository")):
            target["repository"] = DEFAULT["github"]["repository"]
        return config

    def configure(self, update):
        """Update selected top-level values; nested dict updates retain other provider keys."""
        with self._lock:
            config = self.config()
            for key, value in update.items():
                if key not in DEFAULT:
                    raise ValueError("Unknown configuration field")
                expected = DEFAULT[key]
                if isinstance(expected, dict):
                    if not isinstance(value, dict):
                        raise ValueError("Configuration section must be a dictionary")
                    if key in ("sports", "epg") and (
                        any(k not in (providers.SPORTS if key == "sports" else providers.EPG) or type(v) is not bool
                            for k, v in value.items())
                    ):
                        raise ValueError("Unknown provider or invalid enabled state")
                    if key == "github" and any(k not in expected for k in value):
                        raise ValueError("Unsupported publication setting")
                    config[key].update(value)
                elif isinstance(expected, bool):
                    if type(value) is not bool:
                        raise ValueError("Expected boolean configuration")
                    config[key] = value
                elif isinstance(expected, list):
                    if not isinstance(value, list) or len(value) > 100 or any(not isinstance(x, str) for x in value):
                        raise ValueError("Invalid configuration list")
                    if key == "schedule" and any(
                        len(x) != 5 or x[2] != ":" or not x[:2].isdigit() or not x[3:].isdigit()
                        or int(x[:2]) > 23 or int(x[3:]) > 59 for x in value
                    ):
                        raise ValueError("Invalid scheduler time")
                    if key == "publication_approvals" and any(x not in providers.SPORTS for x in value):
                        raise ValueError("Unknown publication source")
                    config[key] = value
                else:
                    config[key] = value
            self._put("config", config)
            return config

    def snapshot(self, product):
        return self.read_snapshots(products=(product,)).get(product)

    def read_snapshots(self, *, products=(), timestamps_only=()):
        """Read requested snapshots in one SQLite statement, omitting large payloads when possible."""
        names = tuple(dict.fromkeys((*products, *timestamps_only)))
        if not names:
            return {}
        full = ",".join("?" for _ in products) or "NULL"
        requested = ",".join("?" for _ in names)
        with self._lock, self._db() as db:
            rows = db.execute(
                f"SELECT product, updated_at, CASE WHEN product IN ({full}) THEN data END "
                f"FROM snapshots WHERE product IN ({requested})", (*products, *names)
            ).fetchall()
        return {name: {"updated_at": updated_at, "data": json.loads(data) if data is not None else None}
                for name, updated_at, data in rows}

    def save_snapshot(self, product, data):
        self.save_snapshots({product: data})

    def save_snapshots(self, products):
        """Commit related products together using one refresh timestamp."""
        updated_at = utcnow()
        rows = [(product, updated_at, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
                for product, data in products.items()]
        with self._lock, self._db() as db:
            db.executemany("INSERT INTO snapshots(product,updated_at,data) VALUES(?,?,?) "
                           "ON CONFLICT(product) DO UPDATE SET updated_at=excluded.updated_at,data=excluded.data", rows)
            db.commit()

    def job(self, provider, state, details=""):
        # Never call with credentials, source URLs containing credentials, or raw response bodies.
        details = str(details)[:350]
        with self._lock, self._db() as db:
            db.execute("INSERT INTO jobs(time,provider,state,details) VALUES(?,?,?,?)", (utcnow(), provider, state, details))
            db.execute("DELETE FROM jobs WHERE id NOT IN (SELECT id FROM jobs ORDER BY id DESC LIMIT 300)")
            db.commit()

    def recent_jobs(self, limit=20, *, provider=None):
        query = "SELECT time,provider,state,details FROM jobs"
        where = " WHERE provider=?" if provider is not None else ""
        params = (provider, limit) if provider is not None else (limit,)
        with self._lock, self._db() as db:
            return [dict(row) for row in db.execute(query + where + " ORDER BY id DESC LIMIT ?", params)]

    def increment(self, provider, limit):
        """Reserve before network IO; atomic even across separate Store instances/processes.

        RLock alone does not serialize another process using the same SQLite file.
        BEGIN IMMEDIATE avoids a SELECT-then-UPDATE quota overspend race.
        """
        if not isinstance(provider, str) or not provider or type(limit) is not int or limit <= 0:
            raise ValueError("Invalid API quota")
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT count FROM requests WHERE provider=? AND utc_day=?", (provider, day)).fetchone()
            count = old[0] if old else 0
            if count >= limit:
                raise RuntimeError("Configured daily call budget exhausted")
            db.execute("INSERT INTO requests(provider,utc_day,count) VALUES(?,?,1) ON CONFLICT(provider,utc_day) DO UPDATE SET count=count+1", (provider, day))
            return count + 1

    def claim_scheduler_slot(self, slot):
        """Claim local-time daily scheduler slot exactly once across restarts/workers."""
        if not isinstance(slot, str) or len(slot) != 16:
            raise ValueError("Invalid scheduler slot")
        try:
            datetime.strptime(slot, "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise ValueError("Invalid scheduler slot") from exc
        with self._lock, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                "INSERT OR IGNORE INTO scheduler_slots(slot,claimed_at) VALUES (?,?)",
                (slot, utcnow()),
            )
            db.execute("DELETE FROM scheduler_slots WHERE claimed_at < ?",
                       ((datetime.now(timezone.utc) - timedelta(days=35)).isoformat(),))
            return cursor.rowcount == 1

    def release_scheduler_slot(self, slot):
        """Undo a slot claim when no collection was scheduled (e.g. collector busy)."""
        with self._lock, self._db() as db:
            db.execute("DELETE FROM scheduler_slots WHERE slot=?", (slot,))

    def usage(self):
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock, self._db() as db:
            return {r[0]: r[1] for r in db.execute("SELECT provider,count FROM requests WHERE utc_day=?", (day,))}
