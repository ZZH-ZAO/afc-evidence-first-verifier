from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


CORE = "core"
SUPPORTING = "supporting"
PERIPHERAL = "peripheral"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", "", _text(value).lower())


def _has(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, flags=re.I))


def infer_user_need_slot(question: str, user_need: str, need_type: str) -> Dict[str, Any]:
    """Infer the answer slot the user is actually asking for.

    This is intentionally coarse. It is a calibration feature, not a final label
    decision. The goal is to make "directly answers the user" observable.
    """

    text = _norm(f"{question} {user_need}")
    slots: List[str] = []
    if _has(text, r"(什么时候|何时|哪天|日期|时间|几点|公布|发布|结果.*出|出炉)"):
        slots.append("time_or_release")
    if _has(text, r"(汇率|兑换|兑|买入价|卖出价|中间价|牌价|现汇|现钞)"):
        slots.append("quote_or_metric")
    if _has(text, r"(比分|vs|战胜|谁赢|赛果|结果|退赛|不战而胜)"):
        slots.append("event_result")
    if _has(text, r"(谁|哪位|哪个|哪家|给了谁|授予谁|是谁|获奖者|名单)"):
        slots.append("entity_identity")
    if _has(text, r"(多远|距离|离.*远|位置|在哪|靠近)"):
        slots.append("current_position_distance")
    if _has(text, r"(涨|跌|开盘|收盘|上涨|下跌|贵|便宜|升值|贬值)"):
        slots.append("market_or_price_movement")
    if _has(text, r"(代表什么|意味着什么|说明什么|怎么看|反映什么|原因|为什么)"):
        slots.append("interpretation_or_cause")
    if _has(text, r"(影响|有没有影响|会不会|是否|能不能|要不要|配合|攻打|打击|经过|绕开|领空|通道|路线|唯一)"):
        slots.append("relation_or_policy_status")
    if _has(text, r"(现在|目前|当前|今天|最新|截至)"):
        slots.append("current_time_context")
    need_type_slots = {
        "schedule_time": "time_or_release",
        "financial_quote": "quote_or_metric",
        "sports_result": "event_result",
        "distance_position": "current_position_distance",
        "market_movement": "market_or_price_movement",
        "geopolitical_claim": "relation_or_policy_status",
        "current_geopolitical_status": "relation_or_policy_status",
        "current_result": "event_result",
    }
    mapped = need_type_slots.get(_text(need_type))
    if mapped:
        slots.append(mapped)
    if not slots:
        slots.append(str(need_type or "general_fact"))
    return {
        "question_text": question,
        "user_need": user_need,
        "need_type": need_type,
        "need_slots": list(dict.fromkeys(slots)),
    }


def _claim_mode_target(claim: Dict[str, Any]) -> Tuple[str, str, str]:
    source_intent = _as_dict(claim.get("source_intent"))
    return (
        _text(source_intent.get("evidence_mode")),
        _text(source_intent.get("evidence_target")),
        _text(source_intent.get("risk_type")),
    )


def _program(claim: Dict[str, Any]) -> Dict[str, Any]:
    return _as_dict(claim.get("evidence_need_program"))


def _structured_detail_without_user_slot(claim_text: str, mode: str, target: str, risk_type: str, slots: List[str]) -> bool:
    high_detail = (
        mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result"}
        or target in {"prize_amount", "market_calendar", "position_distance", "match_result", "market_price"}
        or risk_type in {"detail_numeric", "detail_date"}
        or bool(re.search(r"(奖金|金额|比分|距离|公里|千米|海里|克朗|美元|人民币|买入价|卖出价|中间价|牌价|现汇|现钞|%|百分比)", claim_text))
    )
    if not high_detail:
        return False
    if "quote_or_metric" in slots and (mode == "numeric_fact" or target in {"market_price"}):
        return False
    if "time_or_release" in slots and mode in {"date_fact", "schedule_fact"}:
        return False
    if "event_result" in slots and (mode == "event_result" or target == "match_result"):
        return False
    if "current_position_distance" in slots and target == "position_distance":
        return False
    if "market_or_price_movement" in slots and target in {"market_price", "market_calendar"}:
        return False
    return True


