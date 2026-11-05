import hashlib
import json
import sqlite3
from datetime import datetime

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS voters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    voter_id      TEXT UNIQUE NOT NULL,       -- EPIC / ID number
    name          TEXT NOT NULL,
    age           INTEGER NOT NULL DEFAULT 0,
    contact       TEXT NOT NULL DEFAULT '',
    encodings     TEXT NOT NULL,              -- JSON list of 128-d face vectors
    has_voted     INTEGER NOT NULL DEFAULT 0,
    registered_at TEXT NOT NULL
);

-- Each "candidate" is a party on the ballot.
CREATE TABLE IF NOT EXISTS candidates (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL,
    slogan TEXT NOT NULL DEFAULT '',
    color  TEXT NOT NULL DEFAULT '#0b2545'
);

-- Ballots are stored separately from voters so a vote cannot be linked to a voter.
-- Every ballot is chained to the previous one by a SHA-256 hash (tamper evident).
CREATE TABLE IF NOT EXISTS votes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id),
    cast_at      TEXT NOT NULL,
    prev_hash    TEXT,
    hash         TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    voter_id TEXT,
    event    TEXT NOT NULL,
    detail   TEXT,
    ts       TEXT NOT NULL
);
"""

DEFAULT_PARTIES = [
    ("AIADMK", "Era of Prosperity", "#2f9e44"),
    ("Dravida Munnetra Kazhagam", "Rising Sun of Tamil Nadu", "#c92a2a"),
    ("Naam Tamilar Katchi", "Cement our Foundation", "#2b8a3e"),
    ("PAMAKA", "Voice of the People", "#e67700"),
    ("Tamilaga Vettri Kazhagam", "For the People, By the People", "#862e9c"),
]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _columns(db, table):
    return {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}


def init_db():
    db = get_db()
    db.executescript(SCHEMA)

    # ---- lightweight migrations for databases created by the older version
    for col, ddl in (("age", "INTEGER NOT NULL DEFAULT 0"),
                     ("contact", "TEXT NOT NULL DEFAULT ''")):
        if col not in _columns(db, "voters"):
            db.execute(f"ALTER TABLE voters ADD COLUMN {col} {ddl}")
    for col in ("prev_hash", "hash"):
        if col not in _columns(db, "votes"):
            db.execute(f"ALTER TABLE votes ADD COLUMN {col} TEXT")
    ccols = _columns(db, "candidates")
    if "slogan" not in ccols:
        db.execute("ALTER TABLE candidates ADD COLUMN slogan TEXT NOT NULL DEFAULT ''")
    if "color" not in ccols:
        db.execute("ALTER TABLE candidates ADD COLUMN color TEXT NOT NULL DEFAULT '#0b2545'")

    # Replace the old placeholder ballot (Candidate A/B/C) if nobody has voted yet
    old = db.execute("SELECT COUNT(*) FROM candidates WHERE name LIKE 'Candidate %'").fetchone()[0]
    if old and db.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 0:
        db.execute("DELETE FROM candidates")

    if db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 0:
        db.executemany("INSERT INTO candidates (name, slogan, color) VALUES (?, ?, ?)",
                       DEFAULT_PARTIES)
    db.commit()


def log_event(voter_id, event, detail=""):
    db = get_db()
    db.execute(
        "INSERT INTO audit_log (voter_id, event, detail, ts) VALUES (?, ?, ?, ?)",
        (voter_id, event, detail, now()),
    )
    db.commit()


# ---------- voters ----------
def add_voter(voter_id, name, age, contact, encodings):
    db = get_db()
    db.execute(
        "INSERT INTO voters (voter_id, name, age, contact, encodings, registered_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (voter_id, name, age, contact, json.dumps([e.tolist() for e in encodings]), now()),
    )
    db.commit()


def get_voter_by_voter_id(voter_id):
    return get_db().execute("SELECT * FROM voters WHERE voter_id = ?", (voter_id,)).fetchone()


def get_voter(pk):
    return get_db().execute("SELECT * FROM voters WHERE id = ?", (pk,)).fetchone()


def all_voters():
    return get_db().execute("SELECT * FROM voters ORDER BY id").fetchall()


# ---------- parties / votes ----------
def all_candidates():
    return get_db().execute("SELECT * FROM candidates ORDER BY id").fetchall()


def add_candidate(name, slogan="", color="#0b2545"):
    db = get_db()
    db.execute("INSERT INTO candidates (name, slogan, color) VALUES (?, ?, ?)",
               (name, slogan, color))
    db.commit()


def _hash(prev, candidate_id, cast_at):
    return hashlib.sha256(f"{prev}|{candidate_id}|{cast_at}".encode()).hexdigest()


def cast_vote(voter_pk, candidate_id):
    """Atomically mark the voter as voted and append a hash-chained ballot.

    Returns True on success, False if the voter had already voted.
    """
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        cur = db.execute(
            "UPDATE voters SET has_voted = 1 WHERE id = ? AND has_voted = 0", (voter_pk,)
        )
        if cur.rowcount != 1:
            db.rollback()
            return False
        last = db.execute(
            "SELECT hash FROM votes WHERE hash IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev = last["hash"] if last else "GENESIS"
        ts = now()
        db.execute(
            "INSERT INTO votes (candidate_id, cast_at, prev_hash, hash) VALUES (?, ?, ?, ?)",
            (candidate_id, ts, prev, _hash(prev, candidate_id, ts)),
        )
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def ledger_status():
    """Re-compute the hash chain. Returns (is_valid, number_of_chained_blocks)."""
    rows = get_db().execute(
        "SELECT * FROM votes WHERE hash IS NOT NULL ORDER BY id").fetchall()
    prev = rows[0]["prev_hash"] if rows else "GENESIS"
    for r in rows:
        if r["prev_hash"] != prev or r["hash"] != _hash(prev, r["candidate_id"], r["cast_at"]):
            return False, len(rows)
        prev = r["hash"]
    return True, len(rows)


def results():
    return get_db().execute(
        """SELECT c.id, c.name, c.slogan, c.color, COUNT(v.id) AS total
           FROM candidates c LEFT JOIN votes v ON v.candidate_id = c.id
           GROUP BY c.id ORDER BY total DESC, c.id"""
    ).fetchall()


def stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM voters").fetchone()[0]
    voted = db.execute("SELECT COUNT(*) FROM voters WHERE has_voted = 1").fetchone()[0]
    return {"registered": total, "voted": voted, "pending": total - voted}


def recent_logs(limit=25):
    return get_db().execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
