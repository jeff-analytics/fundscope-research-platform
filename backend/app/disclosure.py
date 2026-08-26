"""Disclosure-scope utilities for comparable mutual-fund research.

Chinese public funds commonly disclose only the top ten equity holdings in Q1/Q3,
while semiannual and annual reports can contain a broader portfolio.  Any change
metric that compares report periods must therefore normalize the snapshots before
interpreting entries, exits, turnover or style drift.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

_TOP10_TOKENS = {"top10", "top_10", "top 10", "十大重仓", "前十大", "quarterly_top10"}
_FULL_TOKENS = {"full", "full_portfolio", "完整", "全部持仓", "semiannual", "annual"}


def normalize_period(value: Any) -> str:
    s = str(value or "").strip().upper().replace("年", "").replace("季度", "Q")
    s = s.replace("第", "").replace("季", "")
    m = re.search(r"(20\d{2}).*?([1-4])", s)
    if "Q" in s:
        m = re.search(r"(20\d{2})\D*Q\D*([1-4])", s) or m
    return f"{m.group(1)}Q{m.group(2)}" if m else s


def scope_for_period(period: Any, explicit_scope: Any = None) -> str:
    explicit = str(explicit_scope or "").strip().lower()
    if explicit:
        if explicit in _TOP10_TOKENS or "top10" in explicit or "前十" in explicit or "十大" in explicit:
            return "top10"
        if explicit in _FULL_TOKENS or "full" in explicit or "完整" in explicit:
            return "full"
    p = normalize_period(period)
    q = int(p[-1]) if re.fullmatch(r"20\d{2}Q[1-4]", p) else None
    return "top10" if q in {1, 3} else "full" if q in {2, 4} else "unknown"


def frame_scope(frame: pd.DataFrame, period: Any = None) -> str:
    if frame is None or frame.empty:
        return scope_for_period(period)
    p = normalize_period(period or (frame.iloc[0].get("quarter") if "quarter" in frame.columns else ""))
    if "disclosure_scope" in frame.columns:
        vals = [scope_for_period(p, x) for x in frame["disclosure_scope"].dropna().astype(str).tolist()]
        if "top10" in vals:
            return "top10"
        if "full" in vals:
            return "full"
    return scope_for_period(p)


def top_n(frame: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    x = frame.copy()
    if "weight_pct" in x.columns:
        x["weight_pct"] = pd.to_numeric(x["weight_pct"], errors="coerce")
        return x.sort_values("weight_pct", ascending=False, na_position="last").head(n).copy()
    return x.head(n).copy()


def comparable_pair(
    old: pd.DataFrame,
    new: pd.DataFrame,
    old_period: Any,
    new_period: Any,
    *,
    force_basis: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Normalize two snapshots to a disclosure-comparable basis.

    If either side is a top-ten disclosure, both sides are restricted to top ten.
    A full-portfolio comparison is allowed only when both periods are full scope.
    """
    old_scope = frame_scope(old, old_period)
    new_scope = frame_scope(new, new_period)
    basis = force_basis or ("full_portfolio" if old_scope == new_scope == "full" else "top10_comparable")
    if basis == "top10_comparable":
        old_cmp = top_n(old, 10)
        new_cmp = top_n(new, 10)
    else:
        old_cmp = old.copy()
        new_cmp = new.copy()
    meta = {
        "basis": basis,
        "old_period": normalize_period(old_period),
        "new_period": normalize_period(new_period),
        "old_scope": old_scope,
        "new_scope": new_scope,
        "comparable": True,
        "note": "两期统一按前十大披露持仓比较" if basis == "top10_comparable" else "两期均为较完整披露，按完整组合比较",
    }
    return old_cmp, new_cmp, meta


def comparable_history(frame: pd.DataFrame, periods: list[str]) -> pd.DataFrame:
    """Return a top-ten normalized history suitable for sequential trajectories."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=frame.columns if isinstance(frame, pd.DataFrame) else [])
    parts = []
    for p in periods:
        x = frame[frame["quarter"].astype(str).map(normalize_period) == normalize_period(p)].copy()
        if not x.empty:
            x = top_n(x, 10)
            x["comparison_basis"] = "top10_comparable"
            parts.append(x)
    return pd.concat(parts, ignore_index=True) if parts else frame.iloc[0:0].copy()


def periods_apart(old_period: Any, new_period: Any) -> int | None:
    a, b = normalize_period(old_period), normalize_period(new_period)
    if not re.fullmatch(r"20\d{2}Q[1-4]", a) or not re.fullmatch(r"20\d{2}Q[1-4]", b):
        return None
    ay, aq = int(a[:4]), int(a[-1])
    by, bq = int(b[:4]), int(b[-1])
    return (by * 4 + bq) - (ay * 4 + aq)


def equal_spacing(p0: Any, p1: Any, p2: Any) -> bool:
    d1 = periods_apart(p0, p1)
    d2 = periods_apart(p1, p2)
    return bool(d1 and d2 and d1 == d2 and d1 > 0)


def context_label(meta: dict[str, Any] | None) -> str:
    if not meta:
        return ""
    return "Top 10 Comparable" if meta.get("basis") == "top10_comparable" else "Full Portfolio"
