"""
tests/test_pipeline.py — end-to-end check of the NetSage AI pipeline.

Run:  python tests/test_pipeline.py

Uses a throwaway SQLite file so the real database is untouched. The Groq leg is
skipped (not failed) when GROQ_API_KEY is absent.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Point the DB at a temp file BEFORE anything reads it.
import database.db as db  # noqa: E402

_tmp = Path(tempfile.mkdtemp(prefix="netsage_test_")) / "test.db"
db.DB_PATH = _tmp

import config  # noqa: E402
from ai.groq_client import GroqError  # noqa: E402
from ai.schemas import REQUIRED_FIELDS, DiagnosisParseError  # noqa: E402
from checker import analyze as run_checker, conflict_summary  # noqa: E402
from database import seed  # noqa: E402

VLAN_CASE = {
    "symptom": "PC1 in VLAN 30 cannot reach the server; VLAN 10 and VLAN 20 work fine.",
    "topology": "PC1(VLAN30) -> SW1 -> [trunk] -> SW2 -> Server",
    "show_output": """show vlan brief
VLAN Name       Status    Ports
---- ---------- --------- -----
1    default    active    Fa0/1
30   FINANCE    active    Fa0/4
show interfaces trunk
Port   Mode  Encapsulation  Status    Native vlan
Gi0/1  on    802.1q         trunking  1
VLANs allowed on trunk: 1-29,31-4094
""",
    "category": "VLAN",
}

ROUTING_CASE = {
    "symptom": "PC1 can ping its gateway but cannot reach the 192.168.30.0/24 server network.",
    "topology": "PC1 -> R1 -> R2 -> Server(192.168.30.0/24)",
    # Next-hop 10.99.99.1 sits in no directly connected subnet — the route can
    # never be resolved, which is exactly what next_hop_reachable exists to catch.
    "show_output": """show ip route
