from __future__ import annotations

from typing import Any, Dict, List, Optional


LABEL_0 = "0-主需存在事实错误"
LABEL_1 = "1-次需存在事实错误"
LABEL_2 = "2-无事实错误"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _infer_scope(claim: Dict[str, Any]) -> str:
    centrality = _text(claim.get("centrality"))
    if centrality in {"core", "supporting", "peripheral"}:
        return centrality
    hint = _text(claim.get("centrality_hint"))
    if hint in {"core", "supporting", "peripheral"}:
        return hint
    return "supporting"


def _infer_evidence_state(summary: Dict[str, Any]) -> str:
    point_conversion = _as_dict(summary.get("point_conversion"))
    direct_refute = [
        row for row in _as_list(summary.get("refuting_points"))
        if isinstance(row, dict) and _text(row.get("direct_answer")) == "direct"
    ]
    direct_support = [
        row for row in _as_list(summary.get("supporting_points"))
        if isinstance(row, dict) and _text(row.get("direct_answer")) == "direct"
    ]
    if direct_refute:
        return "direct_refuted"
    if direct_support:
        return "direct_supported"
    if point_conversion.get("same_slot_conflict_ready"):
        return "same_slot_conflict_candidate"
    if point_conversion.get("same_slot_ready"):
        return "same_slot_related"
    if _as_list(summary.get("evidence_sentence_candidates")):
        return "candidate_unconverted"
    coverage = _as_dict(summary.get("coverage"))
    coverage_level = _text(coverage.get("coverage_level"))
    if coverage_level in {"weak", "partial", "moderate", "strong"}:
        return "partial_incomparable"
    return "unsupported"


def _infer_slot_state(summary: Dict[str, Any]) -> str:
    point_conversion = _as_dict(summary.get("point_conversion"))
    phase_graph = _as_dict(summary.get("phase_graph"))
    claim_role = _text(phase_graph.get("claim_role"))
    if point_conversion.get("same_slot_conflict_ready"):
        return "same_slot_conflict"
    if point_conversion.get("same_slot_ready"):
        return "same_slot"
    missing = _as_list(point_conversion.get("slot_missing"))
    mismatch = _as_list(point_conversion.get("slot_mismatch"))
    if claim_role in {"phase_start", "phase_end", "current_status", "whole_event_end_or_result_release"} and (
        int(phase_graph.get("date_only_guard_block_count") or 0) > 0 or mismatch
    ):
        return "phase_boundary_conflict"
    if mismatch:
        return "slot_mismatch"
    if missing:
        return "missing_slot"
    if claim_role in {"phase_start", "phase_end", "current_status", "whole_event_end_or_result_release"}:
        return "phase_boundary_candidate"
    if _text(point_conversion.get("conflict_slot")):
        return "conflict_slot_candidate"
    return "unknown"


def _infer_risk_shape(claim: Dict[str, Any], summary: Dict[str, Any], phase_graph: Dict[str, Any]) -> List[str]:
    source_intent = _as_dict(claim.get("source_intent"))
    claim_text = _text(claim.get("claim"))
    shapes: List[str] = []
    risk_type = _text(source_intent.get("risk_type"))
    if risk_type:
        shapes.append(risk_type)
    mode = _text(source_intent.get("evidence_mode") or summary.get("evidence_mode"))
    if mode:
        shapes.append(mode)
    if any(token in claim_text for token in ["唯一", "完全", "根本不需要", "没有实质性影响", "无悬念"]):
        shapes.append("absolute_or_resolved_claim")
    if any(token in claim_text for token in ["第一阶段", "第二阶段", "开始", "结束", "发布时间", "什么时候出"]):
        shapes.append("phase_boundary_time")
    phase_claim_role = _text(phase_graph.get("claim_role"))
    if phase_claim_role in {"phase_start", "phase_end", "current_status", "whole_event_end_or_result_release"}:
        shapes.append(f"phase_graph:{phase_claim_role}")
    if int(phase_graph.get("date_only_guard_block_count") or 0) > 0:
        shapes.append("date_only_conflict_guarded")
    return list(dict.fromkeys([shape for shape in shapes if shape]))