def _direct_need_score(claim: Dict[str, Any], slots: List[str]) -> Tuple[int, List[str]]:
    claim_text = _norm(claim.get("claim"))
    mode, target, risk_type = _claim_mode_target(claim)
    program = _program(claim)
    answer_role = _text(program.get("answer_role_impact"))
    score = 0
    reasons: List[str] = []
    if answer_role == CORE:
        score += 2
        reasons.append("program_marks_core")
    if "time_or_release" in slots:
        if mode in {"date_fact", "schedule_fact"} and _has(claim_text, r"(结果|公布|发布|出|结束|完成|什么时候|何时|时间|日期)"):
            score += 4
            reasons.append("fills_user_time_or_release_slot")
        elif mode in {"date_fact", "schedule_fact"}:
            score += 1
            reasons.append("date_related_but_slot_role_unclear")
    if "quote_or_metric" in slots and (target == "market_price" or _has(claim_text, r"(汇率|买入价|卖出价|中间价|牌价|现汇|现钞|兑)")):
        score += 4
        reasons.append("fills_user_quote_or_metric_slot")
    if "event_result" in slots and (mode == "event_result" or target == "match_result" or _has(claim_text, r"(比分|战胜|获胜|退赛|不战而胜|赛果)")):
        direct_result = _has(claim_text, r"(\d+\s*[-:：]\s*\d+|战胜|击败|获胜|不敌|负于|退赛|弃权|不战而胜|已结束|大胜|惜败)")
        season_or_record_summary = _has(claim_text, r"(本赛季|赛季|常规赛交锋|交锋|交手|总战绩|战绩提升|战绩滑落)")
        if season_or_record_summary and not direct_result:
            score += 1
            reasons.append("event_record_summary_not_direct_user_result")
        else:
            score += 4
            reasons.append("fills_user_event_result_slot")
    if "entity_identity" in slots and (
        mode == "entity_fact"
        or _has(claim_text, r"(授予|获得|获奖|是谁|名单|包括)")
    ):
        score += 4
        reasons.append("fills_user_entity_identity_slot")
    if "current_position_distance" in slots and (target == "position_distance" or _has(claim_text, r"(距离|多远|位置|公里|千米|海里)")):
        score += 4
        reasons.append("fills_user_distance_slot")
    if "market_or_price_movement" in slots and (target in {"market_price", "market_calendar"} or _has(claim_text, r"(涨|跌|开盘|收盘|上涨|下跌|升值|贬值|休市|交易日)")):
        score += 3
        reasons.append("fills_user_market_movement_slot")
    if "interpretation_or_cause" in slots and _has(claim_text, r"(代表|意味着|说明|反映|原因|因为|由于|导致|推动|定价|抢筹|影响)"):
        score += 4
        reasons.append("fills_user_interpretation_slot")
    if "relation_or_policy_status" in slots and (
        mode in {"route_fact", "policy_fact", "entity_fact"}
        or _has(claim_text, r"(影响|配合|打击|攻打|经过|绕开|领空|通道|路线|唯一|政策|状态)")
    ):
        score += 3
        reasons.append("fills_user_relation_or_status_slot")
    if "current_time_context" in slots and _has(claim_text, r"(现在|目前|当前|今天|截至|最新)"):
        score += 1
        reasons.append("matches_current_time_context")
    if _structured_detail_without_user_slot(claim_text, mode, target, risk_type, slots):
        score -= 3
        reasons.append("structured_detail_not_direct_user_slot")
    return score, reasons


def calibrate_claim_centrality(extracted: Dict[str, Any], claims: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    question = _text(extracted.get("_question_text") or extracted.get("question"))
    user_need = _text(extracted.get("user_need"))
    need_type = _text(extracted.get("need_type"))
    need_slot = infer_user_need_slot(question, user_need, need_type)
    slots = [str(slot) for slot in need_slot.get("need_slots") or []]

    scored: List[Tuple[int, int, Dict[str, Any], List[str]]] = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        score, reasons = _direct_need_score(claim, slots)
        centrality = _text(claim.get("centrality")) or SUPPORTING
        if centrality == CORE:
            score += 1
            reasons.append("llm_initial_core")
        scored.append((score, index, claim, reasons))

    direct_answer_rows = [
        (score, index, reasons)
        for score, index, _claim, reasons in scored
        if score >= 3 and any(str(reason).startswith("fills_user_") for reason in reasons)
    ]
    allow_two_core = "interpretation_or_cause" in slots and any(
        slot in slots for slot in ["market_or_price_movement", "quote_or_metric", "event_result", "time_or_release"]
    )
    if "event_result" in slots:
        core_budget = min(3, max(1, len(direct_answer_rows)))
    elif "time_or_release" in slots:
        core_budget = min(2, max(1, len(direct_answer_rows)))
    elif "quote_or_metric" in slots:
        core_budget = min(2, max(1, len(direct_answer_rows)))
    else:
        core_budget = 2 if allow_two_core else 1
    ranked_rows = sorted(scored, key=lambda item: (item[0], -item[1]), reverse=True)
    core_indices = {
        index
        for score, index, _claim, _reasons in ranked_rows[:core_budget]
        if score >= 3
    }

    rows: List[Dict[str, Any]] = []
    calibrated: List[Dict[str, Any]] = []
    for score, index, claim, reasons in scored:
        out = dict(claim)
        original = _text(out.get("centrality")) or SUPPORTING
        new = CORE if index in core_indices else original
        if index not in core_indices and original == CORE and score < 3:
            new = SUPPORTING
            reasons.append("demoted_initial_core_not_direct_user_slot")
        if new not in {CORE, SUPPORTING, PERIPHERAL}:
            new = SUPPORTING
        out["centrality"] = new
        out["centrality_original"] = original
        out["centrality_calibrated"] = new
        out["centrality_calibration"] = {
            "score": score,
            "need_slots": slots,
            "reason": reasons[:6],
            "changed": new != original,
        }
        program = dict(_program(out))
        previous_role = _text(program.get("answer_role_impact"))
        if new == CORE:
            program["answer_role_impact"] = CORE
        elif previous_role == CORE and new != CORE:
            program["answer_role_impact"] = SUPPORTING
        out["evidence_need_program"] = program
        calibrated.append(out)
        rows.append(
            {
                "claim_id": _text(out.get("claim_id") or out.get("id")),
                "claim": _text(out.get("claim"))[:160],
                "original": original,
                "calibrated": new,
                "score": score,
                "reason": reasons[:6],
            }
        )

    debug = {
        "user_need_slot": need_slot,
        "core_budget": core_budget,
        "rows": rows,
    }
    return calibrated, debug
