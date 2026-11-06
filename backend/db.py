"""SQLite storage for the leaderboard (one best score per player, mission and difficulty)."""
import os
import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(os.environ.get("STELLAVEX_DB", Path(__file__).parent / "stellavex.db"))
_lock = threading.Lock()
_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


def init():
    with _lock, conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS scores (
                player_id TEXT NOT NULL, mission TEXT NOT NULL, difficulty TEXT NOT NULL,
                name TEXT NOT NULL, score INTEGER NOT NULL, landed INTEGER NOT NULL, seed INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (player_id, mission, difficulty))"""
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_scores_rank ON scores (mission, score DESC)")


def upsert(player_id, name, mission, difficulty, score, landed, seed):
    """Keep only the best score. Returns True if this score is the new best."""
    with _lock, conn() as c:
        cur = c.execute(
            """INSERT INTO scores (player_id, mission, difficulty, name, score, landed, seed)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(player_id, mission, difficulty) DO UPDATE SET
                 name = excluded.name, score = excluded.score, landed = excluded.landed,
                 seed = excluded.seed, updated_at = CURRENT_TIMESTAMP
               WHERE excluded.score > scores.score""",
            (player_id, mission, difficulty, name, score, int(landed), seed),
        )
        return cur.rowcount > 0


def leaderboard(mission, limit=8):
    """Top players for a mission, one row per player (their best difficulty)."""
    with _lock:
        rows = conn().execute(
            """SELECT name, score, landed, difficulty FROM scores s1
               WHERE mission = ? AND score = (SELECT MAX(score) FROM scores s2
                                              WHERE s2.player_id = s1.player_id AND s2.mission = s1.mission)
               GROUP BY player_id ORDER BY score DESC, updated_at ASC LIMIT ?""",
            (mission, limit),
        ).fetchall()
    return [{"name": r["name"], "score": r["score"], "landed": bool(r["landed"]), "diff": r["difficulty"].capitalize()} for r in rows]


def rank(mission, score):
    with _lock:
        return conn().execute("SELECT COUNT(DISTINCT player_id) + 1 FROM scores WHERE mission = ? AND score > ?", (mission, score)).fetchone()[0]


def stats(mission):
    with _lock:
        r = conn().execute(
            "SELECT COUNT(*) n, COALESCE(SUM(landed),0) l, COALESCE(AVG(score),0) a, COALESCE(MAX(score),0) b FROM scores WHERE mission = ?",
            (mission,),
        ).fetchone()
    return {"players": r["n"], "landing_rate": round(r["l"] / r["n"], 3) if r["n"] else 0, "avg_score": round(r["a"], 1), "best_score": r["b"]}
