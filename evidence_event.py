from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _compact(value: Any, limit: int = 180) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_text(row: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _event_role_from_text(text: str, fallback: str) -> str:
    lowered = text.lower()
    if any(token in text for token in ["退赛", "弃权", "不战而胜"]) or any(
        token in lowered for token in ["walkover", "withdraw", "retired", "retirement"]
    ):
        return "actual_result_status"
    if any(token in text for token in ["第一阶段", "第二阶段", "阶段"]):
        if any(token in text for token in ["启动", "开始", "开启"]):
            return "phase_start"
        if any(token in text for token in ["结束", "完成", "截止"]):
            return "phase_end"
    if any(token in text for token in ["公布", "发布", "宣布", "结果出炉"]):
        return "result_release"
    if any(token in text for token in ["目前", "当前", "截至", "现位于", "距离"]):
        return "current_status"
    if re.search(r"\b20\d{2}[-年/.]\d{1,2}[-月/.]\d{1,2}", text):
        return "dated_fact"
    return fallback


def _infer_predicate(row: Dict[str, Any], summary: Dict[str, Any]) -> str:
    point_conversion = _as_dict(summary.get("point_conversion"))
    return _first_text(
        row,
        [
            "conflict_slot",
            "slot",
            "predicate",
            "metric",
            "relation",
            "evidence_mode",
            "page_role",
        ],
    ) or _first_text(
        point_conversion,
        ["conflict_slot", "evidence_mode", "query_effective_role", "page_role"],
    )


def _date_only_guard(event: Dict[str, Any]) -> Dict[str, Any]:
    predicate = _text(event.get("predicate"))
    subject = _text(event.get("subject"))
    object_value = _text(event.get("object"))
    event_role = _text(event.get("event_role"))
    text = _text(event.get("source_sentence"))
    date_like = bool(re.search(r"20\d{2}[-年/.]\d{1,2}([-月/.]\d{1,2})?", text))
    date_only_predicate = predicate in {
        "date",
        "time",
        "publish_time",
        "page_publish_time",
        "published_at",
    }
    page_date_role = event_role in {"page_publish_time", "dated_fact"} and not any(
        token in event_role for token in ["current", "phase", "result", "status"]
    )
    has_fact_binding = bool(subject or object_value or predicate not in {"", "date", "time", "publish_time"})
    blocked = bool((date_only_predicate or page_date_role) and date_like and not has_fact_binding)
    return {
        "blocked": blocked,
        "reason": "date_without_subject_or_fact_binding" if blocked else "",
    }


def _event_from_point(
    claim_id: str,
    claim_text: str,
    row: Dict[str, Any],
    summary: Dict[str, Any],
    role: str,
    index: int,
) -> Dict[str, Any]:
    source_sentence = _first_text(
        row,
        ["text", "sentence", "evidence_sentence", "point", "snippet", "detail", "title"],
    )
    event_role = _event_role_from_text(source_sentence, role)
    event = {
        "event_id": f"{claim_id}:ev{index}",
        "claim_id": claim_id,
        "claim": _compact(claim_text, 120),
        "source_sentence": _compact(source_sentence, 240),
        "subject": _first_text(row, ["subject", "entity", "team", "person", "company"]),
        "object": _first_text(row, ["object", "opponent", "counterparty", "target"]),
        "predicate": _infer_predicate(row, summary),
        "claim_value": row.get("claim_value"),
        "evidence_value": row.get("evidence_value") or row.get("value"),
        "time_scope": _first_text(row, ["time_scope", "date", "event_date", "published_at"]),
        "event_role": event_role,
        "source_type": _first_text(row, ["source_type", "source"]),
        "page_role": _first_text(row, ["page_role"]),
        "url": _first_text(row, ["url"]),
        "title": _compact(_first_text(row, ["title"]), 120),
        "direct_answer": _first_text(row, ["direct_answer", "directness"]),
        "direct_evidence_gate_result": _first_text(row, ["direct_evidence_gate_result"]),
        "slot_contract_state": _first_text(row, ["slot_contract_state"]),
        "slot_missing": _as_list(row.get("slot_missing"))[:6],
        "slot_mismatch": _as_list(row.get("slot_mismatch"))[:6],
        "same_slot_ready": bool(row.get("same_slot_ready")),
        "same_slot_conflict_ready": bool(row.get("same_slot_conflict_ready")),
        "event_source_role": role,
        "confidence": float(row.get("confidence") or row.get("score") or row.get("relevance_score") or 0.0),
        "blocking_risks": [],
    }
    guard = _date_only_guard(event)
    if guard.get("blocked"):
        event["blocking_risks"].append(guard.get("reason"))
    if not event["source_sentence"]:
        event["blocking_risks"].append("missing_source_sentence")
    if not event["predicate"]:
        event["blocking_risks"].append("missing_predicate")
    return event


def build_evidence_events(
    claim_item: Dict[str, Any],
    raw_evidence: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
    coverage: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    summary = _as_dict(summary)
    claim_id = _text(claim_item.get("claim_id") or claim_item.get("id"))
    claim_text = _text(claim_item.get("claim"))
    rows: List[Dict[str, Any]] = []
    index = 1
    for role, bucket_name in [
        ("support_candidate", "supporting_points"),
        ("refutation_candidate", "refuting_points"),
        ("uncertain_candidate", "uncertain_points"),
        ("reader_candidate", "evidence_sentence_candidates"),
    ]:
        for point in _as_list(summary.get(bucket_name)):
            if not isinstance(point, dict):
                continue
            rows.append(_event_from_point(claim_id, claim_text, point, summary, role, index))
            index += 1
    if not rows:
        for item in raw_evidence[:6]:
            if not isinstance(item, dict):
                continue
            rows.append(_event_from_point(claim_id, claim_text, item, summary, "raw_page_candidate", index))
            index += 1
    return rows[:12]


def build_phase_graph_summary(
    claim_item: Dict[str, Any],
    evidence_events: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
    coverage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    claim_id = _text(claim_item.get("claim_id") or claim_item.get("id"))
    claim_text = _text(claim_item.get("claim"))
    phase_roles = [_text(row.get("event_role")) for row in evidence_events if isinstance(row, dict)]
    role_counts: Dict[str, int] = {}
    for role in phase_roles:
        if role:
            role_counts[role] = role_counts.get(role, 0) + 1
    claim_role = ""
    if any(token in claim_text for token in ["结束", "完成", "结果", "什么时候出"]):
        claim_role = "whole_event_end_or_result_release"
    elif any(token in claim_text for token in ["开始", "启动", "开启", "第一阶段", "第二阶段"]):
        claim_role = "phase_start"
    elif any(token in claim_text for token in ["目前", "当前", "现在", "距离"]):
        claim_role = "current_status"
    date_only_blocks = [
        row for row in evidence_events
        if isinstance(row, dict) and "date_without_subject_or_fact_binding" in _as_list(row.get("blocking_risks"))
    ]
    return {
        "claim_id": claim_id,
        "claim_role": claim_role,
        "evidence_roles": role_counts,
        "phase_graph_state": "has_phase_or_time_role" if claim_role or role_counts else "no_phase_signal",
        "date_only_guard_block_count": len(date_only_blocks),
        "date_only_guard_examples": [
            {
                "event_id": row.get("event_id"),
                "source_sentence": row.get("source_sentence"),
                "reason": "date_without_subject_or_fact_binding",
            }
            for row in date_only_blocks[:3]
        ],
    }


def flatten_event_debug(events_by_claim: Dict[str, List[Dict[str, Any]]], limit: int = 24) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for claim_id, events in events_by_claim.items():
        for event in events:
            if not isinstance(event, dict):
                continue
            rows.append(
                {
                    "event_id": event.get("event_id"),
                    "claim_id": claim_id,
                    "event_role": event.get("event_role"),
                    "predicate": event.get("predicate"),
                    "source_sentence": event.get("source_sentence"),
                    "same_slot_ready": event.get("same_slot_ready"),
                    "same_slot_conflict_ready": event.get("same_slot_conflict_ready"),
                    "blocking_risks": event.get("blocking_risks") or [],
                    "page_role": event.get("page_role"),
                    "source_type": event.get("source_type"),
                }
            )
            if len(rows) >= limit:
                return rows
    return rows
