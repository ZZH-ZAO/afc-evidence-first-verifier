# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set


EXCLUSIVE_ROUTE_HINT_PATTERN = re.compile(
    r"(唯一|只能|必经|必须经过|完全绕开|根本不需要经过|唯一海上通道|only route|must pass|without crossing)",
    flags=re.I,
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def required_slot_profile_for_mode(
    evidence_mode: str,
    claim_text: str = "",
    source_intent: Optional[Dict[str, Any]] = None,
    decision_slots: Optional[Dict[str, Any]] = None,
) -> List[str]:
    source_intent = source_intent if isinstance(source_intent, dict) else {}
    decision_slots = decision_slots if isinstance(decision_slots, dict) else {}
    mode = str(evidence_mode or "")
    claim_shape = str(source_intent.get("claim_shape") or "")
    route_meta = source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}
    text = normalize_text(claim_text)

    if mode == "numeric_fact":
        return ["time_scope", "metric_or_relation"]
    if mode in {"date_fact", "schedule_fact"}:
        profile = ["time_scope", "status_or_result"]
        if not normalize_text(str(decision_slots.get("subject") or "")) and re.search(
            r"(A股|港股|黄蜂|篮网|阿联酋|美国|伊朗|球队|银行|汇丰|央行)",
            text,
        ):
            profile.append("subject")
        return profile
    if mode == "event_result":
        return ["subject", "status_or_result"]
    if mode == "route_fact":
        profile = ["subject", "metric_or_relation"]
        route_object_explicit = bool(
            normalize_text(str(decision_slots.get("object") or ""))
            or normalize_text(str(route_meta.get("destination") or ""))
            or EXCLUSIVE_ROUTE_HINT_PATTERN.search(text)
        )
        if claim_shape == "exclusive_premise" or route_object_explicit:
            profile.append("object")
        return profile
    if mode in {"policy_fact", "entity_fact"}:
        return ["subject", "status_or_result"]
    return ["subject", "status_or_result"]


def slot_bucket_aliases(slot_name: str, evidence_mode: str) -> List[str]:
    mapping = {
        "subject": ["entity", "route"],
        "object": ["entity", "route"],
        "time_scope": ["time"],
        "metric_or_relation": ["numeric", "event", "route", "policy", "status"],
        "status_or_result": ["status", "event", "policy"],
    }
    aliases = list(mapping.get(slot_name, []))
    if evidence_mode == "numeric_fact" and "numeric" not in aliases:
        aliases.append("numeric")
    if evidence_mode in {"date_fact", "schedule_fact"} and "time" not in aliases:
        aliases.append("time")
    if evidence_mode == "route_fact" and "route" not in aliases:
        aliases.append("route")
    return aliases


def _normalize_observed_slots(observed_slots: Optional[Dict[str, Iterable[Any]]]) -> Dict[str, Set[str]]:
    normalized: Dict[str, Set[str]] = {}
    if not isinstance(observed_slots, dict):
        return normalized
    for slot_name, values in observed_slots.items():
        slot_key = normalize_text(str(slot_name))
        if not slot_key:
            continue
        bucket: Set[str] = set()
        if isinstance(values, (list, tuple, set)):
            for value in values:
                text = normalize_text(str(value))
                if text:
                    bucket.add(text.lower())
        elif values is not None:
            text = normalize_text(str(values))
            if text:
                bucket.add(text.lower())
        if bucket:
            normalized[slot_key] = bucket
    return normalized


def infer_missing_required_slots(
    decision_slots: Dict[str, Any],
    evidence_mode: str,
    claim_text: str = "",
    source_intent: Optional[Dict[str, Any]] = None,
    observed_buckets: Optional[Iterable[str]] = None,
    observed_slots: Optional[Dict[str, Iterable[Any]]] = None,
    required_slots: Optional[Iterable[str]] = None,
) -> List[str]:
    decision_slots = decision_slots if isinstance(decision_slots, dict) else {}
    required = (
        [normalize_text(str(slot)) for slot in required_slots if normalize_text(str(slot))]
        if required_slots is not None
        else required_slot_profile_for_mode(evidence_mode, claim_text, source_intent, decision_slots)
    )
    normalized_observed_buckets = {
        normalize_text(str(bucket))
        for bucket in (observed_buckets or [])
        if normalize_text(str(bucket))
    }
    normalized_observed_slots = _normalize_observed_slots(observed_slots)
    missing: List[str] = []

    for slot_name in required:
        slot_value = normalize_text(str(decision_slots.get(slot_name) or ""))
        if slot_value:
            continue
        if normalized_observed_slots.get(slot_name):
            continue
        aliases = slot_bucket_aliases(slot_name, evidence_mode)
        if aliases and any(alias in normalized_observed_buckets for alias in aliases):
            continue
        missing.append(slot_name)
    return missing
