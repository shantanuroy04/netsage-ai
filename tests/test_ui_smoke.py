"""
tests/test_ui_smoke.py — render every Streamlit page headlessly and fail on any
uncaught exception.

Run:  python tests/test_ui_smoke.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import re  # noqa: E402

from streamlit.string_util import validate_emoji  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from database import db  # noqa: E402
from database.seed import bootstrap  # noqa: E402

PAGES = [
    "app.py",
    "pages/dashboard.py",
    "pages/analyze.py",
    "pages/cases.py",
    "pages/review.py",
    "pages/responsible_ai.py",
    "pages/system.py",
]

failures = []


def render(path: str) -> None:
    at = AppTest.from_file(str(ROOT / path), default_timeout=60)
    at.run()
    if at.exception:
        for exc in at.exception:
            failures.append((path, f"{exc.type}: {exc.message}"))
        print(f"  FAIL  {path}")
        for exc in at.exception:
            print(f"          {exc.type}: {exc.message}")
        return
    errors = [e.value for e in at.error]
    widgets = len(at.markdown) + len(at.metric) + len(at.dataframe)
    note = f"({widgets} elements" + (f", {len(errors)} st.error" if errors else "") + ")"
    print(f"  PASS  {path} {note}")
    for e in errors:
        print(f"          st.error: {e[:120]}")


def check_icons() -> None:
    """
    Streamlit rejects non-emoji icon= values at render time. Symbols like '✓'
    look right in an editor but crash the page, so validate them all up front
    rather than only on whichever branch a test happens to reach.
    """
    sources = [ROOT / "app.py"]
    sources += sorted((ROOT / "pages").glob("*.py"))
    sources += sorted((ROOT / "utils").glob("*.py"))
    bad = []
    for path in sources:
        for m in re.finditer(r'icon="([^"]+)"', path.read_text(encoding="utf-8")):
            try:
                validate_emoji(m.group(1))
            except Exception as exc:
                bad.append((path.name, m.group(1), str(exc)))
    for name, icon, err in bad:
        failures.append((name, f"invalid icon {icon!r}"))
        print(f"  FAIL  {name}: invalid icon {icon!r} — {err}")
    if not bad:
        print(f"  PASS  all icon= values are valid emoji ({len(sources)} files)")


def ensure_pending_diagnosis() -> None:
    """
    review.py has two very different branches. A freshly seeded database has no
    unreviewed rows, so without this the pending branch — the one with the
    decision form — is never rendered by this test.
    """
    if db.get_unreviewed_diagnoses():
        return
    db.insert_diagnosis({
        "category": "VLAN", "symptom": "smoke-test pending diagnosis",
        "topology": "PC1 -> SW1", "show_output": "show vlan brief",
        "root_cause": "smoke-test root cause", "osi_layer": "Layer 2",
        "confidence": "Low", "severity": "Medium", "concept": "Trunking",
        "evidence": ["smoke evidence"], "next_command": "show interfaces trunk",
        "fix_steps": ["smoke step"], "rule_results": [], "ai_conflict": True,
        "model": "smoke-test",
    })
    print("  (inserted one unreviewed diagnosis so review.py renders its form)")


def main():
    print("\nBootstrapping database…")
    print(bootstrap())
    print("\nChecking icons:")
    check_icons()
    print("\nPreparing review queue:")
    ensure_pending_diagnosis()
    print("\nRendering pages:")
    for page in PAGES:
        render(page)
    print()
    if failures:
        print(f"{len(failures)} page(s) raised exceptions:")
        for path, msg in failures:
            print(f"  {path}: {msg}")
        sys.exit(1)
    print(f"All {len(PAGES)} pages rendered without exceptions.\n")


if __name__ == "__main__":
    main()