C    192.168.10.0/24 is directly connected, Gi0/0
C    192.168.20.0/24 is directly connected, Gi0/1
S    192.168.30.0/24 [1/0] via 10.99.99.1
""",
    "category": "Routing",
}

passed, skipped = [], []


def ok(name):
    passed.append(name)
    print(f"  PASS  {name}")


def skip(name, why):
    skipped.append(name)
    print(f"  SKIP  {name} ({why})")


# ── Test 1 — dataset loads, checker runs on a dataset case ───────────────────
def test_bootstrap_and_dataset():
    info = seed.bootstrap()
    assert info["cases"] >= 30, f"expected >=30 cases, got {info['cases']}"
    cases = db.get_all_cases()
    categories = {c["category"] for c in cases}
    for required in ["VLAN", "Routing", "DHCP", "DNS", "Gateway", "ACL", "NAT", "Wireless"]:
        assert required in categories, f"dataset missing category {required}"
    ok(f"dataset loads ({info['cases']} cases, {len(categories)} categories)")

    case = db.get_case(cases[0]["case_id"])
    raw, report = run_checker(case["symptom"], case["show_output"], case["category"])
    assert report["status"] in ("ok", "warning", "fail")
    assert raw, "checker produced no results for a dataset case"
    ok("rule checker runs on a dataset case")


# ── Test 2/3 — checker catches the VLAN and routing faults deterministically ──
def test_checker_finds_faults():
    raw, report = run_checker(**{k: VLAN_CASE[k] for k in ("symptom", "show_output", "category")})
    types = {f["type"] for f in report["findings"]}
    assert "trunk_allowed" in types, f"VLAN trunk fault not caught: {types}"
    assert report["status"] == "fail"
    ok("VLAN case: checker flags trunk_allowed without any AI call")

    raw, report = run_checker(**{k: ROUTING_CASE[k] for k in ("symptom", "show_output", "category")})
    types = {f["type"] for f in report["findings"]}
    assert "next_hop_reachable" in types, f"routing fault not caught: {types}"
    ok("Routing case: checker flags unreachable next-hop without any AI call")


# ── Test 4 — malformed / empty input never crashes ───────────────────────────
def test_empty_and_malformed_input():
    for bad in ["", "   ", "!!!!", "\n\n"]:
        raw, report = run_checker("something is broken", bad, "VLAN")
        assert isinstance(report["findings"], list)
    ok("empty/malformed show output does not crash the checker")

    from ai.diagnosis import diagnose
    try:
        diagnose("", "", "", "VLAN")
        raise AssertionError("empty symptom should raise ValueError")
    except ValueError:
        ok("empty symptom is rejected before any API call")


# ── Test 5 — missing API key produces a friendly, non-fatal error ────────────
def test_missing_api_key():
    original = config.get_groq_api_key
    config.get_groq_api_key = lambda: None
    try:
        from ai.diagnosis import diagnose
        try:
            diagnose(VLAN_CASE["symptom"], "", VLAN_CASE["show_output"], "VLAN")
            raise AssertionError("expected GroqError with no API key")
        except GroqError as exc:
            assert "GROQ_API_KEY" in str(exc), str(exc)
            assert exc.retryable is False
            ok("missing GROQ_API_KEY -> friendly, non-retryable GroqError")
    finally:
        config.get_groq_api_key = original


# ── Test 6 — conflict detection ──────────────────────────────────────────────
def test_conflict_detection():
    raw, _ = run_checker(**{k: VLAN_CASE[k] for k in ("symptom", "show_output", "category")})
    agree = conflict_summary(raw, "VLAN 30 missing from the trunk allowed list")
    disagree = conflict_summary(raw, "An ACL on the router is dropping the traffic")
    assert agree["conflict"] is False
    assert disagree["conflict"] is True and disagree["checker_findings"]
    ok("AI/checker conflict is detected and summarised")


# ── Tests 7-9 — review decisions persist without overwriting the AI record ───
def test_review_decisions():
    raw, _ = run_checker(**{k: VLAN_CASE[k] for k in ("symptom", "show_output", "category")})
    base = {
        "category": "VLAN", "symptom": VLAN_CASE["symptom"],
        "topology": VLAN_CASE["topology"], "show_output": VLAN_CASE["show_output"],
        "root_cause": "AI original root cause", "osi_layer": "Layer 2",
        "confidence": "Medium", "severity": "High", "concept": "Trunking",
        "evidence": ["ev1"], "next_command": "show interfaces trunk",
        "fix_steps": ["step1"], "rule_results": raw, "ai_conflict": True,
        "model": "test-model",
    }

    accept_id = db.insert_diagnosis(base)
    db.insert_review({"diagnosis_id": accept_id, "decision": "accept",
                      "human_root_cause": base["root_cause"], "reviewer": "tester"})
    r = db.get_review_for_diagnosis(accept_id)
    assert r["decision"] == "accept"
    assert db.get_diagnosis(accept_id)["root_cause"] == "AI original root cause"
    ok("ACCEPT persists and leaves the AI record intact")

    edit_id = db.insert_diagnosis(base)
    db.insert_review({
        "diagnosis_id": edit_id, "decision": "edit",
        "human_root_cause": "Human corrected root cause",
        "human_osi_layer": "Layer 3", "human_evidence": ["human ev"],
        "human_fix_steps": ["human fix"], "reason": "AI ignored the checker",
        "reviewer": "tester",
    })
    ai_row = db.get_diagnosis(edit_id)
    hu_row = db.get_review_for_diagnosis(edit_id)
    assert ai_row["root_cause"] == "AI original root cause", "AI row was overwritten!"
    assert hu_row["human_root_cause"] == "Human corrected root cause"
    assert hu_row["human_evidence"] == ["human ev"]
    ok("EDIT stores the correction alongside the untouched AI diagnosis")

    reject_id = db.insert_diagnosis(base)
    db.insert_review({"diagnosis_id": reject_id, "decision": "reject",
                      "human_root_cause": "Completely different cause",
                      "reason": "Wrong layer entirely", "reviewer": "tester"})
    log = db.get_responsible_ai_log()
    assert any(r["diagnosis_id"] == reject_id for r in log)
    assert any(r["diagnosis_id"] == edit_id for r in log)
    assert not any(r["diagnosis_id"] == accept_id for r in log), \
        "accepted diagnoses must not appear in the responsible-AI log"
    ok("REJECT appears in the responsible-AI log; ACCEPT does not")

    try:
        db.insert_review({"diagnosis_id": accept_id, "decision": "approve"})
        raise AssertionError("invalid decision should be rejected")
    except db.DatabaseError:
        ok("invalid review decision is rejected")


# ── Test 10 — dashboard metrics come from the database ───────────────────────
def test_stats_are_derived():
    from utils.metrics import agreement_rate, correction_rate, responsible_ai_summary

    stats = db.get_stats()
    assert stats["reviewed"] == stats["accepted"] + stats["edited"] + stats["rejected"]
    assert stats["corrections"] == stats["edited"] + stats["rejected"]
    assert stats["total_cases"] == len(db.get_all_cases())

    before = stats["reviewed"]
    did = db.insert_diagnosis({"symptom": "extra", "root_cause": "x", "confidence": "Low"})
    db.insert_review({"diagnosis_id": did, "decision": "accept", "reviewer": "tester"})
    after = db.get_stats()
    assert after["reviewed"] == before + 1, "stats did not follow the database"
    ok("dashboard metrics are derived from stored rows, not hard-coded")

    empty = {"accepted": 0, "reviewed": 0, "corrections": 0}
    assert agreement_rate(empty) is None and correction_rate(empty) is None
    ok("no reviews -> rates are None ('not enough data'), never a fabricated 0%")

    summary = responsible_ai_summary(db.get_stats(), db.get_responsible_ai_log())
    assert summary["corrections"] == len(db.get_responsible_ai_log())
    assert summary["target"] == 5
    ok(f"responsible-AI summary reports {summary['corrections']} real corrections "
       f"(target met: {summary['target_met']})")


# ── Live Groq leg ────────────────────────────────────────────────────────────
def test_groq_live():
    if not config.api_key_configured():
        skip("live Groq diagnosis", "GROQ_API_KEY not set")
        return

    from ai.diagnosis import diagnose

    raw, _ = run_checker(**{k: VLAN_CASE[k] for k in ("symptom", "show_output", "category")})
    try:
        diag = diagnose(
            symptom=VLAN_CASE["symptom"], topology=VLAN_CASE["topology"],
            show_output=VLAN_CASE["show_output"], category="VLAN", rule_results=raw,
        )
    except (GroqError, DiagnosisParseError) as exc:
        skip("live Groq diagnosis", f"{type(exc).__name__}: {exc}")
        return

    missing = [f for f in REQUIRED_FIELDS if f not in diag]
    assert not missing, f"diagnosis missing fields: {missing}"
    assert diag["confidence"] in ("Low", "Medium", "High")
    assert diag["severity"] in ("Low", "Medium", "High", "Critical")
    assert isinstance(diag["evidence"], list) and isinstance(diag["fix_steps"], list)
    assert diag["model"], "model not recorded on the diagnosis"
    ok(f"live Groq diagnosis validated ({diag['model']})")
    print(f"        root cause: {diag['root_cause'][:100]}")
    print(f"        confidence: {diag['confidence']} | severity: {diag['severity']} "
          f"| OSI: {diag['osi_layer']}")

    summary = conflict_summary(raw, diag["root_cause"])
    diag_id = db.insert_diagnosis({
        "case_ref": None, "category": "VLAN", "symptom": VLAN_CASE["symptom"],
        "topology": VLAN_CASE["topology"], "show_output": VLAN_CASE["show_output"],
        **diag, "rule_results": raw, "ai_conflict": summary["conflict"],
    })
    stored = db.get_diagnosis(diag_id)
    assert stored["root_cause"] == diag["root_cause"]
    assert stored["evidence"] == diag["evidence"]
    ok(f"live diagnosis round-trips through SQLite (conflict={summary['conflict']})")


def main():
    print(f"\nNetSage AI pipeline tests — temp DB: {_tmp}\n")
    for fn in [
        test_bootstrap_and_dataset,
        test_checker_finds_faults,
        test_empty_and_malformed_input,
        test_missing_api_key,
        test_conflict_detection,
        test_review_decisions,
        test_stats_are_derived,
        test_groq_live,
    ]:
        print(f"{fn.__name__}:")
        fn()
    print(f"\n{len(passed)} passed, {len(skipped)} skipped\n")


if __name__ == "__main__":
    main()
