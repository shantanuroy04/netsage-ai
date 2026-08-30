"""
checker/runner.py — deterministic rule-checker orchestration.

Runs before every AI call. The individual checkers (ip/vlan/route/interface)
are unchanged; this module aggregates them and normalises their output into the
structured report the UI and the AI prompt consume.
"""
from .interface_checker import check_all_interface_rules
from .ip_checker import check_all_ip_rules
from .route_checker import check_all_route_rules
from .vlan_checker import check_all_vlan_rules

# checker status -> report severity
SEVERITY_BY_STATUS = {"fail": "high", "warn": "medium", "pass": "info"}

# Which show command each rule draws its evidence from — used in the UI so a
# finding always points back at observable output rather than an assertion.
EVIDENCE_COMMAND = {
    "duplicate_ip": "show ip interface brief",
    "subnet_mask": "show running-config",
    "gateway_mismatch": "ipconfig / show ip interface brief",
    "private_on_wan": "show ip interface brief",
    "vlan_present": "show vlan brief",
    "trunk_allowed": "show interfaces trunk",
    "native_vlan_mismatch": "show interfaces trunk",
    "trunk_mode": "show interfaces trunk",
    "default_route": "show ip route",
    "route_to_dest": "show ip route",
    "next_hop_reachable": "show ip route",
    "routing_loop": "show ip route",
    "interface_up": "show ip interface brief",
    "ip_assigned": "show ip interface brief",
    "duplex_mismatch": "show interfaces",
    "error_counters": "show interfaces",
}


def run_all_checks(symptom: str, show_output: str, category: str,
                   extra: dict | None = None) -> list[dict]:
    """
    Run every applicable deterministic rule against the supplied show-output.

    Returns a list of raw result dicts: {"rule", "status", "detail"}.
    """
    extra = extra or {}
    results: list[dict] = []
    results.extend(check_all_ip_rules(show_output, extra))
    results.extend(check_all_vlan_rules(show_output, category))
    results.extend(check_all_route_rules(show_output, category))
    results.extend(check_all_interface_rules(show_output))
    return results


def build_report(rule_results: list[dict]) -> dict:
    """
    Normalise raw results into the structured report:

        {"status": "ok"|"warning"|"fail", "findings": [
            {"type","severity","message","evidence"}], "counts": {...}}

    Only warn/fail rules become findings — a passing rule is not a finding.
    """
    findings = [
        {
            "type": r["rule"],
            "severity": SEVERITY_BY_STATUS.get(r["status"], "info"),
            "message": r["detail"],
            "evidence": EVIDENCE_COMMAND.get(r["rule"], "supplied show output"),
        }
        for r in rule_results
        if r.get("status") in ("warn", "fail")
    ]
    counts = {s: sum(1 for r in rule_results if r.get("status") == s)
              for s in ("pass", "warn", "fail")}

    if counts["fail"]:
        status = "fail"
    elif counts["warn"]:
        status = "warning"
    else:
        status = "ok"

    return {"status": status, "findings": findings, "counts": counts}


def analyze(symptom: str, show_output: str, category: str,
            extra: dict | None = None) -> tuple[list[dict], dict]:
    """Convenience: raw results plus the structured report in one call."""
    raw = run_all_checks(symptom, show_output, category, extra)
    return raw, build_report(raw)


def failed_rules(rule_results: list[dict]) -> list[dict]:
    return [r for r in rule_results if r.get("status") == "fail"]


def has_conflict(rule_results: list[dict], ai_diagnosis: str) -> bool:
    """
    Heuristic: a rule hard-failed but the AI root cause never mentions that
    concept -> the two disagree and a human must arbitrate.
    """
    failing = failed_rules(rule_results)
    if not failing:
        return False
    ai_lower = (ai_diagnosis or "").lower()
    for rule in failing:
        key = rule["rule"].lower().replace("_", " ").split()[0]
        if key not in ai_lower:
            return True
    return False


def conflict_summary(rule_results: list[dict], ai_root_cause: str) -> dict:
    """Everything the UI needs to render the agreement/conflict banner."""
    failing = failed_rules(rule_results)
    conflict = has_conflict(rule_results, ai_root_cause)
    return {
        "conflict": conflict,
        "ai_root_cause": ai_root_cause,
        "checker_findings": [r["detail"] for r in failing],
        "checker_rules": [r["rule"] for r in failing],
        "message": (
            "Human review required — the AI and the deterministic checker point at "
            "different faults."
            if conflict
            else "AI diagnosis and deterministic checker are consistent."
        ),
    }


def demo():
    trunk = (
        "show vlan brief\n"
        "VLAN Name     Status    Ports\n"
        "30   FINANCE  active    Fa0/4\n"
        "show interfaces trunk\n"
        "Port  Mode  Encapsulation Status    Native vlan\n"
        "Gi0/1 on    802.1q        trunking  1\n"
        "VLANs allowed on trunk: 1-29,31-4094\n"
    )
    raw, report = analyze("VLAN 30 unreachable", trunk, "VLAN")
    assert report["status"] == "fail", report
    assert any(f["type"] == "trunk_allowed" for f in report["findings"]), report
    assert all(f["severity"] != "info" for f in report["findings"])

    # AI names the trunk -> agreement; AI blames an ACL -> conflict.
    assert has_conflict(raw, "VLAN 30 missing from the trunk allowed list") is False
    assert has_conflict(raw, "An ACL is dropping the traffic") is True
    assert conflict_summary(raw, "An ACL is dropping the traffic")["conflict"] is True

    # Clean input produces no hard failures.
    clean = "Interface        IP-Address      OK? Method Status Protocol\nGi0/0 10.0.0.1 YES manual up up\n"
    _, ok_report = analyze("all fine", clean, "Gateway")
    assert ok_report["status"] in ("ok", "warning"), ok_report
    print("checker/runner.py self-check OK")


if __name__ == "__main__":
    demo()
