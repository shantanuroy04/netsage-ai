-- NetSage AI Database Schema
-- Applied on every start; CREATE ... IF NOT EXISTS keeps it idempotent.
-- Column additions for pre-existing databases are handled by db._migrate().

-- Pre-loaded troubleshooting case dataset
CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    category    TEXT NOT NULL,
    symptom     TEXT NOT NULL,
    topology    TEXT NOT NULL,
    show_output TEXT NOT NULL,
    expected_fault TEXT NOT NULL,
    osi_layer   TEXT NOT NULL,
    concept     TEXT NOT NULL,
    severity    TEXT NOT NULL CHECK(severity IN ('Low','Medium','High','Critical'))
);

-- AI-generated diagnoses (one row per analysis run)
CREATE TABLE IF NOT EXISTS diagnoses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_ref        TEXT,                       -- NULL for free-form inputs
    category        TEXT,
    symptom         TEXT NOT NULL,
    topology        TEXT,
    show_output     TEXT,
    root_cause      TEXT,
    osi_layer       TEXT,
    confidence      TEXT CHECK(confidence IN ('Low','Medium','High')),
    severity        TEXT,                       -- AI-assessed severity
    concept         TEXT,                       -- networking concept involved
    evidence        TEXT,                       -- JSON array as text
    next_command    TEXT,
    fix_steps       TEXT,                       -- JSON array as text
    rule_results    TEXT,                       -- JSON array as text (checker output)
    ai_conflict     INTEGER DEFAULT 0,          -- 1 if AI vs rule checker disagree
    model           TEXT,                       -- Groq model that produced this
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Human review decisions. The AI row above is never overwritten — corrections
-- live here so the original output stays auditable.
CREATE TABLE IF NOT EXISTS reviews (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    diagnosis_id        INTEGER NOT NULL REFERENCES diagnoses(id),
    decision            TEXT NOT NULL CHECK(decision IN ('accept','edit','reject')),
    human_root_cause    TEXT,
    human_osi_layer     TEXT,
    human_confidence    TEXT,
    human_severity      TEXT,
    human_evidence      TEXT,                   -- JSON array as text
    human_next_command  TEXT,
    human_fix_steps     TEXT,                   -- JSON array as text
    human_correction    TEXT,                   -- free-text correction notes
    reason              TEXT,                   -- why the AI was edited/rejected
    reviewer            TEXT,
    verified_before     TEXT,                   -- 'pass' | 'fail' | NULL
    fix_applied         TEXT,
    verified_after      TEXT,
    reviewed_at         DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reviews_diagnosis ON reviews(diagnosis_id);
CREATE INDEX IF NOT EXISTS idx_diagnoses_case ON diagnoses(case_ref);

-- Responsible-AI log: every diagnosis a human corrected.
DROP VIEW IF EXISTS responsible_ai_log;
CREATE VIEW responsible_ai_log AS
SELECT
    d.id                AS diagnosis_id,
    d.case_ref,
    d.category,
    d.root_cause        AS ai_diagnosis,
    d.osi_layer         AS ai_osi_layer,
    d.confidence        AS ai_confidence,
    d.model             AS model,
    r.decision          AS human_decision,
    r.human_root_cause  AS human_diagnosis,
    r.human_osi_layer,
    r.human_correction,
    r.reason,
    r.reviewer,
    r.reviewed_at
FROM diagnoses d
JOIN reviews r ON r.diagnosis_id = d.id
WHERE r.decision IN ('edit', 'reject')
ORDER BY r.reviewed_at DESC;
