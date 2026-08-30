"""
utils/metrics.py — derived metrics for the dashboard and responsible-AI log.

Every number comes from database rows. When there is no data the functions
return None rather than 0, so the UI can say "not enough reviewed cases yet"
instead of implying a real measurement.
"""
MIN_CORRECTIONS_TARGET = 5


def rate(part: int, whole: int) -> float | None:
    """Percentage, or None when there is nothing to divide by."""
    if not whole:
        return None
    return round(part / whole * 100, 1)


def agreement_rate(stats: dict) -> float | None:
    """Share of reviewed diagnoses the human accepted unchanged."""
    return rate(stats.get("accepted", 0), stats.get("reviewed", 0))


def correction_rate(stats: dict) -> float | None:
    """Share of reviewed diagnoses the human edited or rejected."""
    return rate(stats.get("corrections", 0), stats.get("reviewed", 0))


def conflict_rate(stats: dict) -> float | None:
    """Share of diagnoses where the AI and the rule checker disagreed."""
    return rate(stats.get("conflicts", 0), stats.get("total_diagnoses", 0))


def pct_label(value: float | None, fallback: str = "—") -> str:
    return f"{value}%" if value is not None else fallback


def responsible_ai_summary(stats: dict, log_rows: list[dict]) -> dict:
    """Counts + the shortfall against the 5-correction demonstration target."""
    corrections = len(log_rows)
    return {
        "total_diagnoses": stats.get("total_diagnoses", 0),
        "reviewed": stats.get("reviewed", 0),
        "accepted": stats.get("accepted", 0),
        "edited": stats.get("edited", 0),
        "rejected": stats.get("rejected", 0),
        "corrections": corrections,
        "agreement_rate": agreement_rate(stats),
        "correction_rate": correction_rate(stats),
        "target": MIN_CORRECTIONS_TARGET,
        "target_met": corrections >= MIN_CORRECTIONS_TARGET,
        "shortfall": max(MIN_CORRECTIONS_TARGET - corrections, 0),
    }


def distribution(rows: list[dict], label_key: str = "label",
                 count_key: str = "count") -> list[tuple[str, int]]:
    """Normalise a grouped SQL result into (label, count) pairs."""
    return [(str(r.get(label_key) or "Unspecified"), int(r.get(count_key) or 0))
            for r in rows if int(r.get(count_key) or 0) > 0]


def demo():
    empty = {"accepted": 0, "reviewed": 0, "corrections": 0,
             "conflicts": 0, "total_diagnoses": 0}
    assert agreement_rate(empty) is None
    assert correction_rate(empty) is None
    assert pct_label(None) == "—"

    stats = {"accepted": 3, "reviewed": 10, "corrections": 7,
             "conflicts": 2, "total_diagnoses": 20, "edited": 4, "rejected": 3}
    assert agreement_rate(stats) == 30.0
    assert correction_rate(stats) == 70.0
    assert conflict_rate(stats) == 10.0
    assert pct_label(30.0) == "30.0%"

    s = responsible_ai_summary(stats, [{}] * 7)
    assert s["target_met"] is True and s["shortfall"] == 0
    s2 = responsible_ai_summary(stats, [{}] * 2)
    assert s2["target_met"] is False and s2["shortfall"] == 3

    assert distribution([{"label": "VLAN", "count": 5}, {"label": None, "count": 0}]) \
        == [("VLAN", 5)]
    print("utils/metrics.py self-check OK")


if __name__ == "__main__":
    demo()
