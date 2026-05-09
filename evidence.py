# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from afc_route_markers import (
    ROUTE_DIRECTIONAL_MARKERS,
    ROUTE_OBJECT_MARKERS,
    ROUTE_QUERY_STOPWORDS,
    ROUTE_RELATION_MARKERS,
    ROUTE_STRICT_OBJECT_MARKERS,
)
from afc_schema import (
    EVIDENCE_MODE_DATE,
    EVIDENCE_MODE_NUMERIC,
    EVIDENCE_MODE_ROUTE,
    EVIDENCE_MODE_SCHEDULE,
    POINT_STAGE_CONVERTED,
    POINT_STAGE_DIRECT_NOT_CONVERTED,
    POINT_STAGE_DIRECT_TO_UNCERTAIN,
    POINT_STAGE_NO_CANDIDATE,
    POINT_STAGE_NO_DIRECT,
    POINT_STAGE_POINT_NOT_DIRECT,
    POINT_STAGE_RELATED_ONLY,
    POINT_STAGE_ROUTE_RELATION_MISSING,
    SENTENCE_DIRECTNESS_DIRECT,
    SENTENCE_DIRECTNESS_PARTIAL,
    SENTENCE_DIRECTNESS_RELATED_ONLY,
)
from evidence_contract import infer_missing_required_slots as shared_infer_missing_required_slots

VERIFICATION_MECHANISM_TYPES = {
    "structured_numeric_authority",
    "date_authority",
    "event_result_page",
    "relation_sentence",
    "current_status_update",
    "symbolic_compute",
    "general_web_evidence",
    "unknown",
}

STRUCTURED_POINT_DIRECT_BLOCKING_RISKS = {
    "point_time_scope_mismatch",
    "point_subject_currency_mismatch",
    "point_metric_field_missing",
    "point_metric_value_missing",
}

ANNOUNCEMENT_CLAIM_MARKERS = ("announce", "announced", "announcement", "公布", "宣布", "发布")
NON_ANNOUNCEMENT_EVENT_MARKERS = (
    "lecture",
    "podcast",
    "interview",
    "banquet",
    "ceremony",
    "speech",
    "photo gallery",
    "award ceremony",
    "prize lecture",
    "prize presentation",
    "award ceremony video",
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def dedupe_keep_order(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        text = normalize_text(str(value))
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def unique_points(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for point in points:
        key = (
            point.get("type"),
            point.get("claim_value"),
            point.get("evidence_value"),
            point.get("url"),
            point.get("source_type"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(point)
    return deduped


def evidence_text(item: Dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("snippet") or ""),
                str(item.get("detail") or ""),
            ]
        )
    )


def is_discovery_only_item(item: Dict[str, Any]) -> bool:
    source = normalize_text(str(item.get("source") or "")).lower()
    snippet = normalize_text(str(item.get("snippet") or "")).lower()
    return source == "official_discovery" or snippet == "official discovery candidate"


def should_summarize_item(item: Dict[str, Any]) -> bool:
    return item.get("source_type") != "input_context" and not is_discovery_only_item(item)


def point_source(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_type": item.get("source_type"),
        "url": item.get("url"),
        "title": item.get("title"),
        "directness_score": item.get("directness_score", 0),
        "relevance_score": item.get("relevance_score", 0),
        "event_window_score": item.get("event_window_score", 0),
        "evidence_contract_status": item.get("evidence_contract_status"),
        "evidence_contract_score": item.get("evidence_contract_score"),
        "evidence_contract_role": item.get("evidence_contract_role"),
        "evidence_contract_risks": item.get("evidence_contract_risks", []),
    }


def direct_answer_level(item: Dict[str, Any], required_hits: int = 2) -> str:
    directness = int(item.get("directness_score") or 0)
    entity_hits = int(item.get("entity_match_count") or 0)
    relevance = int(item.get("relevance_score") or 0)
    source_type = str(item.get("source_type") or "")
    contract_status = normalize_text(str(item.get("evidence_contract_status") or "")).lower()
    contract_role = normalize_text(str(item.get("evidence_contract_role") or "")).lower()
    if source_type == "official" and directness >= 4 and relevance >= 6:
        return "direct"
    if directness >= 2 and entity_hits >= required_hits:
        if contract_status == "failed" and directness < 4 and contract_role not in {"structured_metric_table_page", "evidence_sentence_page"}:
            return "partial" if entity_hits >= 1 else "related_only"
        return "direct"
    if directness >= 1 and entity_hits >= 1 and source_type in {"official", "news", "encyclopedia"}:
        if contract_status == "failed" and contract_role not in {"structured_metric_table_page", "evidence_sentence_page"}:
            return "related_only"
        return "partial"
    if relevance >= 6 and entity_hits >= required_hits:
        if contract_status == "failed" and contract_role not in {"structured_metric_table_page", "evidence_sentence_page"}:
            return "related_only"
        return "partial"
    return "related_only"


def point_with_source(item: Dict[str, Any], point: Dict[str, Any], required_hits: int = 2) -> Dict[str, Any]:
    out = dict(point)
    out.update(point_source(item))
    out["direct_answer"] = direct_answer_level(item, required_hits=required_hits)
    point_contract = item.get("structured_table_best_point", {}).get("point_contract") if isinstance(item.get("structured_table_best_point"), dict) else {}
    if not isinstance(point_contract, dict):
        point_contract = {}
    out["point_contract_status"] = point_contract.get("status") or item.get("structured_point_contract_status")
    out["point_contract_risks"] = list(point_contract.get("risks", []) or item.get("structured_point_contract_risks", []) or [])
    return out


def structured_best_point(item: Dict[str, Any]) -> Dict[str, Any]:
    best_point = item.get("structured_table_best_point") if isinstance(item.get("structured_table_best_point"), dict) else {}
    return best_point if isinstance(best_point, dict) else {}


def structured_best_point_contract(item: Dict[str, Any]) -> Dict[str, Any]:
    best_point = structured_best_point(item)
    contract = best_point.get("point_contract") if isinstance(best_point.get("point_contract"), dict) else {}
    if isinstance(contract, dict) and contract:
        return contract
    return {
        "status": item.get("structured_point_contract_status"),
        "score": item.get("structured_point_contract_score"),
        "signals": item.get("structured_point_contract_signals", []),
        "risks": item.get("structured_point_contract_risks", []),
        "value": "",
    }


def structured_best_point_evidence(item: Dict[str, Any]) -> Tuple[str, str, str]:
    best_point = structured_best_point(item)
    contract = structured_best_point_contract(item)
    value = normalize_text(str(contract.get("value") or ""))
    publish_time = normalize_text(str(best_point.get("publish_time") or ""))
    currency = normalize_text(str(best_point.get("currency") or ""))
    fields = best_point.get("fields") if isinstance(best_point.get("fields"), dict) else {}
    if not value and fields:
        numeric_values = [
            normalize_text(str(field_value))
            for field_name, field_value in fields.items()
            if normalize_text(str(field_value)) and field_name not in {"publish_time", "currency"}
        ]
        value = numeric_values[0] if numeric_values else ""
    sentence_parts = [part for part in [publish_time, currency, value] if part]
    sentence = " ".join(sentence_parts)
    return value, sentence, publish_time


def required_hits_for_mode(mode: str) -> int:
    if mode in {EVIDENCE_MODE_NUMERIC, EVIDENCE_MODE_DATE, EVIDENCE_MODE_SCHEDULE}:
        return 1
    return 2


def item_structured_point_blocking_risks(item: Dict[str, Any]) -> List[str]:
    risks = item.get("structured_point_contract_risks") if isinstance(item.get("structured_point_contract_risks"), list) else []
    blocking: List[str] = []
    for risk in risks:
        normalized = normalize_text(str(risk))
        if normalized in STRUCTURED_POINT_DIRECT_BLOCKING_RISKS and normalized not in blocking:
            blocking.append(normalized)
    return blocking


def item_blocks_structured_direct_verdict(item: Dict[str, Any]) -> bool:
    return bool(item_structured_point_blocking_risks(item))


def claim_is_announcement_date_claim(claim: str) -> bool:
    text = normalize_text(claim).lower()
    return any(marker in text for marker in ANNOUNCEMENT_CLAIM_MARKERS)


def sentence_is_non_announcement_event(sentence: str, item: Dict[str, Any]) -> bool:
    combined = normalize_text(
        " ".join(
            [
                sentence or "",
                str(item.get("title") or ""),
                str(item.get("url") or ""),
            ]
        )
    ).lower()
    has_announcement_marker = any(marker in combined for marker in ANNOUNCEMENT_CLAIM_MARKERS)
    has_non_announcement_event = any(marker in combined for marker in NON_ANNOUNCEMENT_EVENT_MARKERS)
    return has_non_announcement_event and not has_announcement_marker


# Keep these markers ASCII-safe via unicode escapes so state-slot extraction
# stays stable even if the editor or terminal display encoding is noisy.
MARKET_CALENDAR_CLAIM_MARKERS = [
    "\u4f11\u5e02", "\u505c\u5e02", "\u8282\u5047\u65e5", "\u5047\u671f", "\u4ea4\u6613\u65e5",
    "\u5f00\u76d8", "\u958b\u76e4", "\u6536\u76d8", "\u9ad8\u5f00", "\u9ad8\u958b", "\u4f4e\u5f00", "\u4f4e\u958b",
    "\u4ea4\u6613\u516c\u5f00\u4fe1\u606f", "\u4ea4\u6613\u516c\u958b\u4fe1\u606f",
    "market holiday", "market closed", "trading day", "opened", "open", "closed",
]


def is_market_calendar_state_claim(text: str) -> bool:
    normalized = normalize_text(text).lower()
    return bool(normalized) and any(marker in normalized for marker in MARKET_CALENDAR_CLAIM_MARKERS)


def market_calendar_state_slot(text: str) -> str:
    normalized = normalize_text(text).lower()
    if not normalized:
        return ""
    closed_markers = [
        "\u4f11\u5e02", "\u505c\u5e02", "market holiday", "market closed", "closed for holiday", "holiday closure",
    ]
    open_markers = [
        "\u9ad8\u5f00", "\u9ad8\u958b", "\u4f4e\u5f00", "\u4f4e\u958b", "\u5f00\u76d8", "\u958b\u76e4",
        "\u4ea4\u6613\u516c\u5f00\u4fe1\u606f", "\u4ea4\u6613\u516c\u958b\u4fe1\u606f",
        "\u4ea4\u6613\u63d0\u793a", "\u6b63\u5e38\u4ea4\u6613", "trading information", "trading day", "opened", "open for trading",
    ]
    has_closed = any(marker in normalized for marker in closed_markers)
    has_open = any(marker in normalized for marker in open_markers)
    if has_closed and not has_open:
        return "closed"
    if has_open and not has_closed:
        return "open"
    clauses = [
        normalize_text(part).lower()
        for part in re.split(r"[，,。；;！？!?]", normalized)
        if normalize_text(part)
    ]
    for clause in clauses:
        clause_has_closed = any(marker in clause for marker in closed_markers)
        clause_has_open = any(marker in clause for marker in open_markers)
        if clause_has_closed and not clause_has_open:
            return "closed"
        if clause_has_open and not clause_has_closed:
            return "open"
    return ""


def extract_year_values(text: str) -> List[str]:
    return list(dict.fromkeys(re.findall(r"(?:19|20)\d{2}", normalize_text(text))))


def local_year_contexts(text: str, anchor: str = "") -> List[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    contexts: List[str] = []
    anchor = normalize_text(anchor)
    if anchor:
        idx = normalized.find(anchor)
        if idx >= 0:
            start = max(0, idx - 120)
            end = min(len(normalized), idx + len(anchor) + 120)
            contexts.append(normalized[start:end])
    segments = [
        segment.strip()
        for segment in re.split(r"(?<=[\.\?!;。！？；])\s+|\n+", normalized)
        if segment and segment.strip()
    ]
    if anchor:
        contexts.extend(segment for segment in segments if anchor in segment)
    if not contexts:
        contexts.extend(segments[:3] or [normalized])
    return list(dict.fromkeys(contexts))


def numeric_point_has_year_mismatch(claim: str, sentence: str, item: Dict[str, Any], evidence_value: str = "") -> bool:
    claim_years = extract_year_values(claim)
    if not claim_years:
        return False
    local_contexts = local_year_contexts(sentence or "", evidence_value)
    local_year_sets = [extract_year_values(context) for context in local_contexts if extract_year_values(context)]
    if local_year_sets:
        if any(any(year in year_set for year in claim_years) for year_set in local_year_sets):
            return False
        return True
    title_url_text = normalize_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("url") or ""),
            ]
        )
    )
    title_url_years = extract_year_values(title_url_text)
    if not title_url_years:
        return False
    return not any(year in title_url_years for year in claim_years)


def numeric_point_lacks_time_scope_binding(
    claim: str,
    sentence: str,
    item: Dict[str, Any],
    evidence_value: str = "",
) -> bool:
    claim_years = extract_year_values(claim)
    if not claim_years:
        return False
    if numeric_point_has_year_mismatch(claim, sentence, item, evidence_value):
        return True
    combined_risks = [
        normalize_text(str(risk))
        for risk in (
            list(item.get("evidence_contract_risks") or [])
            + list(item.get("structured_point_contract_risks") or [])
        )
        if normalize_text(str(risk))
    ]
    if not any(
        risk in {"missing_binding_time_scope", "missing_time_scope", "point_time_scope_mismatch", "date_window_mismatch"}
        for risk in combined_risks
    ):
        return False
    title_url_text = normalize_text(
        " ".join(
            [
                sentence or "",
                evidence_value or "",
                str(item.get("title") or ""),
                str(item.get("url") or ""),
            ]
        )
    )
    visible_years = extract_year_values(title_url_text)
    if visible_years and any(year in visible_years for year in claim_years):
        return False
    return True


def mechanism_type_from_intent(source_intent: Dict[str, Any]) -> str:
    if not isinstance(source_intent, dict):
        return "general_web_evidence"
    mechanism_type = normalize_text(str(source_intent.get("mechanism_type") or ""))
    if mechanism_type in VERIFICATION_MECHANISM_TYPES:
        return mechanism_type
    metric_slots = source_intent.get("metric_slots") if isinstance(source_intent.get("metric_slots"), dict) else {}
    value_type = normalize_text(str(metric_slots.get("value_type") or ""))
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    shape = str(source_intent.get("evidence_shape") or "")
    if value_type and value_type != "not_metric":
        return "structured_numeric_authority"
    if mode in {"date_fact", "schedule_fact"}:
        return "date_authority"
    if mode == "event_result" or target in {"match_result", "withdrawal_status"}:
        return "event_result_page"
    if mode == "route_fact" or target == "route_relation":
        return "relation_sentence"
    if target == "current_status" or shape == "current_status_update":
        return "current_status_update"
    if mode == "numeric_fact":
        return "structured_numeric_authority"
    return "general_web_evidence"


def summary_mode_from_intent(source_intent: Dict[str, Any]) -> str:
    mechanism_type = mechanism_type_from_intent(source_intent)
    mode = str(source_intent.get("evidence_mode") or "entity_fact")
    if mechanism_type == "relation_sentence":
        return EVIDENCE_MODE_ROUTE
    if mechanism_type == "structured_numeric_authority":
        return EVIDENCE_MODE_NUMERIC
    if mechanism_type == "date_authority":
        return EVIDENCE_MODE_DATE
    if mechanism_type == "event_result_page":
        return "event_result"
    if mechanism_type == "current_status_update":
        return "entity_fact"
    return mode or "entity_fact"


def coverage_mode(mode: str, summary: Dict[str, Any]) -> str:
    normalized = str(mode or "")
    mechanism_type = normalize_text(str(summary.get("mechanism_type") or ""))
    if mechanism_type == "relation_sentence":
        return EVIDENCE_MODE_ROUTE
    if mechanism_type == "structured_numeric_authority":
        return EVIDENCE_MODE_NUMERIC
    if mechanism_type == "date_authority":
        return EVIDENCE_MODE_DATE
    if mechanism_type == "event_result_page":
        return "event_result"
    if mechanism_type == "current_status_update":
        return "entity_fact"
    return normalized or "entity_fact"


def claim_entities(claim: str) -> List[str]:
    entities = re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z.]+)+|[\u4e00-\u9fff]{2,}", claim)
    cleaned = []
    for entity in entities:
        entity = normalize_text(entity)
        if not entity:
            continue
        if entity in {"官方", "", "回答", "用户"}:
            continue
        cleaned.append(entity)
    return list(dict.fromkeys(cleaned))[:8]


def entity_matches_text(entity: str, text_lower: str) -> bool:
    entity_lower = entity.lower()
    if entity_lower in text_lower:
        return True
    latin_parts = re.findall(r"[a-z]+", entity_lower)
    if len(latin_parts) >= 2 and latin_parts[0] in text_lower and latin_parts[-1] in text_lower:
        return True
    return False




def pick_claim_number(values: List[Tuple[str, str]]) -> Tuple[str, str]:
    for raw, unit in values:
        if unit != "year":
            return raw, unit
    return values[0] if values else ("", "")


def numeric_equal(left: str, right: str) -> bool:
    left_value = numeric_value(left)
    right_value = numeric_value(right)
    if left_value is None or right_value is None:
        return left.lower() == right.lower()
    return abs(left_value - right_value) <= max(1e-6, abs(left_value) * 0.001)


def claim_has_approx_marker(claim: str) -> bool:
    return bool(re.search(r"(约|大约|约为|左右|接近|around|about|approximately|roughly)", claim or "", flags=re.I))


def numeric_match_for_claim(claim: str, left: str, right: str) -> bool:
    if numeric_equal(left, right):
        return True
    left_value = numeric_value(left)
    right_value = numeric_value(right)
    if left_value is None or right_value is None:
        return False
    if not claim_has_approx_marker(claim):
        return False
    tolerance = max(0.2, min(5.0, abs(right_value) * 0.15))
    return abs(left_value - right_value) <= tolerance




