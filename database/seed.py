"""
database/seed.py — dataset loading and the pre-loaded responsible-AI examples.

The six correction records below are *demonstration* data carried over from the
original project. They are written with reviewer = SEED_REVIEWER so the UI can
label them as pre-loaded and never present them as live human reviews. Nothing
is invented at runtime: real reviews only appear when a person submits one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import db

SEED_REVIEWER = "Pre-loaded demo record"
SEED_MODEL = "pre-migration (Gemini 1.5 Flash)"

# Each entry: the AI diagnosis as originally produced, plus the human correction.
RESPONSIBLE_AI_SEEDS = [
    {
        "case_ref": "004", "category": "ACL",
        "symptom": "PC1 in VLAN 30 cannot reach the server even though VLAN 10 and VLAN 20 work fine",
        "topology": "PC1(VLAN30) -> SW1 -> Router -> Server",
        "show_output": "show vlan brief\nVLAN 30 active Fa0/4\nshow interfaces trunk\nVLANs allowed: 1-29,31-4094",
        "root_cause": "ACL may be blocking VLAN 30 traffic on the router",
        "osi_layer": "Layer 3/4", "confidence": "Medium", "severity": "High",
        "concept": "Access control lists",
        "evidence": ["ACL mismatch suspected", "Other VLANs work"],
        "next_command": "show access-lists",
        "fix_steps": ["Review ACL rules", "Remove deny entry for VLAN 30"],
        "review": {
            "decision": "edit",
            "human_root_cause": "VLAN 30 is not allowed on the trunk link",
            "human_osi_layer": "Layer 2",
            "human_correction": "ACL was not the issue. 'show interfaces trunk' shows VLAN 30 excluded from the allowed list.",
            "reason": "Rule checker flagged VLAN 30 missing from trunk — AI missed this and incorrectly blamed ACL.",
        },
    },
    {
        "case_ref": "008", "category": "DNS",
        "symptom": "All PCs lose connectivity to the server after a new trunk was configured",
        "topology": "PC1 -> SW1 ==(trunk)== SW2 -> Server",
        "show_output": "show interfaces trunk\nSW1 native vlan 1\nSW2 native vlan 99",
        "root_cause": "DNS server is unreachable after trunk reconfiguration",
        "osi_layer": "Layer 7", "confidence": "Low", "severity": "Critical",
        "concept": "Name resolution",
        "evidence": ["Connectivity lost after trunk change", "DNS service suspected"],
        "next_command": "ping dns-server",
        "fix_steps": ["Verify DNS server connectivity", "Check DNS configuration"],
        "review": {
            "decision": "reject",
            "human_root_cause": "Native VLAN mismatch between SW1 (VLAN 1) and SW2 (VLAN 99)",
            "human_osi_layer": "Layer 2",
            "human_correction": "Native VLAN mismatch causes STP issues and traffic black-holing. Not a DNS issue.",
            "reason": "AI incorrectly blamed DNS. The trunk show output clearly shows different native VLANs.",
        },
    },
    {
        "case_ref": "013", "category": "Routing",
        "symptom": "PC1 can ping its default gateway but cannot reach the 192.168.30.0/24 server network",
        "topology": "PC1 -> R1 -> R2 -> Server(192.168.30.0/24)",
        "show_output": "show ip route (R1)\nC 192.168.10.0/24 directly connected\nS 192.168.30.0/24 via 192.168.20.99",
        "root_cause": "ACL on R2 may be blocking traffic to 192.168.30.0/24",
        "osi_layer": "Layer 3/4", "confidence": "Medium", "severity": "High",
        "concept": "Static routing",
        "evidence": ["Traffic fails at R2", "ACL could block transit traffic"],
        "next_command": "show access-lists",
        "fix_steps": ["Check ACLs on R2", "Remove blocking rules"],
        "review": {
            "decision": "edit",
            "human_root_cause": "Incorrect next-hop in static route — 192.168.20.99 does not exist",
            "human_osi_layer": "Layer 3",
            "human_correction": "Static route next-hop 192.168.20.99 is incorrect; R2 is at 192.168.20.2. The route is broken before traffic ever reaches R2.",
            "reason": "AI blamed ACL without verifying the static route next-hop. Rule checker caught the unreachable next-hop.",
        },
    },
    {
        "case_ref": "019", "category": "DHCP",
        "symptom": "New PC cannot get an IP address — all DHCP requests are dropped",
        "topology": "PC1 -> SW1 -> R1(DHCP Server)",
        "show_output": "show ip dhcp pool\nPool LAN\nNetwork: 192.168.10.0/24\nExcluded: 192.168.10.1 to 192.168.10.254",
        "root_cause": "DHCP server pool is not configured or server is unreachable",
        "osi_layer": "Layer 3", "confidence": "Medium", "severity": "High",
        "concept": "DHCP address allocation",
        "evidence": ["DHCP requests dropped", "No binding created"],
        "next_command": "show ip dhcp pool",
        "fix_steps": ["Configure DHCP pool", "Verify server reachability"],
        "review": {
            "decision": "edit",
            "human_root_cause": "Entire address range excluded — no addresses available in the DHCP pool",
            "human_osi_layer": "Layer 3",
            "human_correction": "Pool exists but 'ip dhcp excluded-address 192.168.10.1 192.168.10.254' excludes every usable address. The AI missed the excluded range.",
            "reason": "AI claimed the pool does not exist — it does exist, but all addresses are excluded.",
        },
    },
    {
        "case_ref": "026", "category": "VLAN",
        "symptom": "Intermittent connectivity between devices in different VLANs after SW2 was added",
        "topology": "PC1(VLAN10) -> SW1 -> SW2 -> PC2(VLAN20)",
        "show_output": "show interfaces trunk\nSW1 Gi0/1 mode auto not-trunking\nSW2 Gi0/1 mode auto not-trunking",
        "root_cause": "VLAN 20 may be missing from the switch configuration",
        "osi_layer": "Layer 2", "confidence": "Low", "severity": "Medium",
        "concept": "DTP trunk negotiation",
        "evidence": ["VLANs work intermittently", "SW2 recently added"],
        "next_command": "show vlan brief",
        "fix_steps": ["Check VLAN 20 exists on SW2", "Add missing VLAN"],
        "review": {
            "decision": "reject",
            "human_root_cause": "Trunk link not established — both sides are set to DTP auto mode",
            "human_osi_layer": "Layer 2",
            "human_correction": "Output clearly shows 'not-trunking' on both sides with mode 'auto'. DTP auto+auto never forms a trunk. VLAN 20 exists on both switches.",
            "reason": "AI missed the explicit 'not-trunking' status. One side must be set to 'on' or 'desirable'.",
        },
    },
    {
        "case_ref": "031", "category": "NAT",
        "symptom": "Internal PCs can reach each other but cannot access the internet despite NAT being configured",
        "topology": "PC1(192.168.10.10) -> R1(NAT) -> ISP",
        "show_output": "show ip nat translations\n(no entries)\nip nat inside source list 1 interface Gi0/1 overload\naccess-list 1 permit 10.0.0.0 0.0.0.255",
        "root_cause": "R1 WAN interface Gi0/1 may be down causing NAT failures",
        "osi_layer": "Layer 1/3", "confidence": "Medium", "severity": "High",
        "concept": "NAT overload (PAT)",
        "evidence": ["NAT translation table empty", "No entries showing"],
        "next_command": "show ip interface brief",
        "fix_steps": ["Check WAN interface status", "Apply no shutdown if down"],
        "review": {
            "decision": "edit",
            "human_root_cause": "NAT ACL matches the wrong subnet (10.0.0.0/24 instead of 192.168.10.0/24)",
            "human_osi_layer": "Layer 3",
            "human_correction": "ACL 1 permits 10.0.0.0/24, the WAN subnet. LAN hosts (192.168.10.x) never match, so no translations are created. The interface is up.",
            "reason": "AI focused on interface status. The ACL subnet mismatch is the actual fault and is visible in the running config.",
        },
    },
]


def seeded_correction_count() -> int:
    with db.get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE reviewer=?", (SEED_REVIEWER,)
        ).fetchone()[0]


def seed_responsible_ai(force: bool = False) -> int:
    """
    Insert the pre-loaded correction examples. Idempotent: does nothing once
    they are present unless force=True.
    """
    if not force and seeded_correction_count() >= len(RESPONSIBLE_AI_SEEDS):
        return 0

    inserted = 0
    for entry in RESPONSIBLE_AI_SEEDS:
        record = {k: v for k, v in entry.items() if k != "review"}
        record["model"] = SEED_MODEL
        record["rule_results"] = []
        record["ai_conflict"] = True  # each of these was caught by a human/checker
        diag_id = db.insert_diagnosis(record)

        review = dict(entry["review"])
        review["diagnosis_id"] = diag_id
        review["reviewer"] = SEED_REVIEWER
        db.insert_review(review)
        inserted += 1
    return inserted


def clear_seed_data() -> int:
    """Remove the pre-loaded demo records (and their diagnoses)."""
    with db.get_connection() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT diagnosis_id FROM reviews WHERE reviewer=?", (SEED_REVIEWER,))]
        conn.execute("DELETE FROM reviews WHERE reviewer=?", (SEED_REVIEWER,))
        for did in ids:
            conn.execute("DELETE FROM diagnoses WHERE id=?", (did,))
    return len(ids)


def bootstrap() -> dict:
    """Called once per app start: schema, dataset, demo corrections."""
    db.init_db()
    cases = db.seed_cases_from_csv()
    corrections = seed_responsible_ai()
    return {"cases": cases, "seeded_corrections": corrections}
