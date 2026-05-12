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


def _scope_name(scope: str) -> str:
    if scope == "core":
        return "主需"
    if scope == "peripheral":
        return "背景"
    return "次需"


def _risk_name(shape: str) -> str:
    mapping = {
        "absolute_or_resolved_claim": "强绝对或确定化事实表达",
        "phase_boundary_time": "阶段边界或发布时间口径",
        "date_only_conflict_guarded": "只有日期差异、缺少事实绑定",
        "numeric_quote_or_metric": "数值或指标口径",
        "market_calendar_status": "交易日历状态",
        "exclusive_or_only_path": "唯一通道或排他前提",
        "event_result_status": "事件结果状态",
        "current_position_distance": "当前位置或距离口径",
        "reality_vs_fiction_status": "现实状态与虚构内容边界",
    }
    if shape.startswith("phase_graph:"):
        role = shape.split(":", 1)[1]
        role_mapping = {
            "phase_start": "阶段开始",
            "phase_end": "阶段结束",
            "whole_event_end_or_result_release": "整体结束或结果公布",
            "current_status": "当前状态",
        }
        return f"阶段角色：{role_mapping.get(role, role)}"
    return mapping.get(shape, shape)


def _risk_text(shapes: List[Any]) -> str:
    names = [_risk_name(_text(shape)) for shape in shapes if _text(shape)]
    names = list(dict.fromkeys(names))
    if not names:
        return "高风险事实表达"
    return "、".join(names[:4])


def _rank_rows(rows: List[Dict[str, Any]], label: str) -> List[Dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            0 if _text(row.get("label_candidate")) == label else 1,
            0 if _text(row.get("scope")) == "core" else 1,
            {
                "evidence_decide": 0,
                "risk_calibrate": 1,
                "rubric_fallback": 2,
                "insufficient_until_fact_binding": 3,
                "insufficient": 4,
            }.get(_text(row.get("decision_permission")), 5),
        ),
    )


def build_decision_state_reason(
    label: str,
    decision_state_debug: Optional[Dict[str, Any]],
    decision_policy_debug: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a natural-language reason from already computed state.

    This module does not decide labels. It only turns state/policy rows into a
    readable explanation candidate for the final reason selector.
    """

    debug = _as_dict(decision_state_debug)
    policy = _as_dict(decision_policy_debug)
    rows = [row for row in _as_list(debug.get("claim_state_rows")) if isinstance(row, dict)]
    if not rows:
        return ""

    policy_route = _text(policy.get("policy_route"))
    for row in _rank_rows(rows, label):
        scope = _text(row.get("scope"))
        scope_cn = _scope_name(scope)
        evidence_state = _text(row.get("evidence_state"))
        slot_state = _text(row.get("slot_state"))
        permission = _text(row.get("decision_permission"))
        candidate = _text(row.get("label_candidate"))
        risk_shapes = _as_list(row.get("risk_shape"))
        risk_cn = _risk_text(risk_shapes)

        if label == LABEL_2 and permission == "insufficient_until_fact_binding":
            return (
                f"裁决状态显示当前{scope_cn}证据停在“缺少事实绑定”：已有线索主要是日期或页面时间差异，"
                "但还没有同时绑定同一主体、事实关系和时间槽。该线索不能作为同槽反证，"
                "因此不把未闭合证据包装成事实错误。"
            )
        if label == LABEL_2 and permission == "insufficient":
            return (
                f"裁决状态显示当前{scope_cn} claim 仍未形成可裁决证据，"
                "也没有被策略允许的高风险补判形态。因此按证据不足处理，不判定为事实错误。"
            )
        if label == LABEL_2 and evidence_state == "direct_supported":
            return f"裁决状态显示当前{scope_cn} claim 已有直接支持证据，因此不判定为事实错误。"

        if label in {LABEL_0, LABEL_1} and candidate == label:
            if permission == "evidence_decide" and evidence_state == "direct_refuted":
                return f"裁决状态显示当前{scope_cn} claim 已形成同槽直接反证，因此判为{scope_cn}事实错误。"
            if permission in {"risk_calibrate", "rubric_fallback"}:
                route_text = "风险校准" if policy_route == "risk_calibrate" else "受控兜底"
                return (
                    f"本次判断来自{route_text}：当前{scope_cn} claim 尚未由直接证据闭合，"
                    f"但存在{risk_cn}，属于可授权补判的事实表达边界。因此判为{scope_cn}事实错误风险。"
                )

        if label == LABEL_2 and evidence_state in {"candidate_unconverted", "partial_incomparable"}:
            return (
                f"裁决状态显示当前{scope_cn} claim 只有候选材料，未通过同槽裁决；"
                f"当前槽位状态为 {slot_state or '未闭合'}。因此不判定为事实错误。"
            )
    return ""