def sentence_for_value(text: str, value: str) -> str:
    for sentence in split_sentences(text):
        if value and value.lower() in sentence.lower():
            return sentence
    return text[:300]


def choose_numeric_value(text: str, values: List[Tuple[str, str]], claim: str) -> str:
    if not values:
        return ""
    return max(values, key=lambda pair: numeric_sentence_score(sentence_for_value(text, pair[0]), claim))[0]


def qa_text_tokens(text: str) -> List[str]:
    stop = {
        "??", "?", "??", "??", "??", "??", "??", "??", "??", "??",
        "??", "???",
        "what", "when", "where", "which", "result", "score", "official", "match", "game",
    }
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}|\d+(?:-\d+)?", text or "")
    out = []
    for token in tokens:
        token = token.strip()
        if not token or token.lower() in stop:
            continue
        out.append(token)
    return list(dict.fromkeys(out))[:10]


def sentence_overlap_score(sentence: str, claim: str) -> int:
    lower = sentence.lower()
    score = 0
    for token in qa_text_tokens(claim):
        if token.lower() in lower:
            score += 2 if len(token) >= 3 else 1
    if re.search(r"\d+\s*[-:：比]\s*\d+|\b\d+-\d+\b", sentence):
        score += 3
    if any(marker in lower or marker in sentence for marker in ["retired", "withdraw", "walkover", "bye", "??", "????", "w/o"]):
        score += 4
    if any(marker in lower or marker in sentence for marker in ["defeated", "beat", "lost", "won", "?", "?", "??", "??"]):
        score += 2
    return score


def answer_candidates_from_item(item: Dict[str, Any], claim: str, limit: int = 3) -> List[Dict[str, Any]]:
    existing = item.get("answer_candidates") if isinstance(item.get("answer_candidates"), list) else []
    if existing:
        out = []
        for candidate in existing[:limit]:
            if not isinstance(candidate, dict):
                continue
            enriched = dict(candidate)
            enriched.setdefault("source_type", item.get("source_type"))
            enriched.setdefault("url", item.get("url"))
            enriched.setdefault("title", item.get("title"))
            out.append(enriched)
        if out:
            return out
    text = evidence_text(item)
    candidates: List[Dict[str, Any]] = []
    for sentence in split_sentences(text):
        score = sentence_overlap_score(sentence, claim)
        if score <= 0:
            continue
        candidates.append(
            {
                "sentence": sentence[:260],
                "score": score,
                "source_type": item.get("source_type"),
                "url": item.get("url"),
                "title": item.get("title"),
            }
        )
    candidates.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
    return candidates[:limit]


def best_answer_candidate(item: Dict[str, Any], claim: str) -> Dict[str, Any]:
    candidates = answer_candidates_from_item(item, claim, limit=1)
    if candidates:
        return candidates[0]
    return {}


def sentence_directness_rank(level: str) -> int:
    value = normalize_text(level)
    if value == SENTENCE_DIRECTNESS_DIRECT:
        return 3
    if value == SENTENCE_DIRECTNESS_PARTIAL:
        return 2
    if value == SENTENCE_DIRECTNESS_RELATED_ONLY:
        return 1
    return 0


def point_direct_answer_rank(level: str) -> int:
    value = normalize_text(level)
    if value == "direct":
        return 3
    if value == "partial":
        return 2
    if value == "related_only":
        return 1
    return 0


def direct_answer_from_sentence_directness(level: str) -> str:
    value = normalize_text(level)
    if value == SENTENCE_DIRECTNESS_DIRECT:
        return "direct"
    if value == SENTENCE_DIRECTNESS_PARTIAL:
        return "partial"
    return "related_only"


def enrich_candidate_for_mode(item: Dict[str, Any], candidate: Dict[str, Any], claim: str, mode: str) -> Dict[str, Any]:
    enriched = dict(candidate)
    enriched.setdefault("source_type", item.get("source_type"))
    enriched.setdefault("url", item.get("url"))
    enriched.setdefault("title", item.get("title"))
    enriched.update(sentence_candidate_features(item, enriched, claim, mode))
    return enriched


