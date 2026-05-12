from __future__ import annotations

from typing import Any, Dict, List, Optional


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def build_decision_policy_debug(decision_state_debug: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    decision_state_debug = _as_dict(decision_state_debug)
    rows = [row for row in _as_list(decision_state_debug.get("claim_state_rows")) if isinstance(row, dict)]
    if not rows:
        return {
            "policy_route": "insufficient",
            "allow_rubric_fallback": False,
            "dominant_scope": "",
            "dominant_reason_basis": "",
            "state_counts": {},
        }
    state_counts: Dict[str, int] = {}
    permission_counts: Dict[str, int] = {}
    for row in rows:
        state = _text(row.get("evidence_state"))
        permission = _text(row.get("decision_permission"))
        if state:
            state_counts[state] = state_counts.get(state, 0) + 1
        if permission:
            permission_counts[permission] = permission_counts.get(permission, 0) + 1
    ranked_rows = sorted(
        rows,
        key=lambda row: (
            0 if _text(row.get("scope")) == "core" else 1,
            0 if _text(row.get("decision_permission")) == "evidence_decide" else 1,
            0 if _text(row.get("decision_permission")) == "risk_calibrate" else 1,
            0 if _text(row.get("decision_permission")) == "rubric_fallback" else 1,
        ),
    )
    dominant = ranked_rows[0]
    dominant_scope = _text(dominant.get("scope"))
    dominant_reason_basis = _text(dominant.get("reason_basis"))
    allow_rubric_fallback = any(
        _text(row.get("decision_permission")) in {"risk_calibrate", "rubric_fallback"}
        for row in rows
    )
    if any(_text(row.get("decision_permission")) == "evidence_decide" for row in rows):
        policy_route = "evidence_decide"
    elif any(_text(row.get("decision_permission")) == "risk_calibrate" for row in rows):
        policy_route = "risk_calibrate"
    elif allow_rubric_fallback:
        policy_route = "rubric_fallback"
    else:
        policy_route = "insufficient"
    return {
        "policy_route": policy_route,
        "allow_rubric_fallback": allow_rubric_fallback,
        "dominant_scope": dominant_scope,
        "dominant_reason_basis": dominant_reason_basis,
        "state_counts": state_counts,
        "permission_counts": permission_counts,
    }
