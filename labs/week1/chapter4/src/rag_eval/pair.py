"""Optional pairwise model/config evaluation."""
from __future__ import annotations


def run_pair(rows_a: list[dict], rows_b: list[dict]) -> dict:
    cases = []
    wins = 0
    for left, right in zip(rows_a, rows_b, strict=False):
        a = left.get("metrics", {}).get("accuracy", 0)
        b = right.get("metrics", {}).get("accuracy", 0)
        winner = "A" if a > b else "B" if b > a else "TIE"
        wins += winner == "A"
        cases.append({"case_id": left.get("case_id"), "winner": winner})
    comparisons = len(cases)
    return {"comparisons": comparisons, "a_wins": wins, "win_rate_a": wins / comparisons if comparisons else 0.0, "cases": cases}