def best_mode_answer_candidate(item: Dict[str, Any], claim: str, mode: str, limit: int = 5) -> Dict[str, Any]:
    candidates = answer_candidates_from_item(item, claim, limit=limit)
    enriched_candidates: List[Dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        enriched = enrich_candidate_for_mode(item, candidate, claim, mode)
        if mode == EVIDENCE_MODE_NUMERIC and not enriched.get("numeric_hits"):
            continue
        if mode in {EVIDENCE_MODE_DATE, EVIDENCE_MODE_SCHEDULE} and not enriched.get("date_hits"):
            continue
        enriched_candidates.append(enriched)
    if not enriched_candidates:
        return {}
    enriched_candidates.sort(
        key=lambda candidate: (
            sentence_directness_rank(str(candidate.get("sentence_directness") or "")),
            int(candidate.get("sentence_score_total") or 0),
            int(candidate.get("sentence_utility_score") or 0),
            int(candidate.get("score") or 0),
            str(candidate.get("field") or "") == "detail",
            str(candidate.get("field") or "") != "title",
        ),
        reverse=True,
    )
    return enriched_candidates[0]


def apply_candidate_features_to_point(point: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(point)
    if not isinstance(candidate, dict):
        return out
    sentence_directness = normalize_text(str(candidate.get("sentence_directness") or ""))
    if sentence_directness:
        out["sentence_directness"] = sentence_directness
        candidate_direct_answer = direct_answer_from_sentence_directness(sentence_directness)
        if point_direct_answer_rank(candidate_direct_answer) > point_direct_answer_rank(str(out.get("direct_answer") or "")):
            out["direct_answer"] = candidate_direct_answer
    for key in (
        "sentence_score_total",
        "sentence_utility_score",
        "sentence_utility_label",
        "sentence_score_components",
        "sentence_utility_components",
        "claim_token_hits",
        "numeric_hits",
        "date_hits",
        "sentence_candidate_profile",
        "candidate_slot_match",
        "direct_candidate_gap_reason",
    ):
        if key in candidate:
            out[key] = candidate.get(key)
    return out


def sentence_candidate_features(item: Dict[str, Any], candidate: Dict[str, Any], claim: str, mode: str) -> Dict[str, Any]:
    sentence = normalize_text(str(candidate.get("sentence") or ""))
    sentence_lower = sentence.lower()
    claim_lower = normalize_text(claim).lower()
    claim_tokens = qa_text_tokens(claim)
    numeric_hits = [value for value, _unit in extract_numbers(sentence)]
    date_hits = extract_dates(sentence)
    route_analysis = (
        merge_route_analysis(
            route_relation_analysis(claim, sentence),
            candidate.get("route_relation") if isinstance(candidate.get("route_relation"), dict) else {},
        )
        if mode == EVIDENCE_MODE_ROUTE else {}
    )
    if mode == EVIDENCE_MODE_ROUTE:
        token_hits = [
            str(token)
            for token in (route_analysis.get("token_hits") or [])
            if normalize_text(str(token))
        ]
        entity_hit_count = max(len(token_hits), int(route_analysis.get("token_hit_count") or 0))
    else:
        token_hits = [token for token in claim_tokens if token.lower() in sentence_lower]
        entity_hit_count = len(token_hits)
    overlap_score = sentence_overlap_score(sentence, claim)
    numeric_score = numeric_sentence_score(sentence, claim) if mode == EVIDENCE_MODE_NUMERIC else 0
    claim_dates = extract_dates(claim) if mode in {EVIDENCE_MODE_DATE, EVIDENCE_MODE_SCHEDULE} else []
    relation_evidence = 0
    answerability = 0
    specificity = 0
    structural_extractability = 3 if 12 <= len(sentence) <= 160 else 2 if 8 <= len(sentence) <= 220 else 0
    noise_penalty = 0
    utility_label = "noise"
    directness = SENTENCE_DIRECTNESS_RELATED_ONLY
    narrowing_bonus = 0
    narrowing_reasons: List[str] = []
    if mode == EVIDENCE_MODE_ROUTE:
        if route_analysis.get("directly_answers_route"):
            relation_evidence = 3
            answerability = 3
            specificity = 3
            directness = SENTENCE_DIRECTNESS_DIRECT
        elif route_analysis.get("has_relation_marker") and route_analysis.get("token_hit_count", 0) >= 2:
            relation_evidence = 2
            answerability = 2 if (route_analysis.get("has_route_object_marker") or not route_analysis.get("claim_requires_route_object")) else 1
            specificity = 2
            directness = SENTENCE_DIRECTNESS_PARTIAL
        elif route_analysis.get("has_relation_marker") and route_analysis.get("token_hit_count", 0) >= 1:
            relation_evidence = 1
            answerability = 1
            specificity = 1
            directness = SENTENCE_DIRECTNESS_PARTIAL
        elif route_analysis.get("token_hit_count", 0) >= 1:
            specificity = 1
        if str(candidate.get("field") or "") == "title" and directness != SENTENCE_DIRECTNESS_DIRECT:
            noise_penalty += 1
        if len(sentence) > 180:
            noise_penalty += 2
        if re.search(r"(发布于|官方账号|you are using an outdated browser|_腾新闻|login|sign in)", sentence, flags=re.I):
            noise_penalty += 2
        if answerability >= 3:
            utility_label = "answerable"
        elif answerability >= 2:
            utility_label = "borderline"
        elif relation_evidence >= 1 or entity_hit_count >= 1:
            utility_label = "background"
    elif mode == EVIDENCE_MODE_NUMERIC:
        if numeric_score >= 5 and numeric_hits:
            relation_evidence = 3
            answerability = 3
            specificity = 3
            directness = SENTENCE_DIRECTNESS_DIRECT
        elif numeric_score >= 2 and numeric_hits:
            relation_evidence = 2
            answerability = 2
            specificity = 2
            directness = SENTENCE_DIRECTNESS_PARTIAL
        elif numeric_hits:
            relation_evidence = 1
            answerability = 1
            specificity = 1
        claim_needs_open = bool(re.search(r"(开盘|开市|opening|opened)", claim, flags=re.I))
        sentence_has_open = bool(re.search(r"(开盘|开市|高开|opening|opened)", sentence, flags=re.I))
        sentence_has_intraday = bool(re.search(r"(盘中|一度|曾|瞬时|最高|新高|intraday|at one point|session high|hit as high as)", sentence, flags=re.I))
        sentence_has_close = bool(re.search(r"(收盘|尾盘|close|closed)", sentence, flags=re.I))
        sentence_has_commentary = bool(re.search(r"(代表|意味着|反映|说明|主要因为|reflects|means|suggests|because)", sentence, flags=re.I))
        sentence_has_market_quote = bool(re.search(r"(中间价|汇率|牌价|报价|rate|price|basis point|基点)", sentence, flags=re.I))
        if claim_needs_open and sentence_has_open:
            narrowing_bonus += 8
            narrowing_reasons.append("opening_fact_slot_hit")
        if claim_needs_open and sentence_has_intraday and not sentence_has_open:
            narrowing_bonus -= 8
            narrowing_reasons.append("intraday_not_opening_slot")
            if directness == SENTENCE_DIRECTNESS_DIRECT:
                directness = SENTENCE_DIRECTNESS_PARTIAL
        if claim_needs_open and sentence_has_close and not sentence_has_open:
            narrowing_bonus -= 6
            narrowing_reasons.append("closing_not_opening_slot")
            if directness == SENTENCE_DIRECTNESS_DIRECT:
                directness = SENTENCE_DIRECTNESS_PARTIAL
        if sentence_has_commentary:
            narrowing_bonus -= 5
            narrowing_reasons.append("commentary_not_direct_quote")
            if directness == SENTENCE_DIRECTNESS_DIRECT and not numeric_hits:
                directness = SENTENCE_DIRECTNESS_PARTIAL
        if sentence_has_market_quote:
            narrowing_bonus += 2
            narrowing_reasons.append("market_quote_marker")
        utility_label = "answerable" if answerability >= 3 else "borderline" if answerability >= 2 else "background" if relation_evidence >= 1 else "noise"
    elif mode in {EVIDENCE_MODE_DATE, EVIDENCE_MODE_SCHEDULE}:
        if claim_dates and any(normalize_date_value(hit) == normalize_date_value(claim_dates[0]) for hit in date_hits):
            relation_evidence = 3
            answerability = 3
            specificity = 3
            directness = SENTENCE_DIRECTNESS_DIRECT
        elif date_hits:
            relation_evidence = 2
            answerability = 2
            specificity = 2
            directness = SENTENCE_DIRECTNESS_PARTIAL
        utility_label = "answerable" if answerability >= 3 else "borderline" if answerability >= 2 else "background" if relation_evidence >= 1 else "noise"
    else:
        if overlap_score >= 6 and entity_hit_count >= 2:
            relation_evidence = 3
            answerability = 3
            specificity = 3
            directness = SENTENCE_DIRECTNESS_DIRECT
        elif overlap_score >= 3 and entity_hit_count >= 1:
            relation_evidence = 2
            answerability = 2
            specificity = 2
            directness = SENTENCE_DIRECTNESS_PARTIAL
        elif entity_hit_count >= 1:
            relation_evidence = 1
            answerability = 1
            specificity = 1
        utility_label = "answerable" if answerability >= 3 else "borderline" if answerability >= 2 else "background" if relation_evidence >= 1 else "noise"
    if mode == "event_result":
        sentence_has_result_marker = bool(re.search(r"(战胜|击败|获胜|赢|比分|result|won|beat|defeated|score|winner)", sentence, flags=re.I))
        sentence_has_commentary = bool(re.search(r"(复盘|影响|说明|意味着|reflects|means|suggests|because)", sentence, flags=re.I))
        if sentence_has_result_marker:
            narrowing_bonus += 4
            narrowing_reasons.append("result_marker")
        if sentence_has_commentary and not sentence_has_result_marker:
            narrowing_bonus -= 4
            narrowing_reasons.append("commentary_not_result")
            if directness == SENTENCE_DIRECTNESS_DIRECT:
                directness = SENTENCE_DIRECTNESS_PARTIAL
    if len(sentence) > 220:
        noise_penalty += 1
    utility_bonus = (
        answerability * 5
        + relation_evidence * 4
        + specificity * 3
        + structural_extractability * 2
        - noise_penalty * 4
        + narrowing_bonus
    )
    source_type = str(item.get("source_type") or "")
    source_bonus = {"official": 3, "news": 2, "encyclopedia": 1}.get(source_type, 0)
    direct_bonus = {
        SENTENCE_DIRECTNESS_DIRECT: 6,
        SENTENCE_DIRECTNESS_PARTIAL: 3,
        SENTENCE_DIRECTNESS_RELATED_ONLY: 0,
    }.get(directness, 0)
    total_score = (
        int(candidate.get("score") or 0)
        + min(6, entity_hit_count * 2)
        + min(4, len(numeric_hits) * 2)
        + min(4, len(date_hits) * 2)
        + source_bonus
        + direct_bonus
        + utility_bonus
    )
    status_or_result_hit = bool(
        route_analysis.get("has_relation_marker") if isinstance(route_analysis, dict) else False
    ) or bool(
        re.search(
            r"(休市|开盘|停牌|生效|发布|公布|取消|暂停|战胜|击败|赢|获胜|晋级|比分|结果|result|won|beat|score|effective|announced|released|open|closed)",
            sentence,
            flags=re.I,
        )
    )
    slot_match = infer_sentence_candidate_slot_match(
        claim,
        sentence,
        mode,
        entity_hit_count=entity_hit_count,
        numeric_hits=numeric_hits,
        date_hits=date_hits,
        route_analysis=route_analysis,
        status_or_result_hit=status_or_result_hit,
    )
    gap_reason = infer_sentence_candidate_gap_reason(
        claim,
        sentence,
        mode,
        slot_match=slot_match,
        directness=directness,
        utility_label=utility_label,
        numeric_hits=numeric_hits,
        date_hits=date_hits,
        route_analysis=route_analysis,
    )
    profile = infer_sentence_candidate_profile(
        mode,
        slot_match=slot_match,
        gap_reason=gap_reason,
        directness=directness,
        utility_label=utility_label,
        numeric_hits=numeric_hits,
        date_hits=date_hits,
        route_analysis=route_analysis,
    )
    return {
        "sentence_directness": directness,
        "sentence_score_total": total_score,
        "sentence_utility_score": utility_bonus,
        "sentence_utility_label": utility_label,
        "sentence_score_components": {
            "base": int(candidate.get("score") or 0),
            "entity_hits": entity_hit_count,
            "numeric_hits": len(numeric_hits),
            "date_hits": len(date_hits),
            "source_bonus": source_bonus,
            "direct_bonus": direct_bonus,
            "route_relation": route_analysis.get("token_hit_count", 0) if route_analysis else 0,
            "numeric_score": numeric_score,
            "overlap_score": overlap_score,
            "utility_bonus": utility_bonus,
            "narrowing_bonus": narrowing_bonus,
        },
        "sentence_utility_components": {
            "answerability": answerability,
            "relation_evidence": relation_evidence,
            "entity_grounding": min(3, entity_hit_count),
            "structural_extractability": structural_extractability,
            "specificity": specificity,
            "noise_penalty": noise_penalty,
            "narrowing_bonus": narrowing_bonus,
        },
        "claim_token_hits": token_hits[:8],
        "numeric_hits": numeric_hits[:6],
        "date_hits": date_hits[:6],
        "route_relation": route_analysis,
        "conversion_narrowing_reasons": narrowing_reasons[:6],
        "sentence_candidate_profile": profile,
        "candidate_slot_match": slot_match,
        "direct_candidate_gap_reason": gap_reason,
    }


def infer_sentence_candidate_slot_match(
    claim: str,
    sentence: str,
    mode: str,
    *,
    entity_hit_count: int,
    numeric_hits: List[Any],
    date_hits: List[Any],
    route_analysis: Optional[Dict[str, Any]] = None,
    status_or_result_hit: bool = False,
) -> str:
    has_subject = entity_hit_count >= 1
    has_time = bool(date_hits)
    has_metric = bool(numeric_hits)
    has_route = bool((route_analysis or {}).get("has_relation_marker"))
    has_status = bool(status_or_result_hit)
    if mode == EVIDENCE_MODE_ROUTE or has_route:
        if has_subject and has_route:
            return "subject+metric_or_result"
        if has_route:
            return "metric_or_result_only"
    if has_subject and has_time and (has_metric or has_status):
        return "subject+time+metric_or_result"
    if has_subject and (has_metric or has_status):
        return "subject+metric_or_result"
    if has_time and (has_metric or has_status):
        return "time+metric_or_result"
    if has_subject and has_time:
        return "subject+time"
    if has_metric or has_status:
        return "metric_or_result_only"
    if has_time:
        return "time_scope_only"
    return "weak_anchor"


def infer_sentence_candidate_gap_reason(
    claim: str,
    sentence: str,
    mode: str,
    *,
    slot_match: str,
    directness: str,
    utility_label: str,
    numeric_hits: List[Any],
    date_hits: List[Any],
    route_analysis: Optional[Dict[str, Any]] = None,
) -> str:
    claim_needs_open = bool(re.search(r"(开盘|开市|opening|opened)", claim, flags=re.I))
    sentence_has_open = bool(re.search(r"(开盘|开市|高开|opening|opened|open price|open gain)", sentence, flags=re.I))
    sentence_has_intraday = bool(re.search(r"(盘中|一度|曾|瞬时|最高|新高|intraday|at one point|session high|hit as high as)", sentence, flags=re.I))
    sentence_has_close = bool(re.search(r"(收盘|尾盘|close|closed)", sentence, flags=re.I))
    sentence_has_commentary = bool(re.search(r"(代表|意味着|反映|说明|主要因为|reflects|means|suggests|because)", sentence, flags=re.I))
    if claim_needs_open and (sentence_has_intraday or sentence_has_close) and not sentence_has_open:
        return "opening_slot_mismatch"
    if mode in {EVIDENCE_MODE_DATE, EVIDENCE_MODE_SCHEDULE}:
        claim_publish = bool(re.search(r"(发布|公布|宣布|announced|released)", claim, flags=re.I))
        claim_effective = bool(re.search(r"(生效|实施|effective|in force)", claim, flags=re.I))
        sentence_publish = bool(re.search(r"(发布|公布|宣布|announced|released)", sentence, flags=re.I))
        sentence_effective = bool(re.search(r"(生效|实施|effective|in force)", sentence, flags=re.I))
        if (claim_publish and sentence_effective and not sentence_publish) or (claim_effective and sentence_publish and not sentence_effective):
            return "date_role_mismatch"
    if mode == "event_result":
        claim_needs_final = bool(re.search(r"(比分|赛果|结果|获胜|winner|won|beat|result|score)", claim, flags=re.I))
        sentence_partial = bool(re.search(r"(首节|次节|半场|加时|单盘|盘点|quarter|period|half|set|inning)", sentence, flags=re.I))
        if claim_needs_final and sentence_partial:
            return "result_granularity_mismatch"
    if sentence_has_commentary and utility_label in {"background", "noise"}:
        return "commentary_only"
    if mode == EVIDENCE_MODE_NUMERIC and slot_match in {"metric_or_result_only", "weak_anchor"} and numeric_hits:
        return "numeric_reference_only"
    if mode in {EVIDENCE_MODE_DATE, EVIDENCE_MODE_SCHEDULE} and slot_match == "time_scope_only" and date_hits:
        return "date_reference_only"
    if mode == EVIDENCE_MODE_ROUTE and route_analysis and not route_analysis.get("directly_answers_route") and route_analysis.get("has_relation_marker"):
        return "route_relation_indirect"
    if directness == SENTENCE_DIRECTNESS_RELATED_ONLY and slot_match == "weak_anchor":
        return "weak_anchor_only"
    if sentence_has_commentary:
        return "commentary_only"
    return ""


def infer_sentence_candidate_profile(
    mode: str,
    *,
    slot_match: str,
    gap_reason: str,
    directness: str,
    utility_label: str,
    numeric_hits: List[Any],
    date_hits: List[Any],
    route_analysis: Optional[Dict[str, Any]] = None,
) -> str:
    if gap_reason == "commentary_only":
        return "background_commentary"
    if mode == EVIDENCE_MODE_NUMERIC and gap_reason == "numeric_reference_only":
        return "numeric_reference_only"
    if mode in {EVIDENCE_MODE_DATE, EVIDENCE_MODE_SCHEDULE} and gap_reason == "date_reference_only":
        return "date_reference_only"
    if directness == SENTENCE_DIRECTNESS_DIRECT and slot_match == "subject+time+metric_or_result" and not gap_reason:
        return "direct_candidate"
    if directness == SENTENCE_DIRECTNESS_DIRECT and slot_match in {"subject+metric_or_result", "time+metric_or_result"} and not gap_reason:
        return "direct_candidate"
    if slot_match in {"subject+time+metric_or_result", "subject+metric_or_result", "time+metric_or_result", "subject+time"}:
        return "slot_hit_but_indirect"
    if mode == EVIDENCE_MODE_NUMERIC and numeric_hits:
        return "numeric_reference_only"
    if mode in {EVIDENCE_MODE_DATE, EVIDENCE_MODE_SCHEDULE} and date_hits:
        return "date_reference_only"
    if mode == EVIDENCE_MODE_ROUTE and route_analysis and route_analysis.get("has_relation_marker"):
        return "slot_hit_but_indirect"
    if utility_label in {"background", "noise"}:
        return "background_commentary"
    return "slot_hit_but_indirect"


def merge_route_analysis(
    base_analysis: Dict[str, Any],
    retrieval_hint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged = dict(base_analysis or {})
    hint = retrieval_hint if isinstance(retrieval_hint, dict) else {}
    if not hint:
        return merged
    merged_hits = dedupe_keep_order(
        [str(token) for token in (merged.get("token_hits") or [])]
        + [str(token) for token in (hint.get("entity_hits") or hint.get("token_hits") or [])]
    )
    merged["token_hits"] = merged_hits
    merged["token_hit_count"] = max(
        len(merged_hits),
        int(merged.get("token_hit_count") or 0),
        int(hint.get("entity_hit_count") or hint.get("token_hit_count") or 0),
    )
    merged["has_relation_marker"] = bool(merged.get("has_relation_marker") or hint.get("has_relation_marker"))
    merged["has_directional_relation_marker"] = bool(
        merged.get("has_directional_relation_marker")
        or hint.get("has_directional_relation")
        or hint.get("has_directional_relation_marker")
    )
    merged["has_route_object_marker"] = bool(
        merged.get("has_route_object_marker")
        or hint.get("has_route_object_marker")
    )
    merged["claim_requires_route_object"] = bool(
        merged.get("claim_requires_route_object")
        or hint.get("claim_requires_route_object")
        or hint.get("query_requires_route_object")
    )
    merged["has_extra_route_anchor"] = bool(
        merged.get("has_extra_route_anchor") or hint.get("has_extra_route_anchor")
    )
    merged["directly_answers_route"] = bool(
        merged.get("directly_answers_route") or hint.get("direct_sentence")
    )
    return merged


def utility_signal_profile_matches(
    signals: Dict[str, Any],
    require_all: Optional[List[str]] = None,
    require_any: Optional[List[str]] = None,
    require_false: Optional[List[str]] = None,
) -> bool:
    require_all = require_all or []
    require_any = require_any or []
    require_false = require_false or []
    for field in require_all:
        if not signals.get(field):
            return False
    if require_any and not any(bool(signals.get(field)) for field in require_any):
        return False
    for field in require_false:
        if signals.get(field):
            return False
    return True


def route_sentence_meets_minimum_utility(route_relation: Dict[str, Any]) -> bool:
    if not isinstance(route_relation, dict):
        return False
    if utility_signal_profile_matches(route_relation, require_all=["directly_answers_route"]):
        return True
    support_slots = route_relation.get("support_slots") if isinstance(route_relation.get("support_slots"), dict) else {}
    support_status = str(support_slots.get("support_status") or "")
    if support_status == "support_ready":
        return True
    if (
        support_status == "sequence_inferred_only"
        and route_relation.get("has_extra_route_anchor")
        and not support_slots.get("multi_origin_ambiguity")
    ):
        return True
    requires_object = bool(route_relation.get("claim_requires_route_object"))
    profiles = [
        ["has_relation_marker", "has_route_object_marker", "has_extra_route_anchor"],
    ]
    if not requires_object:
        profiles.append(["has_relation_marker", "has_directional_relation_marker", "has_extra_route_anchor"])
    for profile in profiles:
        if utility_signal_profile_matches(route_relation, require_all=profile):
            return True
    return False


def collect_evidence_sentence_candidates(evidence: List[Dict[str, Any]], claim: str, mode: str = "", limit: int = 6) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    seen = set()
    for item in evidence:
        if not should_summarize_item(item):
            continue
        for candidate in answer_candidates_from_item(item, claim, limit=3):
            if not isinstance(candidate, dict):
                continue
            sentence = normalize_text(str(candidate.get("sentence") or ""))
            if not sentence:
                continue
            key = (sentence.lower(), str(candidate.get("url") or ""), str(candidate.get("title") or ""))
            if key in seen:
                continue
            seen.add(key)
            enriched = dict(candidate)
            enriched.setdefault("source_type", item.get("source_type"))
            enriched.setdefault("url", item.get("url"))
            enriched.setdefault("title", item.get("title"))
            enriched["direct_answer"] = direct_answer_level(item, required_hits=1)
            enriched.update(sentence_candidate_features(item, enriched, claim, mode))
            if mode == EVIDENCE_MODE_ROUTE:
                route_relation = enriched.get("route_relation") if isinstance(enriched.get("route_relation"), dict) else {}
                if not route_sentence_meets_minimum_utility(route_relation):
                    continue
                if (
                    str(enriched.get("sentence_directness") or "") == SENTENCE_DIRECTNESS_RELATED_ONLY
                    and not route_relation.get("has_relation_marker")
                    and not route_relation.get("has_directional_relation_marker")
                ):
                    continue
            collected.append(enriched)
    collected.sort(
        key=lambda row: (
            int(row.get("sentence_score_total") or 0),
            int(row.get("sentence_utility_score") or 0),
            str(row.get("sentence_directness") or "") == SENTENCE_DIRECTNESS_DIRECT,
            str(row.get("sentence_directness") or "") == SENTENCE_DIRECTNESS_PARTIAL,
            int(row.get("score") or 0),
            str(row.get("field") or "") == "detail",
            str(row.get("field") or "") == "title",
        ),
        reverse=True,
    )
    return collected[:limit]


def summarize_event_claim(claim_id: str, claim: str, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    supporting_points: List[Dict[str, Any]] = []
    uncertain_points: List[Dict[str, Any]] = []
    answer_candidates: List[Dict[str, Any]] = []
    claim_numbers = [value for value, _unit in extract_numbers(claim)]
    for item in evidence:
        if not should_summarize_item(item):
            continue
        candidates = answer_candidates_from_item(item, claim)
        answer_candidates.extend(candidates)
        if not candidates:
            continue
        best = candidates[0]
        sentence = str(best.get("sentence") or "")
        sentence_numbers = [value for value, _unit in extract_numbers(sentence)]
        has_claim_number = bool(claim_numbers and any(value in sentence for value in claim_numbers))
        point = point_with_source(
            item,
            {
                "type": "event_answer_candidate",
                "claim_value": claim_numbers[0] if claim_numbers else "",
                "evidence_value": ", ".join(sentence_numbers[:3]),
                "evidence_sentence": sentence,
                "answer_candidate_score": best.get("score", 0),
            },
            required_hits=1,
        )
        if item.get("source_type") in {"official", "news", "encyclopedia"} and int(best.get("score") or 0) >= 5:
            point["direct_answer"] = "direct" if has_claim_number or not claim_numbers else point.get("direct_answer")
        if has_claim_number:
            supporting_points.append(point)
        else:
            uncertain_points.append(point)
    return {
        "claim_id": claim_id,
        "claim": claim,
        "evidence_mode": "event_result",
        "supporting_points": unique_points(supporting_points)[:3],
        "refuting_points": [],
        "uncertain_points": unique_points(uncertain_points)[:3],
        "answer_candidates": unique_points(answer_candidates)[:6],
        "evidence_sentence_candidates": collect_evidence_sentence_candidates(evidence, claim, mode="event_result", limit=6),
    }


def summarize_date_claim(
    claim_id: str,
    claim: str,
    evidence: List[Dict[str, Any]],
    source_intent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    claim_dates = extract_dates(claim)
    source_intent = source_intent if isinstance(source_intent, dict) else {}
    evidence_target = normalize_text(str(source_intent.get("evidence_target") or "")).lower()
    claim_is_calendar_state = evidence_target == "market_calendar" or is_market_calendar_state_claim(claim)
    claim_calendar_state = market_calendar_state_slot(claim) if claim_is_calendar_state else ""
    supporting_points: List[Dict[str, Any]] = []
    refuting_points: List[Dict[str, Any]] = []
    uncertain_points: List[Dict[str, Any]] = []
    for item in evidence:
        if not should_summarize_item(item):
            continue
        text = evidence_text(item)
        best = best_mode_answer_candidate(item, claim, EVIDENCE_MODE_DATE, limit=5) or best_answer_candidate(item, claim)
        best_sentence = normalize_text(str(best.get("sentence") or ""))
        evidence_calendar_state = market_calendar_state_slot(
            " ".join(
                [
                    best_sentence,
                    str(item.get("title") or ""),
                    str(item.get("snippet") or ""),
                ]
            )
        )
        sentence_dates = extract_dates(best_sentence)
        text_dates = extract_dates(text)
        evidence_dates = sentence_dates or text_dates
        if not evidence_dates:
            continue
        if claim_dates:
            claim_value = claim_dates[0]
            matched_value = next((value for value in evidence_dates if date_values_match(claim_value, value)), "")
            exact_match = bool(matched_value)
            calendar_state_conflict = bool(
                exact_match
                and claim_is_calendar_state
                and claim_calendar_state
                and evidence_calendar_state
                and claim_calendar_state != evidence_calendar_state
            )
            calendar_state_match = bool(
                exact_match
                and claim_is_calendar_state
                and claim_calendar_state
                and evidence_calendar_state
                and claim_calendar_state == evidence_calendar_state
            )
            if calendar_state_conflict:
                exact_match = False
            mismatch = bool(sentence_dates) and bool(evidence_dates) and not exact_match
            if calendar_state_conflict:
                mismatch = True
            if not exact_match and not mismatch:
                continue
            evidence_value = matched_value or evidence_dates[0]
            point = {
                "type": "date_match" if exact_match else "date_mismatch" if mismatch else "date_reference",
                "claim_value": claim_value,
                "evidence_value": evidence_value,
                "evidence_sentence": best_sentence or sentence_for_value(text, evidence_value),
            }
            if claim_is_calendar_state:
                point["calendar_state_claim"] = claim_calendar_state
                point["calendar_state_evidence"] = evidence_calendar_state
                point["calendar_state_alignment"] = "conflict" if calendar_state_conflict else "match" if calendar_state_match else "none"
            point = apply_candidate_features_to_point(point_with_source(item, point, required_hits=1), best)
            blocking_risks = item_structured_point_blocking_risks(item)
            if blocking_risks:
                point["type"] = "date_reference"
                point["point_contract_blocking_risks"] = blocking_risks
                uncertain_points.append(point)
            elif mismatch and claim_is_announcement_date_claim(claim) and sentence_is_non_announcement_event(best_sentence or point.get("evidence_sentence") or "", item):
                point["type"] = "date_reference"
                point["date_contract_note"] = "non_announcement_event_page"
                uncertain_points.append(point)
            elif exact_match:
                if calendar_state_match:
                    point["date_contract_note"] = "market_calendar_state_match"
                supporting_points.append(point)
            elif mismatch:
                if calendar_state_conflict:
                    point["date_contract_note"] = "market_calendar_state_conflict"
                refuting_points.append(point)
        else:
            uncertain_points.append(
                apply_candidate_features_to_point(
                    point_with_source(
                        item,
                        {
                        "type": "date_reference",
                        "claim_value": "",
                        "evidence_value": evidence_dates[0],
                        "evidence_sentence": best_sentence or sentence_for_value(text, evidence_dates[0]),
                        },
                        required_hits=1,
                    ),
                    best,
                )
            )
    return {
        "claim_id": claim_id,
        "claim": claim,
        "evidence_mode": "date_fact",
        "supporting_points": unique_points(supporting_points)[:3],
        "refuting_points": unique_points(refuting_points)[:3],
        "uncertain_points": unique_points(uncertain_points)[:3],
        "evidence_sentence_candidates": collect_evidence_sentence_candidates(evidence, claim, mode="date_fact", limit=6),
    }


def summarize_entity_claim(claim_id: str, claim: str, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    entities = claim_entities(claim)
    supporting_points: List[Dict[str, Any]] = []
    uncertain_points: List[Dict[str, Any]] = []
    for item in evidence:
        if not should_summarize_item(item):
            continue
        text = evidence_text(item)
        best = best_answer_candidate(item, claim)
        best_sentence = normalize_text(str(best.get("sentence") or ""))
        text_lower = text.lower()
        matched = [entity for entity in entities if entity_matches_text(entity, text_lower)]
        if matched:
            supporting_points.append(
                point_with_source(
                    item,
                    {
                    "type": "entity_match",
                    "claim_value": ", ".join(matched),
                    "evidence_value": ", ".join(matched),
                    "evidence_sentence": best_sentence,
                    },
                    required_hits=2,
                )
            )
        elif item.get("source_type") in {"official", "news"} and int(item.get("directness_score") or 0) >= 2 and best_sentence:
            point = point_with_source(
                item,
                {
                "type": "entity_reference_direct",
                "claim_value": claim,
                "evidence_value": best_sentence,
                "evidence_sentence": best_sentence,
                },
                required_hits=1,
            )
            if entity_sentence_has_relation_support(claim, best_sentence, int(best.get("score") or 0)):
                supporting_points.append(point)
            else:
                point["type"] = "entity_reference"
                point["direct_answer"] = "partial" if point.get("direct_answer") == "direct" else point.get("direct_answer")
                point["entity_contract_note"] = "background_entity_hit_without_relation_support"
                uncertain_points.append(point)
        elif item.get("source_type") in {"official", "news"}:
            uncertain_points.append(
                point_with_source(
                    item,
                    {
                    "type": "entity_reference",
                    "claim_value": ", ".join(entities[:2]),
                    "evidence_value": "",
                    "evidence_sentence": best_sentence,
                    },
                    required_hits=2,
                )
            )
    return {
        "claim_id": claim_id,
        "claim": claim,
        "evidence_mode": "entity_fact",
        "supporting_points": unique_points(supporting_points)[:3],
        "refuting_points": [],
        "uncertain_points": unique_points(uncertain_points)[:3],
        "evidence_sentence_candidates": collect_evidence_sentence_candidates(evidence, claim, mode="entity_fact", limit=6),
    }


ROUTE_SUPPORT_SLOT_STATUS_TEXT = {
    "support_ready": "support slots ready",
    "sequence_inferred_only": "direction and anchors present but no explicit transit phrase",
    "mixed_origin_reference": "mixed origins in one sentence; route reference remains ambiguous",
    "alias_anchor_reference": "only alias anchor matched; route reference remains weak",
    "direct_reference_only": "已经 direct，但攌槽位仍不完整",
}

ENTITY_RELATION_SUPPORT_MARKERS = (
    "影响",
    "导致",
    "原因",
    "因为",
    "目的",
    "为了",
    "宣布",
    "公布",
    "发布",
    "获奖",
    "授予",
    "奖金",
    "平分",
    "上调",
    "下调",
    "生效",
    "结果",
    "获胜",
    "击败",
    "不需要经过",
    "无需经过",
    "绕开",
    "经过",
)


def entity_sentence_has_relation_support(claim: str, sentence: str, answer_score: int = 0) -> bool:
    claim_text = normalize_text(claim)
    sentence_text = normalize_text(sentence)
    if not claim_text or not sentence_text:
        return False
    claim_markers = [marker for marker in ENTITY_RELATION_SUPPORT_MARKERS if marker in claim_text]
    if claim_markers:
        return any(marker in sentence_text for marker in claim_markers)
    claim_tokens = qa_text_tokens(claim_text)
    entity_tokens = set(claim_entities(claim_text))
    relation_tokens = [
        token for token in claim_tokens
        if token not in entity_tokens and len(token) >= 2 and not re.fullmatch(r"\d+(?:-\d+)?", token)
    ]
    if relation_tokens:
        relation_hits = sum(1 for token in relation_tokens if token.lower() in sentence_text.lower())
        if relation_hits >= 2:
            return True
    return answer_score >= 16 and len(claim_entities(claim_text)) >= 3 and len(sentence_text) <= 160


def route_support_slots(
    sentence: str,
    evidence_positive: bool,
    directional_relation: bool,
    evidence_has_object: bool,
    anchor_match_details: List[Dict[str, Any]],
    anchor_group_hit_count: int,
    required_anchor_group_hits: int,
) -> Dict[str, Any]:
    normalized_sentence = normalize_text(sentence)
    full_anchor_match_count = len(
        [
            detail for detail in anchor_match_details
            if isinstance(detail, dict) and not bool(detail.get("alias_match"))
        ]
    )
    alias_only_anchor_match = bool(anchor_match_details) and full_anchor_match_count <= 0
    multi_origin_ambiguity = bool(
        normalized_sentence
        and (
            normalized_sentence.count("?") + normalized_sentence.count(",") + normalized_sentence.count("?") >= 2
            or "等地" in normalized_sentence
        )
    )
    anchor_groups_satisfied = bool(required_anchor_group_hits <= 0 or anchor_group_hit_count >= required_anchor_group_hits)
    support_slot_score = (
        int(bool(evidence_positive)) * 2
        + int(bool(directional_relation))
        + int(bool(evidence_has_object))
        + int(anchor_groups_satisfied)
        + int(full_anchor_match_count > 0)
        - int(multi_origin_ambiguity)
    )
    support_status = "direct_reference_only"
    if evidence_positive and evidence_has_object and anchor_groups_satisfied and not multi_origin_ambiguity:
        support_status = "support_ready"
    elif multi_origin_ambiguity:
        support_status = "mixed_origin_reference"
    elif alias_only_anchor_match:
        support_status = "alias_anchor_reference"
    elif directional_relation and evidence_has_object and anchor_groups_satisfied:
        support_status = "sequence_inferred_only"
    return {
        "explicit_positive_phrase": bool(evidence_positive),
        "directional_path": bool(directional_relation),
        "route_object_present": bool(evidence_has_object),
        "anchor_groups_satisfied": anchor_groups_satisfied,
        "full_anchor_match_count": full_anchor_match_count,
        "alias_only_anchor_match": alias_only_anchor_match,
        "multi_origin_ambiguity": multi_origin_ambiguity,
        "support_slot_score": support_slot_score,
        "support_status": support_status,
        "support_status_text": ROUTE_SUPPORT_SLOT_STATUS_TEXT.get(support_status, support_status),
    }




def route_point(
    item: Dict[str, Any],
    claim: str,
    claim_route_hint: str,
    sentence: str,
    point_type: str,
    analysis_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    analysis = analysis_override or route_relation_analysis(claim, sentence)
    point = point_with_source(
        item,
        {
            "type": point_type,
            "claim_value": claim_route_hint,
            "evidence_value": sentence,
            "route_relation": analysis,
        },
        required_hits=2,
    )
    if not analysis["directly_answers_route"]:
        point["direct_answer"] = "related_only"
    else:
        support_slots = analysis.get("support_slots") if isinstance(analysis.get("support_slots"), dict) else {}
        support_status = normalize_text(str(support_slots.get("support_status") or "")).lower()
        polarity = normalize_text(str(analysis.get("polarity") or "")).lower()
        anchor_hit_count = int(analysis.get("anchor_hit_count") or 0)
        anchor_group_hit_count = int(analysis.get("anchor_group_hit_count") or 0)
        if (
            support_status == "support_ready"
            or anchor_hit_count > 0
            or anchor_group_hit_count > 0
            or (
                analysis.get("has_relation_marker")
                and analysis.get("has_route_object_marker")
                and analysis.get("has_directional_relation_marker")
                and polarity in {"support", "conflict"}
            )
        ):
            point["direct_answer"] = "direct"
        elif analysis.get("has_relation_marker"):
            point["direct_answer"] = "partial"
        else:
            point["direct_answer"] = "related_only"
    return point


def route_candidate_sentences(item: Dict[str, Any], claim: str) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    source_type = item.get("source_type")
    url = item.get("url")
    title = item.get("title")

    def append_candidate(sentence: str, analysis: Dict[str, Any], origin: str, retrieval_hint: Optional[Dict[str, Any]] = None) -> None:
        analysis = merge_route_analysis(analysis, retrieval_hint)
        if not sentence or not route_sentence_meets_minimum_utility(analysis):
            return
        candidate = {
            "sentence": sentence,
            "route_relation": analysis,
            "source_type": source_type,
            "url": url,
            "title": title,
            "from": origin,
            "field": "detail",
            "score": 12 if analysis.get("directly_answers_route") else 8 if analysis.get("token_hit_count", 0) >= 2 else 5,
        }
        candidate["direct_answer"] = "direct" if analysis.get("directly_answers_route") else "related_only"
        candidate.update(sentence_candidate_features(item, candidate, claim, EVIDENCE_MODE_ROUTE))
        candidates.append(candidate)

    route_sentence = item.get("route_sentence") if isinstance(item.get("route_sentence"), dict) else {}
    if route_sentence.get("sentence"):
        sentence = normalize_text(str(route_sentence.get("sentence") or ""))
        analysis = route_relation_analysis(claim, sentence)
        append_candidate(sentence, analysis, "retrieval_route_sentence", route_sentence)
    for candidate in route_sentence.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        sentence = normalize_text(str(candidate.get("sentence") or ""))
        if not sentence:
            continue
        analysis = route_relation_analysis(claim, sentence)
        append_candidate(sentence, analysis, "retrieval_candidate", candidate)
    for sentence in extract_route_sentences(evidence_text(item)):
        append_candidate(sentence, route_relation_analysis(claim, sentence), "evidence_text")
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for candidate in candidates:
        sentence = candidate["sentence"]
        if sentence in seen:
            continue
        seen.add(sentence)
        deduped.append(candidate)
    return sorted(
        deduped,
        key=lambda candidate: (
            int(candidate.get("sentence_score_total") or 0),
            int(candidate.get("sentence_utility_score") or 0),
            int(candidate["route_relation"].get("directly_answers_route") or 0),
            int(candidate["route_relation"].get("token_hit_count") or 0),
        ),
        reverse=True,
    )[:5]


def unique_route_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for candidate in candidates:
        sentence = normalize_text(str(candidate.get("sentence") or ""))
        if not sentence or sentence in seen:
            continue
        seen.add(sentence)
        deduped.append(candidate)
    return sorted(
        deduped,
        key=lambda candidate: (
            int(candidate.get("sentence_score_total") or 0),
            int(candidate.get("sentence_utility_score") or 0),
            int(candidate.get("route_relation", {}).get("directly_answers_route") or 0),
            int(candidate.get("route_relation", {}).get("token_hit_count") or 0),
            int(candidate.get("route_relation", {}).get("has_relation_marker") or 0),
        ),
        reverse=True,
    )


def summarize_route_claim(claim_id: str, claim: str, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    claim_sentences = extract_route_sentences(claim)
    claim_route_hint = claim_sentences[0] if claim_sentences else claim
    supporting_points: List[Dict[str, Any]] = []
    refuting_points: List[Dict[str, Any]] = []
    uncertain_points: List[Dict[str, Any]] = []
    candidate_sentences: List[Dict[str, Any]] = []
    for item in evidence:
        if not should_summarize_item(item):
            continue
        route_sentence = item.get("route_sentence") if isinstance(item.get("route_sentence"), dict) else {}
        item_route_candidates = route_candidate_sentences(item, claim)
        candidate_sentences.extend(item_route_candidates)
        chosen_candidate: Dict[str, Any] = {}
        title = normalize_text(str(item.get("title") or ""))
        title_analysis = route_relation_analysis(claim, title) if title else {}
        title_has_route_relation = bool(
            re.search(r"\b(cross|crossed|through|via|overfly|overflight|airspace|transit)\b", title.lower())
            or any(marker in title for marker in ["经过", "飞越", "领空", "跺"])
        )
        if route_sentence.get("direct_sentence") and title_has_route_relation:
            chosen = title
        elif title_analysis.get("directly_answers_route") and title_analysis.get("polarity") != "uncertain":
            chosen = title
            route_sentence = {}
        elif route_sentence.get("direct_sentence") and route_sentence.get("sentence"):
            chosen = normalize_text(str(route_sentence.get("sentence") or ""))
        else:
            candidates = item_route_candidates
            if not candidates:
                continue
            chosen_candidate = candidates[0]
            chosen = candidates[0]["sentence"]
        chosen_hint = route_sentence if normalize_text(str(route_sentence.get("sentence") or "")) == normalize_text(chosen) else {}
        if isinstance(chosen_candidate.get("route_relation"), dict):
            analysis = merge_route_analysis(dict(chosen_candidate.get("route_relation") or {}), chosen_hint)
        else:
            analysis = merge_route_analysis(route_relation_analysis(claim, chosen), chosen_hint)
        hint_support_slots = chosen_hint.get("support_slots") if isinstance(chosen_hint.get("support_slots"), dict) else {}
        hint_can_promote_direct = bool(
            chosen_hint.get("direct_sentence")
            and not hint_support_slots.get("multi_origin_ambiguity")
            and not hint_support_slots.get("alias_only_anchor_match")
            and (
                chosen_hint.get("has_extra_route_anchor")
                or hint_support_slots.get("anchor_groups_satisfied")
            )
        )
        if hint_can_promote_direct:
            analysis["directly_answers_route"] = True
            analysis["token_hits"] = chosen_hint.get("entity_hits") or analysis.get("token_hits", [])
            analysis["token_hit_count"] = int(chosen_hint.get("entity_hit_count") or analysis.get("token_hit_count") or 0)
            analysis["has_relation_marker"] = True
            if analysis.get("claim_negative") and analysis.get("evidence_positive") and not analysis.get("evidence_negative"):
                analysis["polarity"] = "conflict"
        if analysis["polarity"] == "conflict":
            refuting_points.append(route_point(item, claim, claim_route_hint, chosen, "route_conflict", analysis))
        elif analysis["polarity"] == "support":
            supporting_points.append(route_point(item, claim, claim_route_hint, chosen, "route_support", analysis))
        else:
            uncertain_points.append(route_point(item, claim, claim_route_hint, chosen, "route_reference", analysis))
    route_candidates = unique_route_candidates(candidate_sentences)[:6]
    generic_candidates = collect_evidence_sentence_candidates(evidence, claim, mode="route_fact", limit=6)
    merged_candidates: List[Dict[str, Any]] = []
    seen_sentences = set()
    for candidate in route_candidates + generic_candidates:
        if not isinstance(candidate, dict):
            continue
        sentence = normalize_text(str(candidate.get("sentence") or ""))
        if not sentence or sentence.lower() in seen_sentences:
            continue
        seen_sentences.add(sentence.lower())
        merged_candidates.append(candidate)
    merged_candidates.sort(
        key=lambda candidate: (
            int(candidate.get("sentence_score_total") or 0),
            int(candidate.get("sentence_utility_score") or 0),
            str(candidate.get("sentence_directness") or "") == SENTENCE_DIRECTNESS_DIRECT,
            str(candidate.get("sentence_directness") or "") == SENTENCE_DIRECTNESS_PARTIAL,
            int(candidate.get("route_relation", {}).get("directly_answers_route") or 0),
        ),
        reverse=True,
    )
    return {
        "claim_id": claim_id,
        "evidence_mode": "route_fact",
        "supporting_points": unique_points(supporting_points)[:3],
        "refuting_points": unique_points(refuting_points)[:3],
        "uncertain_points": unique_points(uncertain_points)[:3],
        "candidate_sentences": route_candidates,
        "evidence_sentence_candidates": merged_candidates[:6],
    }


def claim_coverage(
    claim_id: str,
    mode: str,
    evidence: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    mode = coverage_mode(mode, summary)
    web_items = [item for item in evidence if item.get("source_type") not in {"input_context", "computed"}]
    if mode == "route_fact":
        def route_point_counts_as_direct(point: Dict[str, Any]) -> bool:
            route_relation = point.get("route_relation") if isinstance(point.get("route_relation"), dict) else {}
            support_slots = route_relation.get("support_slots") if isinstance(route_relation.get("support_slots"), dict) else {}
            support_status = normalize_text(str(support_slots.get("support_status") or "")).lower()
            anchor_hit_count = int(route_relation.get("anchor_hit_count") or 0)
            anchor_group_hit_count = int(route_relation.get("anchor_group_hit_count") or 0)
            if not (
                route_relation.get("directly_answers_route")
                and point.get("direct_answer") == "direct"
                and route_relation.get("has_relation_marker")
            ):
                return False
            if support_status in {"direct_reference_only", "reference_only", "weak_reference_only"}:
                return False
            if anchor_hit_count > 0 or anchor_group_hit_count > 0:
                return True
            return bool(
                route_relation.get("has_route_object_marker")
                and route_relation.get("has_directional_relation_marker")
                and normalize_text(str(route_relation.get("polarity") or "")).lower() in {"support", "conflict"}
            )

        route_points = [
            point
            for point in (
                list(summary.get("supporting_points", []))
                + list(summary.get("refuting_points", []))
                + list(summary.get("uncertain_points", []))
            )
            if route_point_counts_as_direct(point)
        ]
        official_points = [point for point in route_points if point.get("source_type") == "official"]
        news_points = [point for point in route_points if point.get("source_type") == "news"]
        weak_items = [item for item in web_items if item.get("source_type") in {"forum", "unknown"}]
        if official_points:
            level = "strong"
            reason = "direct_official_route_relation"
        elif news_points:
            level = "moderate"
            reason = "direct_news_route_relation"
        elif route_points:
            level = "weak"
            reason = "direct_weak_route_relation"
        elif web_items:
            level = "weak"
            reason = "related_route_evidence_only"
        else:
            level = "none"
            reason = "no_web_evidence"
        return {
            "claim_id": claim_id,
            "evidence_mode": mode,
            "coverage_level": level,
            "coverage_reason": reason,
            "web_evidence_count": len(web_items),
            "direct_evidence_count": len(route_points),
            "partial_evidence_count": 0,
            "official_direct_count": len(official_points),
            "news_direct_count": len(news_points),
            "weak_evidence_count": len(weak_items),
            "supporting_direct_points": len([point for point in summary.get("supporting_points", []) if point in route_points]),
            "refuting_direct_points": len([point for point in summary.get("refuting_points", []) if point in route_points]),
        }
    if mode == "numeric_fact":
        direct_numeric_points = [
            point
            for point in list(summary.get("supporting_points", [])) + list(summary.get("refuting_points", []))
            if point.get("direct_answer") == "direct"
        ]
        official_points = [point for point in direct_numeric_points if point.get("source_type") == "official"]
        news_points = [point for point in direct_numeric_points if point.get("source_type") == "news"]
        weak_items = [item for item in web_items if item.get("source_type") in {"forum", "unknown"}]
        if official_points:
            level = "strong"
            reason = "direct_official_numeric_point"
        elif news_points:
            level = "moderate"
            reason = "direct_news_numeric_point"
        elif direct_numeric_points:
            level = "weak"
            reason = "direct_weak_numeric_point"
        elif web_items:
            level = "partial"
            reason = "numeric_reference_only"
        else:
            level = "none"
            reason = "no_web_evidence"
        return {
            "claim_id": claim_id,
            "evidence_mode": mode,
            "coverage_level": level,
            "coverage_reason": reason,
            "web_evidence_count": len(web_items),
            "direct_evidence_count": len(direct_numeric_points),
            "partial_evidence_count": 0,
            "official_direct_count": len(official_points),
            "news_direct_count": len(news_points),
            "weak_evidence_count": len(weak_items),
            "supporting_direct_points": len([point for point in summary.get("supporting_points", []) if point in direct_numeric_points]),
            "refuting_direct_points": len([point for point in summary.get("refuting_points", []) if point in direct_numeric_points]),
        }
    required_hits = required_hits_for_mode(mode)
    direct_items = [item for item in web_items if direct_answer_level(item, required_hits=required_hits) == "direct"]
    partial_items = [item for item in web_items if direct_answer_level(item, required_hits=required_hits) == "partial"]
    official_direct = [item for item in direct_items if item.get("source_type") == "official"]
    news_direct = [item for item in direct_items if item.get("source_type") == "news"]
    weak_items = [item for item in web_items if item.get("source_type") in {"forum", "unknown"}]
    supporting_direct = [
        point for point in summary.get("supporting_points", [])
        if point.get("direct_answer") == "direct"
    ]
    refuting_direct = [
        point for point in summary.get("refuting_points", [])
        if point.get("direct_answer") == "direct"
    ]
    strong_direct_points = [
        point for point in supporting_direct + refuting_direct
        if point.get("source_type") in {"official", "news", "encyclopedia"}
    ]
    if official_direct:
        level = "strong"
        reason = "direct_official_evidence"
    elif strong_direct_points or news_direct:
        level = "moderate"
        reason = "direct_non_official_evidence"
    elif partial_items:
        level = "partial"
        reason = "partial_evidence_only"
    elif web_items:
        level = "weak"
        reason = "related_or_weak_evidence_only"
    else:
        level = "none"
        reason = "no_web_evidence"
    return {
        "claim_id": claim_id,
        "evidence_mode": mode,
        "coverage_level": level,
        "coverage_reason": reason,
        "web_evidence_count": len(web_items),
        "direct_evidence_count": len(direct_items),
        "partial_evidence_count": len(partial_items),
        "official_direct_count": len(official_direct),
        "news_direct_count": len(news_direct),
        "weak_evidence_count": len(weak_items),
        "supporting_direct_points": len(supporting_direct),
        "refuting_direct_points": len(refuting_direct),
    }


def route_direct_uncertain_diagnostics(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    reason_counts: Dict[str, int] = {}
    examples: List[str] = []
    for point in points:
        route_relation = point.get("route_relation") if isinstance(point.get("route_relation"), dict) else {}
        sentence = normalize_text(str(point.get("evidence_value") or point.get("evidence_sentence") or ""))
        labels: List[str] = []
        if not route_relation.get("evidence_positive"):
            labels.append("no_explicit_positive_route_phrase")
        if (
            route_relation.get("has_directional_relation_marker")
            and int(route_relation.get("anchor_group_hit_count") or 0) >= int(route_relation.get("required_anchor_group_hits") or 0)
            and not route_relation.get("evidence_positive")
        ):
            labels.append("direction_without_transit_sequence")
        if sentence and (sentence.count("?") + sentence.count(",") + sentence.count("?") >= 2 or "??" in sentence):
            labels.append("multi_origin_ambiguity")
        match_details = route_relation.get("anchor_match_details") if isinstance(route_relation.get("anchor_match_details"), list) else []
        if match_details and all(bool(detail.get("alias_match")) for detail in match_details if isinstance(detail, dict)):
            labels.append("alias_only_anchor_match")
        labels = dedupe_keep_order(labels)
        for label in labels:
            reason_counts[label] = reason_counts.get(label, 0) + 1
        if labels and len(examples) < 3:
            examples.append(
                f"{', '.join(ROUTE_DIRECT_UNCERTAIN_REASON_TEXT.get(label, label) for label in labels)}: {compact_claim_text(sentence, 60)}"
            )
    return {
        "reason_counts": reason_counts,
        "examples": examples,
    }


def route_direct_uncertain_slot_diagnostics(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    reason_counts: Dict[str, int] = {}
    examples: List[str] = []
    status_counts: Dict[str, int] = {}
    for point in points:
        route_relation = point.get("route_relation") if isinstance(point.get("route_relation"), dict) else {}
        support_slots = route_relation.get("support_slots") if isinstance(route_relation.get("support_slots"), dict) else {}
        sentence = normalize_text(str(point.get("evidence_value") or point.get("evidence_sentence") or ""))
        labels: List[str] = []
        if not support_slots.get("explicit_positive_phrase"):
            labels.append("no_explicit_positive_route_phrase")
        if (
            support_slots.get("directional_path")
            and support_slots.get("anchor_groups_satisfied")
            and not support_slots.get("explicit_positive_phrase")
        ):
            labels.append("direction_without_transit_sequence")
        if support_slots.get("multi_origin_ambiguity"):
            labels.append("multi_origin_ambiguity")
        if support_slots.get("alias_only_anchor_match"):
            labels.append("alias_only_anchor_match")
        labels = dedupe_keep_order(labels)
        for label in labels:
            reason_counts[label] = reason_counts.get(label, 0) + 1
        support_status = str(support_slots.get("support_status") or "")
        if support_status:
            status_counts[support_status] = status_counts.get(support_status, 0) + 1
        if labels and len(examples) < 3:
            examples.append(
                f"{support_slots.get('support_status_text') or support_status}: "
                f"{', '.join(ROUTE_DIRECT_UNCERTAIN_REASON_TEXT.get(label, label) for label in labels)}: "
                f"{compact_claim_text(sentence, 60)}"
            )
    return {
        "reason_counts": reason_counts,
        "examples": examples,
        "status_counts": status_counts,
    }


def point_conversion_diagnostics(summary: Dict[str, Any], coverage: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(summary.get("evidence_mode") or "")
    sentence_candidates = [
        candidate
        for candidate in (summary.get("evidence_sentence_candidates") or [])
        if isinstance(candidate, dict)
    ]
    route_candidates = [
        candidate
        for candidate in (summary.get("candidate_sentences") or [])
        if isinstance(candidate, dict)
    ]
    direct_candidates = [
        candidate for candidate in sentence_candidates
        if str(candidate.get("sentence_directness") or "") == SENTENCE_DIRECTNESS_DIRECT
    ]
    partial_candidates = [
        candidate for candidate in sentence_candidates
        if str(candidate.get("sentence_directness") or "") == SENTENCE_DIRECTNESS_PARTIAL
    ]
    related_candidates = [
        candidate for candidate in sentence_candidates
        if str(candidate.get("sentence_directness") or "") == SENTENCE_DIRECTNESS_RELATED_ONLY
    ]
    supporting_points = [point for point in (summary.get("supporting_points") or []) if isinstance(point, dict)]
    refuting_points = [point for point in (summary.get("refuting_points") or []) if isinstance(point, dict)]
    uncertain_points = [point for point in (summary.get("uncertain_points") or []) if isinstance(point, dict)]
    support_refute_points = supporting_points + refuting_points
    direct_support_refute_points = [
        point for point in support_refute_points
        if str(point.get("direct_answer") or "") == "direct"
    ]
    direct_uncertain_points = [
        point for point in uncertain_points
        if str(point.get("direct_answer") or "") == "direct"
    ]
    sentence_candidate_profile: Dict[str, int] = {}
    for candidate in sentence_candidates:
        profile = normalize_text(str(candidate.get("sentence_candidate_profile") or ""))
        if profile:
            sentence_candidate_profile[profile] = int(sentence_candidate_profile.get(profile, 0) or 0) + 1
    top_candidate = sentence_candidates[0] if sentence_candidates else {}
    top_candidate_slot_match = normalize_text(str(top_candidate.get("candidate_slot_match") or ""))
    direct_candidate_gap_reason = normalize_text(str(top_candidate.get("direct_candidate_gap_reason") or ""))
    stage = POINT_STAGE_CONVERTED
    reason = "已有 supporting/refuting points"
    if not sentence_candidates:
        stage = POINT_STAGE_NO_CANDIDATE
        reason = "没有候证捏"
    elif mode == EVIDENCE_MODE_ROUTE and not route_candidates:
        stage = POINT_STAGE_ROUTE_RELATION_MISSING
        reason = "叜通用 related_only 候句，没有抽到包吘硷线关系词?route candidate"
    elif not direct_candidates and not partial_candidates:
        stage = POINT_STAGE_RELATED_ONLY
        reason = "叜 related_only 候句，尚朽?direct/partial 候句"
    elif not direct_candidates:
        stage = POINT_STAGE_NO_DIRECT
        reason = "已有 partial 候句，但还没?direct 候句"
    elif direct_candidates and not support_refute_points and uncertain_points:
        stage = POINT_STAGE_DIRECT_TO_UNCERTAIN
        reason = "已有 direct 候句，但叽?uncertain points，未形成 supporting/refuting points"
    elif direct_candidates and not support_refute_points:
        stage = POINT_STAGE_DIRECT_NOT_CONVERTED
        reason = "已有 direct 候句，但朽?supporting/refuting points"
    elif support_refute_points and not direct_support_refute_points:
        stage = POINT_STAGE_POINT_NOT_DIRECT
        reason = "已形?supporting/refuting points，但这些 points 仍不?direct 级别"
    return {
        "candidate_sentence_count": len(sentence_candidates),
        "route_candidate_count": len(route_candidates),
        "direct_count": len(direct_candidates),
        "partial_count": len(partial_candidates),
        "related_only_count": len(related_candidates),
        "supporting_count": len(supporting_points),
        "refuting_count": len(refuting_points),
        "uncertain_count": len(uncertain_points),
        "support_refute_count": len(support_refute_points),
        "direct_support_refute_count": len(direct_support_refute_points),
        "coverage_direct_count": int(coverage.get("direct_evidence_count") or 0),
        "direct_uncertain_count": len(direct_uncertain_points),
        "direct_uncertain_reason_counts": (
            route_direct_uncertain_slot_diagnostics(direct_uncertain_points).get("reason_counts") or {}
            if mode == EVIDENCE_MODE_ROUTE else {}
        ),
        "direct_uncertain_examples": (
            route_direct_uncertain_slot_diagnostics(direct_uncertain_points).get("examples") or []
            if mode == EVIDENCE_MODE_ROUTE else []
        ),
        "direct_uncertain_status_counts": (
            route_direct_uncertain_slot_diagnostics(direct_uncertain_points).get("status_counts") or {}
            if mode == EVIDENCE_MODE_ROUTE else {}
        ),
        "sentence_candidate_profile": sentence_candidate_profile,
        "top_candidate_slot_match": top_candidate_slot_match,
        "direct_candidate_gap_reason": direct_candidate_gap_reason,
        "stage": stage,
        "reason": reason,
    }

def point_conversion_block_layer(point_conversion: Dict[str, Any]) -> str:
    stage = str(point_conversion.get("stage") or "")
    if stage in {POINT_STAGE_DIRECT_TO_UNCERTAIN, POINT_STAGE_DIRECT_NOT_CONVERTED, POINT_STAGE_POINT_NOT_DIRECT, POINT_STAGE_CONVERTED}:
        return "point"
    if stage in {POINT_STAGE_NO_CANDIDATE, POINT_STAGE_NO_DIRECT, POINT_STAGE_RELATED_ONLY, POINT_STAGE_ROUTE_RELATION_MISSING}:
        return "sentence"
    return ""


def observed_slot_signals_from_summary(summary: Dict[str, Any]) -> Tuple[set[str], Dict[str, List[str]]]:
    buckets: set[str] = set()
    observed_slots: Dict[str, List[str]] = {}

    def add_slot(slot_name: str, value: str) -> None:
        text = normalize_text(value)
        if not text:
            return
        observed_slots.setdefault(slot_name, []).append(text[:160])

    status_pattern = re.compile(
        r"(休市|开盘|停牌|生效|发布|公布|取消|暂停|战胜|击败|赢|获胜|晋级|result|won|beat|open|closed|effective|announced|released)",
        flags=re.I,
    )
    for candidate in summary.get("evidence_sentence_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        sentence = normalize_text(str(candidate.get("sentence") or ""))
        if candidate.get("time_hits"):
            buckets.add("time")
            add_slot("time_scope", sentence)
        if candidate.get("numeric_hits"):
            buckets.add("numeric")
            add_slot("metric_or_relation", sentence)
        if candidate.get("route_hits"):
            buckets.add("route")
            add_slot("metric_or_relation", sentence)
            add_slot("object", sentence)
        if sentence and status_pattern.search(sentence):
            buckets.update({"status", "event"})
            add_slot("status_or_result", sentence)

    all_points = [
        point
        for bucket_name in ("supporting_points", "refuting_points", "uncertain_points")
        for point in (summary.get(bucket_name) or [])
        if isinstance(point, dict)
    ]
    for point in all_points:
        claim_value = normalize_text(str(point.get("claim_value") or ""))
        evidence_value = normalize_text(str(point.get("evidence_value") or ""))
        direct_text = " ".join(value for value in [claim_value, evidence_value] if value)
        if direct_text:
            add_slot("status_or_result", direct_text)
        if isinstance(point.get("numeric_alignment"), dict):
            buckets.add("numeric")
            add_slot("metric_or_relation", direct_text or str(point.get("type") or ""))
        if normalize_text(str(point.get("numeric_contract_note") or "")) == "time_scope_mismatch":
            buckets.add("time")
            add_slot("time_scope", direct_text or "time_scope_mismatch")
        if normalize_text(str(point.get("date_contract_note") or "")) in {"market_calendar_state_conflict", "time_scope_mismatch"}:
            buckets.add("time")
            add_slot("time_scope", direct_text or str(point.get("date_contract_note") or ""))
    return buckets, observed_slots


def infer_point_conversion_block_reason(summary: Dict[str, Any], point_conversion: Dict[str, Any]) -> str:
    mode = str(summary.get("evidence_mode") or "")
    stage = str(point_conversion.get("stage") or "")
    evidence_need_program = summary.get("evidence_need_program") if isinstance(summary.get("evidence_need_program"), dict) else {}
    decision_slots = evidence_need_program.get("decision_slots") if isinstance(evidence_need_program.get("decision_slots"), dict) else {}
    anchor_buckets = set(str(item) for item in (decision_slots.get("anchor_buckets") or []) if str(item))
    direct_need = evidence_need_program.get("direct_evidence_need") if isinstance(evidence_need_program.get("direct_evidence_need"), dict) else {}
    evidence_kind = str(direct_need.get("evidence_kind") or "")
    sentence_candidates = [
        candidate for candidate in (summary.get("evidence_sentence_candidates") or [])
        if isinstance(candidate, dict)
    ]
    sentence_candidate_profiles = {
        normalize_text(str(candidate.get("sentence_candidate_profile") or ""))
        for candidate in sentence_candidates
        if normalize_text(str(candidate.get("sentence_candidate_profile") or ""))
    }
    top_gap_reason = normalize_text(
        str(
            (
                point_conversion.get("direct_candidate_gap_reason")
                if isinstance(point_conversion, dict) else ""
            )
            or (
                sentence_candidates[0].get("direct_candidate_gap_reason")
                if sentence_candidates and isinstance(sentence_candidates[0], dict) else ""
            )
            or ""
        )
    )
    claim_needs_open = bool(
        re.search(
            r"(开盘|开市|opening|opened)",
            " ".join(
                normalize_text(str(part or ""))
                for part in [
                    summary.get("claim") or "",
                    evidence_need_program.get("normalized_assertion") if isinstance(evidence_need_program, dict) else "",
                    direct_need.get("must_answer") if isinstance(direct_need, dict) else "",
                ]
                if normalize_text(str(part or ""))
            ),
            flags=re.I,
        )
    )
    if claim_needs_open and sentence_candidates:
        candidate_text = " ".join(normalize_text(str(candidate.get("sentence") or "")) for candidate in sentence_candidates)
        has_open = bool(re.search(r"(开盘|开市|高开|opening|opened|open price|open gain)", candidate_text, flags=re.I))
        has_intraday = bool(re.search(r"(盘中|一度|曾|瞬时|最高|新高|intraday|at one point|session high|hit as high as)", candidate_text, flags=re.I))
        has_close = bool(re.search(r"(收盘|尾盘|close|closed)", candidate_text, flags=re.I))
        if (has_intraday or has_close) and not has_open:
            return "not_same_fact_slot"
    if top_gap_reason in {"opening_slot_mismatch", "route_relation_indirect"}:
        return "not_same_fact_slot"
    if top_gap_reason == "date_role_mismatch":
        return "date_role_mismatch"
    if top_gap_reason == "result_granularity_mismatch":
        return "result_granularity_mismatch"
    rescued_sentence_candidates = [
        candidate for candidate in sentence_candidates
        if "deterministic_candidate_rescue" in {
            normalize_text(str(reason or "")).lower()
            for reason in (candidate.get("reasons") or [])
        }
    ]
    all_points = [
        point for bucket in ("supporting_points", "refuting_points", "uncertain_points")
        for point in (summary.get(bucket) or [])
        if isinstance(point, dict)
    ]
    numeric_mismatch = any(
        isinstance(point.get("numeric_alignment"), dict)
        and point.get("numeric_alignment", {}).get("comparable") is False
        for point in all_points
    )
    if numeric_mismatch:
        return "numeric_not_normalizable"
    required_slots = evidence_need_program.get("required_slot_profile") if isinstance(evidence_need_program.get("required_slot_profile"), list) else []
    observed_buckets, observed_slots = observed_slot_signals_from_summary(summary)
    missing_required_slots = shared_infer_missing_required_slots(
        decision_slots,
        mode,
        claim_text=str(summary.get("claim") or ""),
        source_intent=None,
        observed_buckets=observed_buckets,
        observed_slots=observed_slots,
        required_slots=required_slots,
    )
    if missing_required_slots and not sentence_candidates and stage in {POINT_STAGE_RELATED_ONLY, POINT_STAGE_NO_DIRECT, POINT_STAGE_NO_CANDIDATE}:
        if mode == "numeric_fact" and any(slot in {"time_scope", "metric_or_relation"} for slot in missing_required_slots):
            return "numeric_not_normalizable"
        if mode in {"date_fact", "schedule_fact"} and any(slot in {"time_scope", "status_or_result"} for slot in missing_required_slots):
            return "date_role_mismatch"
        if mode == "event_result" and any(slot in {"subject", "status_or_result"} for slot in missing_required_slots):
            return "result_granularity_mismatch"
        if mode == EVIDENCE_MODE_ROUTE and any(slot in {"subject", "object", "metric_or_relation"} for slot in missing_required_slots):
            return "not_same_fact_slot"
    time_scope_risk = any(
        normalize_text(str(point.get("numeric_contract_note") or "")) == "time_scope_mismatch"
        or normalize_text(str(point.get("date_contract_note") or "")) in {"market_calendar_state_conflict", "time_scope_mismatch"}
        or any(
            normalize_text(str(risk)) in {
                "point_time_scope_mismatch",
                "time_scope_not_bound_to_metric_point",
                "missing_binding_time_scope",
                "missing_time_scope",
                "date_window_mismatch",
            }
            for risk in (point.get("point_contract_risks") or [])
        )
        for point in all_points
    )
    if time_scope_risk:
        return "date_role_mismatch"
    if evidence_kind == "route_or_exclusivity" and stage in {POINT_STAGE_ROUTE_RELATION_MISSING, POINT_STAGE_DIRECT_TO_UNCERTAIN, POINT_STAGE_DIRECT_NOT_CONVERTED, POINT_STAGE_POINT_NOT_DIRECT}:
        return "not_same_fact_slot"
    if evidence_kind == "numeric_quote_or_table" and stage in {POINT_STAGE_DIRECT_TO_UNCERTAIN, POINT_STAGE_DIRECT_NOT_CONVERTED, POINT_STAGE_POINT_NOT_DIRECT}:
        return "numeric_not_normalizable"
    if evidence_kind == "official_date_or_schedule" and stage in {POINT_STAGE_DIRECT_TO_UNCERTAIN, POINT_STAGE_DIRECT_NOT_CONVERTED, POINT_STAGE_POINT_NOT_DIRECT}:
        return "date_role_mismatch"
    if evidence_kind == "direct_result" and stage in {POINT_STAGE_DIRECT_TO_UNCERTAIN, POINT_STAGE_DIRECT_NOT_CONVERTED, POINT_STAGE_POINT_NOT_DIRECT}:
        return "result_granularity_mismatch"
    if mode == "event_result" and stage in {POINT_STAGE_DIRECT_TO_UNCERTAIN, POINT_STAGE_DIRECT_NOT_CONVERTED, POINT_STAGE_POINT_NOT_DIRECT}:
        return "result_granularity_mismatch"
    if mode == EVIDENCE_MODE_ROUTE and stage in {POINT_STAGE_ROUTE_RELATION_MISSING, POINT_STAGE_DIRECT_TO_UNCERTAIN, POINT_STAGE_DIRECT_NOT_CONVERTED}:
        return "not_same_fact_slot"
    if "route" in anchor_buckets and stage in {POINT_STAGE_RELATED_ONLY, POINT_STAGE_NO_DIRECT}:
        return "not_same_fact_slot"
    if "time" in anchor_buckets and mode in {"date_fact", "schedule_fact"} and stage in {POINT_STAGE_RELATED_ONLY, POINT_STAGE_NO_DIRECT}:
        return "date_role_mismatch"
    if stage in {POINT_STAGE_RELATED_ONLY, POINT_STAGE_NO_DIRECT, POINT_STAGE_NO_CANDIDATE, POINT_STAGE_POINT_NOT_DIRECT}:
        if top_gap_reason in {"numeric_reference_only", "date_reference_only", "commentary_only", "weak_anchor_only"}:
            return "candidate_not_direct"
        if "slot_hit_but_indirect" in sentence_candidate_profiles or "direct_candidate" in sentence_candidate_profiles:
            return "candidate_not_direct"
        if rescued_sentence_candidates or sentence_candidates:
            return "candidate_not_direct"
        return "related_but_not_assertive"
    if sentence_candidates:
        return "candidate_not_direct"
    return ""


def compact_evidence_point_event(point: Dict[str, Any]) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        "type": point.get("type") or "",
        "direct_answer": point.get("direct_answer") or "",
        "source_type": point.get("source_type") or "",
    }
    for key in ("claim_value", "evidence_value", "evidence_sentence", "numeric_contract_note", "date_contract_note", "entity_contract_note"):
        value = normalize_text(str(point.get(key) or ""))
        if value:
            event[key] = compact_claim_text(value, 120)
    route_relation = point.get("route_relation") if isinstance(point.get("route_relation"), dict) else {}
    if route_relation:
        event["route_relation"] = {
            key: route_relation.get(key)
            for key in (
                "directly_answers_route",
                "has_relation_marker",
                "has_route_object_marker",
                "has_directional_relation_marker",
                "anchor_hit_count",
                "anchor_group_hit_count",
                "polarity",
                "support_status",
            )
            if key in route_relation
        }
    numeric_alignment = point.get("numeric_alignment") if isinstance(point.get("numeric_alignment"), dict) else {}
    if numeric_alignment:
        event["numeric_alignment"] = {
            key: numeric_alignment.get(key)
            for key in ("family", "claim_unit_signature", "evidence_unit_signature", "comparable", "mismatch_reason")
            if key in numeric_alignment
        }
    if point.get("point_contract_status") or point.get("point_contract_risks"):
        event["point_contract"] = {
            "status": point.get("point_contract_status") or "",
            "risks": list(point.get("point_contract_risks") or [])[:4],
        }
    return event


def evidence_event_summary(summary: Dict[str, Any], coverage: Dict[str, Any]) -> Dict[str, Any]:
    sentence_candidates = [candidate for candidate in (summary.get("evidence_sentence_candidates") or []) if isinstance(candidate, dict)]
    supporting_points = [point for point in (summary.get("supporting_points") or []) if isinstance(point, dict)]
    refuting_points = [point for point in (summary.get("refuting_points") or []) if isinstance(point, dict)]
    uncertain_points = [point for point in (summary.get("uncertain_points") or []) if isinstance(point, dict)]
    direct_supporting = [point for point in supporting_points if str(point.get("direct_answer") or "") == "direct"]
    direct_refuting = [point for point in refuting_points if str(point.get("direct_answer") or "") == "direct"]
    direct_uncertain = [point for point in uncertain_points if str(point.get("direct_answer") or "") == "direct"]
    point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
    events: List[Dict[str, Any]] = []
    events.append(
        {
            "event": "candidate_generated",
            "count": len(sentence_candidates),
            "top_directness": sentence_candidates[0].get("sentence_directness") if sentence_candidates else "",
            "top_utility_label": sentence_candidates[0].get("sentence_utility_label") if sentence_candidates else "",
            "top_sentence": compact_claim_text(str(sentence_candidates[0].get("sentence") or ""), 140) if sentence_candidates else "",
        }
    )
    events.append(
        {
            "event": "page_retained",
            "coverage_level": coverage.get("coverage_level") or "",
            "coverage_reason": coverage.get("coverage_reason") or "",
            "web_evidence_count": coverage.get("web_evidence_count") or 0,
            "direct_evidence_count": coverage.get("direct_evidence_count") or 0,
            "partial_evidence_count": coverage.get("partial_evidence_count") or 0,
        }
    )
    events.append(
        {
            "event": "point_conversion",
            "stage": point_conversion.get("stage") or "",
            "reason": point_conversion.get("reason") or "",
            "block_reason": point_conversion.get("block_reason") or "",
            "candidate_sentence_count": point_conversion.get("candidate_sentence_count") or 0,
            "direct_count": point_conversion.get("direct_count") or 0,
            "partial_count": point_conversion.get("partial_count") or 0,
            "related_only_count": point_conversion.get("related_only_count") or 0,
            "support_refute_count": point_conversion.get("support_refute_count") or 0,
            "direct_support_refute_count": point_conversion.get("direct_support_refute_count") or 0,
        }
    )
    if direct_refuting:
        events.append(
            {
                "event": "evidence_refutation",
                "count": len(direct_refuting),
                "points": [compact_evidence_point_event(point) for point in direct_refuting[:2]],
            }
        )
    elif direct_supporting:
        events.append(
            {
                "event": "evidence_support",
                "count": len(direct_supporting),
                "points": [compact_evidence_point_event(point) for point in direct_supporting[:2]],
            }
        )
    elif direct_uncertain:
        events.append(
            {
                "event": "evidence_uncertain",
                "count": len(direct_uncertain),
                "points": [compact_evidence_point_event(point) for point in direct_uncertain[:2]],
            }
        )
    else:
        events.append(
            {
                "event": "evidence_gap",
                "count": len(uncertain_points),
                "points": [compact_evidence_point_event(point) for point in uncertain_points[:2]],
            }
        )
    return {
        "events": events,
        "has_direct_refutation": bool(direct_refuting),
        "has_direct_support": bool(direct_supporting),
        "has_direct_uncertain": bool(direct_uncertain),
    }


def compact_claim_text(text: str, limit: int = 56) -> str:
    text = normalize_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip(" ;,.") + "..."


def point_value_text(point: Dict[str, Any]) -> str:
    claim_value = normalize_text(str(point.get("claim_value") or ""))
    evidence_value = normalize_text(str(point.get("evidence_value") or ""))
    evidence_sentence = normalize_text(str(point.get("evidence_sentence") or ""))
    if claim_value and evidence_value and claim_value != evidence_value:
        return f"claim says {compact_claim_text(claim_value, 28)}; evidence shows {compact_claim_text(evidence_value, 36)}"
    if evidence_value:
        return f"evidence shows {compact_claim_text(evidence_value, 42)}"
    if evidence_sentence:
        return f"evidence sentence: {compact_claim_text(evidence_sentence, 48)}"
    return ""


def route_gap_text(summary: Dict[str, Any], coverage: Dict[str, Any]) -> str:
    reason = str(coverage.get("coverage_reason") or "")
    web_count = int(coverage.get("web_evidence_count") or 0)
    direct_count = int(coverage.get("direct_evidence_count") or 0)
    uncertain_count = len(summary.get("uncertain_points") or [])
    candidates = [item for item in summary.get("candidate_sentences") or [] if isinstance(item, dict)]
    if direct_count == 0 and candidates:
        best = normalize_text(str(candidates[0].get("sentence") or ""))
        if best:
            return f"索到跺相关候句“{best[:90]}”，但它没有同时形成足的核心实体与跺关系直接反证"
    if reason == "no_web_evidence" or web_count == 0:
        return "没有索到叔网页证据"
    if direct_count == 0 and uncertain_count:
        return "retrieved route-related material, but no single sentence directly answers the route relation"
    if direct_count == 0:
        return "索到相关材料，但缺少直接跺关系证据"
    return "跺证据较薄，仍更强直接材料"


def build_reason_hint(claim: str, mode: str, summary: Dict[str, Any], coverage: Dict[str, Any]) -> Dict[str, str]:
    claim_text = compact_claim_text(claim)
    refuting = [point for point in summary.get("refuting_points") or [] if isinstance(point, dict)]
    supporting = [point for point in summary.get("supporting_points") or [] if isinstance(point, dict)]
    refuting_direct = [point for point in refuting if point.get("direct_answer") == "direct"]
    supporting_direct = [point for point in supporting if point.get("direct_answer") == "direct"]
    if refuting_direct:
        detail = point_value_text(refuting_direct[0]) or "存在直接反证"
        return {
            "status": "refuted",
            "text": f"answer says {claim_text}; {detail}; therefore the claim is refuted",
        }
    if supporting_direct:
        detail = point_value_text(supporting_direct[0]) or "存在直接攌证据"
        return {
            "status": "supported",
            "text": f"answer says {claim_text}; {detail}; therefore the claim is supported",
        }
    if mode == "route_fact":
        gap = route_gap_text(summary, coverage)
    else:
        web_count = int(coverage.get("web_evidence_count") or 0)
        direct_count = int(coverage.get("direct_evidence_count") or 0)
        if web_count == 0:
            gap = "没有索到叔网页证据"
        elif direct_count == 0:
            gap = "索到相关材料，但没有直接攌或反驳 claim"
        else:
            gap = "证据不足以形成稳定支持或反驳"
    return {
        "status": "uncertain",
        "text": f"answer says {claim_text}; {gap}; this is not enough to mark the claim false",
    }


def build_reason_hint_v2(claim: str, mode: str, summary: Dict[str, Any], coverage: Dict[str, Any]) -> Dict[str, str]:
    claim_text = compact_claim_text(claim)
    mechanism_type = str(summary.get("mechanism_type") or coverage.get("mechanism_type") or "")
    refuting = [point for point in summary.get("refuting_points") or [] if isinstance(point, dict)]
    supporting = [point for point in summary.get("supporting_points") or [] if isinstance(point, dict)]
    refuting_direct = [point for point in refuting if point.get("direct_answer") == "direct"]
    supporting_direct = [point for point in supporting if point.get("direct_answer") == "direct"]
    if refuting_direct:
        detail = point_value_text(refuting_direct[0]) or "direct refuting evidence exists"
        return {
            "status": "refuted",
            "text": f"answer says {claim_text}; {detail}; therefore the claim is refuted",
        }
    if supporting_direct:
        detail = point_value_text(supporting_direct[0]) or "direct supporting evidence exists"
        return {
            "status": "supported",
            "text": f"answer says {claim_text}; {detail}; therefore the claim is supported",
        }
    if mode == "route_fact" or mechanism_type == "relation_sentence":
        gap = route_gap_text(summary, coverage)
    else:
        web_count = int(coverage.get("web_evidence_count") or 0)
        direct_count = int(coverage.get("direct_evidence_count") or 0)
        if web_count == 0:
            gap = "no usable web evidence was retrieved"
        elif direct_count == 0:
            if mechanism_type == "structured_numeric_authority":
                gap = "retrieved related pages, but no directly usable value aligned on entity, date or unit"
            elif mechanism_type == "date_authority":
                gap = "retrieved related pages, but no directly usable date or schedule statement aligned to the claim"
            elif mechanism_type == "event_result_page":
                gap = "retrieved related result pages, but no direct result sentence that can clearly support or refute the claim"
            elif mechanism_type == "current_status_update":
                gap = "retrieved related status pages, but no direct status statement aligned to the claim target"
            else:
                gap = "retrieved related material, but no direct support or refutation of the claim"
        else:
            if mechanism_type == "structured_numeric_authority":
                gap = "evidence remains too weak to form a stable value-level judgment"
            elif mechanism_type == "date_authority":
                gap = "evidence remains too weak to form a stable date-level judgment"
            else:
                gap = "evidence remains too weak to form a stable support/refute judgment"
    return {
        "status": "uncertain",
        "text": f"answer says {claim_text}; {gap}; this is not enough to mark the claim false",
    }


def summarize_claim_evidence(claims: List[Dict[str, Any]], evidence_by_claim: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    summaries: Dict[str, Dict[str, Any]] = {}
    coverage: Dict[str, Dict[str, Any]] = {}
    numeric_evidence_pool: List[Dict[str, Any]] = []
    for claim_item in claims:
        claim_id = str(claim_item.get("claim_id") or claim_item.get("id") or "")
        source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
        if summary_mode_from_intent(source_intent) != EVIDENCE_MODE_NUMERIC:
            continue
        for item in evidence_by_claim.get(claim_id) or []:
            if item.get("source_type") not in {"input_context", "computed"}:
                numeric_evidence_pool.append(item)
    for claim_item in claims:
        claim_id = str(claim_item.get("claim_id") or claim_item.get("id") or "")
        claim_text = normalize_text(str(claim_item.get("claim") or ""))
        evidence = evidence_by_claim.get(claim_id) or []
        source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
        evidence_need_program = claim_item.get("evidence_need_program") if isinstance(claim_item.get("evidence_need_program"), dict) else {}
        mechanism_type = mechanism_type_from_intent(source_intent)
        mode = summary_mode_from_intent(source_intent)
        if mode == "numeric_fact":
            own_web = [item for item in evidence if item.get("source_type") not in {"input_context", "computed"}]
            if not own_web and numeric_evidence_pool:
                evidence = evidence + numeric_evidence_pool
            summaries[claim_id] = summarize_numeric_claim(claim_id, claim_text, evidence)
        elif mode == "date_fact" or mode == "schedule_fact":
            summaries[claim_id] = summarize_date_claim(claim_id, claim_text, evidence, source_intent)
        elif mode == "event_result":
            summaries[claim_id] = summarize_event_claim(claim_id, claim_text, evidence)
        elif mode == "entity_fact":
            summaries[claim_id] = summarize_entity_claim(claim_id, claim_text, evidence)
        elif mode == "route_fact":
            summaries[claim_id] = summarize_route_claim(claim_id, claim_text, evidence)
        else:
            summaries[claim_id] = {
                "claim_id": claim_id,
                "claim": claim_text,
                "evidence_mode": mode,
                "supporting_points": [],
                "refuting_points": [],
                "uncertain_points": [],
                "evidence_sentence_candidates": collect_evidence_sentence_candidates(evidence, claim_text, limit=6),
            }
        summaries[claim_id]["mechanism_type"] = mechanism_type
        if evidence_need_program:
            summaries[claim_id]["evidence_need_program"] = evidence_need_program
        coverage[claim_id] = claim_coverage(claim_id, mode, evidence, summaries[claim_id])
        coverage[claim_id]["mechanism_type"] = mechanism_type
        summaries[claim_id]["coverage"] = coverage[claim_id]
        summaries[claim_id]["point_conversion"] = point_conversion_diagnostics(summaries[claim_id], coverage[claim_id])
        summaries[claim_id]["point_conversion"]["block_reason"] = infer_point_conversion_block_reason(
            summaries[claim_id],
            summaries[claim_id]["point_conversion"],
        )
        summaries[claim_id]["point_conversion"]["block_layer"] = point_conversion_block_layer(
            summaries[claim_id]["point_conversion"]
        )
        summaries[claim_id]["evidence_events"] = evidence_event_summary(summaries[claim_id], coverage[claim_id])
        summaries[claim_id]["reason_hint"] = build_reason_hint_v2(claim_text, mode, summaries[claim_id], coverage[claim_id])
    return {"claim_summaries": summaries, "claim_coverage": coverage}


# v3.3 evidence-first overrides
# Keep these definitions at the end so they replace earlier legacy helpers at runtime.
# They are type-level mechanisms: numeric/date/route extraction, not sample keyword stacking.

_ZH_MULTIPLIERS = {
    "?": 10_000,
    "百万": 1_000_000,
    "千万": 10_000_000,
    "?": 100_000_000,
}

_EN_MULTIPLIERS = {
    "million": 1_000_000,
    "billion": 1_000_000_000,
    "trillion": 1_000_000_000_000,
}


def split_sentences(text: str) -> List[str]:
    return [
        normalize_text(part)
        for part in re.split(r"(?<=[。！???])\s*|(?<=\.)\s+", text or "")
        if normalize_text(part)
    ]


def numeric_unit_category(raw: str) -> str:
    lower = (raw or "").lower()
    if "%" in lower:
        return "percent"
    if any(token in lower for token in ["瑞典克朗", "克朗", "swedish kronor", "kronor", "sek"]):
        return "money_sek"
    if any(token in lower for token in ["美元", "usd", "dollar"]):
        return "money_usd"
    if any(token in lower for token in ["人民币", "港元", "欧元", "cny"]):
        return "money_cny"
    if any(token in lower for token in ["瑞典克朗", "克朗", "swedish kronor", "kronor", "sek"]):
        return "money_sek"
    if any(token in lower for token in ["美元", "usd", "dollar"]):
        return "money_usd"
    if any(token in lower for token in ["???", "??", "??", "?", "cny"]):
        return "money_cny"
    if any(token in lower for token in ["??", "??", "??", "??", "km", "mile"]):
        return "distance"
    if any(token in lower for token in ["分钟", "小时", "minute", "hour"]):
        return "time"
    if any(token in lower for token in ["?", "?"]):
        return "quantity"
    if any(token in lower for token in ["million", "billion", "trillion", "?", "?", "??", "??"]):
        return "amount"
    if re.fullmatch(r"(?:19|20)\d{2}", lower):
        return "year"
    return "number"


def extract_numbers(text: str) -> List[Tuple[str, str]]:
    patterns = [
        r"(?:swedish kronor\s*)?\(?\s*(?:sek|swedish kronor|kronor)\s*\)?\s*\d+(?:\.\d+)?\s*(?:million|billion|trillion)?",
        r"\d+(?:\.\d+)?\s*(?:million|billion|trillion)\s*(?:swedish kronor|kronor|sek|usd|dollars?)?",
        r"(?:瑞典克朗|克朗|美元|人民币|港元|欧元|元)\s*\d+(?:\.\d+)?\s*(?:万|亿|百万|千万)?",
        r"\d+(?:\.\d+)?\s*(?:万|亿|百万|千万)?\s*(?:瑞典克朗|克朗|美元|人民币|港元|欧元|元)",
        r"\d+(?:\.\d+)?\s*(?:公里|千米|海里|英里|分钟|小时|吨|升)",
        r"\d+(?:\.\d+)?\s*%",
        r"(?:19|20)\d{2}",
        r"\d+(?:\.\d+)?",
    ]
    values: List[Tuple[str, str]] = []
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text or "", flags=re.I):
            raw = normalize_text(match.group(0))
            if not raw or raw in seen:
                continue
            seen.add(raw)
            values.append((raw, numeric_unit_category(raw)))
    return values


def numeric_value(raw: str) -> Optional[float]:
    match = re.search(r"\d+(?:\.\d+)?", raw or "")
    if not match:
        return None
    value = float(match.group(0))
    lower = (raw or "").lower()
    for token, multiplier in sorted(_ZH_MULTIPLIERS.items(), key=lambda pair: len(pair[0]), reverse=True):
        if token in lower:
            return value * multiplier
    for token, multiplier in _EN_MULTIPLIERS.items():
        if token in lower:
            return value * multiplier
    return value


def extract_dates(text: str) -> List[str]:
    patterns = [
        r"\b(?:19|20)\d{2}-\d{1,2}-\d{1,2}\b",
        r"(?:19|20)\d{2}年\d{1,2}月\d{1,2}日?",
        r"\d{1,2}月\d{1,2}日?(?:[：:]\d{1,2}时)?",
        r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+(?:19|20)\d{2}",
        r"\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(?:19|20)\d{2}",
        r"\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b",
        r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}\b",
    ]
    out: List[str] = []
    for pattern in patterns:
        out.extend(normalize_text(match.group(0)) for match in re.finditer(pattern, text or "", flags=re.I))
    return list(dict.fromkeys(out))


def normalize_date_value(value: str) -> str:
    value = normalize_text(value).lower()
    month_map = {
        "jan": "01", "january": "01",
        "feb": "02", "february": "02",
        "mar": "03", "march": "03",
        "apr": "04", "april": "04",
        "may": "05",
        "jun": "06", "june": "06",
        "jul": "07", "july": "07",
        "aug": "08", "august": "08",
        "sep": "09", "sept": "09", "september": "09",
        "oct": "10", "october": "10",
        "nov": "11", "november": "11",
        "dec": "12", "december": "12",
    }
    match = re.search(r"\b((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})\b", value)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"((?:19|20)\d{2})年(\d{1,2})月(\d{1,2})日?", value)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"(\d{1,2})月(\d{1,2})日?", value)
    if match:
        return f"{int(match.group(1)):02d}-{int(match.group(2)):02d}"
    match = re.search(r"([a-z]+)\s+(\d{1,2}),?\s+((?:19|20)\d{2})", value)
    if match and match.group(1) in month_map:
        return f"{match.group(3)}-{month_map[match.group(1)]}-{int(match.group(2)):02d}"
    match = re.search(r"(\d{1,2})\s+([a-z]+)\s+((?:19|20)\d{2})", value)
    if match and match.group(2) in month_map:
        return f"{match.group(3)}-{month_map[match.group(2)]}-{int(match.group(1)):02d}"
    match = re.search(r"(\d{1,2})\s+([a-z]+)", value)
    if match and match.group(2) in month_map:
        return f"{month_map[match.group(2)]}-{int(match.group(1)):02d}"
    match = re.search(r"([a-z]+)\s+(\d{1,2})", value)
    if match and match.group(1) in month_map:
        return f"{month_map[match.group(1)]}-{int(match.group(2)):02d}"
    return value


def date_values_match(claim_value: str, evidence_value: str) -> bool:
    claim_normalized = normalize_date_value(claim_value)
    evidence_normalized = normalize_date_value(evidence_value)
    if not claim_normalized or not evidence_normalized:
        return False
    if claim_normalized == evidence_normalized:
        return True
    full_date = re.compile(r"^(?:19|20)\d{2}-\d{2}-\d{2}$")
    month_day = re.compile(r"^\d{2}-\d{2}$")
    if full_date.match(claim_normalized) and month_day.match(evidence_normalized):
        return claim_normalized[5:] == evidence_normalized
    if full_date.match(evidence_normalized) and month_day.match(claim_normalized):
        return evidence_normalized[5:] == claim_normalized
    return False


def numeric_sentence_score(sentence: str, claim: str) -> int:
    lower = sentence.lower()
    claim_lower = claim.lower()
    score = 0
    for entity in claim_entities(claim):
        if entity_matches_text(entity, lower):
            score += 2
    for year in re.findall(r"\b(?:19|20)\d{2}\b", claim_lower):
        if year in lower:
            score += 3
    if any(unit in claim_lower and unit in lower for unit in ["%", "????", "??", "?", "??", "sek", "kronor", "??", "??"]):
        score += 3
    if any(token in lower for token in ["amount", "price", "prize money", "set at", "announced", "confirmed", "per prize", "per category", "full nobel prize", "官方", "典", "调整", "奖金"]):
        score += 2
    if any(token in lower for token in ["original amount", "estate", "market value", "invested capital", "1901", "1895"]):
        score -= 4
    if any(token in lower for token in ["raised by", "increase of", "increased by"]) and not any(token in claim_lower for token in ["增加", "上调", "提高", "raised", "increase"]):
        score -= 3
    return score


def _best_numeric_sentence(text: str, values: List[Tuple[str, str]], claim: str) -> Tuple[str, str]:
    best_value = values[0][0] if values else ""
    best_sentence = sentence_for_value(text, best_value)
    best_score = -999
    for value, _unit in values:
        sentence = sentence_for_value(text, value)
        score = numeric_sentence_score(sentence, claim)
        if score > best_score:
            best_score = score
            best_value = value
            best_sentence = sentence
    return best_value, best_sentence


def numeric_unit_signature(raw: str) -> str:
    lower = normalize_text(raw).lower()
    unit_patterns = [
        ("money_cny_per_ton", r"(?:\u5143|cny)\s*/\s*(?:\u5428|ton(?:ne)?)"),
        ("money_cny_per_liter", r"(?:\u5143|cny)\s*/\s*(?:\u5347|l(?:iter|itre)?)"),
        ("percent", r"%"),
        ("money_sek", r"瑞典克朗|克朗|swedish kronor|kronor|sek"),
        ("money_usd", r"美元|usd|dollars?"),
        ("money_cny", r"(?:\u4eba\u6c11\u5e01|\u6e2f\u5143|\u6b27\u5143|\u5143|cny)"),
        ("distance", r"兇|千米|海里|英里|km|mile"),
        ("time", r"分钟|小时|minute|hour"),
        ("quantity_ton", r"(?:\u5428|ton(?:ne)?)"),
        ("quantity_liter", r"(?:\u5347|l(?:iter|itre)?)"),
    ]
    for label, pattern in unit_patterns:
        if re.search(pattern, lower, flags=re.I):
            return label
    if re.search(r"\b(?:19|20)\d{2}\b", lower):
        return "year"
    return numeric_unit_category(raw)


def numeric_family(signature: str) -> str:
    if signature.startswith("money_"):
        return "money"
    if signature.startswith("quantity_"):
        return "quantity"
    return signature


def numeric_context_terms(text: str, value: str) -> List[str]:
    sentence = sentence_for_value(text, value)
    sentence_lower = sentence.lower()
    cleaned = re.sub(r"\d+(?:\.\d+)?", " ", sentence.lower())
    cleaned = re.sub(r"[，！？；?.!?;:（）()\"“\-?]", " ", cleaned)
    stop_terms = {
        "??", "??", "??", "??", "??", "??", "??", "??",
        "the", "and", "for", "with", "from", "that", "this", "was", "were", "will",
        "million", "billion", "trillion", "sek", "usd", "kronor", "dollars",
        "?", "?", "?", "?", "??", "????", "??", "??", "???",
    }
    terms: List[str] = []
    semantic_markers = [
        ("prize_amount", ["??", "prize amount", "prize money", "full nobel prize", "per prize"]),
        ("score_result", ["比分", "得分", "score", "points", "defeated", "beat"]),
        ("exchange_rate", ["汇率", "牌价", "exchange rate", "currency", "forex"]),
        ("distance_position", ["距", "兇", "千米", "海里", "position", "distance", "located"]),
        ("retail_price", ["??", "??", "??", "retail", "per litre", "per liter"]),
        ("per_ton_adjustment", ["??", "??", "per tonne", "per ton"]),
    ]
    semantic_markers.extend(
        [
            ("prize_amount", ["奖金", "奖金额", "奖金金额"]),
            ("score_result", ["比分", "得分"]),
            ("exchange_rate", ["汇率", "牌价"]),
            ("distance_position", ["距离", "位置", "公里", "千米", "海里"]),
            ("retail_price", ["油价", "售价"]),
            ("per_ton_adjustment", ["每吨"]),
        ]
    )
    for marker, keywords in semantic_markers:
        if any(keyword in sentence_lower for keyword in keywords):
            terms.append(marker)
    for token in re.findall(r"[a-z][a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", cleaned):
        token = normalize_text(token)
        if not token or token in stop_terms:
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", token):
            continue
        terms.append(token)
        if re.search(r"[\u4e00-\u9fff]", token) and len(token) > 2:
            terms.extend(token[index : index + 2] for index in range(0, len(token) - 1))
            terms.extend(token[index : index + 3] for index in range(0, len(token) - 2))
    deduped: List[str] = []
    seen = set()
    for term in terms:
        if term in seen or term in stop_terms:
            continue
        seen.add(term)
        deduped.append(term)
    return deduped[:40]


def numeric_alignment(claim: str, claim_value: str, evidence_sentence: str, evidence_value: str) -> Dict[str, Any]:
    claim_signature = numeric_unit_signature(claim_value)
    evidence_signature = numeric_unit_signature(evidence_value)
    claim_terms = numeric_context_terms(claim, claim_value)
    evidence_terms = numeric_context_terms(evidence_sentence, evidence_value)
    overlap = sorted(set(claim_terms) & set(evidence_terms))
    object_overlap = [term for term in overlap if term not in {"per_ton_adjustment"}]
    unit_exact = claim_signature == evidence_signature
    family_match = numeric_family(claim_signature) == numeric_family(evidence_signature)
    comparable = unit_exact and (bool(object_overlap) or len(claim_terms) <= 1)
    mismatch_reasons: List[str] = []
    if not unit_exact:
        mismatch_reasons.append("unit_signature_mismatch")
    elif not object_overlap and len(claim_terms) > 1:
        mismatch_reasons.append("object_phrase_mismatch")
    if not family_match:
        mismatch_reasons.append("numeric_family_mismatch")
    return {
        "family": numeric_family(claim_signature),
        "claim_unit_signature": claim_signature,
        "evidence_unit_signature": evidence_signature,
        "claim_object_terms": claim_terms[:12],
        "evidence_object_terms": evidence_terms[:12],
        "object_overlap": object_overlap[:8],
        "comparable": comparable,
        "mismatch_reason": ",".join(mismatch_reasons),
    }


def summarize_numeric_claim(claim_id: str, claim: str, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    claim_numbers = extract_numbers(claim)
    supporting_points: List[Dict[str, Any]] = []
    refuting_points: List[Dict[str, Any]] = []
    uncertain_points: List[Dict[str, Any]] = []
    for item in evidence:
        if not should_summarize_item(item):
            continue
        text = evidence_text(item)
        if not str(item.get("detail") or "").strip() and re.fullmatch(r"\s*sitemap match score=\d+\s*", str(item.get("snippet") or ""), flags=re.I):
            continue
        values = extract_numbers(text)
        if not values:
            continue
        best_candidate = best_mode_answer_candidate(item, claim, EVIDENCE_MODE_NUMERIC, limit=5)
        if not claim_numbers:
            if best_candidate:
                sentence = normalize_text(str(best_candidate.get("sentence") or ""))
                sentence_values = extract_numbers(sentence)
                evidence_value = choose_numeric_value(sentence, sentence_values, claim) if sentence_values else ""
            else:
                evidence_value, sentence = _best_numeric_sentence(text, values, claim)
            point = apply_candidate_features_to_point(point_with_source(
                item,
                {"type": "numeric_reference", "claim_value": "", "evidence_value": evidence_value, "evidence_sentence": sentence},
                required_hits=1,
            ), best_candidate)
            uncertain_points.append(point)
            continue
        claim_value, claim_unit = pick_claim_number(claim_numbers)
        structured_contract = structured_best_point_contract(item)
        structured_status = normalize_text(str(structured_contract.get("status") or "")).lower()
        structured_value, structured_sentence, _structured_time = structured_best_point_evidence(item)
        if structured_status == "satisfied" and structured_value:
            alignment = numeric_alignment(claim, claim_value, structured_sentence or structured_value, structured_value)
            point = point_with_source(
                item,
                {
                    "type": "numeric_match",
                    "claim_value": claim_value,
                    "evidence_value": structured_value,
                    "evidence_sentence": structured_sentence or structured_value,
                    "numeric_alignment": alignment,
                    "structured_point_used": True,
                },
                required_hits=1,
            )
            point["point_contract_status"] = "satisfied"
            point["point_contract_risks"] = list(structured_contract.get("risks", []) or [])
            point["direct_answer"] = "direct"
            if numeric_point_lacks_time_scope_binding(claim, structured_sentence or structured_value, item, structured_value):
                point["type"] = "numeric_reference"
                point["numeric_contract_note"] = "time_scope_mismatch"
                uncertain_points.append(point)
                continue
            if not alignment.get("comparable"):
                point["type"] = "numeric_reference"
                point["numeric_contract_note"] = "structured_point_not_comparable"
                uncertain_points.append(point)
                continue
            exact_match = numeric_match_for_claim(claim, structured_value, claim_value)
            point["type"] = "numeric_match" if exact_match else "numeric_mismatch"
            if exact_match:
                supporting_points.append(point)
            else:
                refuting_points.append(point)
            continue
        same_unit_values = [(value, unit) for value, unit in values if unit == claim_unit and unit != "year"]
        if not same_unit_values and claim_unit == "amount":
            same_unit_values = [(value, unit) for value, unit in values if unit not in {"year", "number"}]
        if not same_unit_values:
            continue
        if best_candidate:
            sentence = normalize_text(str(best_candidate.get("sentence") or ""))
            sentence_values = extract_numbers(sentence)
            sentence_same_unit_values = [(value, unit) for value, unit in sentence_values if unit == claim_unit and unit != "year"]
            if not sentence_same_unit_values and claim_unit == "amount":
                sentence_same_unit_values = [(value, unit) for value, unit in sentence_values if unit not in {"year", "number"}]
            if sentence_same_unit_values:
                evidence_value = choose_numeric_value(sentence, sentence_same_unit_values, claim)
            else:
                evidence_value, sentence = _best_numeric_sentence(text, same_unit_values, claim)
        else:
            evidence_value, sentence = _best_numeric_sentence(text, same_unit_values, claim)
        alignment = numeric_alignment(claim, claim_value, sentence, evidence_value)
        if not alignment["comparable"]:
            uncertain_points.append(
                apply_candidate_features_to_point(
                    point_with_source(
                        item,
                        {
                            "type": "numeric_reference",
                            "claim_value": claim_value,
                            "evidence_value": evidence_value,
                            "evidence_sentence": sentence,
                            "numeric_alignment": alignment,
                        },
                        required_hits=1,
                    ),
                    best_candidate,
                )
            )
            continue
        exact_match = any(numeric_match_for_claim(claim, value, claim_value) for value, _unit in same_unit_values)
        point = apply_candidate_features_to_point(point_with_source(
            item,
            {
                "type": "numeric_match" if exact_match else "numeric_mismatch",
                "claim_value": claim_value,
                "evidence_value": evidence_value,
                "evidence_sentence": sentence,
                "numeric_alignment": alignment,
            },
            required_hits=1,
        ), best_candidate)
        if item.get("source_type") in {"official", "news", "encyclopedia"} and numeric_sentence_score(sentence, claim) >= 3:
            point["direct_answer"] = "direct"
        blocking_risks = item_structured_point_blocking_risks(item)
        if blocking_risks:
            point["type"] = "numeric_reference"
            point["point_contract_blocking_risks"] = blocking_risks
            uncertain_points.append(point)
        elif numeric_point_lacks_time_scope_binding(claim, sentence, item, evidence_value):
            point["type"] = "numeric_reference"
            point["numeric_contract_note"] = "time_scope_mismatch"
            uncertain_points.append(point)
        elif exact_match:
            supporting_points.append(point)
        else:
            refuting_points.append(point)
    return {
        "claim_id": claim_id,
        "claim": claim,
        "evidence_mode": "numeric_fact",
        "supporting_points": unique_points(supporting_points)[:3],
        "refuting_points": unique_points(refuting_points)[:3],
        "uncertain_points": unique_points(uncertain_points)[:3],
        "evidence_sentence_candidates": collect_evidence_sentence_candidates(evidence, claim, mode="numeric_fact", limit=6),
    }

# ROUTE_RUNTIME_OVERRIDE_ANCHOR


def _route_runtime_marker_present(text: str, marker: str) -> bool:
    marker = marker.strip()
    if not marker:
        return False
    if marker == "经过":
        if re.search(r"经过\s*(?:\d+|[一二三四五六七八九十百半两]+)\s*(?:个)?\s*(?:小时|分钟|天|日|月|年)", text):
            return False
        return "经过" in text
    if re.search(r"[A-Za-z]", marker):
        pattern = r"(?<![A-Za-z])" + re.escape(marker.lower()) + r"(?![A-Za-z])"
        return bool(re.search(pattern, text.lower()))
    return marker in text




def _route_runtime_object_marker_present(text: str) -> bool:
    return any(_route_runtime_marker_present(text, marker) for marker in ROUTE_STRICT_OBJECT_MARKERS)


def _route_runtime_directional_relation_present(text: str) -> bool:
    lower = text.lower()
    directional_markers = [
        "toward", "towards", "headed to", "bound for", "entered", "enter", "reached",
        "?", "?", "?", "?", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??",
    ]
    if any(_route_runtime_marker_present(text, marker) for marker in directional_markers):
        return True
    if not _route_runtime_object_marker_present(text):
        return False
    return bool(
        re.search(
            r"(?:向|朝||赴|前往|飞向|驶向|进入|到达|抵达|直达|运往|射向|指向)\s*[^。！?.]{0,20}(?:[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{1,})",
            text,
        )
        or re.search(r"\b(?:toward|towards|headed to|bound for|entered|enter|reached)\b", lower)
    )


def _route_runtime_transit_relation_present(text: str) -> bool:
    transit_markers = [
        "airspace", "route", "via", "through", "transit", "cross", "crossed", "corridor",
        "flight path", "trajectory", "overfly", "overflight", "flew over", "passed through",
        "entered", "enter", "reached",
        "??", "??", "??", "??", "??", "??", "??", "??", "??", "??",
    ]
    lower = text.lower()
    if any(_route_runtime_marker_present(text, marker) for marker in transit_markers):
        return True
    return bool(
        re.search(r"\b(?:pass(?:ed)? through|flew over|overf(?:ly|light)|cross(?:ed)?|enter(?:ed)?|reach(?:ed)?|via|through|transit)\b", lower)
        or re.search(r"(?:经过|经由|通过|穿越|飞越|进入|到达|抵达)\s*[^。！?.]{0,20}(?:领空|空域|地区|东部|西部|南部|北部)", text)
    )


ROUTE_CLAIM_GENERIC_STOPWORDS = {
    "answer", "question", "claim", "user", "route", "airspace", "analysis", "map",
    "事实", "回答", "问题", "是否", "需要", "不需要", "直接", "影响", "没有", "可能", "说明",
    "主要", "最终", "实际", "另一", "其中", "相关", "情况", "原因", "结果",
    "领空", "空域", "路线", "通道", "飞行", "飞行路线", "路径", "轨迹", "过境",
    "东部", "西部", "南部", "北部", "中部",
}
ROUTE_CLAIM_EDGE_CHARS = set("的了是和或与在为从到向往把将及并中内外上下前后对就再又还也而")


ROUTE_CLAIM_BOUNDARY_PATTERN = re.compile(
    r"(?:是否|不需要|需要|没有|以及|或者|并且|其中|主要|最终|实际|另一|之一|的是|经由|经过|通过|穿过|进入|抵达|到达|前往|飞向|驶向|从|向|往|然后|之后|再到|再向|再往|时)"
)

ROUTE_CLAIM_ANCHOR_PATTERN = re.compile(
    r"(?:经由|经过|通过|穿过)"
    r"([\u4e00-\u9fff]{2,16}?)(?=的|或|和|并|到|向|时|，|。|；|$)"
)

ROUTE_CLAIM_LOCATION_SUFFIX_PATTERN = re.compile(
    r"(?:^|经由|经过|通过|穿过|进入|抵达|到达|前往|飞向|驶向)"
    r"([\u4e00-\u9fff]{2,12}(?:领空|空域|波斯湾|海峡|半岛|高原|地区|地带|东部|西部|南部|北部|中部))"
)

ROUTE_CLAIM_OBJECT_OWNER_PATTERN = re.compile(
    r"([\u4e00-\u9fff]{2,8})(?=(?:导弹|无人机|火箭弹|弹道))"
)

ROUTE_CLAIM_TARGET_PATTERN = re.compile(
    r"(?:打击|攻击|被击|进入|抵达|到达|飞向|前往|驶向)"
    r"([\u4e00-\u9fff]{2,12}?)(?=的|时|，|。|和|并|$)"
)

ROUTE_CLAIM_ANCHOR_SPLIT_PATTERN = re.compile(r"[和或及与、/]")

ROUTE_CLAIM_LOCATION_SUFFIXES = (
    "领空", "空域", "波斯湾", "海峡", "半岛", "高原", "地区", "地带",
    "东部", "西部", "南部", "北部", "中部",
)


def _trim_route_claim_chunk(chunk: str) -> str:
    text = normalize_text(chunk)
    while len(text) >= 2 and text[:2] in {"??", "??"}:
        text = text[2:]
    while len(text) >= 2 and text[:2] in {"再到", "再向", "再往"}:
        text = text[2:]
    while text and text[0] in ROUTE_CLAIM_EDGE_CHARS:
        text = text[1:]
    while text and text[-1] in ROUTE_CLAIM_EDGE_CHARS:
        text = text[:-1]
    return normalize_text(text)


def _route_claim_chunk_is_noise(chunk: str) -> bool:
    text = _trim_route_claim_chunk(chunk)
    if len(text) < 2:
        return True
    if text.lower() in ROUTE_QUERY_STOPWORDS or text.lower() in ROUTE_CLAIM_GENERIC_STOPWORDS:
        return True
    if text in ROUTE_CLAIM_GENERIC_STOPWORDS:
        return True
    if len(text) <= 16 and ROUTE_CLAIM_BOUNDARY_PATTERN.search(text):
        return True
    if re.fullmatch(r"[二三四五典兹十两]+", text):
        return True
    if len(text) <= 3 and any(char in ROUTE_CLAIM_EDGE_CHARS for char in text):
        return True
    return False


def _append_route_claim_tokens(out: List[str], values: List[str]) -> None:
    for value in values:
        token = _trim_route_claim_chunk(value)
        if _route_claim_chunk_is_noise(token):
            continue
        out.append(token)


def _route_anchor_aliases(anchor: str) -> List[str]:
    cleaned = _trim_route_claim_chunk(anchor)
    if _route_claim_chunk_is_noise(cleaned):
        return []
    aliases = [cleaned]
    for suffix in ROUTE_CLAIM_LOCATION_SUFFIXES:
        if cleaned.endswith(suffix):
            stem = _trim_route_claim_chunk(cleaned[: -len(suffix)])
            if len(stem) >= 2 and not _route_claim_chunk_is_noise(stem):
                aliases.append(stem)
            break
    return dedupe_keep_order(aliases)


def route_claim_anchor_groups(text: str) -> List[List[str]]:
    groups: List[List[str]] = []
    raw_anchors: List[str] = []
    normalized_text = normalize_text(text)
    raw_anchors.extend(ROUTE_CLAIM_ANCHOR_PATTERN.findall(normalized_text))
    raw_anchors.extend(ROUTE_CLAIM_LOCATION_SUFFIX_PATTERN.findall(normalized_text))
    for segment in re.findall(r"[\u4e00-\u9fff]{2,64}", normalized_text):
        raw_anchors.extend(ROUTE_CLAIM_LOCATION_SUFFIX_PATTERN.findall(segment))
    for raw_anchor in raw_anchors:
        for piece in ROUTE_CLAIM_ANCHOR_SPLIT_PATTERN.split(str(raw_anchor or "")):
            aliases = _route_anchor_aliases(piece)
            if aliases:
                groups.append(aliases)
    deduped_groups: List[List[str]] = []
    seen = set()
    for aliases in groups:
        key = tuple(alias.lower() for alias in aliases)
        if key in seen:
            continue
        seen.add(key)
        deduped_groups.append(aliases)
    return deduped_groups


ROUTE_DIRECT_UNCERTAIN_REASON_TEXT = {
    "no_explicit_positive_route_phrase": "sentence lacks an explicit positive transit phrase",
    "direction_without_transit_sequence": "direction exists but transit sequence is still unclear",
    "multi_origin_ambiguity": "multiple origins or locations are mixed into one sentence",
    "alias_only_anchor_match": "only an alias anchor matched, not a full route anchor",
}


def route_claim_tokens(text: str) -> List[str]:
    text = normalize_text(text)
    stop = ROUTE_QUERY_STOPWORDS | {value.lower() for value in ROUTE_CLAIM_GENERIC_STOPWORDS}
    english_terms: List[str] = []
    core_terms: List[str] = []
    anchor_terms: List[str] = []
    chinese_object_markers = [marker for marker in ROUTE_OBJECT_MARKERS if re.search(r"[\u4e00-\u9fff]", marker)]

    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|\d{4}", text):
        normalized = normalize_text(token)
        if normalized and normalized.lower() not in stop:
            english_terms.append(normalized)

    for aliases in route_claim_anchor_groups(text):
        anchor_terms.extend(aliases)

    for segment in re.findall(r"[\u4e00-\u9fff]{2,64}", text):
        normalized_segment = _trim_route_claim_chunk(segment)
        if len(normalized_segment) < 2:
            continue

        _append_route_claim_tokens(core_terms, ROUTE_CLAIM_OBJECT_OWNER_PATTERN.findall(normalized_segment))
        _append_route_claim_tokens(core_terms, ROUTE_CLAIM_TARGET_PATTERN.findall(normalized_segment))

        for marker in chinese_object_markers:
            if marker in normalized_segment:
                _append_route_claim_tokens(core_terms, [marker])

        for part in ROUTE_CLAIM_BOUNDARY_PATTERN.split(normalized_segment):
            cleaned = _trim_route_claim_chunk(part)
            if _route_claim_chunk_is_noise(cleaned):
                continue
            if ROUTE_CLAIM_BOUNDARY_PATTERN.search(cleaned):
                continue
            if len(cleaned) <= 8:
                core_terms.append(cleaned)
            elif len(cleaned) <= 16:
                anchor_terms.append(cleaned)

    ordered = dedupe_keep_order(english_terms + core_terms + anchor_terms)
    return ordered[:32]


def extract_route_sentences(text: str) -> List[str]:
    relation_markers = [
        "airspace", "route", "via", "through", "transit", "cross", "crossed", "corridor",
        "flight path", "trajectory", "overfly", "overflight", "flew over", "passed through",
        "toward", "towards", "headed to", "bound for", "entered", "enter", "reached",
        "bypass", "bypassed", "avoid", "avoided",
        "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??",
    ]
    selected: List[str] = []
    for sentence in split_sentences(text):
        has_relation = any(_route_runtime_marker_present(sentence, marker) for marker in relation_markers)
        has_directional = _route_runtime_directional_relation_present(sentence)
        if has_relation or has_directional:
            selected.append(sentence)
    return selected[:8]


def route_relation_analysis(claim: str, sentence: str) -> Dict[str, Any]:
    relation_markers = [
        "airspace", "route", "via", "through", "transit", "cross", "crossed", "corridor",
        "flight path", "trajectory", "overfly", "overflight", "flew over", "passed through",
        "toward", "towards", "headed to", "bound for", "entered", "enter", "reached",
        "bypass", "bypassed", "avoid", "avoided",
        "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??",
    ]
    negative_markers = [
        "no need", "not need", "without", "avoid", "bypass", "bypassed", "avoided",
        "does not pass", "did not pass", "not through", "without entering",
        "???", "??", "????", "??", "???", "??", "??", "????",
    ]
    positive_markers = [
        "via", "through", "transit", "cross", "crossed", "passed through", "flew over",
        "overfly", "overflight", "flight path", "trajectory",
        "entered", "enter", "reached",
        "经过", "经由", "穿越", "飞越", "进入", "到达", "抵达",
    ]
    lower = sentence.lower()
    tokens = route_claim_tokens(claim)
    token_hits = [token for token in tokens if token.lower() in lower]
    anchor_groups = route_claim_anchor_groups(claim)
    anchor_hits: List[str] = []
    anchor_match_details: List[Dict[str, Any]] = []
    anchor_group_hit_count = 0
    for aliases in anchor_groups:
        canonical = aliases[0] if aliases else ""
        matched_alias = next((alias for alias in aliases if alias.lower() in lower), "")
        if not matched_alias:
            continue
        anchor_group_hit_count += 1
        anchor_hits.append(matched_alias)
        anchor_match_details.append(
            {
                "canonical": canonical,
                "matched": matched_alias,
                "alias_match": bool(canonical and matched_alias and matched_alias != canonical),
            }
        )
        if matched_alias not in token_hits:
            token_hits.append(matched_alias)
    required_anchor_group_hits = 0 if not anchor_groups else 1 if len(anchor_groups) == 1 else 2
    directional_relation = _route_runtime_directional_relation_present(sentence)
    transit_relation = _route_runtime_transit_relation_present(sentence)
    has_relation = any(_route_runtime_marker_present(sentence, marker) for marker in relation_markers) or directional_relation
    claim_negative = any(_route_runtime_marker_present(claim, marker) for marker in negative_markers)
    evidence_negative = any(_route_runtime_marker_present(sentence, marker) for marker in negative_markers)
    evidence_positive = transit_relation or any(_route_runtime_marker_present(sentence, marker) for marker in positive_markers)
    claim_requires_object = _route_runtime_object_marker_present(claim)
    evidence_has_object = _route_runtime_object_marker_present(sentence)
    has_extra_route_anchor = bool(required_anchor_group_hits and anchor_group_hit_count >= required_anchor_group_hits)
    support_slots = route_support_slots(
        sentence=sentence,
        evidence_positive=evidence_positive,
        directional_relation=directional_relation,
        evidence_has_object=evidence_has_object,
        anchor_match_details=anchor_match_details,
        anchor_group_hit_count=anchor_group_hit_count,
        required_anchor_group_hits=required_anchor_group_hits,
    )
    base_directly_answers = bool(
        has_relation
        and len(token_hits) >= 2
        and (evidence_has_object or not claim_requires_object)
        and (not required_anchor_group_hits or has_extra_route_anchor)
    )
    directly_answers = bool(
        base_directly_answers
        and (
            transit_relation
            or (
                directional_relation
                and support_slots.get("anchor_groups_satisfied")
                and not support_slots.get("multi_origin_ambiguity")
                and not support_slots.get("alias_only_anchor_match")
                and int(support_slots.get("full_anchor_match_count") or 0) > 0
            )
        )
    )
    polarity = "uncertain"
    if directly_answers:
        if claim_negative and evidence_positive and not evidence_negative:
            polarity = "conflict"
        elif claim_negative and evidence_negative:
            polarity = "support"
        elif not claim_negative and evidence_negative:
            polarity = "conflict"
        elif not claim_negative and evidence_positive:
            polarity = "support"
    return {
        "directly_answers_route": directly_answers,
        "token_hits": token_hits,
        "token_hit_count": len(token_hits),
        "has_relation_marker": has_relation,
        "has_directional_relation_marker": directional_relation,
        "has_route_object_marker": evidence_has_object,
        "claim_requires_route_object": claim_requires_object,
        "has_extra_route_anchor": has_extra_route_anchor,
        "anchor_hits": anchor_hits,
        "anchor_match_details": anchor_match_details,
        "anchor_hit_count": len(anchor_hits),
        "anchor_group_hit_count": anchor_group_hit_count,
        "required_anchor_group_hits": required_anchor_group_hits,
        "support_slots": support_slots,
        "claim_negative": claim_negative,
        "evidence_negative": evidence_negative,
        "evidence_positive": evidence_positive,
        "polarity": polarity,
    }