def _infer_permission(scope: str, evidence_state: str, risk_shape: List[str]) -> str:
    if evidence_state == "direct_refuted":
        return "evidence_decide"
    if evidence_state == "direct_supported":
        return "evidence_decide"
    if any(shape.startswith("phase_graph:") for shape in risk_shape):
        return "risk_calibrate" if scope == "core" else "rubric_fallback"
    if "date_only_conflict_guarded" in risk_shape:
        return "insufficient_until_fact_binding"
    if evidence_state in {"same_slot_conflict_candidate", "candidate_unconverted", "partial_incomparable"}:
        return "risk_calibrate" if scope == "core" else "rubric_fallback"
    if risk_shape:
        return "risk_calibrate"
    return "insufficient"


def _label_candidate(scope: str, evidence_state: str, permission: str) -> str:
    if permission == "evidence_decide" and evidence_state == "direct_refuted":
        return LABEL_0 if scope == "core" else LABEL_1
    if permission == "evidence_decide" and evidence_state == "direct_supported":
        return LABEL_2
    if permission == "risk_calibrate":
        return LABEL_0 if scope == "core" else LABEL_1
    if permission == "rubric_fallback":
        return LABEL_1
    return LABEL_2


def build_decision_state_debug(
    claims: List[Dict[str, Any]],
    claim_summaries: Dict[str, Dict[str, Any]],
    phase_graph: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    phase_graph = phase_graph if isinstance(phase_graph, dict) else {}
    rows: List[Dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = _text(claim.get("claim_id") or claim.get("id"))
        if not claim_id:
            continue
        summary = _as_dict(claim_summaries.get(claim_id))
        phase_row = _as_dict(phase_graph.get(claim_id))
        scope = _infer_scope(claim)
        evidence_state = _infer_evidence_state(summary)
        slot_state = _infer_slot_state(summary)
        risk_shape = _infer_risk_shape(claim, summary, phase_row)
        permission = _infer_permission(scope, evidence_state, risk_shape)
        rows.append(
            {
                "claim_id": claim_id,
                "scope": scope,
                "evidence_state": evidence_state,
                "slot_state": slot_state,
                "risk_shape": risk_shape,
                "decision_permission": permission,
                "label_candidate": _label_candidate(scope, evidence_state, permission),
                "reason_basis": _reason_basis(scope, evidence_state, slot_state, permission, risk_shape),
            }
        )
    return {
        "claim_state_rows": rows,
        "sample_state_summary": _sample_state_summary(rows),
    }


def _reason_basis(scope: str, evidence_state: str, slot_state: str, permission: str, risk_shape: List[str]) -> str:
    if permission == "evidence_decide":
        return f"{scope} claim has {evidence_state} with {slot_state}"
    if "date_only_conflict_guarded" in risk_shape:
        return "date conflict is blocked until subject and fact binding are present"
    if permission == "risk_calibrate":
        return f"{scope} claim is not directly decided but has risk shape: {', '.join(risk_shape) or 'unknown'}"
    if permission == "rubric_fallback":
        return "supporting claim remains unresolved and may enter controlled rubric fallback"
    return "no direct evidence decision and no authorized risk shape"


def _sample_state_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {
        "claim_count": len(rows),
        "evidence_decide_count": 0,
        "risk_calibrate_count": 0,
        "rubric_fallback_count": 0,
        "insufficient_count": 0,
        "date_only_guarded_count": 0,
    }
    for row in rows:
        permission = _text(row.get("decision_permission"))
        if permission == "evidence_decide":
            summary["evidence_decide_count"] += 1
        elif permission == "risk_calibrate":
            summary["risk_calibrate_count"] += 1
        elif permission == "rubric_fallback":
            summary["rubric_fallback_count"] += 1
        else:
            summary["insufficient_count"] += 1
        if "date_only_conflict_guarded" in _as_list(row.get("risk_shape")):
            summary["date_only_guarded_count"] += 1
    return summary
