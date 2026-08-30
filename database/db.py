"""
database/db.py — SQLite persistence for NetSage AI.

Thin sqlite3 wrapper. JSON-shaped fields (evidence, fix_steps, rule_results)
are stored as JSON text and decoded on read. API keys are never stored here.
"""
import csv
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "netsage.db"
SCHEMA = BASE_DIR / "database" / "schema.sql"
CASES_CSV = BASE_DIR / "data" / "cases.csv"

JSON_FIELDS = ("evidence", "fix_steps", "rule_results")
HUMAN_JSON_FIELDS = ("human_evidence", "human_fix_steps")

# Columns added after the first release — applied to existing databases.
_MIGRATIONS = {
    "diagnoses": {"severity": "TEXT", "concept": "TEXT", "model": "TEXT"},
    "reviews": {
        "human_osi_layer": "TEXT",
        "human_confidence": "TEXT",
        "human_severity": "TEXT",
        "human_evidence": "TEXT",
        "human_next_command": "TEXT",
        "human_fix_steps": "TEXT",
        "reviewer": "TEXT",
    },
}


class DatabaseError(RuntimeError):
    """Any persistence failure, surfaced to the UI as a friendly message."""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _migrate(conn) -> None:
    """Add any columns missing from a database created by an older release."""
    for table, columns in _MIGRATIONS.items():
        if not _table_exists(conn, table):
            continue
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, coltype in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")


def init_db() -> None:
    """Create/upgrade tables. Safe to call on every app start."""
    try:
        conn = get_connection()
        with conn:
            _migrate(conn)
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.close()
    except sqlite3.Error as exc:
        raise DatabaseError(f"Could not initialise the database: {exc}") from exc


# ── Case dataset ─────────────────────────────────────────────────────────────

def insert_case(row: dict) -> None:
    sql = """
        INSERT OR IGNORE INTO cases
          (case_id, category, symptom, topology, show_output,
           expected_fault, osi_layer, concept, severity)
        VALUES (:case_id,:category,:symptom,:topology,:show_output,
                :expected_fault,:osi_layer,:concept,:severity)
    """
    with get_connection() as conn:
        conn.execute(sql, row)


def seed_cases_from_csv(path: Path | None = None) -> int:
    """Load data/cases.csv into the DB. Idempotent (INSERT OR IGNORE)."""
    path = path or CASES_CSV
    if not path.exists():
        raise DatabaseError(f"Case dataset not found: {path}")
    inserted = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            clean = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            if not clean.get("case_id"):
                continue
            insert_case(clean)
            inserted += 1
    return inserted


def get_all_cases() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY case_id").fetchall()
    return [dict(r) for r in rows]


def get_case(case_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    return dict(row) if row else None


# ── Diagnoses ────────────────────────────────────────────────────────────────

def _decode(row: sqlite3.Row, fields=JSON_FIELDS) -> dict:
    d = dict(row)
    for f in fields:
        if f in d:
            try:
                d[f] = json.loads(d[f] or "[]")
            except (TypeError, json.JSONDecodeError):
                d[f] = []
    return d


def insert_diagnosis(d: dict) -> int:
    """Insert one AI diagnosis. Lists are JSON-encoded on the way in."""
    sql = """
        INSERT INTO diagnoses
          (case_ref, category, symptom, topology, show_output,
           root_cause, osi_layer, confidence, severity, concept, evidence,
           next_command, fix_steps, rule_results, ai_conflict, model)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with get_connection() as conn:
        cur = conn.execute(sql, (
            d.get("case_ref"), d.get("category"), d["symptom"],
            d.get("topology"), d.get("show_output"),
            d.get("root_cause"), d.get("osi_layer"), d.get("confidence"),
            d.get("severity"), d.get("concept"),
            json.dumps(d.get("evidence", [])),
            d.get("next_command"),
            json.dumps(d.get("fix_steps", [])),
            json.dumps(d.get("rule_results", [])),
            int(bool(d.get("ai_conflict", False))),
            d.get("model"),
        ))
        return cur.lastrowid


def get_diagnosis(diag_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM diagnoses WHERE id=?", (diag_id,)).fetchone()
    return _decode(row) if row else None


def get_all_diagnoses() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT d.*, r.decision, r.reviewed_at "
            "FROM diagnoses d LEFT JOIN reviews r ON r.diagnosis_id = d.id "
            "ORDER BY d.created_at DESC, d.id DESC"
        ).fetchall()
    return [_decode(r) for r in rows]


def get_unreviewed_diagnoses() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT d.* FROM diagnoses d "
            "LEFT JOIN reviews r ON r.diagnosis_id = d.id "
            "WHERE r.id IS NULL ORDER BY d.id DESC"
        ).fetchall()
    return [_decode(r) for r in rows]


# ── Reviews ──────────────────────────────────────────────────────────────────

def insert_review(r: dict) -> int:
    """
    Record a human decision. The AI diagnosis row is left untouched — this is
    an additional record, never an overwrite.
    """
    if r.get("decision") not in ("accept", "edit", "reject"):
        raise DatabaseError("Decision must be accept, edit or reject.")

    sql = """
        INSERT INTO reviews
          (diagnosis_id, decision, human_root_cause, human_osi_layer,
           human_confidence, human_severity, human_evidence, human_next_command,
           human_fix_steps, human_correction, reason, reviewer,
           verified_before, fix_applied, verified_after)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with get_connection() as conn:
        cur = conn.execute(sql, (
            r["diagnosis_id"], r["decision"],
            r.get("human_root_cause"), r.get("human_osi_layer"),
            r.get("human_confidence"), r.get("human_severity"),
            json.dumps(r.get("human_evidence", [])),
            r.get("human_next_command"),
            json.dumps(r.get("human_fix_steps", [])),
            r.get("human_correction"), r.get("reason"), r.get("reviewer"),
            r.get("verified_before"), r.get("fix_applied"), r.get("verified_after"),
        ))
        return cur.lastrowid


def get_review_for_diagnosis(diag_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM reviews WHERE diagnosis_id=? ORDER BY id DESC LIMIT 1",
            (diag_id,),
        ).fetchone()
    return _decode(row, HUMAN_JSON_FIELDS) if row else None


def get_all_reviews() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT r.*, d.symptom, d.category, d.root_cause AS ai_root_cause,
                   d.osi_layer AS ai_osi_layer, d.confidence, d.severity AS ai_severity,
                   d.case_ref, d.model, d.ai_conflict
            FROM reviews r
            JOIN diagnoses d ON d.id = r.diagnosis_id
            ORDER BY r.reviewed_at DESC, r.id DESC
        """).fetchall()
    return [_decode(r, HUMAN_JSON_FIELDS) for r in rows]


def get_responsible_ai_log() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM responsible_ai_log").fetchall()
    return [dict(r) for r in rows]


# ── Aggregates ───────────────────────────────────────────────────────────────

def _count(conn, sql: str, params=()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def get_stats() -> dict:
    """
    Every number the dashboard shows. All derived from stored rows — nothing
    here is hard-coded or estimated.
    """
    with get_connection() as conn:
        total_cases = _count(conn, "SELECT COUNT(*) FROM cases")
        total_diagnoses = _count(conn, "SELECT COUNT(*) FROM diagnoses")
        reviewed = _count(conn, "SELECT COUNT(*) FROM reviews")
        accepted = _count(conn, "SELECT COUNT(*) FROM reviews WHERE decision='accept'")
        edited = _count(conn, "SELECT COUNT(*) FROM reviews WHERE decision='edit'")
        rejected = _count(conn, "SELECT COUNT(*) FROM reviews WHERE decision='reject'")
        conflicts = _count(conn, "SELECT COUNT(*) FROM diagnoses WHERE ai_conflict=1")

        rows = {
            "cases_by_category": conn.execute(
                "SELECT category AS label, COUNT(*) AS count FROM cases "
                "GROUP BY category ORDER BY count DESC").fetchall(),
            "cases_by_severity": conn.execute(
                "SELECT severity AS label, COUNT(*) AS count FROM cases "
                "GROUP BY severity").fetchall(),
            "cases_by_osi": conn.execute(
                "SELECT osi_layer AS label, COUNT(*) AS count FROM cases "
                "GROUP BY osi_layer ORDER BY count DESC").fetchall(),
            "diagnoses_by_category": conn.execute(
                "SELECT COALESCE(category,'Unspecified') AS label, COUNT(*) AS count "
                "FROM diagnoses GROUP BY label ORDER BY count DESC").fetchall(),
            "diagnoses_by_confidence": conn.execute(
                "SELECT COALESCE(confidence,'Unknown') AS label, COUNT(*) AS count "
                "FROM diagnoses GROUP BY label").fetchall(),
            "decisions": conn.execute(
                "SELECT decision AS label, COUNT(*) AS count FROM reviews "
                "GROUP BY decision").fetchall(),
            "corrections_by_category": conn.execute(
                "SELECT COALESCE(d.category,'Unspecified') AS label, COUNT(*) AS count "
                "FROM reviews r JOIN diagnoses d ON d.id=r.diagnosis_id "
                "WHERE r.decision IN ('edit','reject') GROUP BY label "
                "ORDER BY count DESC").fetchall(),
        }

    return {
        "total_cases": total_cases,
        "total_diagnoses": total_diagnoses,
        "reviewed": reviewed,
        "accepted": accepted,
        "edited": edited,
        "rejected": rejected,
        "corrections": edited + rejected,
        "conflicts": conflicts,
        "pending_review": max(total_diagnoses - reviewed, 0),
        **{k: [dict(r) for r in v] for k, v in rows.items()},
    }
