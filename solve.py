# -*- coding: utf-8 -*-
from __future__ import annotations

# 1. 基础依赖：命令行、JSON、并发、路径和类型标注。
import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from afc_schema import (
    EVIDENCE_MODE_DATE,
    EVIDENCE_MODE_EVENT,
    EVIDENCE_MODE_NUMERIC,
    EVIDENCE_MODE_POLICY,
    EVIDENCE_MODE_ROUTE,
    EVIDENCE_MODE_SCHEDULE,
    HIGH_RISK_SUPPORTING_EVIDENCE_MODES,
    POINT_STAGE_NO_CANDIDATE,
    POINT_STAGE_NO_DIRECT,
    POINT_STAGE_RELATED_ONLY,
    POINT_STAGE_ROUTE_RELATION_MISSING,
    STRUCTURED_EVIDENCE_MODES,
)
from evidence_contract import (
    infer_missing_required_slots as shared_infer_missing_required_slots,
    required_slot_profile_for_mode as shared_required_slot_profile_for_mode,
)
from event_semantics import EVENT_SCORE_PATTERN, event_has_result_signal

# 2. 项目模块：evidence_v2 做证据结构化，retrieval_v2 做检索取证。
from evidence import claim_coverage, evidence_event_summary, normalize_text, point_conversion_diagnostics, summarize_claim_evidence, unique_points
from retrieval import retrieve_evidence

# 3. 可选依赖：dotenv 读取 .env，OpenAI 兼容客户端调用模型。
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

if load_dotenv:
    load_dotenv()

# 4. 标签与运行配置：统一管理 label、模型参数、检索预算和置信度阈值。
LABEL_0 = "0-主需存在事实错误"
LABEL_1 = "1-次需存在事实错误"
LABEL_2 = "2-无事实错误"
VALID_LABELS = {LABEL_0, LABEL_1, LABEL_2}
NEED_TYPES = {
    "current_result",
    "schedule_time",
    "financial_quote",
    "market_movement",
    "distance_position",
    "geopolitical_claim",
    "current_geopolitical_status",
    "sports_result",
    "general_fact",
}

API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
BASE_URL = os.environ.get("API_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
MODEL = os.environ.get("LLM_MODEL", "gpt-4.1")
TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0"))
MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "800"))
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "45"))
RETRIES = int(os.environ.get("LLM_RETRIES", "1"))
WORKERS = int(os.environ.get("V2_WORKERS", "4"))
RESUME_OUTPUT = os.environ.get("V2_RESUME_OUTPUT", "1").lower() in {"1", "true", "yes"}
FETCH_DETAILS = int(os.environ.get("V2_FETCH_DETAILS", "1"))
MAX_RESULTS_PER_QUERY = int(os.environ.get("V2_MAX_RESULTS_PER_QUERY", "3"))
RETRIEVAL_TIMEOUT = int(os.environ.get("V2_RETRIEVAL_TIMEOUT", "3"))
CONFIDENCE_HIGH = float(os.environ.get("V2_CONFIDENCE_HIGH", "0.75"))
CONFIDENCE_REVIEW = float(os.environ.get("V2_CONFIDENCE_REVIEW", "0.65"))
ENABLE_REWRITE = os.environ.get("V2_ENABLE_REWRITE", "0").lower() in {"1", "true", "yes"}
ENABLE_FINAL_REASON_REFINE = os.environ.get("V2_ENABLE_FINAL_REASON_REFINE", "0").lower() in {"1", "true", "yes"}
ENABLE_DEBUG_VERIFICATION_PLAN = os.environ.get("V2_ENABLE_VERIFICATION_PLAN_DEBUG", "0").lower() in {"1", "true", "yes"}
ENABLE_VERIFICATION_PLAN_RETRY_CONTEXT = os.environ.get("V2_ENABLE_VERIFICATION_PLAN_RETRY_CONTEXT", "0").lower() in {"1", "true", "yes"}
ENABLE_SEMANTIC_AUDIT = os.environ.get("V2_ENABLE_SEMANTIC_AUDIT", "0").lower() in {"1", "true", "yes"}
ENABLE_FULL_EXTRACT_FALLBACK = os.environ.get("V2_ENABLE_FULL_EXTRACT_FALLBACK", "0").lower() in {"1", "true", "yes"}
REWRITE_MAX_CLAIMS = int(os.environ.get("V2_REWRITE_MAX_CLAIMS", "2"))
MAX_CLAIMS = int(os.environ.get("V2_MAX_CLAIMS", "5"))
ENABLE_LLM_CACHE = os.environ.get("V2_ENABLE_LLM_CACHE", "0").lower() in {"1", "true", "yes"}
ENABLE_ROUTE_POINT_CONVERSION_LLM = os.environ.get("V2_ENABLE_ROUTE_POINT_CONVERSION_LLM", "0").lower() in {"1", "true", "yes"}
ENABLE_RUBRIC_PRIOR_FALLBACK = os.environ.get("V2_ENABLE_RUBRIC_PRIOR_FALLBACK", "1").lower() in {"1", "true", "yes"}
RUBRIC_PRIOR_MAX_TOKENS = int(os.environ.get("V2_RUBRIC_PRIOR_MAX_TOKENS", "260"))
LLM_CACHE_DIR = Path(os.environ.get("V2_LLM_CACHE_DIR") or os.path.join(os.path.dirname(__file__), ".cache_v2", "llm"))
HIGH_VALUE_REWRITE_MODES = {
    EVIDENCE_MODE_ROUTE,
    EVIDENCE_MODE_EVENT,
    EVIDENCE_MODE_SCHEDULE,
    EVIDENCE_MODE_POLICY,
    EVIDENCE_MODE_NUMERIC,
    EVIDENCE_MODE_DATE,
}
HIGH_VALUE_REWRITE_NEEDS = {
    "current_result",
    "schedule_time",
    "market_movement",
    "distance_position",
    "geopolitical_claim",
    "current_geopolitical_status",
    "sports_result",
}
RUBRIC_RISK_FLAGS = {
    "absolute_claim",
    "forecast_as_fact",
    "numeric_precision_claim",
    "time_sensitive_claim",
    "core_relation_claim",
    "weak_modalized_claim",
    "fictional_contamination",
    "high_risk_structured_detail",
    "partial_incomparable",
}
RUBRIC_CERTAINTY_PROFILES = {"weak", "medium", "strong"}
RUBRIC_ERROR_SCOPES = {"core", "detail", "none", "unknown"}
RUBRIC_FALLBACK_POLICIES = {"rubric_core_error", "rubric_detail_error", "rubric_no_error"}
RUBRIC_TARGET_DECISION_BASES = {"semantic_boundary", "risk_calibration"}
UNSUPPORTED_COVERAGE_LEVELS = {"none", "weak", "partial"}
FALLBACK_INCOMPARABLE_RISKS = {
    "point_time_scope_mismatch",
    "time_scope_not_bound_to_metric_point",
    "date_window_mismatch",
    "object_phrase_mismatch",
    "structured_point_not_comparable",
    "point_subject_currency_mismatch",
    "point_metric_field_missing",
    "point_metric_value_missing",
}

# 5. Extract Prompt：第一次 LLM 调用，拆 claim 并生成检索计划。
SYSTEM_EXTRACT = """你是严格的 AFC claim planner。你不会联网，不判断真假，只输出 JSON。

任务：
1. 写出 user_need：用户真正要核查的核心事实需求。
2. 从 answer 中提取可核查 claims；question 只用于判断主次，不把 question 本身当 claim。
3. 为每条 claim 给出检索意图、verification_questions、少量短 query，以及 evidence_need_program。

claim 选择规则：
- 最多 5 条；优先 1-2 条直接回答主需的 core claim。
- 如果 answer 同时包含“事实结果/数值/状态”和“代表什么/意味着什么”两类子需，可以保留 2 条 core；否则默认只保 1 条 core。
- 再保留最多 2 条高风险 supporting claim：数字、日期、比分/赛果、路线/领空、金额、距离、政策、预测确定化、强绝对化表述。
- 如果回答里出现“唯一 / 只能 / 必经 / 必须经过 / 完全绕开 / 根本不需要经过 / only route / must pass / without crossing”这类排他性 premise，且它被当作结论前提，要单独抽成 claim。
- 如果一句话同时包含“直接可核查结果”和“原因/含义解释”，优先拆成两条 claim，不要让解释性句子吞掉结果句。
- 如果一句话同时包含“主结论”和“高风险结构化 detail”，优先拆成 `core + supporting`，不要把 detail 粘在解释性 claim 上。
- peripheral 通常不抽；只有明确数字/日期/赛程/金额/比分等结构化细节才保留。
- 每条 claim 只写一个事实，不抽主观评价，不判断对错。

枚举：
- need_type: current_result|schedule_time|financial_quote|market_movement|distance_position|geopolitical_claim|current_geopolitical_status|sports_result|general_fact
- centrality: core|supporting|peripheral
- checkability: checkable|subjective|not_checkable
- evidence_mode: entity_fact|numeric_fact|date_fact|event_result|route_fact|schedule_fact|policy_fact
- evidence_target: match_result|withdrawal_status|market_calendar|market_price|census_phase|position_distance|current_status|prize_amount|route_relation|general
- evidence_shape: authoritative_notice|structured_historical_data|event_detail_page|current_status_update|open_news_analysis|general_evidence_page
- risk_type: direct_answer|detail_numeric|detail_date|route_relation|policy_intent|military_action|current_status|prediction|general
- assertion_strength: low|medium|high

source_intent/source_strategy：
- preferred_source_types/source_types: official|news|encyclopedia|forum，优先 official/news，避免 forum/qa。
- preferred_domains 只有高把握知道权威官网域名才填，否则空数组；不要猜域名，不要写完整 URL。
- search_channels: news_search|web_search|site_search|playwright_detail|general_search；无 preferred_domains 时不要建议 site_search。
- languages: zh|en；国际事件、外国机构/地点、人名明显时可 zh+en。
- must_have 写直接证据必须出现的要素；avoid_sources 写噪声类型；why 一句话说明。
- evidence_shape 表示“需要哪种证据形态”，不要写具体题面类型；不确定就 general_evidence_page。

queries：
- 每条为 {"q":"短 query","goal":"find_official_page|find_result|verify_numeric_detail|verify_date_detail|find_route|find_policy|general_verify"}。
- 每个 claim 最多 3 条 query；短、准、可搜索，不堆同义词。
- route_fact 必须给 route_meta，只从 question/answer 抽 origin/destination/route_area/polarity。

verification_questions：
- 每条 claim 输出 1-3 个核查问题，用于把 claim 转成可回答的问题。
- 问题必须通用、短、可检索，不要写样例答案，不要堆关键词。
- 优先问“实际结果/实际数值/实际日期/是否发生/是否存在特殊情况”。

evidence_need_program：
- 这是证据需求程序层，不是题型标签表。
- 你要先把 claim 压成最短可核查断言，再说明它错了会伤到 answer 的哪一层。
- decision_slots 要写这条 claim 真正要对齐的事实位点；至少尽量覆盖 subject / object / time_scope / metric_or_relation / status_or_result。
- direct_evidence_need 要说明什么证据一出现就能直接支持或直接反驳它。
- false_friend_evidence 要写“看起来相关但其实不是同一事实位点”的材料类型。
- expected_failure_stage 只能写：provider_recall|retrieval_filter|retrieval_readiness|point_conversion|comparability|multi_hop_closure。

输出格式：
{
  "user_need": "...",
  "need_type": "current_result|schedule_time|financial_quote|market_movement|distance_position|geopolitical_claim|current_geopolitical_status|sports_result|general_fact",
  "claims": [
    {
      "claim_id": "c1",
      "claim": "...",
      "centrality": "core|supporting|peripheral",
      "checkability": "checkable|subjective|not_checkable",
      "source_intent": {
        "preferred_source_types": ["official", "news"],
        "preferred_domains": [],
        "evidence_mode": "entity_fact",
        "evidence_target": "general",
        "evidence_shape": "general_evidence_page",
        "time_sensitivity": "high",
        "assertion_strength": "medium",
        "risk_type": "general",
        "stated_as_fact": true,
        "source_strategy": {
          "source_types": ["official", "news"],
          "search_channels": ["news_search", "web_search"],
          "languages": ["zh", "en"],
          "must_have": ["主体", "直接证据要素"],
          "avoid_sources": ["forum", "qa"],
          "why": "为什么优先这些渠道"
        },
        "route_meta": {
          "origin": "",
          "destination": "",
          "route_area": "",
          "polarity": "uncertain"
        }
      },
      "evidence_need_program": {
        "normalized_assertion": "最短可核查断言",
        "answer_role_impact": "core|supporting|background|rhetorical",
        "decision_slots": {
          "subject": "",
          "object": "",
          "time_scope": "",
          "metric_or_relation": "",
          "status_or_result": ""
        },
        "direct_evidence_need": {
          "must_answer": "哪种直接证据才足够裁决",
          "must_include": ["证据必须包含的要素"]
        },
        "false_friend_evidence": ["容易误导但不足以直裁的相关材料"],
        "expected_failure_stage": "provider_recall|retrieval_filter|retrieval_readiness|point_conversion|comparability|multi_hop_closure"
      },
      "verification_questions": ["为了核查该 claim 需要问的问题"],
      "queries": [{"q": "...", "goal": "find_official_page"}]
    }
  ]
}
"""

SYSTEM_EXTRACT_FAST = """你是 AFC 快速 claim planner。你不会联网，不判断真假，只输出紧凑 JSON。

任务：从 answer 抽取用户主需和少量可核查 claims，用于后续检索。

硬规则：
- question 只用于理解主需；claim 必须主要来自 answer。
- 最多 4 条 claims：优先 core，再保留高风险数字/日期/路线/赛果/预测/绝对化细节。
- 如果 answer 同时回答“事实结果/数值/状态”和“代表什么/意味着什么”，允许 2 条 core；否则默认只保 1 条 core。
- 如果回答里把“唯一 / 只能 / 必经 / 完全绕开 / must pass / only route”当作结论前提，要单独抽成 claim。
- 如果一句话同时包含可核查结果和解释性含义，先拆开，不要混成一条长 claim。
- peripheral 通常不抽，除非是明确数字、日期、金额、比分、距离。
- 每条 claim 一个事实；不抽主观评价；不输出 final_label。
- preferred_domains 不确定就空数组，不猜域名。
- 每条 claim 最多 2 条短 query。
- 每条 claim 输出 1-2 个 verification_questions，用于后续证据 QA。
- 每条 checkable claim 额外输出一个 evidence_need_program，用来描述最短断言、事实位点、直接证据需求、假相关材料和预期阻塞层。

枚举：
- need_type: current_result|schedule_time|financial_quote|market_movement|distance_position|geopolitical_claim|current_geopolitical_status|sports_result|general_fact
- centrality: core|supporting|peripheral
- evidence_mode: entity_fact|numeric_fact|date_fact|event_result|route_fact|schedule_fact|policy_fact
- evidence_target: match_result|withdrawal_status|market_calendar|market_price|census_phase|position_distance|current_status|prize_amount|route_relation|general
- evidence_shape: authoritative_notice|structured_historical_data|event_detail_page|current_status_update|open_news_analysis|general_evidence_page
- risk_type: direct_answer|detail_numeric|detail_date|route_relation|policy_intent|military_action|current_status|prediction|general

输出 JSON：
{
  "user_need": "...",
  "need_type": "...",
  "claims": [
    {
      "claim_id": "c1",
      "claim": "...",
      "centrality": "core|supporting|peripheral",
      "checkability": "checkable",
      "source_intent": {
        "preferred_source_types": ["official","news"],
        "preferred_domains": [],
        "evidence_mode": "...",
        "evidence_target": "...",
        "evidence_shape": "general_evidence_page",
        "time_sensitivity": "high|medium|low",
        "assertion_strength": "low|medium|high",
        "risk_type": "...",
        "stated_as_fact": true
      },
      "evidence_need_program": {
        "normalized_assertion": "...",
        "answer_role_impact": "core|supporting|background|rhetorical",
        "decision_slots": {
          "subject": "",
          "object": "",
          "time_scope": "",
          "metric_or_relation": "",
          "status_or_result": ""
        },
        "direct_evidence_need": {
          "must_answer": "...",
          "must_include": ["..."]
        },
        "false_friend_evidence": ["..."],
        "expected_failure_stage": "provider_recall|retrieval_filter|retrieval_readiness|point_conversion|comparability|multi_hop_closure"
      },
      "verification_questions": ["..."],
      "queries": [{"q": "...", "goal": "general_verify"}]
    }
  ]
}
"""

SYSTEM_DETAIL_SUPPLEMENT = """你是 AFC supporting-detail planner。你不会联网，不判断真假，只补充缺失的 supporting claim，并只输出 JSON。

任务：
1. 阅读 question、answer，以及已经抽出的 claims。
2. 只补“答案里明确写出来、但当前 claims 没保住”的高风险附带细节。
3. 只补 supporting claim，最多 2 条。

优先补这些类型：
- 金额、奖金、价格、汇率、比分、距离、百分比、时间长度
- 具体日期、宣布时间、颁奖时间、赛程时间
- 其他会影响可信度但不改变主结论的结构化细节

硬规则：
- 不重复已有 claim。
- 不补主观评价，不补背景解释，不补未在 answer 明说的内容。
- 如果没有明显缺失，返回空数组。
- preferred_domains 只有高把握时才填；若已有 claims 里明显有官方域名，可沿用。

输出：
{
  "claims": [
    {
      "claim_id": "sx1",
      "claim": "...",
      "centrality": "supporting",
      "checkability": "checkable",
      "source_intent": {
        "preferred_source_types": ["official", "news"],
        "preferred_domains": [],
        "evidence_mode": "numeric_fact|date_fact|event_result|entity_fact|policy_fact|route_fact|schedule_fact",
        "evidence_target": "general|prize_amount|market_price|market_calendar|match_result|position_distance|current_status|route_relation",
        "evidence_shape": "authoritative_notice|structured_historical_data|event_detail_page|current_status_update|general_evidence_page",
        "time_sensitivity": "high|medium|low",
        "assertion_strength": "high|medium|low",
        "risk_type": "detail_numeric|detail_date|general|prediction|route_relation|current_status",
        "stated_as_fact": true
      },
      "verification_questions": ["..."],
      "queries": [{"q": "...", "goal": "verify_numeric_detail|verify_date_detail|find_official_page|general_verify"}]
    }
  ]
}
"""

SYSTEM_PROGRAM_REPAIR = """你是 AFC evidence program repair planner。你不会联网，不判断真假，只修复给定 claim 的证据需求程序层，并只输出 JSON。

任务：
1. 只处理输入里明确列出的 claims，不新增 claim，不删除 claim，不改 centrality，不改 final label。
2. 目标是把 claim 压成更短、更可核查的断言，并补齐最小可用的事实位点。
3. 只允许修这些字段：
   - normalized_assertion
   - decision_slots.subject
   - decision_slots.object
   - decision_slots.time_scope
   - decision_slots.metric_or_relation
   - decision_slots.status_or_result
   - direct_evidence_need.must_answer
   - direct_evidence_need.must_include
   - false_friend_evidence

硬规则：
- 不重写整个 extraction。
- 不输出解释文字，只输出 JSON。
- normalized_assertion 必须是短句、声明式、单事实。
- 如果某个 slot 无法从 claim/question/answer 中可靠推出，就保留空字符串，不要猜。
- false_friend_evidence 只写“看起来相关但不是同一事实位点”的材料类型，不写结论。

输出格式：
{
  "claims": [
    {
      "claim_id": "c1",
      "normalized_assertion": "...",
      "decision_slots": {
        "subject": "",
        "object": "",
        "time_scope": "",
        "metric_or_relation": "",
        "status_or_result": ""
      },
      "direct_evidence_need": {
        "must_answer": "...",
        "must_include": ["..."]
      },
      "false_friend_evidence": ["..."]
    }
  ]
}
"""

SYSTEM_VERIFICATION_PLAN = """你是 AFC verification planner。你不会联网，不判断真假，只把已抽取 claim 拆成可验证结构。

目标：
- 生成通用 verification_plan，用于 debug 诊断和后续 slot-targeted retrieval 设计。
- 不输出 final_label，不判断 claim 真假，不补样本答案，不写固定网站或题目专属关键词。
- 每个 claim 拆成 1-3 个 atomic_facts，并给出 1-3 个 verification_subquestions。
- evidence_need / required_evidence / reject_evidence 写“证据能力合同”，不是 query 词表。
- 对数值、日期、行情、涨跌、牌价、价格类 claim，必须输出 metric_slots；这是通用指标槽位，不是汇率专用规则。
- 同时输出更上位的 object-binding 视角：
  - mechanism_type：这条 claim 更像哪种证据机制
  - core_binding：所有 claim 都尽量抽的通用对象约束
  - typed_extension：命中已知机制时再补的增强字段
- 还要输出 task_semantics：这是开放语义层，至少要写 fact_operation / value_semantics / primary_slots / secondary_slots / must_not_confuse / retrieval_focus。
- 这里不要用题材名驱动，而要优先描述证据获取机制；但 metric_slots 仍需保留做兼容。
- 同时输出 task_semantics：这是开放语义层，不要求你把所有题都硬塞进固定题型，而是描述“这条 claim 在核什么结构、容易和什么混淆、检索应优先盯什么”。

枚举：
- claim_type: route_relation|causal_impact|numeric_value|date_schedule|award_fact|prediction_vs_confirmed|event_result|policy_fact|entity_fact|general_fact
- polarity: positive|negative|comparative|causal|prediction|uncertain
- suggested_query_intent: discover_truth|verify_original|find_official_page|find_route_page|find_current_status|find_numeric_source|find_date_source|find_result_page|general_verify
- mechanism_type: structured_numeric_authority|date_authority|event_result_page|relation_sentence|current_status_update|symbolic_compute|general_web_evidence|unknown
- task_semantics.fact_operation: attribute|relation|quantity|time|status|result|cause|mixed|unknown
- task_semantics.value_semantics: person_org_place|route_or_transit|money_or_quantity|date_or_window|policy_or_rule|result_or_outcome|status_or_existence|cause_or_mechanism|classification_or_membership|mixed|unknown
- metric_slots.value_type: central_parity|spot_buying_price|cash_buying_price|selling_price|real_time_rate|movement_direction|movement_amount|movement_percent|open_price|close_price|intraday_price|settlement_price|adjustment_amount|retail_price|effective_time|spot_price|futures_price|index_level|generic_value|not_metric
- metric_slots.source_authority: central_bank|exchange|bank_rate_table|official_notice|financial_quote_page|market_data_page|price_monitoring_report|authoritative_news|general_source|unknown

输出 JSON：
{
  "verification_plan": [
    {
      "claim_id": "c1",
      "claim_type": "general_fact",
      "mechanism_type": "general_web_evidence",
      "polarity": "positive",
      "subject": "...",
      "relation": "...",
      "object": "...",
      "condition_or_scope": "...",
      "task_semantics": {
        "fact_operation": "relation",
        "value_semantics": "route_or_transit",
        "primary_slots": ["subject", "relation", "object", "time_scope"],
        "secondary_slots": ["authority_scope"],
        "must_not_confuse": ["容易混淆的对象/事件/页面"],
        "retrieval_focus": ["检索时要先锁住的要素"]
      },
      "core_binding": {
        "subject_entity": "所有题尽量都填的主体",
        "object_entity": "相关客体/比较对象/被作用对象，没有可留空",
        "relation_or_metric": "核查的关系或指标口径",
        "time_scope": "日期、年份、窗口或当前/历史状态",
        "authority_scope": "理想来源类型，例如 official_notice / exchange / general_source",
        "expected_evidence_shape": "理想证据页/句形态",
        "reject_evidence_shape": "哪些相关页仍不足以裁决"
      },
      "typed_extension": {
        "numeric": {},
        "date": {},
        "event": {},
        "route": {},
        "policy": {}
      },
      "metric_slots": {
        "subject_entity": "被核查的对象，例如币种对/股票/商品/指数/政策指标",
        "metric_name": "指标名，例如汇率/银行牌价/中间价/收盘价/油价调整",
        "value_type": "generic_value",
        "time_scope": "日期或时点",
        "unit": "单位，例如 CNY per USD / CNY per 100 USD / % / points / CNY per liter",
        "source_authority": "general_source",
        "comparison_baseline": "如果核查涨跌/升降/变化，写前一日/前一交易日/上一轮等；否则空字符串",
        "expected_evidence_shape": "带日期+指标+口径+数值+单位的表格/公告/行情页",
        "reject_evidence_shape": "无日期、无口径、只给泛换算或不能比较的相关页"
      },
      "atomic_facts": [
        {
          "fact_id": "c1_f1",
          "fact": "...",
          "polarity": "positive",
          "evidence_need": "direct_sentence|official_source|route_segment_sentence|numeric_value_source|date_source|causal_explanation|prediction_status|result_source|general_evidence"
        }
      ],
      "verification_subquestions": [
        {
          "question": "...",
          "answer_target": "...",
          "suggested_query_intent": "general_verify",
          "missing_slots": ["subject", "relation", "object"]
        }
      ],
      "required_evidence": ["什么证据才足够裁决"],
      "reject_evidence": ["什么相关材料仍不足以裁决"]
    }
  ]
}
"""

# 6. Verify Prompt：第二次 LLM 调用，只基于 evidence 做事实裁决。
SYSTEM_VERIFY = """你是严格的AFC事实裁决器。你不会联网；你只能基于输入的question、answer、claims和evidence做判断。

标签：
- 0：主需存在事实错误
- 1：次需存在事实错误
- 2：无事实错误

判断原则：
1. 先判断每个claim是supported / refuted / uncertain / not_checkable。
2. 再判断严重度 major / minor / none。
3. 只有核心事实错、且影响用户主需，才给0。
4. 只有背景/细节错、不影响主结论，给1。
5. 没有明确事实错误给2。
6. 证据不足时输出uncertain，不要猜。
7. 如果证据冲突，优先保守。
8. 证据类型优先级：computed/input_context 通常比普通搜索摘要更稳定；official 高于 news/encyclopedia；forum/unknown 只能作为弱线索。
9. computed 证据只能证明它明确计算出的内容，不要把“星期计算”扩展成“是否休市”的最终证据。
10. evidence_summary 中 direct_answer=direct 才能作为强支持/反驳；partial 只能辅助；related_only 只能说明相关，不能单独判 supported/refuted。
11. claim_coverage 中 coverage_level=none/weak 时，除非有明确 computed 反证，否则不要判 refuted。
12. coverage_level=strong/moderate 时，可以结合 supporting/refuting direct points 做 supported/refuted。
13. route_fact 必须优先看 route_relation.directly_answers_route；只有同一句明确说明“主体是否经由/绕开某领空或路线”时，才可判 supported/refuted。
14. compact_evidence.qa_evidence 是 claim->核查问题->证据答案 的中间层；优先使用 stance=refute/support 且 directness=direct 的 QA 证据写 reason。
15. 如果 qa_evidence 的 stance=unknown 或 directness=none，只能说明未形成直接证据，不能包装成事实错误。
16. evidence_ledger 是证据账本：confirmed_points/refuted_points/unresolved_points/gate_blocked_pages/slot_blocked_candidates 必须优先用于自检。
17. core_assertion_audit 标出“表层事实已命中/已确认但核心断言未闭合”的情况；这种情况不能因为表层事实相关就判 supported。
18. cross_claim_consistency 标出跨 claim 的同题冲突和核心未闭合；needs_consistency_review=true 时要在 reason 中说明。
19. 没有同槽直接反证时，不要把“未拿到证据”写成事实错误；可以输出 uncertain 或保守 label=2。
20. 输出必须是严格JSON。

输出格式：
{
  "claim_verdicts": [
    {
      "claim_id": "c1",
      "verdict": "supported|refuted|uncertain|not_checkable",
      "severity_if_wrong": "major|minor|none",
      "confidence": {
        "claim_extraction": 0.0,
        "evidence_relevance": 0.0,
        "source_reliability": 0.0,
        "verdict": 0.0,
        "severity": 0.0,
        "temporal": 0.0
      },
      "initial_verdict": "supported|refuted|uncertain|not_checkable",
      "counter_evidence_check": "是否看到同槽反证；没有则写 no_direct_counter_evidence",
      "contradiction_found": false,
      "needs_consistency_review": false,
      "evidence_ledger_used": true,
      "abstain_reason": "",
      "reason": "..."
    }
  ],
  "final_label": 0,
  "analyse": "..."
}
"""

# 7. Review Prompt：条件触发复核，用于检查边缘标签是否过严或过松。
SYSTEM_REVIEW = """你是AFC复核器。你要检查前一次判断是否过严、过松或把不确定当成错误。

只输出JSON：
{
  "final_label": 0,
  "analyse": "...",
  "confidence": 0.0
}
"""

# 8. Semantic Audit Prompt：证据不足时，只检查回答自身是否存在可判定的边界错误。
SYSTEM_SEMANTIC_AUDIT = """你是 AFC 语义边界审计器。你不会联网；你不根据缺少证据判错，只检查 answer 的表达是否越界。

只允许判断以下边界问题：
1. resolved_forecast：把尚未确认/尚未发生/预测中的结果写成确定事实。
2. absolute_route_or_causal：对路线、因果、影响作强绝对化断言，如“根本不需要/完全没有影响/唯一路线/必然”。
3. attached_detail_pollution：主需基本回答正确，但附带了具体金额、日期、比分、数值等高风险细节，且这些细节影响可信度但不改主结论。
4. open_route_summary：开放式路线概括或多路线说明，没有强排他/强否定，不应因证据不足判错。
5. no_boundary_error：没有可判定边界错误。

硬规则：
- 证据不足本身不是事实错误。
- 若只是不确定，输出 no_boundary_error。
- 若 answer 使用强绝对词把不确定内容说死，可以判边界错误。
- 输出必须是严格 JSON。

输出格式：
{
  "audit_type": "resolved_forecast|absolute_route_or_causal|attached_detail_pollution|open_route_summary|no_boundary_error",
  "final_label": 0,
  "analyse": "...",
  "confidence": 0.0
}
"""

SYSTEM_FINAL_REASON = """你是 AFC 最终原因撰写器。你不会联网，也不能修改标签。

任务：基于 question、answer、claims、evidence_summary、decision_basis 和 draft_reason，写一段更具体、更忠实的中文 reason。

硬规则：
1. 不得修改 final_label。
2. 不得编造 evidence 中没有的事实。
3. 如果 decision_basis=evidence_refutation，必须写清楚哪个 claim 被什么证据反驳。
4. 如果 decision_basis=evidence_support，必须写清楚哪些关键 claim 得到了直接支持，不要写成“只是没反证”。
5. 如果 decision_basis=rubric_fallback 或 rubric_fallback_with_partial_evidence，必须写清楚这是风险先验补判，不要伪装成直接证据反驳。
6. 如果 decision_basis=insufficient_evidence，必须写清楚没有形成可直接裁决的支持或反驳证据，所以不能判错。
7. 如果 evidence_summary 没有 direct/refuting points，不要说“证据显示错误”。
8. reason 要围绕决定标签的 claim，不要泛泛说“风险/证据不足”。

只输出严格 JSON：
{
  "analyse": "..."
}
"""

# 8. Search Planner Prompt：检索失败时，让 LLM 规划短 query，不直接判断事实。
SYSTEM_SEARCH_PLANNER = """你是 AFC 检索规划器。你不会联网，不判断 claim 对错，只规划如何找直接证据。

规则：
1. 只为 needs_retry=true 或 evidence_gap 不足的 claim 输出 rewrites。
2. 每个 claim 最多 3 条 query；每条 query 必须短、准、可搜索，通常 6-12 个词。
3. 不要复述整句 claim；不要堆同义词；不要写长句。
4. 不要把答案中的可疑数字/比分/日期当成唯一搜索锚点。
5. 如果 claim 含具体数值/比分/日期，至少给一条 discover_truth：去掉原数值，找真实事实。
6. 如果需要验证原说法，可给 verify_original：带原数值或原日期。
7. 体育赛果优先找 final score / recap / walkover / withdrew / retired / 退赛 / 不战而胜。
8. 市场交易日/休市优先找 exchange calendar / trading day / market holiday / 休市 / 交易日。
9. 阶段/发布时间优先找 phase / start / end / results published / census / 阶段 / 公布。
10. 位置/距离优先找 date + current location/position + distance。
11. 如果高把握知道权威官网，可以写 site:domain；否则不要猜域名。
12. 只有 route_fact 才输出 route_search_frame；非 route_fact 不要输出 route_search_frame。
13. route_fact 若 route_query_quality_score < 45，必须先输出 route_search_frame，再基于 frame 生成 query；不要照抄示例词，不要为当前题面补固定 query。
14. route_search_frame 必须从 claim/question/answer 中抽取：subject、action_or_event、relation_need、object_or_area、time_or_event_window、claim_polarity、evidence_sentence_need。
15. route_fact 的 query 必须服务于 frame：能让网页直接出现“主体/行动 + 路线关系 + 对象/地点”的证据句；避免百科、论坛、泛分析页和只出现单个实体的页面。
16. route_fact 至少一条 discover_truth 必须是中性发现 query：不要带原 claim 的否定/肯定结论词，只找真实路线事实；verify_original 才可以保留原说法。
17. 不能判断 claim 对错，不能输出 final_label，不能输出 Markdown。

输出格式：
{
  "rewrites": [
    {
      "claim_id": "c1",
      "gap_diagnosis": "search_recall|page_contract|sentence_shape|point_grounding|evidence_sufficiency|source_quality",
      "operator_plan": {
        "family": "structured_point_retry|metric_source_probe|page_intent_retry|gap_pseudo_page_probe|route_frame_probe|preferred_domain_probe|general_rewrite_probe",
        "primary_origin": "本轮最该优先服务的 operator origin",
        "supporting_origins": ["最多2个辅助 origin"],
        "variant_hint": "可选；如 dated_record/history/field_record/subject_row/value_extractable_record",
        "reason": "一句话说明为什么这样选"
      },
      "contract_focus": {
        "page_brief": "想找什么页面",
        "target_sentence": "理想网页里可裁决句长什么样",
        "avoid": "应避开的噪声页",
        "answer_target": "本轮要直接回答的核查目标",
        "required_sentence_shape": "可用证据句合同",
        "reject_shape": "应拒绝的页面/句子形态"
      },
      "queries": [
        {
          "q": "...",
          "goal": "verify_original|discover_truth|find_official|find_news|find_context",
          "source_preference": ["official", "news"],
          "why": "为什么这条 query 能找到直接证据"
        }
      ],
      "route_search_frame": {
        "subject": "从 claim 中抽出的主体",
        "action_or_event": "从 claim 中抽出的行动/事件",
        "relation_need": "需要验证的路线关系类型，不要堆同义词",
        "object_or_area": "从 claim 中抽出的对象/地点/区域",
        "time_or_event_window": "从输入时间或 claim 中抽出的时间窗口",
        "claim_polarity": "原 claim 是肯定经过、否定经过、影响判断，还是不明确",
        "evidence_sentence_need": "网页中怎样的中性事实句才算直接证据；不要只写支持原 claim 的句式"
      },
      "must_find": ["需要找到的直接证据类型"],
      "avoid": ["应避免的搜索陷阱"]
    }
  ]
}
"""

# Backward-compatible name for existing call sites.
SYSTEM_REWRITE = SYSTEM_SEARCH_PLANNER

SYSTEM_DECISION_QUERY_PLANNER = """你是 AFC 的中层 query planner。你不会联网，不判断 final_label，只把 claim 转成更有裁决价值的检索计划。

要求：
1. 只能输出严格 JSON，不要输出解释文字。
2. 不要给 0/1/2，不要判断真假。
3. 你的任务是判断这条 claim 更像哪类 claim_family，以及更适合 direct_web_evidence、closure_refutation 还是 insufficient_or_unresolved 通道。
4. query_family_plan 只能从 ["mirror","slot","closure","refute","distinguish"] 中选择，最多 3 个。
5. bridge_fact_plan 只写 1-4 个短词，帮助后续拼接 query，比如“星期”“交易日历”“发布日”“生效日”“最终结果”“替代路径”。
6. 如果 claim 是 date_fact / schedule_fact / route_fact / event_result，优先帮助区分同名不同位点，而不是重复 claim 原句。
7. 不要猜域名，不要编造证据，不要写长句。

输出格式：
{
  "claim_family": "date_fact|schedule_fact|route_fact|event_result|numeric_count_detail|numeric_fact|general_fact",
  "intended_decision_channel": "direct_web_evidence|closure_refutation|insufficient_or_unresolved",
  "query_family_plan": ["closure", "distinguish"],
  "bridge_fact_plan": ["星期", "交易日历"]
}
"""

SYSTEM_EVIDENCE_REFINER = """你是 AFC 的中层 evidence refiner。你不会联网，也不会输出 final_label。

任务：
根据 claim、decision slots 和 top candidate sentence，把候选句整理成一个结构化证据卡，帮助后续判断它到底是：
- 同一事实位点
- 不同日期角色
- 不同结果粒度
- 还是只碰到背景/评论

要求：
1. 只能基于输入文本，不能补外部常识。
2. 不要判断真假，不要输出 0/1/2。
3. evidence_directness 只能写：
   - direct
   - slot_hit_but_indirect
   - numeric_or_date_reference_only
   - background_commentary
4. possible_confusions 最多 4 个短词，优先写：
   - date_role_mismatch
   - result_granularity_mismatch
   - not_same_fact_slot
   - candidate_not_direct
   - commentary_only
5. 若某字段句中根本没有，写空字符串。

输出格式：
{
  "subject": "",
  "time_scope": "",
  "metric_or_relation": "",
  "status_or_result": "",
  "date_role": "",
  "result_granularity": "",
  "evidence_directness": "direct|slot_hit_but_indirect|numeric_or_date_reference_only|background_commentary",
  "possible_confusions": ["date_role_mismatch"]
}
"""

SYSTEM_ROUTE_POINT_CONVERSION = """你是 AFC 的 route_fact 句级证据点转换器。
你的任务不是复述 claim，也不是做最终裁决，而是判断给定候选句里，是否存在“单句就能直接说明主体与路线/领空/区域关系”的证据。

严格要求：
1. 只能基于输入的 claim 与候选句本身判断，不能联网，不能补外部常识。
2. 必须是单句直接表达，不能跨句拼接。
3. 不要因为句子提到了主体和地点就强行判 direct；必须明确出现进入、飞向、前往、到达、经过、穿越、经由、via、through、toward、entered、bound for、headed to、flew over 等真实路线或去向关系。
4. 如果句子只是在讲背景、局势、空域政策、地理位置，但没有说明主体的真实路径关系，就判 route_relation_present=false。
5. polarity 是相对 claim 的：
   - support: 句子直接支持 claim
   - conflict: 句子直接反驳 claim
   - uncertain: 句子与路线话题相关，但不足以单句裁决
6. evidence_span 必须是原句中的连续原文片段，不要改写。
7. 只输出 JSON，不要输出解释文字。

输出格式：
{
  "results": [
    {
      "sentence_index": 0,
      "route_relation_present": true,
      "directness": "direct|partial|related_only",
      "relation_type": "enter|toward|destination|via|through|overfly|avoid|unknown",
      "polarity": "support|conflict|uncertain",
      "subject": "",
      "action_or_vehicle": "",
      "origin": "",
      "transit_area": "",
      "destination": "",
      "evidence_span": "",
      "confidence": 0.0,
      "reason": ""
    }
  ]
}
"""

SYSTEM_RUBRIC_PRIOR = """你是 AFC 的 rubric_prior 判标先验器。

任务：
在“当前没有形成可直接裁决的强证据结论”前提下，只根据题目、回答、claim 摘要、证据状态摘要和风险特征，输出一个结构化判标先验。

要求：
1. 只输出一个 JSON object，不要输出 Markdown，不要输出额外说明。
2. 不要编造外部事实，不要假装已经拿到反证，不要把“证据不足”写成“已被证据推翻”。
3. 你判断的是补判先验，不是最终证据裁决。
4. 优先依据以下通用轴：
   - 回答确定性：weak|medium|strong
   - 错误作用域：core|detail|none|unknown
   - 风险形态：absolute_claim / forecast_as_fact / numeric_precision_claim / time_sensitive_claim / core_relation_claim / weak_modalized_claim / fictional_contamination / high_risk_structured_detail / partial_incomparable
5. prior_label 含义：
   - 0：更像主需存在事实错误风险
   - 1：更像次需存在事实错误风险
   - 2：当前更像不应判定为明确事实错误
6. 如果回答是弱确定表达，且当前没有形成可裁决反证，优先保守为 2。
7. 如果回答是强确定表达，并把核心关系、核心结果、核心时间、预测结论写成已确定事实，可偏向 0。
8. 如果主结论未明显推翻，但附带精确数字、金额、日期、身份等细节更可疑，可偏向 1。
9. 不要因为“核心 claim 目前证据不足”就直接给 0；单纯 unsupported 更适合 2，除非同时存在强绝对化、预测确定化或明显核心关系过度断言。
10. 如果主要风险落在 supporting/peripheral 的结构化细节，而核心主结论本身没有高风险绝对化表达，优先给 1 而不是 0。
11. `partial but incomparable` 不是普通 unsupported；如果证据显示“找到了相关材料但口径不一致/不可直接比较”，应优先把它当成可比性风险，而不是简单视作没证据。
11. fallback_policy 必须与 prior_label 一致：
   - 0 -> rubric_core_error
   - 1 -> rubric_detail_error
   - 2 -> rubric_no_error

输出格式：
{
  "prior_label": "0|1|2",
  "confidence": 0.0,
  "certainty_profile": "weak|medium|strong",
  "error_scope": "core|detail|none|unknown",
  "risk_flags": ["..."],
  "fallback_policy": "rubric_core_error|rubric_detail_error|rubric_no_error",
  "reason": "一句简短中文说明"
}
"""


# 9. 文本与 JSON 工具：清洗文本、从模型输出中提取 JSON。
def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    candidates = [text]
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"): text.rfind("}") + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return None


def normalize_route_meta(route_meta: Dict[str, Any]) -> Dict[str, str]:
    polarity = normalize_text(str(route_meta.get("polarity") or "uncertain")).lower()
    if polarity not in {"positive", "negative", "uncertain"}:
        polarity = "uncertain"
    return {
        "origin": normalize_text(str(route_meta.get("origin") or "")),
        "destination": normalize_text(str(route_meta.get("destination") or "")),
        "route_area": normalize_text(str(route_meta.get("route_area") or "")),
        "polarity": polarity,
    }


def normalize_need_type(value: Any) -> str:
    need_type = normalize_text(str(value or "general_fact")).lower()
    return need_type if need_type in NEED_TYPES else "general_fact"


def normalize_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    text = normalize_text(str(value or "")).lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default


def normalize_market_movement_contract(
    claim_text: str,
    centrality: str,
    need_type: str,
    evidence_mode: str,
    evidence_target: str,
    evidence_shape: str,
    risk_type: str,
) -> Tuple[str, str, str]:
    if need_type != "market_movement":
        return evidence_mode, evidence_target, evidence_shape
    text = normalize_text(claim_text)
    lower_text = text.lower()
    normalized_mode = normalize_text(evidence_mode) or "entity_fact"
    normalized_target = normalize_text(evidence_target)
    normalized_shape = normalize_text(evidence_shape)
    normalized_risk = normalize_text(risk_type)
    has_calendar_terms = any(term in text for term in ["窗口", "调价日", "24时", "交易日", "休市", "开盘", "节假日", "周一", "周二", "周三", "周四", "周五", "周六", "周日"])
    has_price_terms = any(term in text for term in ["油价", "成品油", "汽油", "柴油", "涨幅", "上调", "下调", "每升", "元/吨", "元/升"])
    has_numeric_price_detail = bool(re.search(r"(\d+\s*[-~至]\s*\d+|\d+(?:\.\d+)?)\s*(元/吨|元/升|%|％)", text))
    looks_like_prediction_core = (
        centrality == "core"
        and (
            normalized_risk == "prediction"
            or any(term in text for term in ["预计", "即将", "将", "有望", "无悬念", "年内最大", "确定落地"])
        )
    )
    if normalized_target in {"", "current_status", "general"} and (has_calendar_terms or has_price_terms or looks_like_prediction_core):
        normalized_target = "market_calendar" if has_calendar_terms else "market_price"
    if normalized_shape == "current_status_update":
        if normalized_target == "market_calendar" or normalized_mode in {"date_fact", "schedule_fact"}:
            normalized_shape = "authoritative_notice"
        elif normalized_target == "market_price" or looks_like_prediction_core:
            normalized_shape = "general_evidence_page"
    if normalized_mode == "event_result":
        if normalized_target == "market_calendar":
            normalized_mode = "date_fact"
        elif normalized_target == "market_price":
            normalized_mode = "numeric_fact" if has_numeric_price_detail else "entity_fact"
    if normalized_mode == "entity_fact" and normalized_target == "market_calendar":
        normalized_mode = "date_fact"
    elif normalized_mode == "entity_fact" and normalized_target == "market_price" and has_numeric_price_detail:
        normalized_mode = "numeric_fact"
    if normalized_mode == "entity_fact" and looks_like_prediction_core and normalized_shape == "current_status_update":
        normalized_shape = "general_evidence_page"
    if normalized_mode == "entity_fact" and normalized_target == "market_price" and not has_price_terms and "oil" in lower_text:
        normalized_target = "market_price"
    return normalized_mode, normalized_target, normalized_shape


def infer_evidence_target(claim: str, evidence_mode: str, need_type: str) -> str:
    text = normalize_text(claim).lower()
    if need_type == "sports_result":
        if any(term in text for term in ["退赛", "弃权", "不战而胜", "withdraw", "retired", "walkover"]):
            return "withdrawal_status"
        return "match_result"
    if need_type == "market_movement":
        if any(term in text for term in ["休市", "交易日", "节假日", "清明", "开盘"]):
            return "market_calendar"
        return "market_price"
    if need_type == "distance_position":
        return "position_distance"
    if need_type == "schedule_time":
        return "census_phase" if any(term in text for term in ["阶段", "census", "phase", "enumeration"]) else "general"
    if need_type == "current_geopolitical_status":
        return "current_status"
    if evidence_mode == "route_fact":
        return "route_relation"
    if evidence_mode == "numeric_fact" and any(term in text for term in ["奖金", "瑞典克朗", "sek", "kronor"]):
        return "prize_amount"
    return "general"


def sanitize_extract_evidence_mode(claim_text: str, raw_mode: str, need_type: str, evidence_target: str = "") -> str:
    normalized_mode = normalize_text(raw_mode)
    if normalized_mode in {
        "entity_fact",
        "numeric_fact",
        "date_fact",
        "schedule_fact",
        "event_result",
        "policy_fact",
        "route_fact",
    }:
        return normalized_mode
    text = normalize_text(claim_text)
    lower = text.lower()
    target = normalize_text(evidence_target)
    if target == "route_relation" or EXCLUSIVE_PREMISE_PATTERN.search(text) or EXCLUSIVE_ROUTE_HINT_PATTERN.search(text):
        return "route_fact"
    if re.search(r"(比分|战胜|赢了|输给|退赛|晋级|夺冠|beat|won|result|score)", text, flags=re.I):
        return "event_result"
    if re.search(r"(休市|开盘|交易日|假期|公布|发布|日期|时间|生效|calendar|schedule|announce|release)", text, flags=re.I):
        return "schedule_fact" if need_type == "market_movement" else "date_fact"
    if re.search(r"(\d|中间价|汇率|牌价|金额|奖金|公里|千米|百分比|基点|price|rate|amount|km|%)", text, flags=re.I):
        return "numeric_fact"
    if re.search(r"(政策|执行|允许|禁止|状态|official|status|policy|参与|配合|游说)", lower):
        return "policy_fact"
    return "entity_fact"


def infer_evidence_mode_from_plan(
    claim_type: str,
    metric_slots: Optional[Dict[str, Any]] = None,
    mechanism_type: str = "",
    existing_mode: str = "",
    evidence_target: str = "",
) -> str:
    metric_slots = metric_slots if isinstance(metric_slots, dict) else {}
    normalized_claim_type = normalize_text(claim_type)
    normalized_mechanism = normalize_text(mechanism_type)
    normalized_existing_mode = normalize_text(existing_mode)
    normalized_target = normalize_text(evidence_target)
    value_type = normalize_text(str(metric_slots.get("value_type") or ""))
    if normalized_claim_type == "route_relation" or normalized_target == "route_relation" or normalized_mechanism == "relation_sentence":
        return "route_fact"
    if normalized_claim_type == "numeric_value" or normalized_mechanism == "structured_numeric_authority":
        return "numeric_fact"
    if normalized_claim_type == "date_schedule" or normalized_mechanism == "date_authority":
        return "date_fact"
    if normalized_claim_type == "event_result" or normalized_mechanism == "event_result_page":
        return "event_result"
    if normalized_claim_type == "policy_fact":
        return "policy_fact"
    if normalized_claim_type == "award_fact":
        if value_type and value_type != "not_metric":
            return "numeric_fact"
        return "entity_fact"
    if normalized_mechanism == "current_status_update":
        return "entity_fact"
    if normalized_existing_mode in {
        "entity_fact",
        "numeric_fact",
        "date_fact",
        "schedule_fact",
        "event_result",
        "policy_fact",
        "route_fact",
    }:
        return normalized_existing_mode
    return "entity_fact"


def infer_evidence_shape_from_plan(
    evidence_shape: str,
    claim_type: str,
    mechanism_type: str,
    evidence_mode: str,
) -> str:
    normalized_shape = normalize_text(evidence_shape)
    if normalized_shape and normalized_shape != "general_evidence_page":
        return normalized_shape
    normalized_claim_type = normalize_text(claim_type)
    normalized_mechanism = normalize_text(mechanism_type)
    normalized_mode = normalize_text(evidence_mode)
    if normalized_mechanism in {"structured_numeric_authority", "date_authority"} or normalized_mode in {"numeric_fact", "date_fact", "schedule_fact"}:
        return "authoritative_notice"
    if normalized_mechanism == "event_result_page" or normalized_claim_type == "event_result":
        return "event_detail_page"
    if normalized_mechanism == "current_status_update":
        return "current_status_update"
    if normalized_mechanism == "relation_sentence" or normalized_claim_type == "route_relation" or normalized_mode == "route_fact":
        return "open_news_analysis"
    return "general_evidence_page"


def infer_risk_type_from_plan(
    risk_type: str,
    claim_type: str,
    evidence_mode: str,
    evidence_target: str,
    mechanism_type: str,
    need_type: str,
) -> str:
    normalized_risk = normalize_text(risk_type)
    if normalized_risk and normalized_risk != "general":
        return normalized_risk
    normalized_claim_type = normalize_text(claim_type)
    normalized_mode = normalize_text(evidence_mode)
    normalized_target = normalize_text(evidence_target)
    normalized_mechanism = normalize_text(mechanism_type)
    normalized_need_type = normalize_text(need_type)
    if normalized_claim_type == "route_relation" or normalized_target == "route_relation" or normalized_mechanism == "relation_sentence":
        return "route_relation"
    if normalized_mode in {"numeric_fact"} or normalized_target in {"prize_amount", "market_price", "position_distance"}:
        return "detail_numeric"
    if normalized_mode in {"date_fact", "schedule_fact"}:
        return "detail_date"
    if normalized_claim_type == "policy_fact":
        return "policy_intent"
    if normalized_need_type == "current_geopolitical_status" and normalized_mechanism == "current_status_update":
        return "current_status"
    if normalized_claim_type == "causal_impact":
        return "direct_answer"
    return "general"


def should_override_mechanism_type(raw_mechanism: str, expected_mechanism: str, claim_type: str, evidence_target: str) -> bool:
    normalized_raw = normalize_text(raw_mechanism)
    normalized_expected = normalize_text(expected_mechanism)
    normalized_claim_type = normalize_text(claim_type)
    normalized_target = normalize_text(evidence_target)
    if not normalized_raw or normalized_raw in {"unknown", "general_web_evidence"}:
        return True
    if normalized_raw == normalized_expected:
        return False
    if normalized_target == "route_relation" or normalized_claim_type == "route_relation":
        return True
    if normalized_claim_type in {"numeric_value", "date_schedule", "event_result", "policy_fact"}:
        return True
    if normalized_claim_type == "award_fact" and normalized_raw == "relation_sentence":
        return True
    if normalized_raw in {"relation_sentence", "structured_numeric_authority", "date_authority", "event_result_page"} and normalized_expected != "general_web_evidence":
        return True
    return False


def enrich_route_meta_from_claim(claim_text: str, route_meta: Optional[Dict[str, Any]], typed_extension: Optional[Dict[str, Any]]) -> Dict[str, str]:
    base = normalize_route_meta(route_meta if isinstance(route_meta, dict) else {})
    text = normalize_text(claim_text)
    if base.get("polarity") == "uncertain":
        if re.search(r"(根本不需要|不需要经过|无需经过|完全绕开|绕开|不经由|不必经过)", text):
            base["polarity"] = "negative"
        elif re.search(r"(经过|经由|飞越|穿越)", text):
            base["polarity"] = "positive"
    route_extension = typed_extension.get("route") if isinstance(typed_extension, dict) and isinstance(typed_extension.get("route"), dict) else {}
    if not base.get("route_area"):
        base["route_area"] = normalize_text(str(route_extension.get("intermediate_place") or ""))
    return base


# 10. LLM 客户端：创建 OpenAI 兼容客户端。
def load_client() -> Optional[Any]:
    if not API_KEY or OpenAI is None:
        return None
    return OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=TIMEOUT)


CLIENT = load_client()
LLM_RUNTIME_CHECK: Optional[Dict[str, Any]] = None


def llm_runtime_status() -> Dict[str, Any]:
    if OpenAI is None:
        return {
            "available": False,
            "category": "dependency_missing",
            "reason": "openai package not installed in current python",
            "python": sys.executable,
            "model": MODEL,
            "base_url": BASE_URL,
        }
    if not API_KEY:
        return {
            "available": False,
            "category": "env_missing",
            "reason": "LLM_API_KEY/OPENAI_API_KEY not loaded",
            "python": sys.executable,
            "model": MODEL,
            "base_url": BASE_URL,
        }
    if not MODEL:
        return {
            "available": False,
            "category": "env_missing",
            "reason": "LLM_MODEL not configured",
            "python": sys.executable,
            "model": MODEL,
            "base_url": BASE_URL,
        }
    if not BASE_URL:
        return {
            "available": False,
            "category": "env_missing",
            "reason": "API_BASE_URL/OPENAI_BASE_URL not configured",
            "python": sys.executable,
            "model": MODEL,
            "base_url": BASE_URL,
        }
    if CLIENT is None:
        return {
            "available": False,
            "category": "client_init_failed",
            "reason": "OpenAI client initialization failed",
            "python": sys.executable,
            "model": MODEL,
            "base_url": BASE_URL,
        }
    return {
        "available": True,
        "category": "ready",
        "reason": "client_initialized",
        "python": sys.executable,
        "model": MODEL,
        "base_url": BASE_URL,
    }


def ensure_llm_runtime_check() -> Dict[str, Any]:
    global LLM_RUNTIME_CHECK
    if isinstance(LLM_RUNTIME_CHECK, dict):
        return LLM_RUNTIME_CHECK
    status = llm_runtime_status()
    if not status.get("available"):
        LLM_RUNTIME_CHECK = status
        return status
    try:
        response = CLIENT.chat.completions.create(
            model=MODEL,
            temperature=0,
            max_tokens=20,
            messages=[
                {"role": "system", "content": 'Return JSON only: {"ok": true}.'},
                {"role": "user", "content": "ping"},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        data = extract_json(text)
        if isinstance(data, dict) and data.get("ok") is True:
            status = dict(status)
            status.update({"checked": True, "status": "ok", "reason": "online_smoke_ok"})
            LLM_RUNTIME_CHECK = status
            return status
        status = dict(status)
        status.update({"available": False, "checked": True, "status": "bad_response", "category": "model_response_error", "reason": compact_claim_text(text or "empty_smoke_response", 120)})
        LLM_RUNTIME_CHECK = status
        return status
    except Exception as exc:
        message = str(exc)
        category = "network_or_gateway_error"
        lower = message.lower()
        if "401" in lower or "unauthorized" in lower or "authentication" in lower:
            category = "auth_error"
        elif "404" in lower or "model" in lower and "not" in lower and "found" in lower:
            category = "model_config_error"
        elif "timeout" in lower:
            category = "network_timeout"
        status = dict(status)
        status.update({"available": False, "checked": True, "status": "failed", "category": category, "reason": compact_claim_text(message, 160)})
        LLM_RUNTIME_CHECK = status
        return status


def llm_cache_path(system_prompt: str, user_prompt: str) -> Path:
    raw = json.dumps(
        {
            "model": MODEL,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "system": system_prompt,
            "user": user_prompt,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return LLM_CACHE_DIR / f"{hashlib.sha1(raw.encode('utf-8')).hexdigest()}.json"


def read_llm_cache(system_prompt: str, user_prompt: str) -> Optional[Tuple[Dict[str, Any], str]]:
    if not ENABLE_LLM_CACHE:
        return None
    path = llm_cache_path(system_prompt, user_prompt)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        data = payload.get("data")
        raw = str(payload.get("raw") or "")
        if isinstance(data, dict):
            return data, raw
    except Exception:
        return None
    return None


def write_llm_cache(system_prompt: str, user_prompt: str, data: Dict[str, Any], raw: str) -> None:
    if not ENABLE_LLM_CACHE:
        return
    try:
        LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        llm_cache_path(system_prompt, user_prompt).write_text(
            json.dumps({"data": data, "raw": raw}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


# 11. LLM 调用封装：要求模型输出 JSON，并做基础容错。
def llm_chat(system_prompt: str, user_prompt: str, retries: int = RETRIES) -> Tuple[Optional[Dict[str, Any]], str]:
    runtime_check = ensure_llm_runtime_check()
    if not runtime_check.get("available"):
        category = str(runtime_check.get("category") or "llm_unavailable")
        reason = str(runtime_check.get("reason") or "LLM client unavailable")
        return None, f"LLM client unavailable [{category}]: {reason}"
    cached = read_llm_cache(system_prompt, user_prompt)
    if cached:
        data, raw = cached
        return data, raw
    last_error = None
    for _ in range(max(1, retries + 1)):
        try:
            response = CLIENT.chat.completions.create(
                model=MODEL,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = response.choices[0].message.content or ""
            data = extract_json(text)
            if data is not None:
                write_llm_cache(system_prompt, user_prompt, data, text)
                return data, text
            last_error = f"unparseable_json: {text[:200]}"
        except Exception as exc:
            last_error = str(exc)
    return None, last_error or "llm_failed"


def llm_chat_custom(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int,
    temperature: float = 0.0,
    retries: int = RETRIES,
) -> Tuple[Optional[Dict[str, Any]], str]:
    runtime_check = ensure_llm_runtime_check()
    if not runtime_check.get("available"):
        category = str(runtime_check.get("category") or "llm_unavailable")
        reason = str(runtime_check.get("reason") or "LLM client unavailable")
        return None, f"LLM client unavailable [{category}]: {reason}"
    last_error = None
    for _ in range(max(1, retries + 1)):
        try:
            response = CLIENT.chat.completions.create(
                model=MODEL,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = response.choices[0].message.content or ""
            data = extract_json(text)
            if data is not None:
                return data, text
            last_error = f"unparseable_json: {text[:200]}"
        except Exception as exc:
            last_error = str(exc)
    return None, last_error or "llm_failed"


def compact_history_for_rubric(history: Any, limit: int = 3) -> List[str]:
    if not isinstance(history, list):
        return []
    out: List[str] = []
    for item in history:
        text = compact_claim_text(str(item or ""), 80)
        if text:
            out.append(text)
    return out[:limit]


def compact_claims_for_rubric(extracted: Dict[str, Any], evidence_summary: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    need_type = normalize_need_type(extracted.get("need_type")) if isinstance(extracted, dict) else "general_fact"
    rows: List[Tuple[int, Dict[str, Any]]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
        point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
        centrality = str(claim.get("centrality") or "")
        priority = 0
        if centrality == "core":
            priority += 6
        elif centrality == "supporting":
            priority += 3
        priority += min(2, int(point_conversion.get("direct_support_refute_count") or 0))
        if str(coverage.get("coverage_level") or "") in {"none", "weak", "partial"}:
            priority += 2
        row = {
            "claim_id": claim_id,
            "centrality": centrality,
            "claim": compact_claim_text(str(claim.get("claim") or ""), 120),
            "evidence_mode": str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or ""),
            "evidence_target": str(source_intent.get("evidence_target") or ""),
            "assertion_strength": str(source_intent.get("assertion_strength") or "medium"),
            "risk_type": str(source_intent.get("risk_type") or "general"),
            "stated_as_fact": normalize_bool(source_intent.get("stated_as_fact", True), True),
            "coverage_level": str(coverage.get("coverage_level") or ""),
            "direct_refute_count": len([point for point in (summary.get("refuting_points") or []) if isinstance(point, dict) and point.get("direct_answer") == "direct"]),
            "direct_support_count": len([point for point in (summary.get("supporting_points") or []) if isinstance(point, dict) and point.get("direct_answer") == "direct"]),
            "uncertain_count": len([point for point in (summary.get("uncertain_points") or []) if isinstance(point, dict)]),
            "point_stage": str(point_conversion.get("stage") or ""),
            "point_reason": compact_claim_text(str(point_conversion.get("reason") or ""), 90),
        }
        rows.append((priority, row))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in rows[:3]]


def has_partial_evidence_for_rubric(evidence_summary: Optional[Dict[str, Any]]) -> bool:
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    for summary in summaries.values():
        if not isinstance(summary, dict):
            continue
        coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
        if str(coverage.get("coverage_level") or "") in {"weak", "partial", "moderate", "strong"}:
            return True
        for key in ("supporting_points", "refuting_points", "uncertain_points"):
            if any(isinstance(point, dict) for point in (summary.get(key) or [])):
                return True
    return False


def compact_evidence_state_for_rubric(extracted: Dict[str, Any], evidence_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    direct_refute = 0
    direct_support = 0
    uncertain_points = 0
    coverage_levels: Dict[str, int] = {}
    modes: Dict[str, int] = {}
    point_stages: Dict[str, int] = {}
    for summary in summaries.values():
        if not isinstance(summary, dict):
            continue
        coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
        level = str(coverage.get("coverage_level") or "")
        if level:
            coverage_levels[level] = coverage_levels.get(level, 0) + 1
        mode = str(summary.get("evidence_mode") or "")
        if mode:
            modes[mode] = modes.get(mode, 0) + 1
        point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
        stage = str(point_conversion.get("stage") or "")
        if stage:
            point_stages[stage] = point_stages.get(stage, 0) + 1
        direct_refute += len([point for point in (summary.get("refuting_points") or []) if isinstance(point, dict) and point.get("direct_answer") == "direct"])
        direct_support += len([point for point in (summary.get("supporting_points") or []) if isinstance(point, dict) and point.get("direct_answer") == "direct"])
        uncertain_points += len([point for point in (summary.get("uncertain_points") or []) if isinstance(point, dict)])
    if not coverage_levels:
        dominant_state = "unsupported"
    elif direct_support > 0 and direct_refute == 0:
        dominant_state = "supported"
    elif any(level in coverage_levels for level in {"weak", "partial"}) or uncertain_points > 0:
        dominant_state = "partial_but_incomparable"
    elif "none" in coverage_levels:
        dominant_state = "unsupported"
    else:
        dominant_state = "gap"
    return {
        "need_type": normalize_need_type(extracted.get("need_type")),
        "has_direct_refute": direct_refute > 0,
        "has_direct_support": direct_support > 0,
        "has_decidable_evidence": has_new_scheme_decidable_evidence(extracted, evidence_summary),
        "dominant_state": dominant_state,
        "coverage_levels": coverage_levels,
        "dominant_modes": modes,
        "point_stages": point_stages,
        "partial_evidence": has_partial_evidence_for_rubric(evidence_summary),
    }


def answer_certainty_profile(text: str) -> str:
    text = normalize_text(text)
    if not text:
        return "medium"
    weak_terms = ["可能", "或许", "大概", "预计", "也许", "或将", "有望", "不排除"]
    strong_terms = ["根本不需要", "完全没有", "唯一", "一定", "必然", "无悬念", "确定落地", "年内最大", "即将迎来"]
    if any(term in text for term in weak_terms):
        return "weak"
    if any(term in text for term in strong_terms):
        return "strong"
    return "medium"


def point_has_fallback_incomparable_signal(point: Dict[str, Any]) -> bool:
    if not isinstance(point, dict):
        return False
    numeric_note = normalize_text(str(point.get("numeric_contract_note") or ""))
    if numeric_note in {"time_scope_mismatch", "structured_point_not_comparable"}:
        return True
    point_risks = {
        normalize_text(str(risk))
        for risk in (point.get("point_contract_risks") or [])
        if normalize_text(str(risk))
    }
    evidence_risks = {
        normalize_text(str(risk))
        for risk in (point.get("evidence_contract_risks") or [])
        if normalize_text(str(risk))
    }
    if point_risks.intersection(FALLBACK_INCOMPARABLE_RISKS) or evidence_risks.intersection(FALLBACK_INCOMPARABLE_RISKS):
        return True
    numeric_alignment = point.get("numeric_alignment") if isinstance(point.get("numeric_alignment"), dict) else {}
    if numeric_alignment and numeric_alignment.get("comparable") is False:
        return True
    return False


def build_fallback_risk_features(
    item: Optional[Dict[str, Any]],
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    item = item if isinstance(item, dict) else {}
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    need_type = normalize_need_type(extracted.get("need_type"))
    answer_text = normalize_text(str(item.get("answer") or ""))
    question_text = normalize_text(str(item.get("question") or ""))
    certainty_profile = answer_certainty_profile(answer_text)
    absolute_claim_present = answer_has_absolute_boundary_terms(answer_text)
    forecast_as_fact_present = answer_has_resolved_forecast_terms(answer_text) or any(
        isinstance(claim, dict)
        and str(claim.get("centrality") or "") == "core"
        and str((claim.get("source_intent") or {}).get("risk_type") or "") == "prediction"
        and normalize_bool((claim.get("source_intent") or {}).get("stated_as_fact", True), True)
        for claim in claims
    )

    core_result_unsupported_count = 0
    core_date_unsupported_count = 0
    core_numeric_unsupported_count = 0
    unsupported_core_claim_count = 0
    partial_but_incomparable_count = 0
    supporting_structured_detail_count = 0
    supporting_structured_incomparable_count = 0
    route_uniqueness_overclaim = False
    time_role_conflict_risk = False
    fictional_reality_contamination_risk = False

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
        claim_shape = str(source_intent.get("claim_shape") or "")
        coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
        coverage_level = str(coverage.get("coverage_level") or "")
        profile = summary.get("comparability_profile") if isinstance(summary.get("comparability_profile"), dict) else claim_comparability_profile(claim, summary)
        comparability_status = str(profile.get("comparability_status") or "unsupported")
        centrality = str(claim.get("centrality") or "")
        claim_text = normalize_text(str(claim.get("claim") or ""))
        risk_type = str(source_intent.get("risk_type") or "general")
        stated_as_fact = normalize_bool(source_intent.get("stated_as_fact", True), True)
        direct_points = [
            point
            for point in (summary.get("supporting_points") or []) + (summary.get("refuting_points") or [])
            if isinstance(point, dict) and point.get("direct_answer") == "direct"
        ]
        comparable_direct_count = int(profile.get("comparable_direct_support_count") or 0) + int(profile.get("comparable_direct_refute_count") or 0)
        unsupported_like = comparability_status == "unsupported" and comparable_direct_count <= 0 and coverage_level in UNSUPPORTED_COVERAGE_LEVELS and not direct_points
        incomparable_like = comparability_status == "partial_but_incomparable"
        if not incomparable_like:
            for point in (summary.get("uncertain_points") or []) + (summary.get("supporting_points") or []) + (summary.get("refuting_points") or []):
                if point_has_fallback_incomparable_signal(point):
                    incomparable_like = True
                    break
        if centrality == "core" and unsupported_like:
            unsupported_core_claim_count += 1
            if mode == "event_result":
                core_result_unsupported_count += 1
            elif mode in {"date_fact", "schedule_fact"}:
                core_date_unsupported_count += 1
            elif mode == "numeric_fact":
                core_numeric_unsupported_count += 1
        if incomparable_like:
            partial_but_incomparable_count += 1
        if (
            centrality in {"supporting", "peripheral"}
            and stated_as_fact
            and mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result", "entity_fact"}
        ):
            if unsupported_like:
                supporting_structured_detail_count += 1
            elif incomparable_like:
                supporting_structured_incomparable_count += 1
        if (
            centrality == "core"
            and
            mode == "route_fact"
            and unsupported_like
            and re.search(r"(唯一|必经|根本不需要|不需要经过|无需经过|完全绕开|only route|without crossing)", claim_text, re.I)
        ):
            route_uniqueness_overclaim = True
        if (
            mode in {"date_fact", "schedule_fact"}
            and (
                incomparable_like
                or (
                    unsupported_like
                    and re.search(r"(阶段|开始|开启|结束|截止|截至|公布|发布|生效|普查)", answer_text + " " + claim_text)
                )
            )
        ):
            time_role_conflict_risk = True

    if need_type in {"current_geopolitical_status", "geopolitical_claim"} and any(
        token in answer_text for token in ["虚构", "剧本", "假设", "AI生成", "非真实新闻"]
    ):
        fictional_reality_contamination_risk = True
    if not fictional_reality_contamination_risk and need_type in {"current_geopolitical_status", "geopolitical_claim"}:
        fictional_reality_contamination_risk = bool(
            re.search(r"(未来场景|未来剧本|模拟推演|虚构设定)", answer_text + " " + question_text)
        )

    core_risk_flags: List[str] = []
    detail_risk_flags: List[str] = []
    if absolute_claim_present:
        core_risk_flags.append("absolute_claim_present")
    if forecast_as_fact_present:
        core_risk_flags.append("forecast_as_fact_present")
    if route_uniqueness_overclaim:
        core_risk_flags.append("route_uniqueness_overclaim")
    if fictional_reality_contamination_risk:
        core_risk_flags.append("fictional_reality_contamination_risk")
    if supporting_structured_detail_count > 0:
        detail_risk_flags.append("supporting_structured_detail_risk")
    if supporting_structured_incomparable_count > 0:
        detail_risk_flags.append("supporting_structured_incomparable_risk")
    if core_date_unsupported_count > 0:
        detail_risk_flags.append("core_date_unsupported")
    if core_numeric_unsupported_count > 0:
        detail_risk_flags.append("core_numeric_unsupported")
    if partial_but_incomparable_count > 0:
        detail_risk_flags.append("partial_but_incomparable_present")
    if time_role_conflict_risk:
        detail_risk_flags.append("time_role_conflict_risk")

    unsupported_signals = {
        "unsupported_core_claim_count": unsupported_core_claim_count,
        "core_result_unsupported_count": core_result_unsupported_count,
        "core_date_unsupported_count": core_date_unsupported_count,
        "core_numeric_unsupported_count": core_numeric_unsupported_count,
        "supporting_structured_detail_risk": supporting_structured_detail_count > 0,
        "supporting_structured_detail_count": supporting_structured_detail_count,
    }
    incomparable_signals = {
        "partial_but_incomparable_count": partial_but_incomparable_count,
        "time_role_conflict_risk": time_role_conflict_risk,
    }
    fictional_signals = {
        "fictional_reality_contamination_risk": fictional_reality_contamination_risk,
    }
    return {
        "certainty_profile_hint": certainty_profile,
        "absolute_claim_present": absolute_claim_present,
        "forecast_as_fact_present": forecast_as_fact_present,
        "route_uniqueness_overclaim": route_uniqueness_overclaim,
        "core_risk_flags": dedupe_keep_order(core_risk_flags),
        "detail_risk_flags": dedupe_keep_order(detail_risk_flags),
        "unsupported_signals": unsupported_signals,
        "incomparable_signals": incomparable_signals,
        "fictional_contamination_signals": fictional_signals,
        "supporting_structured_incomparable_count": supporting_structured_incomparable_count,
        "has_high_risk_feature": bool(
            absolute_claim_present
            or forecast_as_fact_present
            or route_uniqueness_overclaim
            or fictional_reality_contamination_risk
            or time_role_conflict_risk
        ),
        "has_any_unsupported": unsupported_core_claim_count > 0 or supporting_structured_detail_count > 0,
        "has_any_incomparable": partial_but_incomparable_count > 0,
    }


def has_high_risk_supporting_structured_claims(extracted: Dict[str, Any], evidence_summary: Optional[Dict[str, Any]]) -> bool:
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        centrality = str(claim.get("centrality") or "")
        if centrality not in {"supporting", "peripheral"}:
            continue
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        if not normalize_bool(source_intent.get("stated_as_fact", True), True):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
        target = str(source_intent.get("evidence_target") or "")
        if mode in {"numeric_fact", "date_fact", "schedule_fact", "entity_fact", "event_result"}:
            return True
        if target in {"prize_amount", "market_price", "market_calendar", "position_distance", "match_result"}:
            return True
    return False


def detail_claim_decidable_error_reason(
    claim: Dict[str, Any],
    summary: Optional[Dict[str, Any]],
    need_type: str,
) -> str:
    summary = summary if isinstance(summary, dict) else {}
    direct_refuting = claim_direct_refuting_points(summary)
    if any(point_is_secondary_detail_refutation(point, need_type, claim, summary) for point in direct_refuting):
        return "direct_comparable_refutation"
    for bucket in ("supporting_points", "refuting_points", "uncertain_points"):
        for point in (summary.get(bucket) or []):
            if point_is_stable_logic_detail_refutation(point, claim):
                return "stable_logic_refutation"
    return ""


def detail_claim_logic_refutation_diagnostics(
    claim: Dict[str, Any],
    summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    summary = summary if isinstance(summary, dict) else {}
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    claim_text = normalize_text(str(claim.get("claim") or ""))
    evidence_mode = normalize_text(str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or ""))
    structured_detail_retained = (
        str(claim.get("centrality") or "") in {"supporting", "peripheral"}
        and normalize_bool(source_intent.get("stated_as_fact", True), True)
        and has_structured_detail(claim_text, source_intent)
    )
    direct_supporting = claim_direct_supporting_points(summary)

    def point_text_for_logic(point: Dict[str, Any]) -> str:
        return normalize_text(
            " ".join(
                [
                    str(point.get("title") or ""),
                    str(point.get("evidence_sentence") or ""),
                    str(point.get("claim_value") or ""),
                    str(point.get("evidence_value") or ""),
                ]
            )
        )

    def is_logic_refutation_form(point: Dict[str, Any]) -> bool:
        if not isinstance(point, dict) or str(point.get("source_type") or "") != "computed":
            return False
        text = point_text_for_logic(point)
        if not text:
            return False
        has_should = bool(re.search(r"(应为|应该为|合计应为|总计应为|应当为)", text))
        has_not = bool(re.search(r"(而不是|不是|而非)", text))
        has_logic_title = "逻辑计算" in normalize_text(str(point.get("title") or ""))
        has_numeric_or_result = bool(re.search(r"\d", text) or re.search(r"(胜|负|平|比分|日期|时间|金额|票房|价格)", text))
        return (has_should and has_not) or (has_logic_title and has_numeric_or_result)

    def point_matches_logic_topic(point: Dict[str, Any], claim_obj: Dict[str, Any]) -> bool:
        text = point_text_for_logic(point)
        claim_body = normalize_text(str(claim_obj.get("claim") or ""))
        if not text or not claim_body:
            return False
        topic_rules = [
            (r"(交锋|交手|总战绩|赛季交锋|常规赛交锋)", r"(交锋|交手|总战绩|赛季交锋|常规赛交锋)"),
            (r"(赛后战绩|战绩提升至|战绩为|\d+胜\d+负)", r"(战绩|胜|负)"),
            (r"(比分|比数|战果)", r"(比分|比数|战果|胜|负)"),
            (r"(发布日期|发布日|公布日)", r"(发布日期|发布日|公布日|发布|公布)"),
            (r"(生效日|生效时间)", r"(生效日|生效时间|生效)"),
            (r"(举办日|开赛日|比赛时间|赛程)", r"(举办日|开赛日|比赛时间|赛程|举行|开赛)"),
            (r"(金额|票房|价格|市值|汇率|美元|元)", r"(金额|票房|价格|市值|汇率|美元|元)"),
            (r"(身份|归属|属于|担任|职位)", r"(身份|归属|属于|担任|职位)"),
        ]
        for claim_pattern, point_pattern in topic_rules:
            if re.search(claim_pattern, claim_body):
                return bool(re.search(point_pattern, text))
        if evidence_mode in {"date_fact", "schedule_fact"}:
            return bool(re.search(r"(日期|时间|日|月|年|发布|生效|举行|开赛)", text))
        if evidence_mode in {"numeric_fact", "event_result"}:
            return bool(re.search(r"(\d|胜|负|比分|金额|价格|涨|跌)", text))
        return True

    broad_logic_points: List[Dict[str, Any]] = []
    same_topic_logic_points: List[Dict[str, Any]] = []
    stable_logic_points: List[Dict[str, Any]] = []
    if structured_detail_retained:
        for bucket in ("supporting_points", "refuting_points", "uncertain_points"):
            for point in (summary.get(bucket) or []):
                if not isinstance(point, dict) or not is_logic_refutation_form(point):
                    continue
                broad_logic_points.append(point)
                if not point_matches_logic_topic(point, claim):
                    continue
                same_topic_logic_points.append(point)
                if point_is_stable_logic_detail_refutation(point, claim):
                    stable_logic_points.append(point)
    logic_point = stable_logic_points[0] if stable_logic_points else same_topic_logic_points[0] if same_topic_logic_points else broad_logic_points[0] if broad_logic_points else {}
    basis_text = ""
    if logic_point:
        basis_text = compact_claim_text(
            normalize_text(
                str(
                    logic_point.get("evidence_sentence")
                    or logic_point.get("title")
                    or logic_point.get("evidence_value")
                    or ""
                )
            ),
            120,
        )
    if not structured_detail_retained:
        logic_refutation_state = "not_retained"
        closure_stage = ""
        gap_reason = ""
    elif stable_logic_points:
        logic_refutation_state = "stable_logic_refutation_ready"
        closure_stage = "stable_logic_point"
        gap_reason = ""
    elif direct_supporting:
        logic_refutation_state = "shadowed_by_direct_channel"
        closure_stage = "direct_support_present"
        if same_topic_logic_points:
            gap_reason = "shadowed_by_direct_channel"
        elif broad_logic_points:
            gap_reason = "logic_point_topic_mismatch"
        else:
            gap_reason = "no_logic_refutation_candidate"
    elif not broad_logic_points:
        logic_refutation_state = "retained_without_logic_point"
        closure_stage = "no_logic_point"
        gap_reason = "no_logic_refutation_candidate"
    elif not same_topic_logic_points:
        logic_refutation_state = "logic_point_topic_mismatch"
        closure_stage = "logic_point_found"
        gap_reason = "logic_point_topic_mismatch"
    else:
        logic_refutation_state = "same_topic_logic_point_unstable"
        closure_stage = "same_topic_logic_point"
        gap_reason = "logic_refutation_closure_unstable"
    return {
        "structured_detail_retained": structured_detail_retained,
        "logic_refutation_candidate": bool(same_topic_logic_points),
        "logic_refutation_basis": basis_text,
        "logic_refutation_gap_reason": gap_reason,
        "logic_refutation_state": logic_refutation_state,
        "logic_refutation_closure_stage": closure_stage,
        "logic_refutation_block_reason": gap_reason,
    }


def claim_has_decidable_detail_error(
    claim: Dict[str, Any],
    summary: Optional[Dict[str, Any]],
    need_type: str,
) -> bool:
    detail_state = detail_claim_resolution_state(claim, summary, need_type)
    return str(detail_state.get("state") or "") == "decidable_error"


def iter_high_risk_detail_claim_contexts(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], Dict[str, Any], str, str]]:
    if not isinstance(evidence_summary, dict):
        return []
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    need_type = normalize_need_type(extracted.get("need_type"))
    contexts: List[Tuple[Dict[str, Any], Dict[str, Any], str, str]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if str(claim.get("centrality") or "") not in {"supporting", "peripheral"}:
            continue
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        if not normalize_bool(source_intent.get("stated_as_fact", True), True):
            continue
        mode = str(source_intent.get("evidence_mode") or "")
        if mode not in HIGH_RISK_SUPPORTING_EVIDENCE_MODES:
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        contexts.append((claim, summary, need_type, mode))
    return contexts


def has_unresolved_high_risk_detail_claims(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> bool:
    for claim, summary, need_type, _mode in iter_high_risk_detail_claim_contexts(extracted, evidence_summary):
        detail_state = detail_claim_resolution_state(claim, summary, need_type)
        if str(detail_state.get("state") or "") == "unresolved":
            return True
    return False


def detail_claim_resolution_state(
    claim: Dict[str, Any],
    summary: Optional[Dict[str, Any]],
    need_type: str,
) -> Dict[str, Any]:
    summary = summary if isinstance(summary, dict) else {}
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    claim_id = str(claim.get("claim_id") or claim.get("id") or "")
    coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
    coverage_level = str(coverage.get("coverage_level") or "")
    profile = summary.get("comparability_profile") if isinstance(summary.get("comparability_profile"), dict) else claim_comparability_profile(claim, summary)
    direct_supporting = claim_direct_supporting_points(summary)
    error_reason = detail_claim_decidable_error_reason(claim, summary, need_type)
    logic_diag = detail_claim_logic_refutation_diagnostics(claim, summary)
    if error_reason:
        return {
            "claim_id": claim_id,
            "state": "decidable_error",
            "reason": error_reason,
            "coverage_level": coverage_level,
            "comparability_status": str(profile.get("comparability_status") or "unsupported"),
            **logic_diag,
            "logic_refutation_gap_reason": "",
        }
    if direct_supporting:
        return {
            "claim_id": claim_id,
            "state": "resolved_support",
            "reason": "direct_support_present",
            "coverage_level": coverage_level,
            "comparability_status": str(profile.get("comparability_status") or "unsupported"),
            **logic_diag,
        }
    status = str(profile.get("comparability_status") or "unsupported")
    if status == "partial_but_incomparable":
        return {
            "claim_id": claim_id,
            "state": "unresolved",
            "reason": "partial_but_incomparable",
            "coverage_level": coverage_level,
            "comparability_status": status,
            **logic_diag,
        }
    if coverage_level in {"none", "weak", "partial"}:
        return {
            "claim_id": claim_id,
            "state": "unresolved",
            "reason": "unsupported_or_weak_coverage",
            "coverage_level": coverage_level,
            "comparability_status": status,
            **logic_diag,
        }
    return {
        "claim_id": claim_id,
        "state": "unresolved",
        "reason": "no_decidable_detail_signal",
        "coverage_level": coverage_level,
        "comparability_status": status,
        **logic_diag,
    }


def high_risk_detail_claim_diagnostics(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for claim, summary, need_type, mode in iter_high_risk_detail_claim_contexts(extracted, evidence_summary):
        row = detail_claim_resolution_state(claim, summary, need_type)
        row["claim"] = normalize_text(str(claim.get("claim") or ""))[:160]
        row["mode"] = mode
        rows.append(row)
    return rows


def evidence_first_audit(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(evidence_summary, dict):
        return {"core_claims": [], "high_risk_detail_claims": [], "supports_label2_lock": False}
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    need_type = normalize_need_type(extracted.get("need_type"))
    core_rows: List[Dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict) or str(claim.get("centrality") or "") != "core":
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        if claim_has_new_scheme_strong_refutation(claim, summary, need_type):
            state = "strong_refute"
            reason = "direct_refutation"
        elif claim_has_new_scheme_strong_support(claim, summary, need_type):
            state = "strong_support"
            reason = "direct_support"
        else:
            state = "unresolved"
            reason = "no_direct_decidable_core_signal"
        core_rows.append(
            {
                "claim_id": claim_id,
                "claim": normalize_text(str(claim.get("claim") or ""))[:160],
                "state": state,
                "reason": reason,
            }
        )
    detail_rows = high_risk_detail_claim_diagnostics(extracted, evidence_summary)
    unresolved_details = [row for row in detail_rows if row.get("state") == "unresolved"]
    return {
        "core_claims": core_rows,
        "high_risk_detail_claims": detail_rows,
        "unresolved_high_risk_detail_claim_ids": [str(row.get("claim_id") or "") for row in unresolved_details],
        "supports_label2_lock": has_new_scheme_core_supporting_evidence(extracted, evidence_summary) and not unresolved_details,
    }


def candidate_slot_coverage_summary(
    candidate_slot_coverage: Optional[Dict[str, Any]],
    top_candidate_slot_match: str,
) -> str:
    coverage = candidate_slot_coverage if isinstance(candidate_slot_coverage, dict) else {}
    ordered_slots = [
        "subject",
        "time_scope",
        "metric_or_relation",
        "status_or_result",
        "date_role",
        "result_granularity",
    ]
    hit_slots = [slot for slot in ordered_slots if coverage.get(slot) is True]
    if hit_slots:
        return "+".join(hit_slots)
    legacy_parts = [
        normalize_text(str(part or ""))
        for part in str(top_candidate_slot_match or "").split("+")
        if normalize_text(str(part or ""))
    ]
    if legacy_parts:
        return "+".join(legacy_parts[:4])
    slot_count = int(coverage.get("slot_count") or 0)
    if slot_count > 0:
        return f"slot_count={slot_count}"
    return ""


def infer_candidate_promotion_basis(
    direct_candidate_promotion_used: int,
    candidate_slot_coverage: Optional[Dict[str, Any]],
    top_candidate_slot_match: str,
    candidate_directness_rank: int,
) -> str:
    if direct_candidate_promotion_used <= 0:
        return ""
    slot_summary = candidate_slot_coverage_summary(candidate_slot_coverage, top_candidate_slot_match)
    if slot_summary:
        return f"{slot_summary}|rank={candidate_directness_rank}"
    return f"rank={candidate_directness_rank}"


def infer_candidate_promotion_block_reason(
    direct_candidate_promotion_used: int,
    direct_candidate_gap_reason: str,
    point_conversion_block_reason: str,
    sentence_candidate_profile: Optional[Dict[str, int]],
    candidate_slot_coverage: Optional[Dict[str, Any]],
) -> str:
    if direct_candidate_promotion_used > 0:
        return ""
    coverage = candidate_slot_coverage if isinstance(candidate_slot_coverage, dict) else {}
    profile = sentence_candidate_profile if isinstance(sentence_candidate_profile, dict) else {}
    if direct_candidate_gap_reason in {
        "opening_slot_mismatch",
        "date_role_mismatch",
        "result_granularity_mismatch",
        "numeric_reference_only",
        "date_reference_only",
        "commentary_only",
    }:
        return direct_candidate_gap_reason
    if point_conversion_block_reason in {
        "not_same_fact_slot",
        "date_role_mismatch",
        "result_granularity_mismatch",
        "numeric_not_normalizable",
    }:
        return point_conversion_block_reason
    if int(profile.get("background_commentary") or 0) > 0 and int(profile.get("direct_candidate") or 0) <= 0:
        return "background_commentary_topranked"
    slot_count = int(coverage.get("slot_count") or 0)
    if slot_count >= 2:
        return "slot_hit_but_indirect"
    return "candidate_not_direct"


def infer_access_path_state(
    environment_block_reason: str,
    raw_results: int,
    kept_web: int,
    answer_candidate_total: int,
    recall_probe_used: int,
    recall_probe_raw_hits: int,
    direct_candidate_rescue_used: int,
    diagnostic_access_path_state: str = "",
    source_budget_cutoff: Optional[Dict[str, Any]] = None,
) -> str:
    if diagnostic_access_path_state:
        return diagnostic_access_path_state
    source_budget_cutoff = source_budget_cutoff if isinstance(source_budget_cutoff, dict) else {}
    if source_budget_cutoff.get("applied") and raw_results <= 0:
        return "source_budget_cutoff"
    if environment_block_reason == "source_access_blocked_without_rescue":
        return "source_access_blocked"
    if environment_block_reason in {"requests_blocked_playwright_failed", "detail_read_failed_after_fetch"}:
        return "page_access_or_read_blocked"
    if raw_results <= 0 and recall_probe_used > 0 and recall_probe_raw_hits <= 0:
        return "provider_recall_insufficient_after_probe"
    if raw_results <= 0:
        return "provider_recall_insufficient"
    if kept_web > 0 or answer_candidate_total > 0 or direct_candidate_rescue_used > 0:
        return "partial_progress_available"
    return "raw_results_returned"


def infer_access_block_source(
    environment_block_reason: str,
    news_family_state: str,
    html_family_state: str,
    diagnostic_access_block_source: str = "",
) -> str:
    if diagnostic_access_block_source:
        return diagnostic_access_block_source
    if environment_block_reason == "source_access_blocked_without_rescue":
        if "blocked" in news_family_state and "blocked" in html_family_state:
            return "news_and_html"
        if "blocked" in news_family_state:
            return "news_family"
        if "blocked" in html_family_state:
            return "html_family"
        return "provider_request_path"
    if environment_block_reason in {"requests_blocked_playwright_failed", "detail_read_failed_after_fetch"}:
        if "blocked" in html_family_state:
            return "html_family"
        return "detail_fetch_path"
    return ""


def infer_rescue_attempt_state(
    environment_block_reason: str,
    recall_probe_used: int,
    recall_probe_raw_hits: int,
    direct_candidate_rescue_used: int,
    rescue_promoted_from_filter: int,
    playwright_rescued: int,
    diagnostic_playwright_rescue_state: str = "",
) -> str:
    if direct_candidate_rescue_used > 0 or rescue_promoted_from_filter > 0:
        return "candidate_rescue_succeeded"
    if diagnostic_playwright_rescue_state == "playwright_rescue_failed":
        return "playwright_rescue_failed"
    if diagnostic_playwright_rescue_state == "playwright_rescue_skipped_by_policy":
        return "playwright_rescue_skipped_by_policy"
    if playwright_rescued > 0:
        return "playwright_rescue_succeeded"
    if recall_probe_used > 0 and recall_probe_raw_hits > 0:
        return "recall_probe_recovered_raw_results"
    if recall_probe_used > 0:
        return "recall_probe_attempted_but_failed"
    if environment_block_reason:
        return "no_rescue_recovered_progress"
    return ""


def build_retrieval_effect_review(
    evidence_bundle: Optional[Dict[str, Any]],
    timing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    diagnostics = (
        evidence_bundle.get("diagnostics_by_claim")
        if isinstance(evidence_bundle, dict) and isinstance(evidence_bundle.get("diagnostics_by_claim"), dict)
        else {}
    )
    rows = [row for row in diagnostics.values() if isinstance(row, dict)]
    authority_hits = sum(1 for row in rows if normalize_bool(row.get("official_entry_hit"), False))
    raw_positive = sum(1 for row in rows if int(row.get("raw_results") or 0) > 0)
    kept_positive = sum(1 for row in rows if int(row.get("kept_web") or 0) > 0)
    kept_progress_claims = sum(1 for row in rows if int(row.get("kept_progress_from_raw") or 0) > 0)
    anti_bot_like = sum(
        1
        for row in rows
        if str(row.get("access_path_state") or "") in {"access_blocked_but_rescuable", "access_blocked_and_unresolved"}
        or str(row.get("official_discovery_block_reason") or "") == "anti_bot_blocked"
    )
    rescue_states: Dict[str, int] = {}
    rescue_success_gates: Dict[str, int] = {}
    rescue_latency_ms = 0.0
    cost_rows = []
    stop_reasons: Dict[str, int] = {}
    for row in rows:
        state = str(row.get("playwright_rescue_state") or "")
        if not state:
            pass
        else:
            rescue_states[state] = int(rescue_states.get(state, 0) or 0) + 1
        success_gate = str(row.get("rescue_success_gate") or "")
        if success_gate:
            rescue_success_gates[success_gate] = int(rescue_success_gates.get(success_gate, 0) or 0) + 1
        rescue_latency_ms += float(row.get("rescue_latency_ms") or 0.0)
        cost_review = row.get("retrieval_cost_review") if isinstance(row.get("retrieval_cost_review"), dict) else {}
        if cost_review:
            cost_rows.append(cost_review)
        stop_reason = str(row.get("claim_retrieve_stop_reason") or "")
        if stop_reason:
            stop_reasons[stop_reason] = int(stop_reasons.get(stop_reason, 0) or 0) + 1
    avg_search_seconds = 0.0
    avg_detail_fetch_seconds = 0.0
    avg_official_discovery_seconds = 0.0
    if cost_rows:
        avg_search_seconds = round(sum(float(row.get("search_seconds") or 0.0) for row in cost_rows) / len(cost_rows), 3)
        avg_detail_fetch_seconds = round(sum(float(row.get("detail_fetch_seconds") or 0.0) for row in cost_rows) / len(cost_rows), 3)
        avg_official_discovery_seconds = round(sum(float(row.get("official_discovery_seconds") or 0.0) for row in cost_rows) / len(cost_rows), 3)
    return {
        "claim_count": len(rows),
        "raw_positive_claims": raw_positive,
        "kept_positive_claims": kept_positive,
        "kept_progress_claims": kept_progress_claims,
        "authority_hit_claims": authority_hits,
        "anti_bot_or_access_blocked_claims": anti_bot_like,
        "playwright_rescue_states": rescue_states,
        "rescue_success_gates": rescue_success_gates,
        "avg_rescue_latency_ms": round(rescue_latency_ms / max(1, len(rows)), 1),
        "avg_search_seconds": avg_search_seconds,
        "avg_detail_fetch_seconds": avg_detail_fetch_seconds,
        "avg_official_discovery_seconds": avg_official_discovery_seconds,
        "claim_stop_reasons": stop_reasons,
        "retrieve_seconds": round(float((timing or {}).get("retrieve") or 0.0), 3),
        "total_so_far_seconds": round(float((timing or {}).get("total_so_far") or 0.0), 3),
    }


DECISION_CHANNEL_DIRECT_WEB = "direct_web_evidence"
DECISION_CHANNEL_CLOSURE = "closure_refutation"
DECISION_CHANNEL_UNRESOLVED = "insufficient_or_unresolved"

LLM_QUERY_PLANNER_FAMILIES = {"date_fact", "schedule_fact", "route_fact", "event_result"}
LLM_EVIDENCE_REFINER_FAMILIES = {"date_fact", "schedule_fact", "route_fact", "event_result"}
LLM_EVIDENCE_REFINER_BLOCK_REASONS = {
    "candidate_not_direct",
    "not_same_fact_slot",
    "date_role_mismatch",
    "result_granularity_mismatch",
}


def claim_is_count_like_detail(claim: Dict[str, Any], source_intent: Dict[str, Any]) -> bool:
    claim_text = normalize_text(str(claim.get("claim") or ""))
    target = normalize_text(str(source_intent.get("evidence_target") or ""))
    if target in {"count", "total", "aggregate", "quantity", "match_result"}:
        return True
    return bool(
        re.search(r"(\d+|数量|总数|合计|累计|票房|金额|价格|市值|战绩|比分|共计|名|个|次|场)", claim_text)
    )


def infer_claim_family(
    claim: Optional[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
) -> str:
    claim = claim if isinstance(claim, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    centrality = str(claim.get("centrality") or "")
    evidence_mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
    evidence_target = str(source_intent.get("evidence_target") or "")
    if evidence_mode in {"date_fact", "schedule_fact", "route_fact", "event_result"}:
        return evidence_mode
    if evidence_mode == "numeric_fact":
        if centrality in {"supporting", "peripheral"} and claim_is_count_like_detail(claim, source_intent):
            return "numeric_count_detail"
        return "numeric_fact"
    if evidence_mode == "policy_fact":
        return "policy_fact"
    if evidence_target in {"market_calendar", "publication_date", "effective_date", "event_date"}:
        return "date_fact"
    if evidence_target in {"route_relation", "position_distance"}:
        return "route_fact"
    return evidence_mode or "general_fact"


def infer_core_binding_strength(
    claim: Dict[str, Any],
    decision_slots: Optional[Dict[str, Any]],
    direct_need: Optional[Dict[str, Any]],
) -> str:
    slots = decision_slots if isinstance(decision_slots, dict) else {}
    need = direct_need if isinstance(direct_need, dict) else {}
    filled = 0
    for key in ("subject", "object", "time_scope", "metric_or_relation", "status_or_result"):
        if normalize_text(str(slots.get(key) or "")):
            filled += 1
    must_answer = normalize_text(str(need.get("must_answer") or ""))
    centrality = str(claim.get("centrality") or "")
    if centrality == "core" and (filled >= 3 or (filled >= 2 and must_answer)):
        return "strong"
    if filled >= 2 or must_answer:
        return "medium"
    return "weak"


def infer_secondary_detail_scope(claim: Dict[str, Any], detail_state: Optional[Dict[str, Any]]) -> str:
    detail_state = detail_state if isinstance(detail_state, dict) else {}
    centrality = str(claim.get("centrality") or "")
    if centrality not in {"supporting", "peripheral"}:
        return ""
    if normalize_bool(detail_state.get("structured_detail_retained"), False):
        return "structured_detail"
    return "supporting_claim"


def infer_intended_decision_channel(
    claim: Dict[str, Any],
    claim_family: str,
    secondary_detail_scope: str,
) -> str:
    centrality = str(claim.get("centrality") or "")
    if secondary_detail_scope == "structured_detail":
        return DECISION_CHANNEL_CLOSURE
    if centrality == "core":
        return DECISION_CHANNEL_DIRECT_WEB
    if claim_family in {"date_fact", "schedule_fact", "route_fact", "event_result", "numeric_fact", "numeric_count_detail"}:
        return DECISION_CHANNEL_DIRECT_WEB
    return DECISION_CHANNEL_UNRESOLVED


def infer_channel_decision_candidate(
    direct_diag: Optional[Dict[str, Any]],
    detail_state: Optional[Dict[str, Any]],
    raw_results: int,
    kept_web: int,
    answer_candidate_total: int,
    pipeline_stage: str,
) -> str:
    direct_diag = direct_diag if isinstance(direct_diag, dict) else {}
    detail_state = detail_state if isinstance(detail_state, dict) else {}
    detail_reason = str(detail_state.get("reason") or "")
    logic_state = str(detail_state.get("logic_refutation_state") or "")
    if detail_reason == "stable_logic_refutation" or logic_state == "stable_logic_refutation_ready":
        return DECISION_CHANNEL_CLOSURE
    if normalize_bool(detail_state.get("logic_refutation_candidate"), False) or normalize_bool(detail_state.get("structured_detail_retained"), False):
        if logic_state in {
            "same_topic_logic_point_unstable",
            "logic_point_topic_mismatch",
            "shadowed_by_direct_channel",
            "retained_without_logic_point",
        }:
            return DECISION_CHANNEL_CLOSURE
    if normalize_bool(direct_diag.get("decidable"), False):
        return DECISION_CHANNEL_DIRECT_WEB
    if raw_results > 0 or kept_web > 0 or answer_candidate_total > 0 or pipeline_stage in {
        "retrieval_filter",
        "retrieval_readiness",
        "evidence_point_not_convertible",
        "evidence_partial_but_incomparable",
    }:
        return DECISION_CHANNEL_DIRECT_WEB
    return DECISION_CHANNEL_UNRESOLVED


def infer_channel_decision_confidence(
    direct_diag: Optional[Dict[str, Any]],
    detail_state: Optional[Dict[str, Any]],
    raw_results: int,
    kept_web: int,
    answer_candidate_total: int,
) -> float:
    direct_diag = direct_diag if isinstance(direct_diag, dict) else {}
    detail_state = detail_state if isinstance(detail_state, dict) else {}
    if str(detail_state.get("logic_refutation_state") or "") == "stable_logic_refutation_ready":
        return 0.86
    if normalize_bool(direct_diag.get("decidable"), False):
        return 0.95
    if normalize_bool(detail_state.get("logic_refutation_candidate"), False):
        return 0.68
    if answer_candidate_total > 0:
        return 0.62
    if kept_web > 0:
        return 0.52
    if raw_results > 0:
        return 0.38
    return 0.18


def infer_closure_chain_family(
    claim_family: str,
    secondary_detail_scope: str,
) -> str:
    if secondary_detail_scope != "structured_detail":
        return ""
    mapping = {
        "date_fact": "date_closure",
        "schedule_fact": "schedule_closure",
        "route_fact": "route_closure",
        "event_result": "result_closure",
        "numeric_count_detail": "count_closure",
        "numeric_fact": "count_closure",
    }
    return mapping.get(claim_family, "")


def infer_closure_chain_state(
    detail_state: Optional[Dict[str, Any]],
    closure_chain_family: str,
) -> str:
    detail_state = detail_state if isinstance(detail_state, dict) else {}
    if not closure_chain_family:
        return ""
    logic_state = str(detail_state.get("logic_refutation_state") or "")
    if logic_state == "stable_logic_refutation_ready":
        return "stable_ready"
    if logic_state in {
        "same_topic_logic_point_unstable",
        "logic_point_topic_mismatch",
        "retained_without_logic_point",
        "shadowed_by_direct_channel",
    }:
        return logic_state
    if normalize_bool(detail_state.get("structured_detail_retained"), False):
        return "retained_unresolved"
    return ""


def claim_direct_decidable_diagnostic(
    claim: Dict[str, Any],
    summary: Optional[Dict[str, Any]],
    need_type: str,
) -> Dict[str, Any]:
    summary = summary if isinstance(summary, dict) else {}
    claim_id = str(claim.get("claim_id") or claim.get("id") or "")
    centrality = str(claim.get("centrality") or "supporting")
    if centrality == "core":
        if claim_has_new_scheme_strong_refutation(claim, summary, need_type):
            return {
                "decidable": True,
                "stage": "evidence_direct_refutation",
                "layer": "evidence",
                "reason": "core_direct_refutation",
                "claim_id": claim_id,
            }
        if claim_has_new_scheme_strong_support(claim, summary, need_type):
            return {
                "decidable": True,
                "stage": "evidence_direct_support",
                "layer": "evidence",
                "reason": "core_direct_support",
                "claim_id": claim_id,
            }
        return {"decidable": False, "claim_id": claim_id}
    detail_state = detail_claim_resolution_state(claim, summary, need_type)
    if detail_state.get("state") == "decidable_error":
        return {
            "decidable": True,
            "stage": "evidence_decidable_detail_error",
            "layer": "evidence",
            "reason": str(detail_state.get("reason") or "detail_decidable_error"),
            "claim_id": claim_id,
        }
    if detail_state.get("state") == "resolved_support":
        return {
            "decidable": True,
            "stage": "evidence_direct_support",
            "layer": "evidence",
            "reason": str(detail_state.get("reason") or "detail_direct_support"),
            "claim_id": claim_id,
        }
    return {"decidable": False, "claim_id": claim_id}


def infer_critical_claim_blocking_state(
    claim: Dict[str, Any],
    budget_priority: str,
    blocked_at: str,
    access_path_state: str,
    raw_results: int,
    kept_web: int,
    answer_candidate_total: int,
    page_keep_review_state: Dict[str, int],
    rescue_success_gate: str,
) -> str:
    if str(claim.get("centrality") or "") != "core":
        return ""
    if budget_priority != "core_critical":
        return "core_noncritical"
    if access_path_state in {"source_access_blocked", "access_blocked_but_rescuable", "access_blocked_and_unresolved", "page_access_or_read_blocked"}:
        return access_path_state
    if rescue_success_gate == "search_result_recovered" and raw_results > 0 and kept_web <= 0:
        return "search_rescued_but_not_kept"
    if raw_results > 0 and kept_web <= 0:
        if page_keep_review_state:
            return "raw_hit_but_page_not_retained_after_review"
        return "raw_hit_but_page_not_retained"
    if kept_web > 0 and answer_candidate_total <= 0:
        return "kept_page_but_no_candidate"
    if answer_candidate_total > 0 and blocked_at in {"retrieval_readiness", "evidence_point_not_convertible"}:
        return "candidate_present_but_not_decidable"
    if blocked_at == "provider_recall":
        return "core_recall_unresolved"
    if blocked_at == "retrieval_filter":
        return "core_filter_unresolved"
    return "core_path_unresolved"


def claim_pipeline_diagnostic(
    claim: Dict[str, Any],
    diagnostic: Optional[Dict[str, Any]],
    summary: Optional[Dict[str, Any]],
    need_type: str,
) -> Dict[str, Any]:
    diagnostic = diagnostic if isinstance(diagnostic, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    claim_id = str(claim.get("claim_id") or claim.get("id") or "")
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
    point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
    profile = summary.get("comparability_profile") if isinstance(summary.get("comparability_profile"), dict) else claim_comparability_profile(claim, summary)
    responsibility = diagnostic.get("responsibility_boundary") if isinstance(diagnostic.get("responsibility_boundary"), dict) else {}
    evidence_need_program = claim.get("evidence_need_program") if isinstance(claim.get("evidence_need_program"), dict) else {}
    decision_slots = evidence_need_program.get("decision_slots") if isinstance(evidence_need_program.get("decision_slots"), dict) else {}
    direct_need = evidence_need_program.get("direct_evidence_need") if isinstance(evidence_need_program.get("direct_evidence_need"), dict) else {}
    direct_diag = claim_direct_decidable_diagnostic(claim, summary, need_type)
    detail_state = detail_claim_resolution_state(claim, summary, need_type)
    readiness_block_reason = str(diagnostic.get("readiness_block_reason") or "")
    readiness_block_layer = str(diagnostic.get("readiness_block_layer") or "")
    point_conversion_block_reason = str(point_conversion.get("block_reason") or "")
    point_conversion_block_layer = str(point_conversion.get("block_layer") or "")
    sentence_candidate_profile = (
        point_conversion.get("sentence_candidate_profile")
        if isinstance(point_conversion.get("sentence_candidate_profile"), dict)
        else {}
    )
    top_candidate_slot_match = str(point_conversion.get("top_candidate_slot_match") or "")
    candidate_slot_coverage = (
        point_conversion.get("candidate_slot_coverage")
        if isinstance(point_conversion.get("candidate_slot_coverage"), dict)
        else {}
    )
    slot_contract_state = str(point_conversion.get("slot_contract_state") or "")
    slot_coverage = point_conversion.get("slot_coverage") if isinstance(point_conversion.get("slot_coverage"), dict) else {}
    slot_missing = point_conversion.get("slot_missing") if isinstance(point_conversion.get("slot_missing"), list) else []
    slot_mismatch = point_conversion.get("slot_mismatch") if isinstance(point_conversion.get("slot_mismatch"), list) else []
    slot_conflict = point_conversion.get("slot_conflict") if isinstance(point_conversion.get("slot_conflict"), list) else []
    same_slot_ready = int(bool(point_conversion.get("same_slot_ready")))
    refute_slot_ready = int(bool(point_conversion.get("refute_slot_ready")))
    candidate_conflict_profile = (
        point_conversion.get("candidate_conflict_profile")
        if isinstance(point_conversion.get("candidate_conflict_profile"), dict)
        else {}
    )
    conflict_type = str(point_conversion.get("conflict_type") or "")
    conflict_strength = str(point_conversion.get("conflict_strength") or "")
    conflict_slot = str(point_conversion.get("conflict_slot") or "")
    claim_value = point_conversion.get("claim_value")
    evidence_value = point_conversion.get("evidence_value")
    same_slot_conflict_ready = int(bool(point_conversion.get("same_slot_conflict_ready")))
    candidate_slot_coverage_summary_text = candidate_slot_coverage_summary(candidate_slot_coverage, top_candidate_slot_match)
    direct_candidate_gap_reason = str(point_conversion.get("direct_candidate_gap_reason") or "")
    candidate_directness_rank = int(point_conversion.get("candidate_directness_rank") or 0)
    point_direct_candidate_promotion_used = int(bool(point_conversion.get("direct_candidate_promotion_used")))
    query_effective_role = str(point_conversion.get("query_effective_role") or query_effective_role_for_claim(claim))
    page_utility_score = int(point_conversion.get("page_utility_score") or 0)
    page_utility_profile = str(point_conversion.get("page_utility_profile") or "")
    decision_useful_hit = int(bool(point_conversion.get("decision_useful_hit")))
    candidate_utility_score = int(point_conversion.get("candidate_utility_score") or 0)
    slot_review_outcome = str(point_conversion.get("slot_review_outcome") or "")
    refiner_consumed = int(bool(point_conversion.get("refiner_consumed")))
    point_consumption_state = str(point_conversion.get("point_consumption_state") or "")
    direct_candidate_promotion_basis = infer_candidate_promotion_basis(
        point_direct_candidate_promotion_used,
        candidate_slot_coverage,
        top_candidate_slot_match,
        candidate_directness_rank,
    )
    candidate_promotion_block_reason = infer_candidate_promotion_block_reason(
        point_direct_candidate_promotion_used,
        direct_candidate_gap_reason,
        point_conversion_block_reason,
        sentence_candidate_profile,
        candidate_slot_coverage,
    )
    missing_required_slots = [
        str(slot)
        for slot in (diagnostic.get("missing_required_slots") or [])
        if str(slot)
    ] if isinstance(diagnostic.get("missing_required_slots"), list) else [
        str(slot) for slot in (evidence_need_program.get("missing_required_slots") or []) if str(slot)
    ]
    slot_alignment_status = str(diagnostic.get("slot_alignment_status") or "")
    environment_block_reason = str(diagnostic.get("environment_block_reason") or "")
    playwright_rescued = int(diagnostic.get("playwright_rescued") or 0)
    detail_read_failed = int(diagnostic.get("detail_read_failed") or 0)
    detail_fetch_paths = diagnostic.get("detail_fetch_paths") if isinstance(diagnostic.get("detail_fetch_paths"), dict) else {}
    direct_candidate_rescue_used = int(diagnostic.get("direct_candidate_rescue_used") or 0)
    direct_candidate_rescue_sources = diagnostic.get("direct_candidate_rescue_sources") if isinstance(diagnostic.get("direct_candidate_rescue_sources"), dict) else {}
    direct_candidate_rescue_stages = diagnostic.get("direct_candidate_rescue_stages") if isinstance(diagnostic.get("direct_candidate_rescue_stages"), dict) else {}
    rescue_promoted_from_filter = int(diagnostic.get("rescue_promoted_from_filter") or 0)
    filter_decision_profile = diagnostic.get("filter_decision_profile") if isinstance(diagnostic.get("filter_decision_profile"), dict) else {}
    recoverable_filter_reason = diagnostic.get("recoverable_filter_reason") if isinstance(diagnostic.get("recoverable_filter_reason"), dict) else {}
    hard_drop_reason = diagnostic.get("hard_drop_reason") if isinstance(diagnostic.get("hard_drop_reason"), dict) else {}
    readiness_promotion_used = int(diagnostic.get("readiness_promotion_used") or 0)
    readiness_promotion_source = diagnostic.get("readiness_promotion_source") if isinstance(diagnostic.get("readiness_promotion_source"), dict) else {}
    candidate_strength_before_keep = int(diagnostic.get("candidate_strength_before_keep") or 0)
    recall_probe_used = int(diagnostic.get("recall_probe_used") or 0)
    recall_probe_raw_hits = int(diagnostic.get("recall_probe_raw_hits") or 0)
    recall_probe_query = normalize_text(str(diagnostic.get("recall_probe_query") or ""))
    recall_probe_source = diagnostic.get("recall_probe_source") if isinstance(diagnostic.get("recall_probe_source"), list) else []
    retrieval_access_path_state = str(diagnostic.get("access_path_state") or "")
    retrieval_access_block_source = str(diagnostic.get("access_block_source") or "")
    source_budget_cutoff = diagnostic.get("source_budget_cutoff") if isinstance(diagnostic.get("source_budget_cutoff"), dict) else {}
    provider_health_snapshot = diagnostic.get("provider_health_snapshot") if isinstance(diagnostic.get("provider_health_snapshot"), list) else []
    effective_source_plan = diagnostic.get("effective_source_plan") if isinstance(diagnostic.get("effective_source_plan"), list) else []
    search_request = diagnostic.get("search_request") if isinstance(diagnostic.get("search_request"), dict) else {}
    search_policy = diagnostic.get("search_policy") if isinstance(diagnostic.get("search_policy"), dict) else {}
    search_execution_trace = diagnostic.get("search_execution_trace") if isinstance(diagnostic.get("search_execution_trace"), dict) else {}
    search_outcome = diagnostic.get("search_outcome") if isinstance(diagnostic.get("search_outcome"), dict) else {}
    playwright_rescue_state = str(diagnostic.get("playwright_rescue_state") or "")
    playwright_rescue_trigger = str(diagnostic.get("playwright_rescue_trigger") or "")
    playwright_rescue_source = str(diagnostic.get("playwright_rescue_source") or "")
    playwright_rescue_result_count = int(diagnostic.get("playwright_rescue_result_count") or 0)
    official_entry_attempted = normalize_bool(diagnostic.get("official_entry_attempted"), False)
    official_entry_hit = normalize_bool(diagnostic.get("official_entry_hit"), False)
    official_entry_source_family = str(diagnostic.get("official_entry_source_family") or "")
    official_discovery_block_reason = str(diagnostic.get("official_discovery_block_reason") or "")
    source_order_trace = diagnostic.get("source_order_trace") if isinstance(diagnostic.get("source_order_trace"), list) else []
    priority_source_dropped_stage = str(diagnostic.get("priority_source_dropped_stage") or "")
    final_source_selection_reason = str(diagnostic.get("final_source_selection_reason") or "")
    final_executed_source_order = diagnostic.get("final_executed_source_order") if isinstance(diagnostic.get("final_executed_source_order"), list) else []
    authority_pair_preserved = normalize_bool(diagnostic.get("authority_pair_preserved"), False)
    rescue_roi_state = str(diagnostic.get("rescue_roi_state") or "")
    rescue_skip_reason = str(diagnostic.get("rescue_skip_reason") or "")
    rescue_latency_ms = float(diagnostic.get("rescue_latency_ms") or 0.0)
    family_rescue_budget_used = diagnostic.get("family_rescue_budget_used") if isinstance(diagnostic.get("family_rescue_budget_used"), dict) else {}
    source_latency_profile = diagnostic.get("source_latency_profile") if isinstance(diagnostic.get("source_latency_profile"), dict) else {}
    slow_source_cutoff = diagnostic.get("slow_source_cutoff") if isinstance(diagnostic.get("slow_source_cutoff"), list) else []
    claim_retrieve_stop_reason = str(diagnostic.get("claim_retrieve_stop_reason") or "")
    retrieval_cost_review = diagnostic.get("retrieval_cost_review") if isinstance(diagnostic.get("retrieval_cost_review"), dict) else {}
    refutation_target = diagnostic.get("refutation_target") if isinstance(diagnostic.get("refutation_target"), dict) else {}
    refutation_query_plan = diagnostic.get("refutation_query_plan") if isinstance(diagnostic.get("refutation_query_plan"), list) else []
    refutation_retry_trigger = str(diagnostic.get("refutation_retry_trigger") or "")
    refutation_slot_gap = diagnostic.get("refutation_slot_gap") if isinstance(diagnostic.get("refutation_slot_gap"), list) else []
    refutation_search_result = str(diagnostic.get("refutation_search_result") or "")
    refutation_retrieval_stop_reason = str(diagnostic.get("refutation_retrieval_stop_reason") or "")
    contrastive_query_plan = diagnostic.get("contrastive_query_plan") if isinstance(diagnostic.get("contrastive_query_plan"), dict) else {}
    contrastive_retry_trigger = str(diagnostic.get("contrastive_retry_trigger") or "")
    contrastive_slot_gap = diagnostic.get("contrastive_slot_gap") if isinstance(diagnostic.get("contrastive_slot_gap"), list) else []
    contrastive_search_result = str(diagnostic.get("contrastive_search_result") or "")
    contrastive_stop_reason = str(diagnostic.get("contrastive_stop_reason") or "")
    page_keep_review_state = diagnostic.get("page_keep_review_state") if isinstance(diagnostic.get("page_keep_review_state"), dict) else {}
    page_keep_review_reason = diagnostic.get("page_keep_review_reason") if isinstance(diagnostic.get("page_keep_review_reason"), dict) else {}
    filtered_rescue_pool_state = str(diagnostic.get("filtered_rescue_pool_state") or "")
    filtered_rescue_pool_reason = str(diagnostic.get("filtered_rescue_pool_reason") or "")
    filtered_rescue_pool_score = int(diagnostic.get("filtered_rescue_pool_score") or 0)
    filtered_rescue_pool_promoted = int(diagnostic.get("filtered_rescue_pool_promoted") or 0)
    second_pass_keep_review_used = int(diagnostic.get("second_pass_keep_review_used") or 0)
    second_pass_keep_review_reason = diagnostic.get("second_pass_keep_review_reason") if isinstance(diagnostic.get("second_pass_keep_review_reason"), dict) else {}
    second_pass_keep_recovered_count = int(diagnostic.get("second_pass_keep_recovered_count") or 0)
    core_keep_review_block_reason = diagnostic.get("core_keep_review_block_reason") if isinstance(diagnostic.get("core_keep_review_block_reason"), dict) else {}
    kept_candidate_source_type = diagnostic.get("kept_candidate_source_type") if isinstance(diagnostic.get("kept_candidate_source_type"), dict) else {}
    kept_progress_from_raw = int(diagnostic.get("kept_progress_from_raw") or 0)
    rescue_progress_delta = diagnostic.get("rescue_progress_delta") if isinstance(diagnostic.get("rescue_progress_delta"), dict) else {}
    rescue_success_gate = str(diagnostic.get("rescue_success_gate") or "")
    rescue_target_page_type = str(diagnostic.get("rescue_target_page_type") or "")
    rescue_non_roi_reason = str(diagnostic.get("rescue_non_roi_reason") or "")
    raw_results = int(diagnostic.get("raw_results") or 0)
    kept_web = int(diagnostic.get("kept_web") or 0)
    answer_candidate_total = int(diagnostic.get("answer_candidate_total") or 0)
    claim_budget_priority_label_value = str(claim.get("_claim_budget_priority") or claim_budget_priority_label(claim))
    core_claim_budget_reserved = normalize_bool(claim.get("_core_claim_budget_reserved"), False)
    supporting_claim_deprioritized = normalize_bool(claim.get("_supporting_claim_deprioritized"), False)
    news_family_state = str(responsibility.get("news_family_state") or "")
    html_family_state = str(responsibility.get("html_family_state") or "")
    access_path_state = infer_access_path_state(
        environment_block_reason,
        raw_results,
        kept_web,
        answer_candidate_total,
        recall_probe_used,
        recall_probe_raw_hits,
        direct_candidate_rescue_used,
        retrieval_access_path_state,
        source_budget_cutoff,
    )
    access_block_source = infer_access_block_source(
        environment_block_reason,
        news_family_state,
        html_family_state,
        retrieval_access_block_source,
    )
    rescue_attempt_state = infer_rescue_attempt_state(
        environment_block_reason,
        recall_probe_used,
        recall_probe_raw_hits,
        direct_candidate_rescue_used,
        rescue_promoted_from_filter,
        playwright_rescued,
        playwright_rescue_state,
    )
    claim_family = infer_claim_family(claim, summary)
    core_binding_strength = infer_core_binding_strength(claim, decision_slots, direct_need)
    secondary_detail_scope = infer_secondary_detail_scope(claim, detail_state)
    closure_chain_family = infer_closure_chain_family(claim_family, secondary_detail_scope)
    closure_chain_state = infer_closure_chain_state(detail_state, closure_chain_family)
    closure_chain_block_reason = str(detail_state.get("logic_refutation_block_reason") or "")
    intended_decision_channel = infer_intended_decision_channel(
        claim,
        claim_family,
        secondary_detail_scope,
    )
    if direct_diag.get("decidable"):
        blocked_at = str(direct_diag.get("stage") or "evidence_direct_decidable")
        boundary_reason = str(direct_diag.get("reason") or "direct_decidable")
        pipeline_layer = "evidence"
    else:
        comparability_status = str(profile.get("comparability_status") or "unsupported")
        coverage_level = str(coverage.get("coverage_level") or "")
        conversion_stage = str(point_conversion.get("stage") or "")
        responsibility_layer = str(responsibility.get("responsibility_layer") or "")
        responsibility_stage = str(responsibility.get("stop_stage") or "")
        if responsibility_layer == "provider_recall":
            blocked_at = "provider_recall"
            if environment_block_reason == "source_access_blocked_without_rescue":
                boundary_reason = "检索源请求阶段疑似被拦截，原始结果没有稳定拿回"
            else:
                boundary_reason = str(responsibility.get("reason") or diagnostic.get("reason") or "检索源没有拿回原始结果")
            pipeline_layer = "provider_recall"
        elif (
            responsibility_layer == "retrieval_filter"
            and int(diagnostic.get("kept_web") or 0) > 0
            and (direct_candidate_rescue_used > 0 or rescue_promoted_from_filter > 0)
        ):
            blocked_at = "retrieval_readiness"
            boundary_reason = "近失页或保留页已补出候选句，但还没有形成稳定可直裁的 ready material"
            pipeline_layer = "retrieval_readiness"
        elif responsibility_layer == "retrieval_filter":
            blocked_at = "retrieval_filter"
            if environment_block_reason == "requests_blocked_playwright_failed":
                boundary_reason = "相关页面出现过，但正文读取受阻，可用材料没有稳定留下"
            else:
                boundary_reason = str(responsibility.get("reason") or diagnostic.get("reason") or "检索层未留下可直接使用的网页材料")
            pipeline_layer = "retrieval_filter"
        elif responsibility_layer == "retrieval_readiness":
            blocked_at = "retrieval_readiness"
            if environment_block_reason in {"requests_blocked_playwright_failed", "detail_read_failed_after_fetch"}:
                boundary_reason = "页面已保留，但正文或关键段落读取受阻，还没整理出可直接比对的候选句"
            else:
                boundary_reason = str(responsibility.get("reason") or diagnostic.get("reason") or "检索层未留下可直接使用的网页材料")
            pipeline_layer = responsibility_layer
        elif int(diagnostic.get("raw_results") or 0) > 0 and int(diagnostic.get("kept_web") or 0) > 0 and slot_alignment_status in {
            "missing_required_slots",
            "anchor_only",
            "structured_unbound",
            "candidate_slot_weak",
        }:
            blocked_at = "retrieval_readiness"
            boundary_reason = "页面已经留下，但关键事实位点还没有在候选页或候选句上对齐"
            pipeline_layer = "retrieval_readiness"
        elif comparability_status == "partial_but_incomparable":
            blocked_at = "evidence_partial_but_incomparable"
            boundary_reason = "检索到了相关材料，但同一事实位点没有对齐，当前不能直接裁决"
            pipeline_layer = "evidence"
        elif conversion_stage == "direct_not_converted":
            blocked_at = "evidence_point_not_convertible"
            boundary_reason = "网页材料已读到，但还没转成可裁决的结构化点"
            pipeline_layer = "evidence"
        elif coverage_level in UNSUPPORTED_COVERAGE_LEVELS:
            blocked_at = "evidence_unsupported"
            boundary_reason = "已有材料不足以形成可比较、可直裁的证据点"
            pipeline_layer = "evidence"
        else:
            blocked_at = "mixed_or_review_needed"
            boundary_reason = "当前链路不是单点阻塞，更像多层薄弱信号叠加"
            pipeline_layer = "mixed"
    channel_decision_candidate = infer_channel_decision_candidate(
        direct_diag,
        detail_state,
        raw_results,
        kept_web,
        answer_candidate_total,
        blocked_at,
    )
    channel_decision_confidence = infer_channel_decision_confidence(
        direct_diag,
        detail_state,
        raw_results,
        kept_web,
        answer_candidate_total,
    )
    critical_claim_blocking_state = infer_critical_claim_blocking_state(
        claim,
        claim_budget_priority_label_value,
        blocked_at,
        access_path_state,
        raw_results,
        kept_web,
        answer_candidate_total,
        page_keep_review_state,
        rescue_success_gate,
    )
    return {
        "claim_id": claim_id,
        "claim": normalize_text(str(claim.get("claim") or ""))[:160],
        "centrality": str(claim.get("centrality") or "supporting"),
        "evidence_mode": str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or ""),
        "claim_family": claim_family,
        "intended_decision_channel": intended_decision_channel,
        "query_effective_role": query_effective_role,
        "page_utility_score": page_utility_score,
        "page_utility_profile": page_utility_profile,
        "decision_useful_hit": decision_useful_hit,
        "candidate_utility_score": candidate_utility_score,
        "slot_review_outcome": slot_review_outcome,
        "refiner_consumed": refiner_consumed,
        "point_consumption_state": point_consumption_state,
        "core_binding_strength": core_binding_strength,
        "secondary_detail_scope": secondary_detail_scope,
        "channel_decision_candidate": channel_decision_candidate,
        "channel_decision_confidence": round(channel_decision_confidence, 3),
        "claim_budget_priority": claim_budget_priority_label_value,
        "core_claim_budget_reserved": core_claim_budget_reserved,
        "supporting_claim_deprioritized": supporting_claim_deprioritized,
        "critical_claim_blocking_state": critical_claim_blocking_state,
        "pipeline_layer": pipeline_layer,
        "pipeline_stage": blocked_at,
        "pipeline_reason": boundary_reason,
        "comparability_status": str(profile.get("comparability_status") or "unsupported"),
        "coverage_level": str(coverage.get("coverage_level") or ""),
        "point_conversion_stage": str(point_conversion.get("stage") or ""),
        "retrieval_quality_stage": str(diagnostic.get("retrieval_quality_stage") or ""),
        "responsibility_layer": str(responsibility.get("responsibility_layer") or ""),
        "responsibility_stage": str(responsibility.get("stop_stage") or ""),
        "readiness_block_reason": readiness_block_reason,
        "readiness_block_layer": readiness_block_layer,
        "point_conversion_block_reason": point_conversion_block_reason,
        "point_conversion_block_layer": point_conversion_block_layer,
        "sentence_candidate_profile": sentence_candidate_profile,
        "top_candidate_slot_match": top_candidate_slot_match,
        "candidate_slot_coverage": candidate_slot_coverage,
        "slot_contract_state": slot_contract_state,
        "slot_coverage": slot_coverage,
        "slot_missing": slot_missing[:5],
        "slot_mismatch": slot_mismatch[:5],
        "slot_conflict": slot_conflict[:5],
        "same_slot_ready": same_slot_ready,
        "refute_slot_ready": refute_slot_ready,
        "candidate_conflict_profile": candidate_conflict_profile,
        "conflict_type": conflict_type,
        "conflict_strength": conflict_strength,
        "conflict_slot": conflict_slot,
        "claim_value": claim_value,
        "evidence_value": evidence_value,
        "same_slot_conflict_ready": same_slot_conflict_ready,
        "direct_candidate_gap_reason": direct_candidate_gap_reason,
        "candidate_directness_rank": candidate_directness_rank,
        "direct_candidate_promotion_used": point_direct_candidate_promotion_used,
        "missing_required_slots": missing_required_slots[:4],
        "slot_alignment_status": slot_alignment_status,
        "environment_block_reason": environment_block_reason,
        "playwright_rescued": playwright_rescued,
        "detail_read_failed": detail_read_failed,
        "detail_fetch_paths": detail_fetch_paths,
        "direct_candidate_rescue_used": direct_candidate_rescue_used,
        "direct_candidate_rescue_sources": direct_candidate_rescue_sources,
        "direct_candidate_rescue_stages": direct_candidate_rescue_stages,
        "rescue_promoted_from_filter": rescue_promoted_from_filter,
        "filter_decision_profile": filter_decision_profile,
        "recoverable_filter_reason": recoverable_filter_reason,
        "hard_drop_reason": hard_drop_reason,
        "readiness_promotion_used": readiness_promotion_used,
        "readiness_promotion_source": readiness_promotion_source,
        "candidate_strength_before_keep": candidate_strength_before_keep,
        "recall_probe_used": recall_probe_used,
        "recall_probe_raw_hits": recall_probe_raw_hits,
        "recall_probe_query": recall_probe_query,
        "recall_probe_source": recall_probe_source[:4],
        "source_budget_cutoff": source_budget_cutoff,
        "provider_health_snapshot": provider_health_snapshot[:5],
        "effective_source_plan": effective_source_plan[:10],
        "search_request": search_request,
        "search_policy": search_policy,
        "search_execution_trace": search_execution_trace,
        "search_outcome": search_outcome,
        "playwright_rescue_state": playwright_rescue_state,
        "playwright_rescue_trigger": playwright_rescue_trigger,
        "playwright_rescue_source": playwright_rescue_source,
        "playwright_rescue_result_count": playwright_rescue_result_count,
        "rescue_roi_state": rescue_roi_state,
        "rescue_skip_reason": rescue_skip_reason,
        "rescue_latency_ms": round(rescue_latency_ms, 1),
        "family_rescue_budget_used": family_rescue_budget_used,
        "official_entry_attempted": official_entry_attempted,
        "official_entry_hit": official_entry_hit,
        "official_entry_source_family": official_entry_source_family,
        "official_discovery_block_reason": official_discovery_block_reason,
        "source_order_trace": source_order_trace[:8],
        "priority_source_dropped_stage": priority_source_dropped_stage,
        "final_source_selection_reason": final_source_selection_reason,
        "final_executed_source_order": final_executed_source_order[:10],
        "authority_pair_preserved": authority_pair_preserved,
        "source_latency_profile": source_latency_profile,
        "slow_source_cutoff": slow_source_cutoff[:5],
        "claim_retrieve_stop_reason": claim_retrieve_stop_reason,
        "retrieval_cost_review": retrieval_cost_review,
        "refutation_target": refutation_target,
        "refutation_query_plan": refutation_query_plan[:3],
        "refutation_retry_trigger": refutation_retry_trigger,
        "refutation_slot_gap": refutation_slot_gap[:5],
        "refutation_search_result": refutation_search_result,
        "refutation_retrieval_stop_reason": refutation_retrieval_stop_reason,
        "contrastive_query_plan": contrastive_query_plan,
        "contrastive_retry_trigger": contrastive_retry_trigger,
        "contrastive_slot_gap": contrastive_slot_gap[:5],
        "contrastive_search_result": contrastive_search_result,
        "contrastive_stop_reason": contrastive_stop_reason,
        "atomic_query_plan": diagnostic.get("atomic_query_plan") if isinstance(diagnostic.get("atomic_query_plan"), list) else [],
        "atomic_retrieval_attempted": bool(diagnostic.get("atomic_retrieval_attempted")),
        "atomic_query_limit": int(diagnostic.get("atomic_query_limit") or 0),
        "atomic_search_results": diagnostic.get("atomic_search_results") if isinstance(diagnostic.get("atomic_search_results"), list) else [],
        "atomic_gate_result": str(diagnostic.get("atomic_gate_result") or ""),
        "atomic_stop_reason": str(diagnostic.get("atomic_stop_reason") or ""),
        "page_keep_review_state": page_keep_review_state,
        "page_keep_review_reason": page_keep_review_reason,
        "filtered_rescue_pool_state": filtered_rescue_pool_state,
        "filtered_rescue_pool_reason": filtered_rescue_pool_reason,
        "filtered_rescue_pool_score": filtered_rescue_pool_score,
        "filtered_rescue_pool_promoted": filtered_rescue_pool_promoted,
        "second_pass_keep_review_used": second_pass_keep_review_used,
        "second_pass_keep_review_reason": second_pass_keep_review_reason,
        "second_pass_keep_recovered_count": second_pass_keep_recovered_count,
        "core_keep_review_block_reason": core_keep_review_block_reason,
        "kept_candidate_source_type": kept_candidate_source_type,
        "kept_progress_from_raw": kept_progress_from_raw,
        "rescue_progress_delta": rescue_progress_delta,
        "rescue_success_gate": rescue_success_gate,
        "rescue_target_page_type": rescue_target_page_type,
        "rescue_non_roi_reason": rescue_non_roi_reason,
        "program_expected_failure_stage": str(evidence_need_program.get("expected_failure_stage") or ""),
        "program_anchor_buckets": list(decision_slots.get("anchor_buckets") or [])[:6] if isinstance(decision_slots, dict) else [],
        "program_direct_evidence_need": compact_claim_text(str(direct_need.get("must_answer") or ""), 120),
        "program_false_friend_evidence": compact_term_list(evidence_need_program.get("false_friend_evidence") or [], 3, 90),
        "news_family_state": news_family_state,
        "html_family_state": html_family_state,
        "raw_results": raw_results,
        "kept_web": kept_web,
        "answer_candidate_total": answer_candidate_total,
        "direct_support_points": len(claim_direct_supporting_points(summary)),
        "direct_refute_points": len(claim_direct_refuting_points(summary)),
        "structured_detail_retained": int(bool(detail_state.get("structured_detail_retained"))),
        "logic_refutation_candidate": int(bool(detail_state.get("logic_refutation_candidate"))),
        "logic_refutation_basis": compact_claim_text(str(detail_state.get("logic_refutation_basis") or ""), 120),
        "logic_refutation_gap_reason": str(detail_state.get("logic_refutation_gap_reason") or ""),
        "logic_refutation_state": str(detail_state.get("logic_refutation_state") or ""),
        "logic_refutation_closure_stage": str(detail_state.get("logic_refutation_closure_stage") or ""),
        "logic_refutation_block_reason": str(detail_state.get("logic_refutation_block_reason") or ""),
        "closure_chain_state": closure_chain_state,
        "closure_chain_family": closure_chain_family,
        "closure_chain_block_reason": closure_chain_block_reason,
        "direct_candidate_promotion_basis": direct_candidate_promotion_basis,
        "candidate_promotion_block_reason": candidate_promotion_block_reason,
        "candidate_slot_coverage_summary": candidate_slot_coverage_summary_text,
        "access_path_state": access_path_state,
        "access_block_source": access_block_source,
        "rescue_attempt_state": rescue_attempt_state,
    }


def build_claim_pipeline_diagnostics(
    extracted: Dict[str, Any],
    evidence_bundle: Optional[Dict[str, Any]],
    evidence_summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    diagnostics = (
        evidence_bundle.get("diagnostics_by_claim")
        if isinstance(evidence_bundle, dict) and isinstance(evidence_bundle.get("diagnostics_by_claim"), dict)
        else {}
    )
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    need_type = normalize_need_type(extracted.get("need_type"))
    items: List[Dict[str, Any]] = []
    layer_counts: Dict[str, int] = {}
    stage_counts: Dict[str, int] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        diagnostic = diagnostics.get(claim_id) if isinstance(diagnostics.get(claim_id), dict) else {}
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        row = claim_pipeline_diagnostic(claim, diagnostic, summary, need_type)
        items.append(row)
        layer = str(row.get("pipeline_layer") or "unknown")
        stage = str(row.get("pipeline_stage") or "unknown")
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    retrieval_effect_review = {
        "claim_count": len(items),
        "raw_positive_claims": sum(1 for row in items if int(row.get("raw_results") or 0) > 0),
        "kept_positive_claims": sum(1 for row in items if int(row.get("kept_web") or 0) > 0),
        "kept_progress_claims": sum(1 for row in items if int(row.get("kept_progress_from_raw") or 0) > 0),
        "authority_hit_claims": sum(1 for row in items if normalize_bool(row.get("official_entry_hit"), False)),
        "atomic_retrieval_claims": sum(1 for row in items if normalize_bool(row.get("atomic_retrieval_attempted"), False)),
        "atomic_raw_positive_claims": sum(
            1
            for row in items
            if any(int(result.get("raw_hits") or 0) > 0 for result in (row.get("atomic_search_results") or []) if isinstance(result, dict))
        ),
        "atomic_kept_positive_claims": sum(
            1
            for row in items
            if any(int(result.get("kept_hits") or 0) > 0 for result in (row.get("atomic_search_results") or []) if isinstance(result, dict))
        ),
        "anti_bot_or_access_blocked_claims": sum(
            1
            for row in items
            if str(row.get("access_path_state") or "") in {"access_blocked_but_rescuable", "access_blocked_and_unresolved"}
            or str(row.get("official_discovery_block_reason") or "") == "anti_bot_blocked"
        ),
    }
    return {
        "items": items,
        "layer_counts": layer_counts,
        "stage_counts": stage_counts,
        "retrieval_effect_review": retrieval_effect_review,
    }


def has_core_route_like_claim(extracted: Dict[str, Any], evidence_summary: Optional[Dict[str, Any]]) -> bool:
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    for claim in claims:
        if not isinstance(claim, dict) or str(claim.get("centrality") or "") != "core":
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
        target = str(source_intent.get("evidence_target") or "")
        claim_text = normalize_text(str(claim.get("claim") or ""))
        if mode == "route_fact" or target == "route_relation":
            return True
        if re.search(r"(领空|空域|路线|经过|经由|飞越|绕开)", claim_text):
            return True
    return False


def should_attempt_rubric_on_implicit_unsupported(item: Dict[str, Any], extracted: Dict[str, Any], evidence_summary: Optional[Dict[str, Any]]) -> bool:
    answer_text = normalize_text(str(item.get("answer") or ""))
    if answer_has_absolute_boundary_terms(answer_text):
        return True
    if answer_has_resolved_forecast_terms(answer_text):
        return True
    if has_core_route_like_claim(extracted, evidence_summary):
        return False
    need_type = normalize_need_type(extracted.get("need_type"))
    if need_type in {"general_fact", "financial_quote", "market_movement", "schedule_time"} and has_high_risk_supporting_structured_claims(extracted, evidence_summary):
        return True
    return False


def normalize_rubric_prior_obj(obj: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return None
    label = pick_label(obj.get("prior_label"))
    if not label:
        return None
    certainty = normalize_text(str(obj.get("certainty_profile") or "")).lower()
    if certainty not in RUBRIC_CERTAINTY_PROFILES:
        certainty = "medium"
    error_scope = normalize_text(str(obj.get("error_scope") or "")).lower()
    if error_scope not in RUBRIC_ERROR_SCOPES:
        error_scope = "unknown"
    try:
        confidence = float(obj.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    risk_flags = [
        normalize_text(str(flag)).lower()
        for flag in (obj.get("risk_flags") or [])
        if normalize_text(str(flag)).lower() in RUBRIC_RISK_FLAGS
    ]
    fallback_policy = normalize_text(str(obj.get("fallback_policy") or ""))
    if fallback_policy not in RUBRIC_FALLBACK_POLICIES:
        fallback_policy = {
            LABEL_0: "rubric_core_error",
            LABEL_1: "rubric_detail_error",
            LABEL_2: "rubric_no_error",
        }[label]
    reason = compact_claim_text(str(obj.get("reason") or ""), 180)
    if not reason:
        return None
    return {
        "prior_label": label,
        "confidence": confidence,
        "certainty_profile": certainty,
        "error_scope": error_scope,
        "risk_flags": dedupe_keep_order(risk_flags)[:6],
        "fallback_policy": fallback_policy,
        "reason": reason,
    }


def adjust_rubric_prior_with_claim_shape(
    rubric_obj: Dict[str, Any],
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    fallback_risk_features: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    answer_text = normalize_text(str(item.get("answer") or ""))
    need_type = normalize_need_type(extracted.get("need_type"))
    core_route_like = has_core_route_like_claim(extracted, evidence_summary)
    fallback_risk_features = fallback_risk_features if isinstance(fallback_risk_features, dict) else {}
    unsupported_signals = fallback_risk_features.get("unsupported_signals") if isinstance(fallback_risk_features.get("unsupported_signals"), dict) else {}
    incomparable_signals = fallback_risk_features.get("incomparable_signals") if isinstance(fallback_risk_features.get("incomparable_signals"), dict) else {}
    fictional_signals = fallback_risk_features.get("fictional_contamination_signals") if isinstance(fallback_risk_features.get("fictional_contamination_signals"), dict) else {}
    high_detail_risk = normalize_bool(unsupported_signals.get("supporting_structured_detail_risk"), False)
    route_uniqueness_overclaim = normalize_bool(fallback_risk_features.get("route_uniqueness_overclaim"), False)
    forecast_as_fact = normalize_bool(fallback_risk_features.get("forecast_as_fact_present"), False)
    fictional_risk = normalize_bool(fictional_signals.get("fictional_reality_contamination_risk"), False)
    time_role_conflict = normalize_bool(incomparable_signals.get("time_role_conflict_risk"), False)
    explicit_core_risk = route_uniqueness_overclaim or forecast_as_fact or fictional_risk
    if (
        rubric_obj.get("prior_label") != LABEL_0
        and answer_has_absolute_boundary_terms(answer_text)
        and route_uniqueness_overclaim
    ):
        adjusted = dict(rubric_obj)
        adjusted["prior_label"] = LABEL_0
        adjusted["error_scope"] = "core"
        adjusted["fallback_policy"] = "rubric_core_error"
        adjusted["reason"] = "回答对核心因果或路线关系作了强绝对化断言，但当前只有部分不相容信息、没有可直接裁决的证据。"
        return adjusted
    if (
        rubric_obj.get("prior_label") != LABEL_0
        and forecast_as_fact
        and need_type in {"market_movement", "schedule_time", "current_result"}
    ):
        adjusted = dict(rubric_obj)
        adjusted["prior_label"] = LABEL_0
        adjusted["error_scope"] = "core"
        adjusted["fallback_policy"] = "rubric_core_error"
        adjusted["reason"] = "回答把未来调价时间和涨幅写成较确定事实，且涉及核心时间与核心结果的强断言，尽管当前证据不足但风险更偏核心。"
        return adjusted
    if rubric_obj.get("prior_label") != LABEL_0 and fictional_risk:
        adjusted = dict(rubric_obj)
        adjusted["prior_label"] = LABEL_0
        adjusted["error_scope"] = "core"
        adjusted["fallback_policy"] = "rubric_core_error"
        adjusted["reason"] = "回答把虚构剧本、假设推演或非现实场景混入当前现实判断，当前虽缺少可直接裁决证据，但核心风险已落在现实层污染。"
        return adjusted
    if (
        rubric_obj.get("prior_label") == LABEL_0
        and not core_route_like
        and not explicit_core_risk
        and high_detail_risk
    ):
        adjusted = dict(rubric_obj)
        adjusted["prior_label"] = LABEL_1
        adjusted["error_scope"] = "detail"
        adjusted["fallback_policy"] = "rubric_detail_error"
        if "次需" not in adjusted.get("reason", ""):
            adjusted["reason"] = "核心主结论暂未被直接推翻，但回答中的金额、日期或其他结构化细节风险更高，按次需事实错误兜底。"
        return adjusted
    if (
        rubric_obj.get("prior_label") == LABEL_2
        and not core_route_like
        and rubric_obj.get("certainty_profile") == "strong"
        and need_type == "general_fact"
        and not explicit_core_risk
        and high_detail_risk
    ):
        adjusted = dict(rubric_obj)
        adjusted["prior_label"] = LABEL_1
        adjusted["error_scope"] = "detail"
        adjusted["fallback_policy"] = "rubric_detail_error"
        adjusted["reason"] = "核心主结论暂未被直接推翻，但回答中的金额、日期或其他结构化细节属于强确定附带断言，按次需事实错误兜底。"
        return adjusted
    if rubric_obj.get("prior_label") == LABEL_1 and time_role_conflict and not high_detail_risk:
        adjusted = dict(rubric_obj)
        adjusted["reason"] = adjusted.get("reason") or "当前更像时间角色或口径混淆，先保留为不可直接裁决的细节风险，不上提为主需错误。"
        return adjusted
    return rubric_obj


def build_rubric_prior_prompt(
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    fallback_risk_features: Optional[Dict[str, Any]] = None,
    evidence_non_decidable_state: Optional[Dict[str, Any]] = None,
) -> str:
    evidence_state = compact_evidence_state_for_rubric(extracted, evidence_summary)
    if isinstance(evidence_non_decidable_state, dict):
        evidence_state["non_decidable_state"] = str(evidence_non_decidable_state.get("state") or "")
        evidence_state["non_decidable_reason"] = str(evidence_non_decidable_state.get("reason") or "")
    payload = {
        "question": normalize_text(str(item.get("question") or "")),
        "answer": normalize_text(str(item.get("answer") or "")),
        "time": normalize_text(str(item.get("time") or "")),
        "history": compact_history_for_rubric(item.get("history_question") or []),
        "need_type": normalize_need_type(extracted.get("need_type")),
        "claims": compact_claims_for_rubric(extracted, evidence_summary),
        "evidence_state": evidence_state,
        "fallback_risk_features": fallback_risk_features if isinstance(fallback_risk_features, dict) else {},
    }
    return "请根据下面输入输出 JSON：\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def legacy_fallback_preview(
    base_label: str,
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    item: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    preview: Dict[str, Any] = {
        "base_label": base_label,
        "label": base_label,
        "policy": "",
        "decision_basis": classify_decision_basis(base_label, "", evidence_summary, extracted),
        "source": "",
    }
    override_label, override_reason = evidence_override_label(extracted, evidence_summary)
    if override_label:
        preview.update(
            {
                "label": override_label,
                "policy": override_reason,
                "decision_basis": classify_decision_basis(override_label, override_reason, evidence_summary, extracted),
                "source": "evidence_override",
            }
        )
    calibrated_label, calibration_reason = regression_label_calibration(preview["label"], extracted, evidence_summary, item)
    if calibration_reason:
        preview.update(
            {
                "label": calibrated_label,
                "policy": calibration_reason,
                "decision_basis": classify_decision_basis(calibrated_label, calibration_reason, evidence_summary, extracted),
                "source": "regression_label_calibration",
            }
        )
    if preview["label"] == LABEL_2 and preview["base_label"] != LABEL_2 and not preview.get("policy"):
        preview.update(
            {
                "policy": "unsupported_claims_are_not_fact_errors",
                "decision_basis": "insufficient_evidence",
                "source": "implicit_unsupported",
            }
        )
    elif preview["label"] == LABEL_2 and preview.get("decision_basis") == "insufficient_evidence" and not preview.get("policy"):
        preview.update(
            {
                "policy": "unsupported_claims_are_not_fact_errors",
                "decision_basis": "insufficient_evidence",
                "source": "implicit_unsupported",
            }
        )
    return preview


def legacy_preview_targets_rubric(preview: Dict[str, Any]) -> bool:
    policy = str(preview.get("policy") or "")
    basis = str(preview.get("decision_basis") or "")
    if policy == "unsupported_claims_are_not_fact_errors":
        return True
    return basis in RUBRIC_TARGET_DECISION_BASES


def legacy_preview_is_actionable_calibration(preview: Dict[str, Any]) -> bool:
    if not isinstance(preview, dict):
        return False
    source = str(preview.get("source") or "")
    policy = str(preview.get("policy") or "")
    if source != "regression_label_calibration":
        return False
    if not policy or policy == "unsupported_claims_are_not_fact_errors":
        return False
    return pick_label(preview.get("label")) in VALID_LABELS


def apply_risk_calibration_result(
    result: Dict[str, Any],
    legacy_preview: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> str:
    final_label = pick_label(legacy_preview.get("label")) or LABEL_2
    calibration_policy = str(legacy_preview.get("policy") or "")
    result["_calibration_override"] = calibration_policy
    result["_calibration_source"] = str(legacy_preview.get("source") or "")
    result["_decision_basis"] = "risk_calibration"
    result["_decision_policy"] = calibration_policy
    result["_decision_policy_explanation"] = policy_reason(final_label, calibration_policy)
    result["_aggregation_analyse"] = policy_reason(final_label, calibration_policy)
    result["analyse"] = result["_aggregation_analyse"]
    result["_rubric_prior_attempted"] = False
    result["_rubric_skip_reason"] = "risk_calibration_precedes_rubric"
    result["_rubric_trigger_gate"] = {
        "allow": False,
        "reason": "risk_calibration_precedes_rubric",
    }
    result["decision_gate_consumed_diagnostics"] = False
    result["decision_gate_primary_block"] = ""
    result["reason_source_layer"] = "risk_calibration"
    return final_label


def rubric_trigger_gate(
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    fallback_risk_features: Optional[Dict[str, Any]],
    evidence_non_decidable_state: Optional[Dict[str, Any]] = None,
    claim_pipeline_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    fallback_risk_features = fallback_risk_features if isinstance(fallback_risk_features, dict) else {}
    evidence_non_decidable_state = evidence_non_decidable_state if isinstance(evidence_non_decidable_state, dict) else {}
    claim_pipeline_diagnostics = claim_pipeline_diagnostics if isinstance(claim_pipeline_diagnostics, dict) else {}
    unsupported_signals = fallback_risk_features.get("unsupported_signals") if isinstance(fallback_risk_features.get("unsupported_signals"), dict) else {}
    incomparable_signals = fallback_risk_features.get("incomparable_signals") if isinstance(fallback_risk_features.get("incomparable_signals"), dict) else {}
    fictional_signals = fallback_risk_features.get("fictional_contamination_signals") if isinstance(fallback_risk_features.get("fictional_contamination_signals"), dict) else {}
    unsupported_core_claim_count = int(unsupported_signals.get("unsupported_core_claim_count") or 0)
    partial_but_incomparable_count = int(incomparable_signals.get("partial_but_incomparable_count") or 0)
    supporting_structured_detail_risk = normalize_bool(unsupported_signals.get("supporting_structured_detail_risk"), False)
    time_role_conflict_risk = normalize_bool(incomparable_signals.get("time_role_conflict_risk"), False)
    fictional_risk = normalize_bool(fictional_signals.get("fictional_reality_contamination_risk"), False)
    certainty_profile = str(fallback_risk_features.get("certainty_profile_hint") or "medium")
    high_risk_feature = normalize_bool(fallback_risk_features.get("has_high_risk_feature"), False)
    has_any_unsupported = normalize_bool(fallback_risk_features.get("has_any_unsupported"), False)
    has_any_incomparable = normalize_bool(fallback_risk_features.get("has_any_incomparable"), False)
    forecast_as_fact = normalize_bool(fallback_risk_features.get("forecast_as_fact_present"), False)
    route_uniqueness_overclaim = normalize_bool(fallback_risk_features.get("route_uniqueness_overclaim"), False)
    explicit_core_risk = route_uniqueness_overclaim or forecast_as_fact or fictional_risk
    fallback_risk_gate_override = explicit_core_risk or supporting_structured_detail_risk or time_role_conflict_risk
    need_type = normalize_need_type(extracted.get("need_type")) if isinstance(extracted, dict) else "general_fact"
    route_guard_blocked = (
        has_core_route_like_claim(extracted, evidence_summary)
        and not normalize_bool(fallback_risk_features.get("absolute_claim_present"), False)
        and not route_uniqueness_overclaim
        and not fictional_risk
    )
    non_decidable_state = str(evidence_non_decidable_state.get("state") or "")
    dominant_row = dominant_pipeline_row(claim_pipeline_diagnostics, evidence_non_decidable_state)
    retrieval_effect_review = (
        claim_pipeline_diagnostics.get("retrieval_effect_review")
        if isinstance(claim_pipeline_diagnostics.get("retrieval_effect_review"), dict)
        else {}
    )
    access_path_state = str(dominant_row.get("access_path_state") or "")
    critical_claim_blocking_state = str(dominant_row.get("critical_claim_blocking_state") or "")
    official_entry_hit = normalize_bool(dominant_row.get("official_entry_hit"), False)
    kept_web = int(dominant_row.get("kept_web") or 0)
    raw_results = int(dominant_row.get("raw_results") or 0)
    answer_candidate_total = int(dominant_row.get("answer_candidate_total") or 0)
    decision_gate_primary_block = (
        critical_claim_blocking_state
        or access_path_state
        or str(dominant_row.get("pipeline_stage") or "")
        or non_decidable_state
    )
    gate = {
        "allow": False,
        "reason": "",
        "non_decidable_state": non_decidable_state,
        "has_high_risk_feature": high_risk_feature,
        "has_any_unsupported": has_any_unsupported,
        "has_any_incomparable": has_any_incomparable,
        "unsupported_core_claim_count": unsupported_core_claim_count,
        "partial_but_incomparable_count": partial_but_incomparable_count,
        "explicit_core_risk": explicit_core_risk,
        "supporting_structured_detail_risk": supporting_structured_detail_risk,
        "time_role_conflict_risk": time_role_conflict_risk,
        "fictional_reality_contamination_risk": fictional_risk,
        "fallback_risk_gate_override": fallback_risk_gate_override,
        "route_guard_blocked": route_guard_blocked,
        "certainty_profile_hint": certainty_profile,
        "decision_gate_consumed_diagnostics": bool(dominant_row or retrieval_effect_review),
        "decision_gate_primary_block": decision_gate_primary_block,
        "reason_source_layer": "diagnostic_gate" if (dominant_row or retrieval_effect_review) else "fallback_risk_only",
    }
    if has_direct_refuting_evidence(evidence_summary):
        gate["reason"] = "direct_refuting_evidence_exists"
        return gate
    if need_type == "current_result" and not explicit_core_risk:
        if not has_new_scheme_core_supporting_evidence(extracted, evidence_summary):
            gate["reason"] = "current_result_without_direct_refutation_or_core_risk"
            return gate
    if need_type == "financial_quote":
        gate["reason"] = "financial_quote_requires_same_metric_refutation"
        return gate
    unresolved_high_risk_details = has_unresolved_high_risk_detail_claims(extracted, evidence_summary)
    gate["unresolved_high_risk_details"] = unresolved_high_risk_details
    if has_new_scheme_core_supporting_evidence(extracted, evidence_summary) and not unresolved_high_risk_details:
        gate["reason"] = "decidable_evidence_exists"
        return gate
    if non_decidable_state == "direct_decidable":
        gate["reason"] = "direct_decision_available"
        return gate
    if critical_claim_blocking_state in {
        "access_blocked_but_rescuable",
        "access_blocked_and_unresolved",
        "official_discovery_failed",
    }:
        gate["reason"] = "access_blocked_not_evidence_absence"
        return gate
    if critical_claim_blocking_state in {
        "raw_hit_but_page_not_retained",
        "raw_hit_but_page_not_retained_after_review",
    } and not fallback_risk_gate_override:
        gate["reason"] = "raw_hit_but_page_not_retained"
        return gate
    if official_entry_hit and raw_results > 0 and kept_web <= 0 and not fallback_risk_gate_override:
        gate["reason"] = "authority_hit_but_not_retained"
        return gate
    if (
        critical_claim_blocking_state == "candidate_present_but_not_decidable"
        or (kept_web > 0 and answer_candidate_total > 0)
    ) and not fallback_risk_gate_override:
        gate["reason"] = "candidate_present_but_not_decidable"
        return gate
    if (
        non_decidable_state == "unsupported"
        and int(retrieval_effect_review.get("authority_hit_claims") or 0) > 0
        and int(retrieval_effect_review.get("kept_positive_claims") or 0) <= 0
        and not fallback_risk_gate_override
    ):
        gate["reason"] = "authority_hit_but_not_retained"
        return gate
    if (
        non_decidable_state == "unsupported"
        and int(retrieval_effect_review.get("kept_progress_claims") or 0) > 0
        and int(retrieval_effect_review.get("kept_positive_claims") or 0) > 0
        and not fallback_risk_gate_override
    ):
        gate["reason"] = "retained_progress_but_not_decidable"
        return gate
    if route_guard_blocked and non_decidable_state == "unsupported" and not high_risk_feature and unsupported_core_claim_count > 0:
        gate["reason"] = "open_route_summary_guard_blocked"
        return gate
    if fictional_risk:
        gate["allow"] = True
        gate["reason"] = "fictional_contamination_signal"
        return gate
    if non_decidable_state == "partial_but_incomparable" and (explicit_core_risk or fictional_risk):
        gate["allow"] = True
        gate["reason"] = "partial_but_incomparable_with_risk_signal"
        return gate
    if non_decidable_state == "unsupported" and explicit_core_risk:
        gate["allow"] = True
        gate["reason"] = "unsupported_plus_explicit_core_risk"
        return gate
    if non_decidable_state in {"unsupported", "partial_but_incomparable", "abstain_no_judge"} and (
        supporting_structured_detail_risk or time_role_conflict_risk
    ):
        gate["allow"] = True
        gate["reason"] = "non_decidable_plus_detail_risk_signal"
        return gate
    if non_decidable_state == "abstain_no_judge" and (fictional_risk or explicit_core_risk):
        gate["allow"] = True
        gate["reason"] = "abstain_but_explicit_core_risk"
        return gate
    gate["reason"] = f"{non_decidable_state or 'unsupported'}_without_fallback_risk_signal"
    return gate


def rubric_prior_head(
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    fallback_risk_features: Optional[Dict[str, Any]] = None,
    evidence_non_decidable_state: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    if not ENABLE_RUBRIC_PRIOR_FALLBACK:
        return None, "rubric_prior_disabled"
    prompt = build_rubric_prior_prompt(item, extracted, evidence_summary, fallback_risk_features, evidence_non_decidable_state)
    data, raw = llm_chat_custom(
        SYSTEM_RUBRIC_PRIOR,
        prompt,
        max_tokens=RUBRIC_PRIOR_MAX_TOKENS,
        temperature=0.0,
        retries=0,
    )
    normalized = normalize_rubric_prior_obj(data)
    if normalized is None:
        return None, raw
    return adjust_rubric_prior_with_claim_shape(normalized, item, extracted, evidence_summary, fallback_risk_features), raw


def rubric_fallback_decide(
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    fallback_risk_features: Optional[Dict[str, Any]],
    evidence_non_decidable_state: Optional[Dict[str, Any]],
    legacy_preview: Dict[str, Any],
    claim_pipeline_diagnostics: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    gate = rubric_trigger_gate(
        item,
        extracted,
        evidence_summary,
        fallback_risk_features,
        evidence_non_decidable_state,
        claim_pipeline_diagnostics,
    )
    if not gate.get("allow"):
        return {
            "attempted": False,
            "valid": False,
            "skip_reason": str(gate.get("reason") or "rubric_gate_blocked"),
            "trigger_gate": gate,
        }
    started_at = time.perf_counter()
    rubric_obj, raw = rubric_prior_head(item, extracted, evidence_summary, fallback_risk_features, evidence_non_decidable_state)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
    if not rubric_obj:
        return {
            "attempted": True,
            "elapsed_ms": elapsed_ms,
            "raw": raw,
            "valid": False,
            "trigger_gate": gate,
        }
    basis = "rubric_fallback_with_partial_evidence" if has_partial_evidence_for_rubric(evidence_summary) else "rubric_fallback"
    return {
        "attempted": True,
        "elapsed_ms": elapsed_ms,
        "valid": True,
        "label": rubric_obj["prior_label"],
        "decision_basis": basis,
        "policy": rubric_obj["fallback_policy"],
        "reason": rubric_obj["reason"],
        "prior": rubric_obj,
        "raw": raw,
        "trigger_gate": gate,
        "replaced_legacy_policy": str(legacy_preview.get("policy") or ""),
        "replaced_legacy_basis": str(legacy_preview.get("decision_basis") or ""),
        "replaced_legacy_source": str(legacy_preview.get("source") or ""),
    }


def build_route_point_conversion_prompt(claim: Dict[str, Any], summary: Dict[str, Any]) -> str:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    route_meta = source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}
    point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
    coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
    page_intent = source_intent.get("page_intent") if isinstance(source_intent.get("page_intent"), dict) else {}
    task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
    candidates = [item for item in (summary.get("evidence_sentence_candidates") or []) if isinstance(item, dict)][:4]
    candidate_lines: List[str] = []
    for idx, candidate in enumerate(candidates):
        route_relation = candidate.get("route_relation") if isinstance(candidate.get("route_relation"), dict) else {}
        route_sentence = candidate.get("route_sentence") if isinstance(candidate.get("route_sentence"), dict) else {}
        candidate_lines.append(
            json.dumps(
                {
                    "sentence_index": idx,
                    "sentence": str(candidate.get("sentence") or ""),
                    "title": compact_claim_text(str(candidate.get("title") or ""), 100),
                    "source_type": candidate.get("source_type") or "",
                    "sentence_directness": candidate.get("sentence_directness") or "",
                    "sentence_utility_score": candidate.get("sentence_utility_score") or 0,
                    "sentence_utility_label": candidate.get("sentence_utility_label") or "",
                    "page_type": candidate.get("page_utility_page_type") or "",
                    "page_focus": candidate.get("page_utility_page_focus") or "",
                    "evidence_contract_status": candidate.get("evidence_contract_status") or "",
                    "evidence_contract_score": candidate.get("evidence_contract_score") or 0,
                    "evidence_contract_risks": candidate.get("evidence_contract_risks") or [],
                    "claim_token_hits": candidate.get("claim_token_hits") or [],
                    "route_sentence": {
                        "direct_sentence": bool(route_sentence.get("direct_sentence")),
                        "has_relation_marker": bool(route_sentence.get("has_relation_marker")),
                        "has_route_object_marker": bool(route_sentence.get("has_route_object_marker")),
                        "entity_hit_count": int(route_sentence.get("entity_hit_count") or 0),
                    },
                    "route_relation": {
                        "directly_answers_route": bool(route_relation.get("directly_answers_route")),
                        "has_relation_marker": bool(route_relation.get("has_relation_marker")),
                        "has_route_object_marker": bool(route_relation.get("has_route_object_marker")),
                        "has_directional_relation_marker": bool(route_relation.get("has_directional_relation_marker")),
                        "anchor_hit_count": int(route_relation.get("anchor_hit_count") or 0),
                        "polarity": route_relation.get("polarity") or "",
                        "support_status": (
                            route_relation.get("support_slots", {})
                            if isinstance(route_relation.get("support_slots"), dict)
                            else {}
                        ).get("support_status", ""),
                    },
                },
                ensure_ascii=False,
            )
        )
    return f"""请把 route claim 的候选句转换成句级结构化判断。

[claim]
{claim.get("claim", "")}

[route_meta]
{json.dumps(route_meta, ensure_ascii=False)}

[stage_diagnostics]
{json.dumps(
    {
        "point_stage": point_conversion.get("stage") or "",
        "coverage_level": coverage.get("coverage_level") or "",
        "coverage_reason": coverage.get("coverage_reason") or "",
        "needed_page_type": page_intent.get("needed_page_type") or "",
        "direct_answer_need": task_card.get("direct_answer_need") or "",
        "verification_focus": task_card.get("verification_focus") or [],
    },
    ensure_ascii=False,
)}

[candidate_sentences]
{chr(10).join(candidate_lines)}
"""


def route_extraction_span_matches(sentence: str, evidence_span: str) -> bool:
    sentence_norm = normalize_text(sentence)
    span_norm = normalize_text(evidence_span)
    if not sentence_norm or not span_norm:
        return False
    if span_norm in sentence_norm:
        return True
    sentence_compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", sentence_norm).lower()
    span_compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", span_norm).lower()
    if not sentence_compact or not span_compact:
        return False
    return span_compact in sentence_compact


def valid_route_extraction_result(item: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    try:
        sentence_index = int(item.get("sentence_index"))
    except Exception:
        return None
    if sentence_index < 0 or sentence_index >= len(candidates):
        return None
    candidate = candidates[sentence_index]
    sentence = normalize_text(str(candidate.get("sentence") or ""))
    if not sentence:
        return None
    if not bool(item.get("route_relation_present")):
        return None
    directness = str(item.get("directness") or "")
    polarity = str(item.get("polarity") or "")
    evidence_span = normalize_text(str(item.get("evidence_span") or ""))
    confidence = float(item.get("confidence", 0.0) or 0.0)
    relation_type = str(item.get("relation_type") or "")
    route_relation = candidate.get("route_relation") if isinstance(candidate.get("route_relation"), dict) else {}
    route_sentence = candidate.get("route_sentence") if isinstance(candidate.get("route_sentence"), dict) else {}
    sentence_utility_score = int(candidate.get("sentence_utility_score") or 0)
    sentence_utility_label = str(candidate.get("sentence_utility_label") or "")
    if directness not in {"direct", "partial"} or polarity not in {"support", "conflict", "uncertain"}:
        return None
    if directness == "partial" and confidence < 0.62:
        return None
    if directness == "partial" and polarity in {"support", "conflict"}:
        filled_partial = sum(
            1
            for key in ("subject", "action_or_vehicle", "origin", "transit_area", "destination")
            if normalize_text(str(item.get(key) or ""))
        )
        if (
            filled_partial < 2
            and relation_type not in {"overfly", "via", "through", "enter", "toward", "destination", "avoid"}
            and int(route_relation.get("anchor_hit_count") or 0) < 2
        ):
            return None
    if confidence < 0.55:
        return None
    if not evidence_span or not route_extraction_span_matches(sentence, evidence_span):
        return None
    filled_fields = sum(
        1
        for key in ("subject", "action_or_vehicle", "origin", "transit_area", "destination")
        if normalize_text(str(item.get(key) or ""))
    )
    strong_relation_hint = bool(
        route_sentence.get("direct_sentence")
        or (
            route_relation.get("directly_answers_route")
            and route_relation.get("has_relation_marker")
            and (
                route_relation.get("has_route_object_marker")
                or int(route_relation.get("anchor_hit_count") or 0) >= 2
            )
        )
    )
    if filled_fields < 2 and not (
        strong_relation_hint
        and relation_type in {"overfly", "via", "through", "enter", "toward", "destination", "avoid"}
        and confidence >= 0.68
    ):
        return None
    if sentence_utility_label not in {"answerable", "partial_answerable", "contextual"} and sentence_utility_score < 20:
        return None
    normalized = dict(item)
    normalized["sentence_index"] = sentence_index
    normalized["confidence"] = confidence
    normalized["_candidate"] = candidate
    normalized["_sentence"] = sentence
    return normalized


def route_point_from_extraction(claim: Dict[str, Any], extraction: Dict[str, Any]) -> Dict[str, Any]:
    candidate = extraction["_candidate"]
    sentence = extraction["_sentence"]
    polarity = str(extraction.get("polarity") or "uncertain")
    point_type = "route_reference"
    if polarity == "support":
        point_type = "route_support"
    elif polarity == "conflict":
        point_type = "route_conflict"
    return {
        "type": point_type,
        "claim_value": compact_claim_text(str(claim.get("claim") or ""), 160),
        "evidence_value": sentence,
        "evidence_sentence": sentence,
        "route_relation": {
            "directly_answers_route": True,
            "has_relation_marker": True,
            "polarity": polarity,
            "relation_type": str(extraction.get("relation_type") or "unknown"),
            "subject": normalize_text(str(extraction.get("subject") or "")),
            "action_or_vehicle": normalize_text(str(extraction.get("action_or_vehicle") or "")),
            "origin": normalize_text(str(extraction.get("origin") or "")),
            "transit_area": normalize_text(str(extraction.get("transit_area") or "")),
            "destination": normalize_text(str(extraction.get("destination") or "")),
            "evidence_span": normalize_text(str(extraction.get("evidence_span") or "")),
            "llm_reason": compact_claim_text(str(extraction.get("reason") or ""), 160),
        },
        "source_type": candidate.get("source_type"),
        "url": candidate.get("url"),
        "title": candidate.get("title"),
        "direct_answer": "direct",
        "confidence": extraction.get("confidence"),
        "llm_route_point": True,
    }


def route_point_from_candidate_fallback(claim: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    sentence = normalize_text(str(candidate.get("sentence") or ""))
    route_relation = candidate.get("route_relation") if isinstance(candidate.get("route_relation"), dict) else {}
    polarity = str(route_relation.get("polarity") or "uncertain")
    sentence_directness = str(candidate.get("sentence_directness") or "")
    if polarity == "support":
        point_type = "route_support"
    elif polarity == "conflict":
        point_type = "route_conflict"
    else:
        point_type = "route_reference"
    direct_answer = "direct" if sentence_directness == "direct" else "partial" if sentence_directness == "partial" else "related_only"
    return {
        "type": point_type,
        "claim_value": compact_claim_text(str(claim.get("claim") or ""), 160),
        "evidence_value": sentence,
        "evidence_sentence": sentence,
        "route_relation": route_relation,
        "source_type": candidate.get("source_type"),
        "url": candidate.get("url"),
        "title": candidate.get("title"),
        "direct_answer": direct_answer,
        "confidence": candidate.get("sentence_score_total") or candidate.get("score") or 0,
        "llm_route_point": False,
        "fallback_route_point": True,
    }


def fallback_route_candidate_usable(candidate: Dict[str, Any]) -> bool:
    if not isinstance(candidate, dict):
        return False
    sentence = normalize_text(str(candidate.get("sentence") or ""))
    if not sentence or len(sentence) > 220:
        return False
    if re.search(r"(Share on Facebook|Opens in new window|登录|login|print email)", sentence, flags=re.I):
        return False
    directness = str(candidate.get("sentence_directness") or "")
    utility_score = int(candidate.get("sentence_utility_score") or 0)
    utility_label = str(candidate.get("sentence_utility_label") or "")
    route_relation = candidate.get("route_relation") if isinstance(candidate.get("route_relation"), dict) else {}
    support_slots = route_relation.get("support_slots") if isinstance(route_relation.get("support_slots"), dict) else {}
    support_status = str(support_slots.get("support_status") or "")
    if directness not in {"direct", "partial"}:
        return False
    if utility_label not in {"answerable", "partial_answerable"} or utility_score < 18:
        return False
    if not route_relation.get("directly_answers_route"):
        return False
    if not route_relation.get("has_relation_marker"):
        return False
    if not route_relation.get("has_route_object_marker") and int(route_relation.get("anchor_hit_count") or 0) < 2:
        return False
    if int(route_relation.get("anchor_hit_count") or 0) <= 0:
        return False
    if support_status not in {"support_ready", "sequence_inferred_only", "relation_ready"}:
        return False
    if support_slots.get("multi_origin_ambiguity") or support_slots.get("alias_only_anchor_match"):
        return False
    if not (route_relation.get("has_directional_relation_marker") or support_slots.get("explicit_positive_phrase")):
        return False
    lower = sentence.lower()
    if not any(marker in lower for marker in ["through", "via", "pass through", "airspace", "entered", "reach", "crossed"]):
        if not any(marker in sentence for marker in ["经过", "经由", "领空", "飞越", "进入", "到达"]):
            return False
    return True


def refine_route_claim_points_with_llm(
    claims: List[Dict[str, Any]],
    evidence_bundle: Dict[str, Any],
    evidence_summary: Dict[str, Any],
    debug_bucket: Optional[Dict[str, Any]] = None,
) -> None:
    if not ENABLE_ROUTE_POINT_CONVERSION_LLM:
        if debug_bucket is not None:
            debug_bucket["route_point_conversion_llm"] = {"enabled": False, "reason": "disabled_by_default_auxiliary_path"}
        return
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary, dict) else {}
    evidence_by_claim = evidence_bundle.get("evidence_by_claim") if isinstance(evidence_bundle, dict) else {}
    diagnostics: Dict[str, Any] = {}
    if not isinstance(summaries, dict) or not isinstance(evidence_by_claim, dict):
        return
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        if not claim_id or claim_id not in summaries:
            continue
        summary = summaries.get(claim_id)
        if not isinstance(summary, dict) or str(summary.get("evidence_mode") or "") != "route_fact":
            continue
        point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
        stage = str(point_conversion.get("stage") or "")
        if stage not in {
            POINT_STAGE_ROUTE_RELATION_MISSING,
            POINT_STAGE_RELATED_ONLY,
            POINT_STAGE_NO_DIRECT,
            POINT_STAGE_NO_CANDIDATE,
        }:
            continue
        candidates = [item for item in (summary.get("evidence_sentence_candidates") or []) if isinstance(item, dict)][:4]
        if not candidates:
            diagnostics[claim_id] = {"stage_before": stage, "skipped": "no_candidates"}
            continue
        prompt = build_route_point_conversion_prompt(claim, summary)
        route_obj, raw = llm_chat(SYSTEM_ROUTE_POINT_CONVERSION, prompt, retries=0)
        diag_item: Dict[str, Any] = {
            "stage_before": stage,
            "candidate_count": len(candidates),
            "raw_preview": compact_claim_text(raw, 220),
        }
        results = route_obj.get("results") if isinstance(route_obj, dict) and isinstance(route_obj.get("results"), list) else []
        valid = [normalized for normalized in (valid_route_extraction_result(item, candidates) for item in results) if normalized]
        if not valid:
            fallback_candidate = next(
                (
                    candidate
                    for candidate in candidates
                    if fallback_route_candidate_usable(candidate)
                ),
                None,
            )
            if fallback_candidate is None:
                diag_item["converted"] = 0
                diag_item["status"] = "no_valid_direct_route_relation"
                diagnostics[claim_id] = diag_item
                continue
            fallback_point = route_point_from_candidate_fallback(claim, fallback_candidate)
            fallback_type = str(fallback_point.get("type") or "route_reference")
            if fallback_type == "route_conflict":
                summary["refuting_points"] = unique_points([fallback_point] + [item for item in (summary.get("refuting_points") or []) if isinstance(item, dict)])[:3]
            elif fallback_type == "route_support":
                summary["supporting_points"] = unique_points([fallback_point] + [item for item in (summary.get("supporting_points") or []) if isinstance(item, dict)])[:3]
            else:
                summary["uncertain_points"] = unique_points([fallback_point] + [item for item in (summary.get("uncertain_points") or []) if isinstance(item, dict)])[:3]
            coverage = claim_coverage(claim_id, "route_fact", evidence_by_claim.get(claim_id, []), summary)
            summary["coverage"] = coverage
            summary["point_conversion"] = point_conversion_diagnostics(summary, coverage)
            summary["evidence_events"] = evidence_event_summary(summary, coverage)
            diag_item["converted"] = 1
            diag_item["status"] = "fallback_converted"
            diag_item["polarity"] = fallback_point.get("route_relation", {}).get("polarity")
            diag_item["confidence"] = fallback_point.get("confidence")
            diag_item["sentence"] = compact_claim_text(str(fallback_point.get("evidence_sentence") or ""), 180)
            diagnostics[claim_id] = diag_item
            continue
        valid.sort(
            key=lambda item: (
                float(item.get("confidence", 0.0) or 0.0),
                str(item.get("polarity") or "") in {"support", "conflict"},
            ),
            reverse=True,
        )
        best = valid[0]
        point = route_point_from_extraction(claim, best)
        if best.get("polarity") == "conflict":
            summary["refuting_points"] = unique_points([point] + [item for item in (summary.get("refuting_points") or []) if isinstance(item, dict)])[:3]
        elif best.get("polarity") == "support":
            summary["supporting_points"] = unique_points([point] + [item for item in (summary.get("supporting_points") or []) if isinstance(item, dict)])[:3]
        else:
            summary["uncertain_points"] = unique_points([point] + [item for item in (summary.get("uncertain_points") or []) if isinstance(item, dict)])[:3]
        coverage = claim_coverage(claim_id, "route_fact", evidence_by_claim.get(claim_id, []), summary)
        summary["coverage"] = coverage
        summary["point_conversion"] = point_conversion_diagnostics(summary, coverage)
        summary["evidence_events"] = evidence_event_summary(summary, coverage)
        diag_item["converted"] = 1
        diag_item["status"] = "converted"
        diag_item["polarity"] = best.get("polarity")
        diag_item["confidence"] = best.get("confidence")
        diag_item["sentence"] = compact_claim_text(best["_sentence"], 180)
        diagnostics[claim_id] = diag_item
    if debug_bucket is not None and diagnostics:
        debug_bucket["route_point_conversion_llm"] = diagnostics


# 12. Extract 输入构造：组织单条样本给第一次 LLM 调用。
def build_extract_prompt(item: Dict[str, Any]) -> str:
    return f"""请抽取主需、可核查 claims 和最小检索计划。

[time]
{item.get('time', '')}

[question]
{item.get('question', '')}

[answer]
{item.get('answer', '')}

[history_question]
{json.dumps(item.get('history_question', []), ensure_ascii=False)}

要求：
- 只保留后续检索真正需要的字段，不写解释文本。
- user_need 只写用户真正要核查的核心目标。
- claims 从 answer 抽取，question 只负责判主次。
- claims 最多 {MAX_CLAIMS} 条，优先 core，其次保留高风险结构化细节。
- preferred_domains 不确定就空数组，不猜域名，不写完整 URL。
- verification_questions 每条 1-2 个，短、通用、可检索。
- queries 每条最多 2 个，短、准、可搜索。
- source_strategy 能省则省；只有在明显能提升检索时再填。
- 只输出 JSON。
"""


def build_fast_extract_prompt(item: Dict[str, Any]) -> str:
    return f"""请快速抽取主需、关键 claims 和短 query。

[time]
{item.get('time', '')}

[question]
{item.get('question', '')}

[answer]
{item.get('answer', '')}

[history_question]
{json.dumps(item.get('history_question', []), ensure_ascii=False)}

要求：
- 最多 4 条 claims。
- 必须保留直接回答主需的 core claim。
- 必须保留 answer 中明确数字/日期/金额/比分/距离/路线/预测确定化/强绝对化表述。
- 只保留最小必要字段；source_strategy 可省略。
- preferred_domains 不确定就空数组。
- evidence_shape 不确定就 general_evidence_page。
- 每条 claim 输出 1-2 个 verification_questions。
- 每条 claim 最多 2 条短 query。
- 不要生成长解释、不要重复题面、不要补充无关字段。
- 只输出 JSON。
"""


VERIFICATION_CLAIM_TYPES = {
    "route_relation",
    "causal_impact",
    "numeric_value",
    "date_schedule",
    "award_fact",
    "prediction_vs_confirmed",
    "event_result",
    "policy_fact",
    "entity_fact",
    "general_fact",
}
VERIFICATION_POLARITIES = {"positive", "negative", "comparative", "causal", "prediction", "uncertain"}
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
VERIFICATION_QUERY_INTENTS = {
    "discover_truth",
    "verify_original",
    "find_official_page",
    "find_route_page",
    "find_current_status",
    "find_numeric_source",
    "find_date_source",
    "find_result_page",
    "general_verify",
}
TASK_FACT_OPERATIONS = {
    "attribute",
    "relation",
    "quantity",
    "time",
    "status",
    "result",
    "cause",
    "mixed",
    "unknown",
}
TASK_VALUE_SEMANTICS = {
    "person_org_place",
    "route_or_transit",
    "money_or_quantity",
    "date_or_window",
    "policy_or_rule",
    "result_or_outcome",
    "status_or_existence",
    "cause_or_mechanism",
    "classification_or_membership",
    "mixed",
    "unknown",
}
METRIC_VALUE_TYPES = {
    "central_parity",
    "spot_buying_price",
    "cash_buying_price",
    "selling_price",
    "real_time_rate",
    "movement_direction",
    "movement_amount",
    "movement_percent",
    "open_price",
    "close_price",
    "intraday_price",
    "settlement_price",
    "adjustment_amount",
    "retail_price",
    "effective_time",
    "spot_price",
    "futures_price",
    "index_level",
    "generic_value",
    "not_metric",
}
METRIC_SOURCE_AUTHORITIES = {
    "central_bank",
    "exchange",
    "bank_rate_table",
    "official_notice",
    "financial_quote_page",
    "market_data_page",
    "price_monitoring_report",
    "authoritative_news",
    "general_source",
    "unknown",
}


def bounded_string_list(value: Any, limit: int, text_limit: int = 80) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        text = normalize_text(str(item or ""))
        if text:
            out.append(compact_claim_text(text, text_limit))
        if len(out) >= limit:
            break
    return out


def metric_slot_diagnostics(slots: Dict[str, Any]) -> List[str]:
    if not isinstance(slots, dict) or str(slots.get("value_type") or "") in {"", "not_metric"}:
        return []
    missing: List[str] = []
    for key in ("subject_entity", "metric_name", "value_type", "time_scope", "source_authority"):
        if not normalize_text(str(slots.get(key) or "")):
            missing.append(f"missing_{key}")
    value_type = str(slots.get("value_type") or "")
    if value_type not in {"movement_direction", "movement_amount", "movement_percent", "effective_time"}:
        if not normalize_text(str(slots.get("unit") or "")):
            missing.append("missing_unit")
    if value_type in {"movement_direction", "movement_amount", "movement_percent"} and not normalize_text(
        str(slots.get("comparison_baseline") or "")
    ):
        missing.append("missing_comparison_baseline")
    if not normalize_text(str(slots.get("expected_evidence_shape") or "")):
        missing.append("missing_expected_evidence_shape")
    return dedupe_keep_order(missing)


def infer_metric_value_type_from_context(raw_slots: Dict[str, Any], current_value_type: str = "") -> str:
    text = normalize_text(
        " ".join(
            [
                str(raw_slots.get("metric_name") or ""),
                str(raw_slots.get("expected_evidence_shape") or ""),
                str(raw_slots.get("reject_evidence_shape") or ""),
                str(raw_slots.get("subject_entity") or raw_slots.get("subject") or ""),
            ]
        )
    )
    if not text:
        return current_value_type or "generic_value"
    if "现汇买入价" in text or "spot buying" in text.lower():
        return "spot_buying_price"
    if "现钞买入价" in text or "cash buying" in text.lower():
        return "cash_buying_price"
    if "现汇卖出价" in text or "卖出价" in text or "selling rate" in text.lower():
        return "selling_price"
    if "中间价" in text or "central parity" in text.lower():
        return "central_parity"
    if "实时汇率" in text or "实时行情" in text or "quote" in text.lower():
        return "real_time_rate"
    if "涨跌幅" in text or "percent change" in text.lower():
        return "movement_percent"
    if "涨跌额" in text or "变动金额" in text or "change amount" in text.lower():
        return "movement_amount"
    if any(marker in text for marker in ["涨跌", "上涨", "下跌", "变动方向"]):
        return "movement_direction"
    if "开盘价" in text or "open price" in text.lower():
        return "open_price"
    if "收盘价" in text or "close price" in text.lower():
        return "close_price"
    return current_value_type or "generic_value"


def normalize_metric_slots(raw_slots: Any) -> Dict[str, Any]:
    if not isinstance(raw_slots, dict):
        return {
            "value_type": "not_metric",
            "slot_diagnostics": [],
        }
    value_type = str(raw_slots.get("value_type") or "generic_value")
    if value_type not in METRIC_VALUE_TYPES:
        value_type = "generic_value"
    inferred_value_type = infer_metric_value_type_from_context(raw_slots, value_type)
    if inferred_value_type in METRIC_VALUE_TYPES and inferred_value_type != "not_metric":
        value_type = inferred_value_type
    source_authority = str(raw_slots.get("source_authority") or "unknown")
    if source_authority not in METRIC_SOURCE_AUTHORITIES:
        source_authority = "general_source"
    slots = {
        "subject_entity": compact_claim_text(str(raw_slots.get("subject_entity") or raw_slots.get("subject") or ""), 80),
        "metric_name": compact_claim_text(str(raw_slots.get("metric_name") or ""), 80),
        "value_type": value_type,
        "time_scope": compact_claim_text(str(raw_slots.get("time_scope") or ""), 80),
        "unit": compact_claim_text(str(raw_slots.get("unit") or ""), 80),
        "source_authority": source_authority,
        "comparison_baseline": compact_claim_text(str(raw_slots.get("comparison_baseline") or ""), 80),
        "expected_evidence_shape": compact_claim_text(str(raw_slots.get("expected_evidence_shape") or ""), 130),
        "reject_evidence_shape": compact_claim_text(str(raw_slots.get("reject_evidence_shape") or ""), 130),
    }
    slots["slot_diagnostics"] = metric_slot_diagnostics(slots)
    return slots


def infer_task_fact_operation(
    claim_type: str,
    evidence_mode: str = "",
    evidence_target: str = "",
    mechanism_type: str = "",
) -> str:
    normalized_claim_type = normalize_text(claim_type)
    normalized_mode = normalize_text(evidence_mode)
    normalized_target = normalize_text(evidence_target)
    normalized_mechanism = normalize_text(mechanism_type)
    if normalized_claim_type == "route_relation" or normalized_mode == "route_fact" or normalized_target == "route_relation":
        return "relation"
    if normalized_claim_type in {"numeric_value", "award_fact"} or normalized_mode == "numeric_fact":
        return "quantity"
    if normalized_claim_type == "date_schedule" or normalized_mode in {"date_fact", "schedule_fact"}:
        return "time"
    if normalized_claim_type == "event_result" or normalized_mode == "event_result":
        return "result"
    if normalized_claim_type == "policy_fact" or normalized_mode == "policy_fact":
        return "status"
    if normalized_claim_type == "causal_impact":
        return "cause"
    if normalized_claim_type == "prediction_vs_confirmed":
        return "status"
    if normalized_claim_type == "entity_fact":
        return "attribute"
    if normalized_mechanism == "current_status_update" or normalized_target == "current_status":
        return "status"
    return "unknown"


def infer_task_value_semantics(
    claim_type: str,
    evidence_mode: str = "",
    evidence_target: str = "",
    mechanism_type: str = "",
    metric_slots: Optional[Dict[str, Any]] = None,
) -> str:
    metric_slots = metric_slots if isinstance(metric_slots, dict) else {}
    normalized_claim_type = normalize_text(claim_type)
    normalized_mode = normalize_text(evidence_mode)
    normalized_target = normalize_text(evidence_target)
    normalized_mechanism = normalize_text(mechanism_type)
    value_type = normalize_text(str(metric_slots.get("value_type") or ""))
    if normalized_claim_type == "route_relation" or normalized_mode == "route_fact" or normalized_target == "route_relation":
        return "route_or_transit"
    if value_type and value_type != "not_metric":
        return "money_or_quantity"
    if normalized_claim_type == "date_schedule" or normalized_mode in {"date_fact", "schedule_fact"}:
        return "date_or_window"
    if normalized_claim_type == "policy_fact" or normalized_mode == "policy_fact":
        return "policy_or_rule"
    if normalized_claim_type == "event_result" or normalized_mode == "event_result":
        return "result_or_outcome"
    if normalized_claim_type == "causal_impact":
        return "cause_or_mechanism"
    if normalized_claim_type == "prediction_vs_confirmed" or normalized_mechanism == "current_status_update" or normalized_target == "current_status":
        return "status_or_existence"
    if normalized_claim_type == "entity_fact":
        return "person_org_place"
    return "unknown"


def normalize_task_semantics(
    raw_semantics: Any,
    claim_type: str,
    evidence_mode: str = "",
    evidence_target: str = "",
    mechanism_type: str = "",
    metric_slots: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw_semantics = raw_semantics if isinstance(raw_semantics, dict) else {}
    metric_slots = metric_slots if isinstance(metric_slots, dict) else {}
    fact_operation = normalize_text(str(raw_semantics.get("fact_operation") or ""))
    if fact_operation not in TASK_FACT_OPERATIONS:
        fact_operation = infer_task_fact_operation(claim_type, evidence_mode, evidence_target, mechanism_type)
    value_semantics = normalize_text(str(raw_semantics.get("value_semantics") or ""))
    if value_semantics not in TASK_VALUE_SEMANTICS:
        value_semantics = infer_task_value_semantics(claim_type, evidence_mode, evidence_target, mechanism_type, metric_slots)
    return {
        "fact_operation": fact_operation if fact_operation in TASK_FACT_OPERATIONS else "unknown",
        "value_semantics": value_semantics if value_semantics in TASK_VALUE_SEMANTICS else "unknown",
        "primary_slots": bounded_string_list(raw_semantics.get("primary_slots"), 6, 40),
        "secondary_slots": bounded_string_list(raw_semantics.get("secondary_slots"), 6, 40),
        "must_not_confuse": bounded_string_list(raw_semantics.get("must_not_confuse"), 5, 70),
        "retrieval_focus": bounded_string_list(raw_semantics.get("retrieval_focus"), 4, 70),
    }


def infer_mechanism_type(
    claim_type: str,
    metric_slots: Optional[Dict[str, Any]] = None,
    evidence_mode: str = "",
    evidence_target: str = "",
    evidence_shape: str = "",
) -> str:
    metric_slots = metric_slots if isinstance(metric_slots, dict) else {}
    metric_value_type = str(metric_slots.get("value_type") or "")
    if metric_value_type and metric_value_type != "not_metric":
        return "structured_numeric_authority"
    if claim_type == "date_schedule" or evidence_mode in {"date_fact", "schedule_fact"}:
        return "date_authority"
    if claim_type == "event_result" or evidence_mode == "event_result" or evidence_target in {"match_result", "withdrawal_status"}:
        return "event_result_page"
    if claim_type == "route_relation" or evidence_mode == "route_fact" or evidence_target == "route_relation":
        return "relation_sentence"
    if evidence_target == "current_status" or evidence_shape == "current_status_update":
        return "current_status_update"
    if claim_type in {"numeric_value", "award_fact"} and evidence_mode == "numeric_fact":
        return "structured_numeric_authority"
    return "general_web_evidence"


def normalize_mechanism_type(
    raw_value: Any,
    claim_type: str,
    metric_slots: Optional[Dict[str, Any]] = None,
    evidence_mode: str = "",
    evidence_target: str = "",
    evidence_shape: str = "",
) -> str:
    mechanism_type = normalize_text(str(raw_value or ""))
    if mechanism_type not in VERIFICATION_MECHANISM_TYPES:
        mechanism_type = infer_mechanism_type(claim_type, metric_slots, evidence_mode, evidence_target, evidence_shape)
    return mechanism_type if mechanism_type in VERIFICATION_MECHANISM_TYPES else "general_web_evidence"


def normalize_core_binding(raw_binding: Any, raw_item: Optional[Dict[str, Any]] = None, metric_slots: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    binding = raw_binding if isinstance(raw_binding, dict) else {}
    raw_item = raw_item if isinstance(raw_item, dict) else {}
    metric_slots = metric_slots if isinstance(metric_slots, dict) else {}
    out = {
        "subject_entity": compact_claim_text(
            str(binding.get("subject_entity") or raw_item.get("subject") or metric_slots.get("subject_entity") or ""),
            90,
        ),
        "object_entity": compact_claim_text(
            str(binding.get("object_entity") or raw_item.get("object") or ""),
            90,
        ),
        "relation_or_metric": compact_claim_text(
            str(binding.get("relation_or_metric") or raw_item.get("relation") or metric_slots.get("metric_name") or ""),
            90,
        ),
        "time_scope": compact_claim_text(
            str(binding.get("time_scope") or raw_item.get("condition_or_scope") or metric_slots.get("time_scope") or ""),
            100,
        ),
        "authority_scope": compact_claim_text(
            str(binding.get("authority_scope") or metric_slots.get("source_authority") or ""),
            60,
        ),
        "expected_evidence_shape": compact_claim_text(
            str(binding.get("expected_evidence_shape") or metric_slots.get("expected_evidence_shape") or ""),
            140,
        ),
        "reject_evidence_shape": compact_claim_text(
            str(binding.get("reject_evidence_shape") or metric_slots.get("reject_evidence_shape") or ""),
            140,
        ),
    }
    out["binding_diagnostics"] = [
        key for key in ("subject_entity", "relation_or_metric", "time_scope", "expected_evidence_shape")
        if not normalize_text(str(out.get(key) or ""))
    ]
    return out


def normalize_typed_extension(raw_extension: Any, metric_slots: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    extension = raw_extension if isinstance(raw_extension, dict) else {}
    metric_slots = metric_slots if isinstance(metric_slots, dict) else {}
    numeric_raw = extension.get("numeric") if isinstance(extension.get("numeric"), dict) else {}
    date_raw = extension.get("date") if isinstance(extension.get("date"), dict) else {}
    event_raw = extension.get("event") if isinstance(extension.get("event"), dict) else {}
    route_raw = extension.get("route") if isinstance(extension.get("route"), dict) else {}
    policy_raw = extension.get("policy") if isinstance(extension.get("policy"), dict) else {}
    normalized_metric_value_type = str(metric_slots.get("value_type") or "not_metric")
    return {
        "numeric": {
            "value_type": normalized_metric_value_type,
            "unit": compact_claim_text(str(numeric_raw.get("unit") or metric_slots.get("unit") or ""), 60),
            "comparison_baseline": compact_claim_text(str(numeric_raw.get("comparison_baseline") or metric_slots.get("comparison_baseline") or ""), 80),
            "metric_scope": compact_claim_text(str(numeric_raw.get("metric_scope") or metric_slots.get("metric_name") or ""), 90),
        },
        "date": {
            "temporal_status": compact_claim_text(str(date_raw.get("temporal_status") or ""), 40),
            "target_date": compact_claim_text(str(date_raw.get("target_date") or ""), 40),
            "target_year": compact_claim_text(str(date_raw.get("target_year") or ""), 20),
            "time_window": compact_claim_text(str(date_raw.get("time_window") or metric_slots.get("time_scope") or ""), 80),
        },
        "event": {
            "event_or_award": compact_claim_text(str(event_raw.get("event_or_award") or ""), 90),
            "category_or_subtype": compact_claim_text(str(event_raw.get("category_or_subtype") or ""), 60),
            "round_or_phase": compact_claim_text(str(event_raw.get("round_or_phase") or ""), 60),
            "instance_id_hint": compact_claim_text(str(event_raw.get("instance_id_hint") or ""), 80),
        },
        "route": {
            "route_relation_type": compact_claim_text(str(route_raw.get("route_relation_type") or ""), 60),
            "intermediate_place": compact_claim_text(str(route_raw.get("intermediate_place") or ""), 80),
            "required_sentence_shape": compact_claim_text(str(route_raw.get("required_sentence_shape") or ""), 120),
        },
        "policy": {
            "policy_status": compact_claim_text(str(policy_raw.get("policy_status") or ""), 60),
            "effective_scope": compact_claim_text(str(policy_raw.get("effective_scope") or ""), 80),
            "issuing_body": compact_claim_text(str(policy_raw.get("issuing_body") or ""), 80),
        },
    }


def build_verification_plan_prompt(item: Dict[str, Any], extracted: Dict[str, Any]) -> str:
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    claim_cards: List[Dict[str, Any]] = []
    for claim in claims[:MAX_CLAIMS]:
        if not isinstance(claim, dict):
            continue
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        claim_cards.append(
            {
                "claim_id": str(claim.get("claim_id") or ""),
                "claim": str(claim.get("claim") or ""),
                "centrality": str(claim.get("centrality") or ""),
                "evidence_mode": str(source_intent.get("evidence_mode") or ""),
                "evidence_target": str(source_intent.get("evidence_target") or ""),
                "evidence_shape": str(source_intent.get("evidence_shape") or ""),
                "risk_type": str(source_intent.get("risk_type") or ""),
                "assertion_strength": str(source_intent.get("assertion_strength") or ""),
                "route_meta": source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {},
                "verification_questions": bounded_string_list(claim.get("verification_questions"), 3, 90),
            }
        )
    return f"""请基于已抽取 claim 生成 debug-only verification_plan。

[time]
{item.get('time', '')}

[question]
{item.get('question', '')}

[answer]
{item.get('answer', '')}

[user_need]
{extracted.get('user_need', '')}

[need_type]
{extracted.get('need_type', '')}

[claims]
{json.dumps(claim_cards, ensure_ascii=False)}

要求：
- 每条 plan 必须对应输入里的 claim_id。
- atomic_facts 必须来自 claim 本身，可把复合句拆开，但不要判断真假。
- verification_subquestions 要问“要核查什么”，不要写“答案应该是什么”。
- required_evidence 要说明可裁决证据页/句需要具备的结构。
- reject_evidence 要说明哪些相关页、背景页、结果页或间接材料仍不足以裁决。
- mechanism_type 先描述“需要哪种证据获取机制”，不要把 route/numeric/date 当题材标签堆砌。
- core_binding 是所有 claim 都尽量填的通用对象约束；即使不是已知题型，也要尽量填 subject_entity / relation_or_metric / time_scope / expected_evidence_shape。
- typed_extension 只在命中已知机制时补充；不确定可留空对象，但不要省略这个字段。
- 如果 claim 涉及数值、行情、汇率、价格、指数、涨跌方向、日期窗口或官方牌价，metric_slots 必须尽量填完整。
- metric_slots 要抽通用指标结构，不能写题目专属规则；如果不是指标型 claim，value_type 写 not_metric。
- 保持紧凑，避免长段解释，只输出 JSON。
"""


def normalize_verification_plan(plan_obj: Optional[Dict[str, Any]], extracted: Dict[str, Any]) -> Dict[str, Any]:
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    valid_claim_ids = {str(claim.get("claim_id") or "") for claim in claims if isinstance(claim, dict)}
    raw_items: Any = []
    if isinstance(plan_obj, dict):
        raw_items = plan_obj.get("verification_plan") or plan_obj.get("claims") or []
    normalized_items: List[Dict[str, Any]] = []
    if isinstance(raw_items, list):
        for index, raw_item in enumerate(raw_items[:MAX_CLAIMS], 1):
            if not isinstance(raw_item, dict):
                continue
            claim_id = str(raw_item.get("claim_id") or f"c{index}")
            if valid_claim_ids and claim_id not in valid_claim_ids:
                continue
            claim_type = str(raw_item.get("claim_type") or "general_fact")
            if claim_type not in VERIFICATION_CLAIM_TYPES:
                claim_type = "general_fact"
            polarity = str(raw_item.get("polarity") or "uncertain")
            if polarity not in VERIFICATION_POLARITIES:
                polarity = "uncertain"
            metric_slots = normalize_metric_slots(raw_item.get("metric_slots"))
            mechanism_type = normalize_mechanism_type(
                raw_item.get("mechanism_type"),
                claim_type,
                metric_slots,
                str(raw_item.get("evidence_mode") or ""),
                str(raw_item.get("evidence_target") or ""),
                str(raw_item.get("evidence_shape") or ""),
            )
            core_binding = normalize_core_binding(raw_item.get("core_binding"), raw_item, metric_slots)
            typed_extension = normalize_typed_extension(raw_item.get("typed_extension"), metric_slots)
            task_semantics = normalize_task_semantics(
                raw_item.get("task_semantics"),
                claim_type,
                str(raw_item.get("evidence_mode") or ""),
                str(raw_item.get("evidence_target") or ""),
                mechanism_type,
                metric_slots,
            )

            atomic_facts: List[Dict[str, Any]] = []
            raw_facts = raw_item.get("atomic_facts") if isinstance(raw_item.get("atomic_facts"), list) else []
            for fact_index, raw_fact in enumerate(raw_facts[:3], 1):
                if not isinstance(raw_fact, dict):
                    continue
                fact_text = normalize_text(str(raw_fact.get("fact") or ""))
                if not fact_text:
                    continue
                fact_polarity = str(raw_fact.get("polarity") or polarity)
                if fact_polarity not in VERIFICATION_POLARITIES:
                    fact_polarity = polarity
                atomic_facts.append(
                    {
                        "fact_id": str(raw_fact.get("fact_id") or f"{claim_id}_f{fact_index}"),
                        "fact": compact_claim_text(fact_text, 160),
                        "polarity": fact_polarity,
                        "evidence_need": compact_claim_text(str(raw_fact.get("evidence_need") or "general_evidence"), 80),
                    }
                )

            subquestions: List[Dict[str, Any]] = []
            raw_questions = raw_item.get("verification_subquestions") if isinstance(raw_item.get("verification_subquestions"), list) else []
            for raw_question in raw_questions[:3]:
                if not isinstance(raw_question, dict):
                    continue
                question_text = normalize_text(str(raw_question.get("question") or ""))
                if not question_text:
                    continue
                query_intent = str(raw_question.get("suggested_query_intent") or "general_verify")
                if query_intent not in VERIFICATION_QUERY_INTENTS:
                    query_intent = "general_verify"
                subquestions.append(
                    {
                        "question": compact_claim_text(question_text, 140),
                        "answer_target": compact_claim_text(str(raw_question.get("answer_target") or ""), 100),
                        "suggested_query_intent": query_intent,
                        "missing_slots": bounded_string_list(raw_question.get("missing_slots"), 5, 40),
                    }
                )

            normalized_items.append(
                {
                    "claim_id": claim_id,
                    "claim_type": claim_type,
                    "mechanism_type": mechanism_type,
                    "polarity": polarity,
                    "subject": compact_claim_text(str(raw_item.get("subject") or ""), 80),
                    "relation": compact_claim_text(str(raw_item.get("relation") or ""), 80),
                    "object": compact_claim_text(str(raw_item.get("object") or ""), 80),
                    "condition_or_scope": compact_claim_text(str(raw_item.get("condition_or_scope") or ""), 120),
                    "task_semantics": task_semantics,
                    "core_binding": core_binding,
                    "typed_extension": typed_extension,
                    "metric_slots": metric_slots,
                    "atomic_facts": atomic_facts,
                    "verification_subquestions": subquestions,
                    "required_evidence": bounded_string_list(raw_item.get("required_evidence"), 5, 120),
                    "reject_evidence": bounded_string_list(raw_item.get("reject_evidence"), 5, 120),
                }
            )
    return {
        "debug_only": True,
        "status": "ok" if normalized_items else "empty",
        "verification_plan": normalized_items,
    }


def build_debug_verification_plan(item: Dict[str, Any], extracted: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    if not ENABLE_DEBUG_VERIFICATION_PLAN:
        return {"debug_only": True, "status": "disabled", "verification_plan": []}, ""
    prompt = build_verification_plan_prompt(item, extracted)
    plan_obj, raw = llm_chat(SYSTEM_VERIFICATION_PLAN, prompt, retries=0)
    if plan_obj is None:
        return {"debug_only": True, "status": "failed", "error": compact_claim_text(raw, 180), "verification_plan": []}, raw
    return normalize_verification_plan(plan_obj, extracted), raw


def verification_gap_layer(diag: Dict[str, Any]) -> str:
    stage = str(diag.get("retrieval_quality_stage") or "")
    flags = diag.get("retrieval_gap_flags") if isinstance(diag.get("retrieval_gap_flags"), list) else []
    flag_set = {str(flag) for flag in flags}
    if stage == "search_recall" or "no_search_result" in flag_set:
        return "search_recall"
    if "all_filtered" in flag_set or "poor_page_type" in flag_set or "background_dominant" in flag_set:
        return "page_contract"
    if any(flag.startswith("point_") for flag in flag_set) or stage == "point_readiness":
        return "point_grounding"
    if "missing_relation" in flag_set or "missing_object" in flag_set or "no_direct_sentence" in flag_set:
        return "sentence_shape"
    if "thin_direct_evidence" in flag_set or stage == "sentence_readiness":
        return "evidence_sufficiency"
    if "low_source_quality" in flag_set or "weak_source_only" in flag_set:
        return "source_quality"
    return stage or "unknown"


def verification_gap_action(layer: str) -> str:
    mapping = {
        "search_recall": "use_subquestion_to_find_recall",
        "page_contract": "target_required_evidence_page_shape",
        "sentence_shape": "target_required_sentence_shape",
        "point_grounding": "repair_same_object_metric_time_binding",
        "evidence_sufficiency": "add_fact_specific_followup",
        "source_quality": "prefer_more_authoritative_source",
    }
    return mapping.get(layer, "inspect_before_retry")


def build_verification_gap_alignment(
    verification_plan: Dict[str, Any],
    evidence_bundle: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    plan_items = verification_plan.get("verification_plan") if isinstance(verification_plan.get("verification_plan"), list) else []
    diagnostics = evidence_bundle.get("diagnostics_by_claim") if isinstance(evidence_bundle, dict) else {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    coverage = evidence_summary.get("claim_coverage") if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_coverage"), dict) else {}
    aligned: List[Dict[str, Any]] = []
    for plan_item in plan_items:
        if not isinstance(plan_item, dict):
            continue
        claim_id = str(plan_item.get("claim_id") or "")
        if not claim_id:
            continue
        diag = diagnostics.get(claim_id) if isinstance(diagnostics.get(claim_id), dict) else {}
        cov = coverage.get(claim_id) if isinstance(coverage.get(claim_id), dict) else {}
        layer = verification_gap_layer(diag)
        quality_label = str(diag.get("retrieval_quality_label") or "")
        stage = str(diag.get("retrieval_quality_stage") or "")
        flags = [str(flag) for flag in diag.get("retrieval_gap_flags", []) if str(flag)] if isinstance(diag.get("retrieval_gap_flags"), list) else []
        retry_needed = bool(diag.get("needs_retry")) or quality_label in {"bad", "borderline"} or layer in {
            "search_recall",
            "page_contract",
            "sentence_shape",
            "point_grounding",
            "evidence_sufficiency",
            "source_quality",
        }
        facts = []
        for fact in plan_item.get("atomic_facts", []) if isinstance(plan_item.get("atomic_facts"), list) else []:
            if isinstance(fact, dict):
                facts.append(
                    {
                        "fact_id": str(fact.get("fact_id") or ""),
                        "fact": compact_claim_text(str(fact.get("fact") or ""), 130),
                        "evidence_need": compact_claim_text(str(fact.get("evidence_need") or ""), 70),
                    }
                )
            if len(facts) >= 3:
                break
        questions = []
        for question in plan_item.get("verification_subquestions", []) if isinstance(plan_item.get("verification_subquestions"), list) else []:
            if isinstance(question, dict):
                questions.append(
                    {
                        "question": compact_claim_text(str(question.get("question") or ""), 120),
                        "answer_target": compact_claim_text(str(question.get("answer_target") or ""), 90),
                        "suggested_query_intent": str(question.get("suggested_query_intent") or "general_verify"),
                        "missing_slots": bounded_string_list(question.get("missing_slots"), 5, 40),
                    }
                )
            if len(questions) >= 3:
                break
        aligned.append(
            {
                "claim_id": claim_id,
                "claim_type": str(plan_item.get("claim_type") or "general_fact"),
                "polarity": str(plan_item.get("polarity") or "uncertain"),
                "retry_needed": retry_needed,
                "gap_layer": layer,
                "slot_retry_action": verification_gap_action(layer),
                "retrieval_quality_label": quality_label,
                "retrieval_quality_stage": stage,
                "retrieval_gap_flags": flags[:6],
                "point_gap_flags": [flag for flag in flags if str(flag).startswith("point_")][:4],
                "recommended_actions": [
                    str(action)
                    for action in diag.get("recommended_actions", [])
                    if str(action)
                ][:4] if isinstance(diag.get("recommended_actions"), list) else [],
                "coverage_level": str(cov.get("coverage_level") or ""),
                "direct_evidence_count": int(cov.get("direct_evidence_count") or 0) if isinstance(cov, dict) else 0,
                "contract_statuses": diag.get("retrieval_dominant_evidence_contract_statuses", {}),
                "contract_risks": diag.get("retrieval_dominant_evidence_contract_risks", {}),
                "page_utility_risks": diag.get("retrieval_dominant_page_utility_risks", {}),
                "dominant_contract_roles": diag.get("retrieval_dominant_evidence_contract_roles", {}),
                "dominant_point_risks": diag.get("retrieval_dominant_structured_point_risks", {}),
                "metric_slots": plan_item.get("metric_slots") if isinstance(plan_item.get("metric_slots"), dict) else {},
                "atomic_facts": facts,
                "verification_subquestions": questions,
                "required_evidence": bounded_string_list(plan_item.get("required_evidence"), 4, 110),
                "reject_evidence": bounded_string_list(plan_item.get("reject_evidence"), 4, 110),
            }
        )
    return {
        "debug_only": not ENABLE_VERIFICATION_PLAN_RETRY_CONTEXT,
        "status": "ok" if aligned else "empty",
        "alignment": aligned,
    }


def attach_verification_plan_hints_to_claims(
    extracted: Dict[str, Any],
    verification_plan: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(extracted, dict) or not isinstance(verification_plan, dict):
        return extracted
    plan_items = verification_plan.get("verification_plan") if isinstance(verification_plan.get("verification_plan"), list) else []
    if not plan_items:
        return extracted
    plan_by_id: Dict[str, Dict[str, Any]] = {}
    for item in plan_items:
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("claim_id") or "")
        if claim_id:
            plan_by_id[claim_id] = item
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    updated_claims: List[Dict[str, Any]] = []
    changed = False
    need_type = normalize_need_type(extracted.get("need_type"))
    for claim in claims:
        if not isinstance(claim, dict):
            updated_claims.append(claim)
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        plan_item = plan_by_id.get(claim_id) if claim_id else None
        if not isinstance(plan_item, dict):
            updated_claims.append(claim)
            continue
        rewritten = dict(claim)
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        rewritten_intent = dict(source_intent)
        claim_text = str(rewritten.get("claim") or "")
        claim_type = normalize_text(str(plan_item.get("claim_type") or ""))
        metric_slots = plan_item.get("metric_slots") if isinstance(plan_item.get("metric_slots"), dict) else {}
        if metric_slots and str(metric_slots.get("value_type") or "not_metric") != "not_metric":
            rewritten_intent["metric_slots"] = metric_slots
        raw_evidence_mode = normalize_text(str(plan_item.get("evidence_mode") or rewritten_intent.get("evidence_mode") or ""))
        raw_evidence_target = normalize_text(str(plan_item.get("evidence_target") or rewritten_intent.get("evidence_target") or ""))
        raw_evidence_shape = normalize_text(str(plan_item.get("evidence_shape") or rewritten_intent.get("evidence_shape") or ""))
        raw_mechanism_type = normalize_text(str(plan_item.get("mechanism_type") or rewritten_intent.get("mechanism_type") or ""))
        evidence_mode = infer_evidence_mode_from_plan(
            claim_type,
            metric_slots,
            raw_mechanism_type,
            raw_evidence_mode,
            raw_evidence_target,
        )
        evidence_target = raw_evidence_target if raw_evidence_target and raw_evidence_target != "general" else infer_evidence_target(claim_text, evidence_mode, need_type)
        evidence_shape = infer_evidence_shape_from_plan(raw_evidence_shape, claim_type, raw_mechanism_type, evidence_mode)
        expected_mechanism_type = infer_mechanism_type(claim_type, metric_slots, evidence_mode, evidence_target, evidence_shape)
        mechanism_type = raw_mechanism_type
        if should_override_mechanism_type(raw_mechanism_type, expected_mechanism_type, claim_type, evidence_target):
            mechanism_type = expected_mechanism_type
        mechanism_type = mechanism_type or expected_mechanism_type
        rewritten_intent["claim_type"] = claim_type or normalize_text(str(source_intent.get("claim_type") or ""))
        rewritten_intent["evidence_mode"] = evidence_mode
        rewritten_intent["evidence_target"] = evidence_target
        rewritten_intent["evidence_shape"] = evidence_shape
        rewritten_intent["mechanism_type"] = mechanism_type
        rewritten_intent["risk_type"] = infer_risk_type_from_plan(
            str(plan_item.get("risk_type") or rewritten_intent.get("risk_type") or ""),
            claim_type,
            evidence_mode,
            evidence_target,
            mechanism_type,
            need_type,
        )
        core_binding = plan_item.get("core_binding") if isinstance(plan_item.get("core_binding"), dict) else {}
        if core_binding:
            rewritten_intent["core_binding"] = core_binding
        typed_extension = plan_item.get("typed_extension") if isinstance(plan_item.get("typed_extension"), dict) else {}
        if typed_extension:
            rewritten_intent["typed_extension"] = typed_extension
        task_semantics = plan_item.get("task_semantics") if isinstance(plan_item.get("task_semantics"), dict) else {}
        if task_semantics:
            rewritten_intent["task_semantics"] = normalize_task_semantics(
                task_semantics,
                claim_type,
                evidence_mode,
                evidence_target,
                mechanism_type,
                metric_slots,
            )
        if evidence_mode == "route_fact" or evidence_target == "route_relation" or mechanism_type == "relation_sentence":
            rewritten_intent["route_meta"] = enrich_route_meta_from_claim(
                claim_text,
                rewritten_intent.get("route_meta") if isinstance(rewritten_intent.get("route_meta"), dict) else {},
                rewritten_intent.get("typed_extension") if isinstance(rewritten_intent.get("typed_extension"), dict) else {},
            )
        rewritten["source_intent"] = rewritten_intent
        rewritten["evidence_task_card"] = build_evidence_task_card(
            str(rewritten.get("claim") or ""),
            str(rewritten.get("centrality") or "supporting"),
            rewritten_intent,
            rewritten.get("verification_questions") if isinstance(rewritten.get("verification_questions"), list) else [],
            rewritten.get("queries") if isinstance(rewritten.get("queries"), list) else [],
        )
        updated_claims.append(rewritten)
        changed = True
    if not changed:
        return refresh_extracted_claim_programs(extracted)
    updated = dict(extracted)
    updated["claims"] = updated_claims
    return refresh_extracted_claim_programs(updated)


def compact_retry_alignment_context(verification_gap_alignment: Optional[Dict[str, Any]], retry_claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not ENABLE_VERIFICATION_PLAN_RETRY_CONTEXT or not isinstance(verification_gap_alignment, dict):
        return {}
    retry_ids = {str(claim.get("claim_id") or claim.get("id") or "") for claim in retry_claims}
    out: Dict[str, Any] = {}
    for item in verification_gap_alignment.get("alignment", []) if isinstance(verification_gap_alignment.get("alignment"), list) else []:
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("claim_id") or "")
        if claim_id not in retry_ids or not bool(item.get("retry_needed")):
            continue
        out[claim_id] = {
            "claim_type": item.get("claim_type"),
            "gap_layer": item.get("gap_layer"),
            "slot_retry_action": item.get("slot_retry_action"),
            "retrieval_gap_flags": item.get("retrieval_gap_flags", [])[:4],
            "point_gap_flags": item.get("point_gap_flags", [])[:4],
            "contract_statuses": item.get("contract_statuses", {}),
            "contract_risks": item.get("contract_risks", {}),
            "dominant_contract_roles": item.get("dominant_contract_roles", {}),
            "dominant_point_risks": item.get("dominant_point_risks", {}),
            "metric_slots": item.get("metric_slots", {}),
            "atomic_facts": item.get("atomic_facts", [])[:2],
            "verification_subquestions": item.get("verification_subquestions", [])[:2],
            "required_evidence": item.get("required_evidence", [])[:2],
            "reject_evidence": item.get("reject_evidence", [])[:2],
        }
    return out


def verification_alignment_supports_retry(verification_gap_alignment: Optional[Dict[str, Any]]) -> bool:
    if not ENABLE_VERIFICATION_PLAN_RETRY_CONTEXT or not isinstance(verification_gap_alignment, dict):
        return False
    actionable_layers = {"search_recall", "page_contract", "sentence_shape", "point_grounding", "evidence_sufficiency", "source_quality"}
    for item in verification_gap_alignment.get("alignment", []) if isinstance(verification_gap_alignment.get("alignment"), list) else []:
        if not isinstance(item, dict) or not bool(item.get("retry_needed")):
            continue
        if str(item.get("gap_layer") or "") in actionable_layers:
            return True
    return False


def verification_alignment_point_gap_retry_claim_ids(verification_gap_alignment: Optional[Dict[str, Any]]) -> set[str]:
    if not ENABLE_VERIFICATION_PLAN_RETRY_CONTEXT or not isinstance(verification_gap_alignment, dict):
        return set()
    out: set[str] = set()
    for item in verification_gap_alignment.get("alignment", []) if isinstance(verification_gap_alignment.get("alignment"), list) else []:
        if not isinstance(item, dict) or not bool(item.get("retry_needed")):
            continue
        claim_id = str(item.get("claim_id") or "")
        flags = [str(flag) for flag in item.get("retrieval_gap_flags", []) if str(flag)] if isinstance(item.get("retrieval_gap_flags"), list) else []
        actions = [str(action) for action in item.get("recommended_actions", []) if str(action)] if isinstance(item.get("recommended_actions"), list) else []
        stage = str(item.get("retrieval_quality_stage") or "")
        gap_layer = str(item.get("gap_layer") or "")
        if claim_id and any(flag.startswith("point_") for flag in flags) and "add_gap_query" in actions and (stage == "point_readiness" or gap_layer == "point_grounding"):
            out.add(claim_id)
    return out


def verification_alignment_supports_point_gap_retry(verification_gap_alignment: Optional[Dict[str, Any]]) -> bool:
    return bool(verification_alignment_point_gap_retry_claim_ids(verification_gap_alignment))


RETRY_STRUCTURED_MECHANISMS = {
    "structured_numeric_authority",
    "date_authority",
    "event_result_page",
    "current_status_update",
}

RETRY_SUPPORTING_STRUCTURED_SHAPES = {
    "authoritative_notice",
    "structured_historical_data",
    "event_detail_page",
    "current_status_update",
}


RETRY_HIGH_IMPACT_TARGETS = {
    "market_price",
    "prize_amount",
    "route_relation",
    "match_result",
    "withdrawal_status",
    "market_calendar",
}


def populated_slot_count(raw: Any, keys: Tuple[str, ...]) -> int:
    if not isinstance(raw, dict):
        return 0
    count = 0
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str):
            if normalize_text(value):
                count += 1
        elif isinstance(value, list):
            if any(normalize_text(str(item)) for item in value):
                count += 1
        elif value:
            count += 1
    return count


def point_gap_priority_score(context: Dict[str, Any]) -> int:
    score = 0
    flags = set(context.get("point_gap_flags") or [])
    if context.get("point_gap_retry"):
        score += 30
    if "point_time_scope_mismatch" in flags:
        score += 18
    if "point_metric_field_missing" in flags:
        score += 16
    if "point_subject_currency_mismatch" in flags:
        score += 14
    if "point_metric_value_missing" in flags:
        score += 10
    if context.get("retrieval_quality_stage") == "point_readiness":
        score += 8
    if context.get("object_binding_focus"):
        score += 8
    if str(context.get("centrality") or "") == "core":
        score += 6
    return score


def select_retry_operator_plan(context: Dict[str, Any]) -> Dict[str, Any]:
    gap_flags = set(context.get("gap_flags") or [])
    point_gap_flags = set(context.get("point_gap_flags") or [])
    recommended_actions = set(context.get("recommended_actions") or [])
    mechanism_type = str(context.get("mechanism_type") or "")
    mode = str(context.get("mode") or "")
    gap_layer = str(context.get("gap_layer") or "")
    gap_action = str(context.get("gap_action") or "")
    plan = {
        "family": "general_rewrite_probe",
        "primary_origin": "planner",
        "supporting_origins": [],
        "variant_hint": "",
        "reason": "fallback_general_rewrite_probe",
    }
    if context.get("point_gap_retry") and context.get("structured_retry_ready"):
        variant_hint = ""
        if "point_time_scope_mismatch" in point_gap_flags:
            variant_hint = "dated_record"
        elif point_gap_flags & {"point_metric_field_missing", "point_metric_value_missing", "point_subject_currency_mismatch"}:
            variant_hint = "history"
        plan.update(
            {
                "family": "structured_point_retry",
                "primary_origin": "structured_point_retry",
                "supporting_origins": ["metric_source_probe", "preferred_domain_probe"],
                "variant_hint": variant_hint,
                "reason": "structured_point_gap_retry",
            }
        )
        return plan
    route_like = bool(context.get("supporting_route_probe")) or mechanism_type == "relation_sentence" or mode == "route_fact"
    if gap_layer in {"search_recall", "page_contract", "sentence_shape", "evidence_sufficiency", "source_quality"}:
        if gap_layer == "search_recall":
            if int(context.get("preferred_domain_count") or 0) > 0 and "change_source_plan" in recommended_actions:
                plan.update(
                    {
                        "family": "preferred_domain_probe",
                        "primary_origin": "preferred_domain_probe",
                        "supporting_origins": ["route_frame_probe", "metric_source_probe"],
                        "reason": "gap_search_recall_preferred_domain",
                    }
                )
            elif route_like:
                plan.update(
                    {
                        "family": "route_frame_probe",
                        "primary_origin": "route_frame_probe",
                        "supporting_origins": ["gap_pseudo_page_probe", "page_intent_retry"],
                        "reason": "gap_search_recall_route_frame",
                    }
                )
            elif context.get("structured_retry_ready") and mechanism_type in RETRY_STRUCTURED_MECHANISMS:
                plan.update(
                    {
                        "family": "metric_source_probe",
                        "primary_origin": "metric_source_probe",
                        "supporting_origins": ["preferred_domain_probe"],
                        "reason": "gap_search_recall_metric_source",
                    }
                )
            else:
                plan.update(
                    {
                        "family": "route_frame_probe",
                        "primary_origin": "route_frame_probe",
                        "supporting_origins": ["metric_source_probe"],
                        "reason": "gap_search_recall_generic",
                    }
                )
            plan["variant_hint"] = gap_action
            return plan
        if gap_layer == "page_contract":
            if "re_retrieve_with_page_intent" in recommended_actions or route_like:
                plan.update(
                    {
                        "family": "page_intent_retry",
                        "primary_origin": "page_intent_retry",
                        "supporting_origins": ["gap_pseudo_page_probe", "route_frame_probe"],
                        "reason": "gap_page_contract_page_intent",
                    }
                )
            else:
                plan.update(
                    {
                        "family": "gap_pseudo_page_probe",
                        "primary_origin": "gap_pseudo_page_probe",
                        "supporting_origins": ["page_intent_retry", "route_frame_probe"],
                        "reason": "gap_page_contract_pseudo_page",
                    }
                )
            plan["variant_hint"] = gap_action
            return plan
        if gap_layer == "sentence_shape":
            if "add_gap_query" in recommended_actions or "re_retrieve_with_page_intent" in recommended_actions:
                plan.update(
                    {
                        "family": "gap_pseudo_page_probe",
                        "primary_origin": "gap_pseudo_page_probe",
                        "supporting_origins": ["page_intent_retry", "route_frame_probe"],
                        "reason": "gap_sentence_shape_pseudo_page",
                    }
                )
            else:
                plan.update(
                    {
                        "family": "page_intent_retry",
                        "primary_origin": "page_intent_retry",
                        "supporting_origins": ["gap_pseudo_page_probe", "route_frame_probe"],
                        "reason": "gap_sentence_shape_page_intent",
                    }
                )
            plan["variant_hint"] = gap_action
            return plan
        if gap_layer == "evidence_sufficiency":
            if context.get("structured_retry_ready") and mechanism_type in RETRY_STRUCTURED_MECHANISMS:
                plan.update(
                    {
                        "family": "metric_source_probe",
                        "primary_origin": "metric_source_probe",
                        "supporting_origins": ["preferred_domain_probe", "structured_point_retry"],
                        "reason": "gap_evidence_sufficiency_metric_source",
                    }
                )
            elif int(context.get("preferred_domain_count") or 0) > 0:
                plan.update(
                    {
                        "family": "preferred_domain_probe",
                        "primary_origin": "preferred_domain_probe",
                        "supporting_origins": ["gap_pseudo_page_probe", "metric_source_probe"],
                        "reason": "gap_evidence_sufficiency_preferred_domain",
                    }
                )
            else:
                plan.update(
                    {
                        "family": "gap_pseudo_page_probe",
                        "primary_origin": "gap_pseudo_page_probe",
                        "supporting_origins": ["metric_source_probe", "page_intent_retry"],
                        "reason": "gap_evidence_sufficiency_generic",
                    }
                )
            plan["variant_hint"] = gap_action
            return plan
        if gap_layer == "source_quality":
            if int(context.get("preferred_domain_count") or 0) > 0:
                plan.update(
                    {
                        "family": "preferred_domain_probe",
                        "primary_origin": "preferred_domain_probe",
                        "supporting_origins": ["metric_source_probe"],
                        "reason": "gap_source_quality_preferred_domain",
                    }
                )
            else:
                plan.update(
                    {
                        "family": "metric_source_probe",
                        "primary_origin": "metric_source_probe",
                        "supporting_origins": ["preferred_domain_probe"],
                        "reason": "gap_source_quality_metric_source",
                    }
                )
            plan["variant_hint"] = gap_action
            return plan
    if route_like:
        if "re_retrieve_with_page_intent" in recommended_actions:
            plan.update(
                {
                    "family": "page_intent_retry",
                    "primary_origin": "page_intent_retry",
                    "supporting_origins": ["gap_pseudo_page_probe", "route_frame_probe"],
                    "reason": "route_page_intent_retry",
                }
            )
        elif context.get("retrieval_quality_stage") in {"page_retention", "sentence_readiness"} or "missing_relation" in gap_flags:
            plan.update(
                {
                    "family": "gap_pseudo_page_probe",
                    "primary_origin": "gap_pseudo_page_probe",
                    "supporting_origins": ["route_frame_probe", "page_shape_probe"],
                    "reason": "route_page_shape_gap_retry",
                }
            )
        else:
            plan.update(
                {
                    "family": "route_frame_probe",
                    "primary_origin": "route_frame_probe",
                    "supporting_origins": ["gap_pseudo_page_probe"],
                    "reason": "route_search_frame_retry",
                }
            )
        return plan
    if "re_retrieve_with_page_intent" in recommended_actions:
        plan.update(
            {
                "family": "page_intent_retry",
                "primary_origin": "page_intent_retry",
                "supporting_origins": ["page_shape_probe"],
                "reason": "generic_page_intent_retry",
            }
        )
        return plan
    if "change_source_plan" in recommended_actions and int(context.get("preferred_domain_count") or 0) > 0:
        plan.update(
            {
                "family": "preferred_domain_probe",
                "primary_origin": "preferred_domain_probe",
                "supporting_origins": ["metric_source_probe"],
                "reason": "preferred_domain_source_shift",
            }
        )
        return plan
    if mechanism_type in {"structured_numeric_authority", "date_authority", "event_result_page", "current_status_update"} or mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result"}:
        plan.update(
            {
                "family": "metric_source_probe",
                "primary_origin": "metric_source_probe",
                "supporting_origins": ["preferred_domain_probe", "numeric_discovery"],
                "reason": "structured_metric_source_probe",
            }
        )
    return plan


def extract_plan_quality(extracted: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    if not isinstance(extracted, dict):
        return False, "not_dict"
    claims = extracted.get("claims")
    if not isinstance(claims, list) or not claims:
        return False, "missing_claims"
    valid_claims = 0
    has_core = False
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if normalize_text(str(claim.get("claim") or "")):
            valid_claims += 1
        if str(claim.get("centrality") or "") == "core":
            has_core = True
    if valid_claims <= 0:
        return False, "empty_claim_text"
    if not has_core:
        return False, "missing_core_claim"
    if not normalize_need_type(extracted.get("need_type")):
        return False, "missing_need_type"
    return True, "ok"


def build_retry_claim_context(
    claim: Dict[str, Any],
    diagnostic: Dict[str, Any],
    claim_coverage: Dict[str, Any],
    claim_summary: Dict[str, Any],
    need_type: str,
    allow_route_supporting_probe: bool,
    point_gap_retry_ids: set[str],
) -> Dict[str, Any]:
    claim_id = str(claim.get("claim_id") or claim.get("id") or "")
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
    centrality = str(claim.get("centrality") or "supporting")
    mode = str(source_intent.get("evidence_mode") or "")
    mechanism_type = str(source_intent.get("mechanism_type") or "")
    evidence_target = str(source_intent.get("evidence_target") or "")
    evidence_shape = str(source_intent.get("evidence_shape") or "")
    coverage_level = str(claim_coverage.get("coverage_level") or "")
    direct_count = int(claim_coverage.get("direct_evidence_count") or 0)
    supporting_direct = int(claim_coverage.get("supporting_direct_points") or 0)
    refuting_direct = int(claim_coverage.get("refuting_direct_points") or 0)
    web_count = int(claim_coverage.get("web_evidence_count") or 0)
    needs_retry = bool(diagnostic.get("needs_retry"))
    route_quality_score = diagnostic.get("route_query_quality_score")
    retrieval_quality_score = diagnostic.get("retrieval_quality_score")
    retrieval_quality_label = str(diagnostic.get("retrieval_quality_label") or "")
    retrieval_quality_stage = str(diagnostic.get("retrieval_quality_stage") or "")
    recommended_actions = diagnostic.get("recommended_actions") if isinstance(diagnostic.get("recommended_actions"), list) else []
    gap_flags = diagnostic.get("retrieval_gap_flags") if isinstance(diagnostic.get("retrieval_gap_flags"), list) else []
    high_value_need = need_type in HIGH_VALUE_REWRITE_NEEDS
    high_value_mode = mode in HIGH_VALUE_REWRITE_MODES
    high_value_mechanism = mechanism_type in RETRY_STRUCTURED_MECHANISMS
    low_route_quality = (
        mode == "route_fact"
        and isinstance(route_quality_score, int)
        and route_quality_score < 45
    )
    low_retrieval_quality = (
        isinstance(retrieval_quality_score, int)
        and (retrieval_quality_score < 55 or retrieval_quality_label == "bad")
    )
    supporting_route_probe = (
        allow_route_supporting_probe
        and centrality == "supporting"
        and is_route_like_claim(claim)
        and str(task_card.get("priority_label") or "normal") in {"critical", "high"}
        and (
            low_route_quality
            or (
                low_retrieval_quality
                and retrieval_quality_stage in {"search_recall", "page_retention", "sentence_readiness"}
                and any(action in {"change_source_plan", "re_retrieve_with_page_intent", "add_gap_query"} for action in recommended_actions)
            )
        )
    )
    point_gap_retry = (
        claim_id in point_gap_retry_ids
        or (
            any(str(flag).startswith("point_") for flag in gap_flags)
            and "add_gap_query" in recommended_actions
            and retrieval_quality_stage == "point_readiness"
        )
    )
    comparable_numeric_signal = False
    mismatch_only = False
    if mode == "numeric_fact":
        for point_key in ("supporting_points", "refuting_points"):
            for point in claim_summary.get(point_key) or []:
                alignment = point.get("numeric_alignment") if isinstance(point, dict) and isinstance(point.get("numeric_alignment"), dict) else {}
                if alignment.get("comparable") and point.get("direct_answer") == "direct":
                    comparable_numeric_signal = True
                    break
            if comparable_numeric_signal:
                break
        mismatch_only = any(
            isinstance(point, dict)
            and isinstance(point.get("numeric_alignment"), dict)
            and not point["numeric_alignment"].get("comparable")
            for point in claim_summary.get("uncertain_points") or []
        )
    point_gap_flags = [str(flag) for flag in gap_flags if str(flag).startswith("point_")]
    preferred_domains = source_intent.get("preferred_domains") if isinstance(source_intent.get("preferred_domains"), list) else []
    structured_point_status = ""
    if isinstance(diagnostic.get("retrieval_dominant_structured_point_statuses"), dict):
        statuses = diagnostic.get("retrieval_dominant_structured_point_statuses") or {}
        structured_point_status = next(iter(statuses.keys()), "")
    gap_layer = verification_gap_layer(diagnostic)
    gap_action = verification_gap_action(gap_layer)
    task_priority_score = int(task_card.get("priority_score") or 0)
    task_priority_label = str(task_card.get("priority_label") or "normal")
    structured_retry_ready = mechanism_type in RETRY_STRUCTURED_MECHANISMS
    core_binding = source_intent.get("core_binding") if isinstance(source_intent.get("core_binding"), dict) else {}
    metric_slots = source_intent.get("metric_slots") if isinstance(source_intent.get("metric_slots"), dict) else {}
    core_binding_slot_count = populated_slot_count(
        core_binding,
        ("subject_entity", "relation_or_metric", "time_scope", "expected_evidence_shape"),
    )
    metric_slot_count = populated_slot_count(
        metric_slots,
        ("metric_name", "value_type", "time_scope", "unit", "source_authority", "comparison_baseline"),
    )
    supporting_structured_retry = (
        centrality == "supporting"
        and structured_retry_ready
        and task_priority_label in {"critical", "high"}
        and (
            evidence_shape in RETRY_SUPPORTING_STRUCTURED_SHAPES
            or evidence_target in RETRY_HIGH_IMPACT_TARGETS
            or mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result", "entity_fact"}
        )
    )
    object_binding_focus = (
        structured_retry_ready
        and (
            core_binding_slot_count >= 3
            or metric_slot_count >= 3
            or evidence_target in RETRY_HIGH_IMPACT_TARGETS
        )
    )
    point_gap_priority = point_gap_priority_score(
        {
            "point_gap_retry": point_gap_retry,
            "point_gap_flags": point_gap_flags,
            "retrieval_quality_stage": retrieval_quality_stage,
            "object_binding_focus": object_binding_focus,
            "centrality": centrality,
        }
    )
    return {
        "claim_id": claim_id,
        "claim": claim,
        "source_intent": source_intent,
        "task_card": task_card,
        "centrality": centrality,
        "mode": mode,
        "mechanism_type": mechanism_type,
        "evidence_target": evidence_target,
        "evidence_shape": evidence_shape,
        "coverage_level": coverage_level,
        "direct_count": direct_count,
        "supporting_direct": supporting_direct,
        "refuting_direct": refuting_direct,
        "web_count": web_count,
        "needs_retry": needs_retry,
        "route_quality_score": route_quality_score,
        "retrieval_quality_score": retrieval_quality_score,
        "retrieval_quality_label": retrieval_quality_label,
        "retrieval_quality_stage": retrieval_quality_stage,
        "recommended_actions": recommended_actions,
        "gap_flags": gap_flags,
        "point_gap_flags": point_gap_flags,
        "high_value_need": high_value_need,
        "high_value_mode": high_value_mode,
        "high_value_mechanism": high_value_mechanism,
        "low_route_quality": low_route_quality,
        "low_retrieval_quality": low_retrieval_quality,
        "supporting_route_probe": supporting_route_probe,
        "supporting_structured_retry": supporting_structured_retry,
        "point_gap_retry": point_gap_retry,
        "comparable_numeric_signal": comparable_numeric_signal,
        "mismatch_only": mismatch_only,
        "preferred_domain_count": len(preferred_domains),
        "structured_point_status": structured_point_status,
        "gap_layer": gap_layer,
        "gap_action": gap_action,
        "task_priority_score": task_priority_score,
        "task_priority_label": task_priority_label,
        "structured_retry_ready": structured_retry_ready,
        "core_binding_slot_count": core_binding_slot_count,
        "metric_slot_count": metric_slot_count,
        "object_binding_focus": object_binding_focus,
        "point_gap_priority": point_gap_priority,
    }


def retry_eligibility(context: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if (
        context["centrality"] != "core"
        and not context["supporting_route_probe"]
        and not context["supporting_structured_retry"]
        and not context["point_gap_retry"]
    ):
        return False, ["non_core_not_retry_target"]
    if (
        not context["high_value_need"]
        and not context["high_value_mode"]
        and not context["high_value_mechanism"]
        and not context["supporting_structured_retry"]
        and not context["point_gap_retry"]
    ):
        return False, ["not_high_value"]
    if (
        (context["coverage_level"] in {"strong", "moderate"} or context["direct_count"] > 0 or context["supporting_direct"] > 0 or context["refuting_direct"] > 0)
        and not context["low_route_quality"]
        and not context["low_retrieval_quality"]
        and not context["point_gap_retry"]
    ):
        return False, ["already_has_direct_evidence"]
    if (
        context["coverage_level"] == "weak"
        and context["web_count"] >= 2
        and context["mode"] not in {"route_fact", "schedule_fact", "event_result"}
        and not context["point_gap_retry"]
    ):
        return False, ["weak_but_enough_web_evidence"]
    if (
        context["mode"] == "numeric_fact"
        and context["mismatch_only"]
        and not context["comparable_numeric_signal"]
        and context["coverage_level"] in {"weak", "partial"}
        and not context["point_gap_retry"]
    ):
        return False, ["numeric_mismatch_only_without_retry_gain"]
    if context["point_gap_retry"]:
        reasons.append("point_gap_retry")
    if context["supporting_structured_retry"]:
        reasons.append("supporting_structured_retry")
    if context["low_route_quality"]:
        reasons.append("low_route_quality")
    if context["low_retrieval_quality"]:
        reasons.append("low_retrieval_quality")
    if context["coverage_level"] in {"none", "weak", "partial"}:
        reasons.append(f"coverage_{context['coverage_level'] or 'unknown'}")
    if context["needs_retry"]:
        reasons.append("diagnostic_retry_flag")
    return True, reasons or ["general_retry_candidate"]


def score_retry_claim(context: Dict[str, Any]) -> Tuple[int, Dict[str, int]]:
    breakdown = {
        "verdict_impact": 0,
        "gap_actionability": 0,
        "repairability": 0,
        "authority_reachability": 0,
        "priority_alignment": 0,
        "object_binding_focus": 0,
        "retry_cost_penalty": 0,
    }
    if context["centrality"] == "core":
        breakdown["verdict_impact"] += 34
    elif context["point_gap_retry"]:
        breakdown["verdict_impact"] += 18
    elif context["supporting_structured_retry"]:
        breakdown["verdict_impact"] += 16
    elif context["supporting_route_probe"]:
        breakdown["verdict_impact"] += 10
    if context["evidence_target"] in RETRY_HIGH_IMPACT_TARGETS:
        breakdown["verdict_impact"] += 8
    elif context["mode"] in {"numeric_fact", "date_fact", "schedule_fact", "event_result"}:
        breakdown["verdict_impact"] += 5

    point_gap_flags = set(context["point_gap_flags"])
    if "point_time_scope_mismatch" in point_gap_flags:
        breakdown["gap_actionability"] += 25
    if "point_metric_field_missing" in point_gap_flags:
        breakdown["gap_actionability"] += 20
    if "point_subject_currency_mismatch" in point_gap_flags:
        breakdown["gap_actionability"] += 18
    if "point_metric_value_missing" in point_gap_flags:
        breakdown["gap_actionability"] += 14
    if context["point_gap_retry"] and "add_gap_query" in context["recommended_actions"]:
        breakdown["gap_actionability"] += 8
    if not breakdown["gap_actionability"]:
        if context["low_route_quality"]:
            breakdown["gap_actionability"] += 16
        elif context["low_retrieval_quality"]:
            breakdown["gap_actionability"] += 12
        elif context["needs_retry"]:
            breakdown["gap_actionability"] += 6

    if context["structured_point_status"] == "partial":
        breakdown["repairability"] += 16
    elif context["structured_point_status"] == "missing":
        breakdown["repairability"] += 10
    if context["retrieval_quality_stage"] == "point_readiness":
        breakdown["repairability"] += 10
    elif context["retrieval_quality_stage"] in {"sentence_readiness", "page_retention"}:
        breakdown["repairability"] += 6
    if context["coverage_level"] in {"strong", "moderate"} and context["point_gap_retry"]:
        breakdown["repairability"] += 8
    elif context["coverage_level"] in {"weak", "partial"} and context["structured_retry_ready"]:
        breakdown["repairability"] += 6

    if context["preferred_domain_count"] > 0:
        breakdown["authority_reachability"] += 8
    if context["mechanism_type"] in {"structured_numeric_authority", "date_authority"}:
        breakdown["authority_reachability"] += 10
    elif context["mechanism_type"] in {"event_result_page", "current_status_update", "relation_sentence"}:
        breakdown["authority_reachability"] += 6
    if context["mode"] in {"numeric_fact", "date_fact", "schedule_fact"}:
        breakdown["authority_reachability"] += 6
    if context["evidence_shape"] in {"structured_historical_data", "authoritative_notice", "official_record"}:
        breakdown["authority_reachability"] += 4

    if context["task_priority_label"] == "critical":
        breakdown["priority_alignment"] += 12
    elif context["task_priority_label"] == "high":
        breakdown["priority_alignment"] += 8
    elif context["task_priority_score"] >= 25:
        breakdown["priority_alignment"] += 4
    if context["structured_retry_ready"] and context["centrality"] == "core":
        breakdown["priority_alignment"] += 8

    if context["object_binding_focus"]:
        breakdown["object_binding_focus"] += 10
    if context["core_binding_slot_count"] >= 3:
        breakdown["object_binding_focus"] += 8
    elif context["core_binding_slot_count"] == 2:
        breakdown["object_binding_focus"] += 4
    if context["metric_slot_count"] >= 4:
        breakdown["object_binding_focus"] += 8
    elif context["metric_slot_count"] >= 2:
        breakdown["object_binding_focus"] += 4
    if context["point_gap_priority"] >= 30:
        breakdown["object_binding_focus"] += 8
    elif context["point_gap_priority"] >= 16:
        breakdown["object_binding_focus"] += 4

    if context["coverage_level"] == "none" and context["web_count"] == 0:
        breakdown["retry_cost_penalty"] += 10
    elif context["low_retrieval_quality"] and context["retrieval_quality_stage"] == "search_recall":
        breakdown["retry_cost_penalty"] += 6
    if context["centrality"] != "core" and not context["point_gap_retry"]:
        breakdown["retry_cost_penalty"] += 6
    if (
        context["centrality"] != "core"
        and context["mechanism_type"] == "date_authority"
        and context["coverage_level"] in {"weak", "partial"}
        and not context["point_gap_retry"]
    ):
        breakdown["retry_cost_penalty"] += 8

    score = (
        breakdown["verdict_impact"]
        + breakdown["gap_actionability"]
        + breakdown["repairability"]
        + breakdown["authority_reachability"]
        + breakdown["priority_alignment"]
        + breakdown["object_binding_focus"]
        - breakdown["retry_cost_penalty"]
    )
    return score, breakdown


def retry_budget_decision(candidates: List[Dict[str, Any]], need_type: str) -> Dict[str, Any]:
    retry_limit = 1
    reason = "default_single_retry"
    structured_core_candidates = [
        item
        for item in candidates
        if str((item.get("context") or {}).get("centrality") or "") == "core"
        and str((item.get("context") or {}).get("task_priority_label") or "") in {"critical", "high"}
        and (
            bool((item.get("context") or {}).get("structured_retry_ready"))
            or str((item.get("context") or {}).get("mechanism_type") or "") == "relation_sentence"
        )
    ]
    structured_supporting_candidates = [
        item
        for item in candidates
        if bool((item.get("context") or {}).get("supporting_structured_retry"))
        and str((item.get("context") or {}).get("task_priority_label") or "") in {"critical", "high"}
    ]
    object_binding_focus_candidates = [
        item
        for item in candidates
        if bool((item.get("context") or {}).get("object_binding_focus"))
        and int((item.get("context") or {}).get("point_gap_priority") or 0) >= 16
    ]
    if need_type in {"sports_result", "current_result", "schedule_time"}:
        retry_limit = min(REWRITE_MAX_CLAIMS, 2)
        reason = "need_type_allows_two_retries"
    elif len(object_binding_focus_candidates) >= 2:
        retry_limit = min(REWRITE_MAX_CLAIMS, 2)
        reason = "multiple_object_binding_point_gap_candidates"
    elif object_binding_focus_candidates and structured_core_candidates:
        retry_limit = min(REWRITE_MAX_CLAIMS, 2)
        reason = "core_plus_object_binding_gap_candidate"
    elif len(structured_core_candidates) >= 2:
        retry_limit = min(REWRITE_MAX_CLAIMS, 2)
        reason = "multiple_high_value_structured_core_claims"
    elif structured_core_candidates and structured_supporting_candidates:
        retry_limit = min(REWRITE_MAX_CLAIMS, 2)
        reason = "core_plus_high_value_structured_supporting"
    elif any((item.get("context") or {}).get("point_gap_retry") for item in candidates[:2]):
        retry_limit = min(REWRITE_MAX_CLAIMS, 2)
        reason = "top_candidates_include_point_gap_retry"
    elif candidates and candidates[0]["claim"].get("source_intent", {}).get("evidence_mode") == "route_fact":
        retry_limit = 1
        reason = "route_retry_kept_single"
    selected = candidates[:retry_limit]
    compact_selected = [
        {
            "claim_id": str(item.get("claim", {}).get("claim_id") or item.get("claim", {}).get("id") or ""),
            "retry_value": int(item.get("priority") or 0),
            "centrality": str((item.get("context") or {}).get("centrality") or ""),
            "mechanism_type": str((item.get("context") or {}).get("mechanism_type") or ""),
            "task_priority_label": str((item.get("context") or {}).get("task_priority_label") or ""),
            "point_gap_retry": bool((item.get("context") or {}).get("point_gap_retry")),
            "point_gap_priority": int((item.get("context") or {}).get("point_gap_priority") or 0),
            "object_binding_focus": bool((item.get("context") or {}).get("object_binding_focus")),
        }
        for item in selected
    ]
    return {
        "retry_limit": retry_limit,
        "reason": reason,
        "selected_items": selected,
        "debug_summary": {
            "retry_limit": retry_limit,
            "reason": reason,
            "selected_claim_ids": [item["claim_id"] for item in compact_selected],
            "selected_candidates": compact_selected,
            "structured_core_candidate_count": len(structured_core_candidates),
            "object_binding_focus_candidate_count": len(object_binding_focus_candidates),
            "top_candidate_scores": [
                {
                    "claim_id": str(item.get("claim", {}).get("claim_id") or item.get("claim", {}).get("id") or ""),
                    "retry_value": int(item.get("priority") or 0),
                    "centrality": str((item.get("context") or {}).get("centrality") or ""),
                    "mechanism_type": str((item.get("context") or {}).get("mechanism_type") or ""),
                    "task_priority_label": str((item.get("context") or {}).get("task_priority_label") or ""),
                    "point_gap_retry": bool((item.get("context") or {}).get("point_gap_retry")),
                    "point_gap_priority": int((item.get("context") or {}).get("point_gap_priority") or 0),
                    "object_binding_focus": bool((item.get("context") or {}).get("object_binding_focus")),
                }
                for item in candidates[:4]
            ],
        },
        "structured_core_candidate_count": len(structured_core_candidates),
    }


def select_retry_claims_under_budget(candidates: List[Dict[str, Any]], need_type: str) -> List[Dict[str, Any]]:
    return retry_budget_decision(candidates, need_type)["selected_items"]


def evaluate_retry_claim_candidates(
    claims: List[Dict[str, Any]],
    evidence_bundle: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]] = None,
    need_type: str = "",
    allow_route_supporting_probe: bool = False,
    verification_gap_alignment: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    diagnostics = evidence_bundle.get("diagnostics_by_claim") if isinstance(evidence_bundle, dict) else {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    coverage = evidence_summary.get("claim_coverage") if isinstance(evidence_summary, dict) else {}
    if not isinstance(coverage, dict):
        coverage = {}
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary, dict) else {}
    if not isinstance(summaries, dict):
        summaries = {}
    point_gap_retry_ids = verification_alignment_point_gap_retry_claim_ids(verification_gap_alignment)
    candidates: List[Dict[str, Any]] = []
    audit_rows: List[Dict[str, Any]] = []
    for claim in claims:
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        diagnostic = diagnostics.get(claim_id) if isinstance(diagnostics.get(claim_id), dict) else {}
        claim_coverage = coverage.get(claim_id) if isinstance(coverage.get(claim_id), dict) else {}
        claim_summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        context = build_retry_claim_context(
            claim,
            diagnostic,
            claim_coverage,
            claim_summary,
            need_type,
            allow_route_supporting_probe,
            point_gap_retry_ids,
        )
        eligible, eligibility_reasons = retry_eligibility(context)
        retry_value = 0
        score_breakdown: Dict[str, int] = {}
        if eligible:
            retry_value, score_breakdown = score_retry_claim(context)
        operator_plan = select_retry_operator_plan(context) if (eligible or context.get("point_gap_retry") or context.get("supporting_route_probe")) else {}
        audit_row = {
            "claim_id": claim_id,
            "claim": str(claim.get("claim") or ""),
            "centrality": context["centrality"],
            "mechanism_type": context["mechanism_type"],
            "evidence_mode": context["mode"],
            "evidence_target": context["evidence_target"],
            "task_priority_label": context["task_priority_label"],
            "task_priority_score": context["task_priority_score"],
            "coverage_level": context["coverage_level"] or "unknown",
            "coverage_reason": claim_coverage.get("coverage_reason") if claim_coverage else "",
            "direct_count": context["direct_count"],
            "supporting_direct": context["supporting_direct"],
            "refuting_direct": context["refuting_direct"],
            "web_count": context["web_count"],
            "retrieval_quality_score": diagnostic.get("retrieval_quality_score"),
            "retrieval_quality_label": context["retrieval_quality_label"],
            "retrieval_quality_stage": context["retrieval_quality_stage"],
            "retrieval_gap_flags": context["gap_flags"],
            "recommended_actions": context["recommended_actions"],
            "gap_layer": context["gap_layer"],
            "gap_action": context["gap_action"],
            "point_gap_retry": context["point_gap_retry"],
            "point_gap_priority": context["point_gap_priority"],
            "object_binding_focus": context["object_binding_focus"],
            "core_binding_slot_count": context["core_binding_slot_count"],
            "metric_slot_count": context["metric_slot_count"],
            "structured_point_status": context["structured_point_status"],
            "retry_eligible": eligible,
            "retry_eligibility_reasons": eligibility_reasons,
            "retry_value": retry_value,
            "retry_score_breakdown": score_breakdown,
            "retry_operator_plan": operator_plan,
            "selected_under_budget": False,
            "candidate_rank": 0,
        }
        audit_rows.append(audit_row)
        if not eligible or retry_value <= 0:
            continue
        retry_claim = dict(claim)
        retry_claim["_retry_reason"] = {
            "coverage_level": context["coverage_level"] or "unknown",
            "coverage_reason": claim_coverage.get("coverage_reason") if claim_coverage else "",
            "diagnostic_reason": diagnostic.get("reason") if diagnostic else "",
            "centrality": context["centrality"],
            "task_priority_label": context["task_priority_label"],
            "task_priority_score": context["task_priority_score"],
            "mechanism_type": context["mechanism_type"],
            "evidence_target": context["evidence_target"],
            "route_query_quality_score": diagnostic.get("route_query_quality_score"),
            "route_query_quality_issue": diagnostic.get("route_query_quality_issue"),
            "route_query_quality_components": diagnostic.get("route_query_quality_components"),
            "retrieval_quality_score": diagnostic.get("retrieval_quality_score"),
            "retrieval_quality_label": diagnostic.get("retrieval_quality_label"),
            "retrieval_quality_stage": diagnostic.get("retrieval_quality_stage"),
            "retrieval_gap_flags": context["gap_flags"],
            "recommended_actions": context["recommended_actions"],
            "gap_layer": context["gap_layer"],
            "gap_action": context["gap_action"],
            "point_gap_retry": context["point_gap_retry"],
            "point_gap_priority": context["point_gap_priority"],
            "object_binding_focus": context["object_binding_focus"],
            "core_binding_slot_count": context["core_binding_slot_count"],
            "metric_slot_count": context["metric_slot_count"],
            "retry_eligible": True,
            "retry_eligibility_reasons": eligibility_reasons,
            "retry_value": retry_value,
            "retry_score_breakdown": score_breakdown,
            "retry_operator_plan": operator_plan,
        }
        candidates.append({"priority": retry_value, "claim": retry_claim, "context": context, "audit_row": audit_row})
    candidates.sort(
        key=lambda item: (
            int(item.get("priority") or 0),
            int(((item.get("context") or {}).get("point_gap_priority") or 0)),
            1 if (item.get("context") or {}).get("object_binding_focus") else 0,
            int(((item.get("context") or {}).get("core_binding_slot_count") or 0)),
            int(((item.get("context") or {}).get("metric_slot_count") or 0)),
            int(((item.get("context") or {}).get("task_priority_score") or 0)),
            1 if (item.get("context") or {}).get("point_gap_retry") else 0,
            1 if str(item.get("claim", {}).get("centrality") or "") == "core" else 0,
        ),
        reverse=True,
    )
    budget_decision = retry_budget_decision(candidates, need_type)
    selected_items = budget_decision["selected_items"]
    selected_ids = {
        str(item.get("claim", {}).get("claim_id") or item.get("claim", {}).get("id") or "")
        for item in selected_items
    }
    for rank, item in enumerate(candidates, 1):
        audit_row = item.get("audit_row") if isinstance(item.get("audit_row"), dict) else {}
        claim_id = str(item.get("claim", {}).get("claim_id") or item.get("claim", {}).get("id") or "")
        if audit_row:
            audit_row["candidate_rank"] = rank
            audit_row["selected_under_budget"] = claim_id in selected_ids
        retry_reason = item.get("claim", {}).get("_retry_reason") if isinstance(item.get("claim", {}).get("_retry_reason"), dict) else {}
        if retry_reason:
            retry_reason["candidate_rank"] = rank
            retry_reason["selected_under_budget"] = claim_id in selected_ids
    return selected_items, audit_rows, budget_decision


def extract_with_fallback(item: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str, Dict[str, Any]]:
    fast_started = time.perf_counter()
    fast_obj, fast_raw = llm_chat(SYSTEM_EXTRACT_FAST, build_fast_extract_prompt(item), retries=0)
    if isinstance(fast_obj, dict):
        fast_obj["_answer_text"] = item.get("answer", "")
        fast_obj["_question_text"] = item.get("question", "")
        fast_obj["_question_time"] = item.get("time", "")
    fast_elapsed = round(time.perf_counter() - fast_started, 3)
    fast_ok, fast_reason = extract_plan_quality(fast_obj)
    meta: Dict[str, Any] = {
        "extract_mode": "fast",
        "fast_elapsed": fast_elapsed,
        "fast_quality": fast_reason,
        "fallback_used": False,
    }
    if fast_ok:
        fast_normalized = normalize_extracted_plan(fast_obj)
        fast_triggers = semantic_audit_triggers(item, fast_normalized, {})
        if "attached_detail_pollution" not in fast_triggers:
            meta["fast_triggers"] = fast_triggers
            return fast_obj, fast_raw, meta
        if not ENABLE_FULL_EXTRACT_FALLBACK:
            meta["fast_triggers"] = fast_triggers
            meta["fallback_skipped"] = True
            meta["fallback_skip_reason"] = "attached_detail_pollution_fast_path"
            return fast_obj, fast_raw, meta
        fast_reason = "attached_detail_pollution_requires_full_extract"
        meta["fast_triggers"] = fast_triggers
    normal_started = time.perf_counter()
    normal_obj, normal_raw = llm_chat(SYSTEM_EXTRACT, build_extract_prompt(item))
    if isinstance(normal_obj, dict):
        normal_obj["_answer_text"] = item.get("answer", "")
        normal_obj["_question_text"] = item.get("question", "")
        normal_obj["_question_time"] = item.get("time", "")
    normal_elapsed = round(time.perf_counter() - normal_started, 3)
    meta.update(
        {
            "extract_mode": "normal_fallback",
            "fallback_used": True,
            "fallback_reason": fast_reason,
            "normal_elapsed": normal_elapsed,
        }
    )
    return normal_obj, normal_raw, meta


STRUCTURED_DETAIL_MODES = STRUCTURED_EVIDENCE_MODES | {EVIDENCE_MODE_EVENT}
HIGH_RISK_SUPPORTING_MODES = HIGH_RISK_SUPPORTING_EVIDENCE_MODES
HIGH_RISK_TYPES = {
    "direct_answer",
    "detail_numeric",
    "detail_date",
    "route_relation",
    "policy_intent",
    "military_action",
    "current_status",
    "prediction",
}


def has_structured_detail(text: str, source_intent: Dict[str, Any]) -> bool:
    mode = str(source_intent.get("evidence_mode") or "")
    risk_type = str(source_intent.get("risk_type") or "")
    target = str(source_intent.get("evidence_target") or "")
    if mode in STRUCTURED_DETAIL_MODES or risk_type in {"detail_numeric", "detail_date"}:
        return True
    if target in {"match_result", "market_calendar", "market_price", "position_distance", "prize_amount"}:
        return True
    return bool(re.search(r"\d|[一二三四五六七八九十百千万亿]+(万|亿|日|月|年|分|比|场|公里|千米|海里|克朗|美元|元)", text))


EXCLUSIVE_PREMISE_PATTERN = re.compile(
    r"(唯一海上通道|唯一通道|唯一|只能|必经|必须经过|完全绕开|根本不需要经过|不需要经过|无需经过|不经由|没有别的通道|only route|must pass|without crossing)",
    flags=re.I,
)
EXCLUSIVE_ROUTE_HINT_PATTERN = re.compile(r"(海峡|通道|航道|路线|领空|港口|管道|出口|进口|经过|绕开|经由|海上通道|陆上管道)")
INTERPRETIVE_EXPLANATION_PATTERN = re.compile(
    r"(代表|意味着|说明|表明|反映|体现|显示出|本质上|主要是|主要意味着|说明了|表明了|说明的是|意味着市场|reflects|means|implies|shows that)",
    flags=re.I,
)
DIRECT_OBSERVABLE_PATTERN = re.compile(
    r"(\d|休市|开盘|高开|低开|上涨|下跌|涨了|跌了|比分|战胜|赢了|输给|退赛|公布|发布|中间价|汇率|牌价|金额|奖金|日期|生效|停牌|通车|开售|only route|must pass|without crossing|唯一|只能|必经)",
    flags=re.I,
)
BACKGROUND_CONTEXT_PATTERN = re.compile(
    r"(市场情绪|风险偏好|地缘政治|宏观环境|整体来看|某种程度上|可以理解为|倾向于|大体上|一般来说|通常会)",
    flags=re.I,
)
MIXED_SENTENCE_SPLIT_PATTERN = re.compile(r"[，,；;：:]")


def split_answer_sentences_for_claims(text: str) -> List[str]:
    raw = str(text or "").replace("\\n", "\n").replace("\\t", "\t")
    if not raw:
        return []
    return [normalize_text(part) for part in re.split(r"[。！？!?；;\n]+", raw) if normalize_text(part)]


def claim_texts_overlap(a: str, b: str) -> bool:
    def overlap_key(text: str) -> str:
        cleaned = normalize_text(text)
        cleaned = re.sub(r"\[]\(@mark_underline=\d+\)", "", cleaned)
        cleaned = re.sub(r"[\*\[\]\(\)`_>#]", " ", cleaned)
        return normalize_text(cleaned)
    a_norm = overlap_key(a)
    b_norm = overlap_key(b)
    if not a_norm or not b_norm:
        return False
    return a_norm in b_norm or b_norm in a_norm


def strip_markdown_noise(text: str) -> str:
    cleaned = normalize_text(text)
    cleaned = re.sub(r"\[]\(@mark_underline=\d+\)", "", cleaned)
    cleaned = re.sub(r"[*`_>#\[\]]", " ", cleaned)
    cleaned = cleaned.replace("（动机）", " ")
    cleaned = cleaned.replace("(动机)", " ")
    return normalize_text(cleaned)


def exclusive_term_bucket(text: str) -> str:
    lowered = normalize_text(text).lower()
    if "唯一海上通道" in lowered:
        return "唯一海上通道"
    for term in [
        "唯一通道",
        "唯一",
        "只能",
        "必经",
        "必须经过",
        "完全绕开",
        "根本不需要经过",
        "不需要经过",
        "无需经过",
        "only route",
        "must pass",
        "without crossing",
    ]:
        if term.lower() in lowered:
            return term
    return ""


def canonical_exclusive_premise_sentence(sentence: str) -> str:
    text = strip_markdown_noise(sentence)
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"被描述为", "是", text)
    text = re.sub(r"\s+唯一", "唯一", text)
    text = re.sub(r"\s+必经", "必经", text)
    fragments = [
        normalize_text(part)
        for part in re.split(r"[；;。！？!?\n]|[:：]", text)
        if normalize_text(part)
    ]
    candidates = [fragment for fragment in fragments if EXCLUSIVE_PREMISE_PATTERN.search(fragment)]
    if not candidates:
        candidates = [text]
    best = candidates[0]
    best_score = -10**9
    for fragment in candidates:
        fragment_score = 0
        if re.search(r"(是|为|属于|构成|意味着|需要|经过|绕开)", fragment):
            fragment_score += 10
        if EXCLUSIVE_ROUTE_HINT_PATTERN.search(fragment):
            fragment_score += 8
        if exclusive_term_bucket(fragment):
            fragment_score += 6
        fragment_score -= max(0, len(fragment) - 42)
        if fragment_score > best_score:
            best = fragment
            best_score = fragment_score
    if len(best) > 72:
        match = re.search(
            r"([^，。；;:：]{0,36}(唯一海上通道|唯一通道|唯一|只能|必经|必须经过|完全绕开|根本不需要经过|不需要经过|无需经过|only route|must pass|without crossing)[^，。；;:：]{0,36})",
            best,
            flags=re.IGNORECASE,
        )
        if match:
            best = normalize_text(match.group(1))
    best = re.sub(r"^[,.;:，。：；\-]+\s*", "", best)
    best = normalize_text(best)
    return compact_claim_text(best, 120)


def exclusive_premise_signature(claim: Dict[str, Any]) -> str:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    claim_text = canonical_exclusive_premise_sentence(str(claim.get("claim") or ""))
    normalized_claim_text = normalize_text(claim_text).lower()
    evidence_mode = str(source_intent.get("evidence_mode") or "")
    centrality = str(claim.get("centrality") or "")
    evidence_target = str(source_intent.get("evidence_target") or "")
    term_bucket = exclusive_term_bucket(claim_text).lower()
    return "||".join([normalized_claim_text, evidence_mode, centrality, term_bucket, evidence_target]).strip("|")


def exclusive_premise_preference_score(claim: Dict[str, Any]) -> int:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    claim_text = str(claim.get("claim") or "")
    canonical_text = canonical_exclusive_premise_sentence(claim_text)
    score = 0
    if canonical_text and canonical_text == normalize_text(claim_text):
        score += 18
    if "（动机）" not in claim_text and "(动机)" not in claim_text:
        score += 6
    if not re.search(r"[\*\[\]`#]", claim_text):
        score += 5
    if re.search(r"(是|为|属于|构成)", canonical_text):
        score += 6
    if str(source_intent.get("evidence_mode") or "") == EVIDENCE_MODE_ROUTE:
        score += 4
    score -= max(0, len(normalize_text(claim_text)) - 60)
    return score


def merge_query_rows(query_rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    seen = set()
    for row in query_rows:
        if not isinstance(row, dict):
            continue
        query_text = normalize_text(str(row.get("q") or row.get("query") or ""))
        if not query_text:
            continue
        key = query_text.lower()
        if key in seen:
            continue
        seen.add(key)
        query_row: Dict[str, Any] = {
            "q": query_text,
            "goal": normalize_text(str(row.get("goal") or "general_verify")) or "general_verify",
        }
        origin = normalize_text(str(row.get("origin") or ""))
        if origin:
            query_row["origin"] = origin
        raw_preference = row.get("source_preference") if isinstance(row.get("source_preference"), list) else []
        source_preference = [normalize_text(str(item)) for item in raw_preference if normalize_text(str(item))][:3]
        if source_preference:
            query_row["source_preference"] = source_preference
        query_family_role = normalize_query_family_role(row.get("query_family_role"))
        if query_family_role != "mirror" or normalize_text(str(row.get("query_family_role") or "")) == "mirror":
            query_row["query_family_role"] = query_family_role
        for extra_key in ("operator", "variant", "gap_flag", "query_variant_origin"):
            extra_value = normalize_text(str(row.get(extra_key) or ""))
            if extra_value:
                query_row[extra_key] = extra_value
        merged.append(query_row)
    return merged[:2]


def merge_exclusive_premise_claim_group(claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    ranked = sorted(
        claims,
        key=lambda item: (
            exclusive_premise_preference_score(item),
            -len(normalize_text(str(item.get("claim") or ""))),
        ),
        reverse=True,
    )
    chosen = dict(ranked[0])
    chosen_text = canonical_exclusive_premise_sentence(str(chosen.get("claim") or ""))
    chosen["claim"] = chosen_text or str(chosen.get("claim") or "")
    all_questions: List[str] = []
    all_queries: List[Dict[str, str]] = []
    source_intent = chosen.get("source_intent") if isinstance(chosen.get("source_intent"), dict) else {}
    page_intent = source_intent.get("page_intent") if isinstance(source_intent.get("page_intent"), dict) else {}
    source_strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
    must_have: List[str] = []
    must_contain: List[str] = []
    risk_types: List[str] = []
    for claim in ranked:
        for question in claim.get("verification_questions") or []:
            question_text = normalize_text(str(question or ""))
            if question_text:
                all_questions.append(question_text)
        all_queries.extend(claim.get("queries") or [])
        claim_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        claim_strategy = claim_intent.get("source_strategy") if isinstance(claim_intent.get("source_strategy"), dict) else {}
        claim_page_intent = claim_intent.get("page_intent") if isinstance(claim_intent.get("page_intent"), dict) else {}
        must_have.extend([normalize_text(str(x)) for x in (claim_strategy.get("must_have") or []) if normalize_text(str(x))])
        must_contain.extend([normalize_text(str(x)) for x in (claim_page_intent.get("must_contain") or []) if normalize_text(str(x))])
        risk_type = normalize_text(str(claim_intent.get("risk_type") or ""))
        if risk_type:
            risk_types.append(risk_type)
    evidence_mode = str(source_intent.get("evidence_mode") or "")
    source_strategy["must_have"] = dedupe_keep_order(must_have or exclusive_premise_terms(chosen_text))
    page_intent["must_contain"] = dedupe_keep_order(must_contain or exclusive_premise_terms(chosen_text))
    source_intent["source_strategy"] = source_strategy
    source_intent["page_intent"] = page_intent
    source_intent["risk_type"] = "route_relation" if "route_relation" in risk_types or evidence_mode == EVIDENCE_MODE_ROUTE else (risk_types[0] if risk_types else source_intent.get("risk_type") or "general")
    chosen["source_intent"] = source_intent
    chosen["verification_questions"] = dedupe_keep_order(all_questions)[:3] or exclusive_premise_verification_questions(chosen_text, evidence_mode)
    chosen["queries"] = merge_query_rows(all_queries) or exclusive_premise_queries(chosen_text, evidence_mode)
    chosen["evidence_task_card"] = build_evidence_task_card(
        chosen_text,
        str(chosen.get("centrality") or "supporting"),
        {
            "evidence_mode": evidence_mode,
            "evidence_target": str(source_intent.get("evidence_target") or ""),
            "evidence_shape": str(source_intent.get("evidence_shape") or ""),
            "source_strategy": {"must_have": source_strategy.get("must_have") or []},
            "route_meta": normalize_route_meta(source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}),
            "risk_type": str(source_intent.get("risk_type") or "general"),
            "assertion_strength": str(source_intent.get("assertion_strength") or "high"),
        },
        chosen["verification_questions"],
        chosen["queries"],
    )
    return chosen


def dedupe_exclusive_premise_claims(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
    passthrough: List[Tuple[int, Dict[str, Any]]] = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        if str(source_intent.get("claim_shape") or "") != "exclusive_premise":
            passthrough.append((index, claim))
            continue
        signature = exclusive_premise_signature(claim)
        if not signature:
            passthrough.append((index, claim))
            continue
        grouped.setdefault(signature, []).append((index, claim))
    merged_rows: List[Tuple[int, Dict[str, Any]]] = passthrough[:]
    for rows in grouped.values():
        first_index = min(index for index, _claim in rows)
        merged_claim = merge_exclusive_premise_claim_group([claim for _, claim in rows])
        merged_rows.append((first_index, merged_claim))
    merged_rows.sort(key=lambda row: row[0])
    return [claim for _, claim in merged_rows]


def claim_has_exclusive_premise_text(claim: Dict[str, Any]) -> bool:
    if not isinstance(claim, dict):
        return False
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    if str(source_intent.get("claim_shape") or "") == "exclusive_premise":
        return True
    text = normalize_text(str(claim.get("claim") or ""))
    return bool(EXCLUSIVE_PREMISE_PATTERN.search(text))


def infer_exclusive_premise_mode(sentence: str) -> tuple[str, str, str]:
    text = normalize_text(sentence)
    if EXCLUSIVE_ROUTE_HINT_PATTERN.search(text):
        return EVIDENCE_MODE_ROUTE, "route_relation", "open_news_analysis"
    return EVIDENCE_MODE_POLICY, "general", "general_evidence_page"


def exclusive_premise_terms(sentence: str) -> List[str]:
    text = normalize_text(sentence)
    terms = [
        term for term in [
            "唯一海上通道",
            "唯一通道",
            "唯一",
            "只能",
            "必经",
            "必须经过",
            "完全绕开",
            "根本不需要经过",
            "不需要经过",
            "无需经过",
            "only route",
            "must pass",
            "without crossing",
        ]
        if term.lower() in text.lower()
    ]
    return dedupe_keep_order(terms)[:4]


def exclusive_premise_verification_questions(sentence: str, evidence_mode: str) -> List[str]:
    if evidence_mode == EVIDENCE_MODE_ROUTE:
        return [
            "该说法是否真的是唯一/必经路线？",
            "是否存在可绕开、替代或不经过该区域的路径？",
        ]
    return [
        "该排他性前提是否被可靠资料直接支持？",
        "是否存在与该前提相冲突的替代条件或反例？",
    ]


def exclusive_premise_queries(sentence: str, evidence_mode: str) -> List[Dict[str, str]]:
    claim_text = compact_claim_text(sentence, 90)
    queries = [{"q": claim_text, "goal": "general_verify"}]
    if evidence_mode == EVIDENCE_MODE_ROUTE:
        queries.append({"q": f"{claim_text} 替代 路径 是否 唯一", "goal": "find_route"})
    else:
        queries.append({"q": f"{claim_text} 是否 唯一 官方", "goal": "general_verify"})
    return queries[:2]


def exclusive_premise_centrality(extracted: Dict[str, Any], sentence: str, claims: List[Dict[str, Any]]) -> str:
    question_text = normalize_text(str(extracted.get("_question_text") or extracted.get("question") or ""))
    user_need = normalize_text(str(extracted.get("user_need") or ""))
    route_need = EXCLUSIVE_ROUTE_HINT_PATTERN.search(question_text) or EXCLUSIVE_ROUTE_HINT_PATTERN.search(user_need)
    if route_need and EXCLUSIVE_ROUTE_HINT_PATTERN.search(sentence):
        has_core_route = any(
            isinstance(claim, dict)
            and str(claim.get("centrality") or "") == "core"
            and str((claim.get("source_intent") or {}).get("evidence_mode") or "") == EVIDENCE_MODE_ROUTE
            for claim in claims
        )
        if not has_core_route:
            return "core"
    return "supporting"


def augment_exclusive_premise_claims(extracted: Dict[str, Any], claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    answer_text = normalize_text(str(extracted.get("_answer_text") or ""))
    if not answer_text:
        return claims
    existing_texts = [canonical_exclusive_premise_sentence(str(item.get("claim") or "")) or normalize_text(str(item.get("claim") or "")) for item in claims if isinstance(item, dict)]
    additions: List[Dict[str, Any]] = []
    next_index = len(claims) + 1
    for sentence in split_answer_sentences_for_claims(answer_text):
        if not EXCLUSIVE_PREMISE_PATTERN.search(sentence):
            continue
        sentence = canonical_exclusive_premise_sentence(sentence)
        if len(sentence) < 10:
            continue
        if any(claim_texts_overlap(sentence, existing) for existing in existing_texts):
            continue
        evidence_mode, evidence_target, evidence_shape = infer_exclusive_premise_mode(sentence)
        centrality = exclusive_premise_centrality(extracted, sentence, claims + additions)
        premise_terms = exclusive_premise_terms(sentence)
        verification_questions = exclusive_premise_verification_questions(sentence, evidence_mode)
        queries = exclusive_premise_queries(sentence, evidence_mode)
        source_intent = {
            "preferred_source_types": ["official", "news"],
            "preferred_domains": [],
            "evidence_mode": evidence_mode,
            "evidence_target": evidence_target,
            "evidence_shape": evidence_shape,
            "time_sensitivity": "medium",
            "assertion_strength": "high",
            "risk_type": "route_relation" if evidence_mode == EVIDENCE_MODE_ROUTE else "general",
            "claim_shape": "exclusive_premise",
            "stated_as_fact": True,
            "source_strategy": {
                "source_types": ["official", "news"],
                "search_channels": ["news_search", "web_search"],
                "languages": ["zh", "en"],
                "must_have": premise_terms,
                "avoid_sources": ["forum", "qa", "generic_encyclopedia"],
                "why": "补充回答中带有排他性 premise 的 supporting claim，避免“唯一/只能/完全绕开”只留在解释层。",
            },
            "page_intent": {
                "needed_page_type": "route_analysis_page" if evidence_mode == EVIDENCE_MODE_ROUTE else "",
                "must_contain": premise_terms,
                "avoid_page_type": [],
                "why": "优先保留能直接说明是否存在替代通道、绕开路径或排他条件的页面。",
            },
            "route_meta": normalize_route_meta({}),
        }
        additions.append(
            {
                "claim_id": f"c{next_index}",
                "claim": sentence,
                "centrality": centrality,
                "checkability": "checkable",
                "source_intent": source_intent,
                "verification_questions": verification_questions,
                "queries": queries,
                "evidence_task_card": build_evidence_task_card(
                    sentence,
                    centrality,
                    {
                        "evidence_mode": evidence_mode,
                        "evidence_target": evidence_target,
                        "evidence_shape": evidence_shape,
                        "source_strategy": {"must_have": premise_terms},
                        "route_meta": normalize_route_meta({}),
                        "risk_type": "route_relation" if evidence_mode == EVIDENCE_MODE_ROUTE else "general",
                        "assertion_strength": "high",
                    },
                    verification_questions,
                    queries,
                ),
            }
        )
        existing_texts.append(sentence)
        next_index += 1
        if len(additions) >= 2:
            break
    return claims + additions


def augment_market_calendar_detail_claims(extracted: Dict[str, Any], claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if normalize_need_type(extracted.get("need_type")) != "market_movement":
        return claims
    answer_text = normalize_text(str(extracted.get("_answer_text") or ""))
    if not answer_text:
        return claims
    existing_texts = [normalize_text(str(item.get("claim") or "")) for item in claims if isinstance(item, dict)]
    interpretive_core_exists = any(
        isinstance(item, dict)
        and str(item.get("centrality") or "") == "core"
        and str(item.get("claim_budget_bucket") or claim_budget_bucket(
            str(item.get("claim") or ""),
            item.get("source_intent") if isinstance(item.get("source_intent"), dict) else {},
            str(item.get("checkability") or "checkable"),
        )) == "interpretive_explanation"
        for item in claims
    )
    if not interpretive_core_exists:
        return claims
    if any(any(marker in text for marker in ["休市", "开盘", "高开", "交易日", "假期"]) for text in existing_texts):
        return claims
    additions: List[Dict[str, Any]] = []
    next_index = len(claims) + 1
    for sentence in split_answer_sentences_for_claims(answer_text):
        if not re.search(r"(休市|开盘|高开|交易日|假期|清明)", sentence):
            continue
        if not re.search(r"(A股|港股|沪深|上证|恒生)", sentence):
            continue
        if any(claim_texts_overlap(sentence, text) for text in existing_texts):
            continue
        terms = compact_term_list(re.findall(r"(A股|港股|沪深|恒生|清明|休市|开盘|高开)", sentence), 6, 20)
        source_intent = {
            "preferred_source_types": ["official", "news"],
            "preferred_domains": [],
            "evidence_mode": "schedule_fact",
            "evidence_target": "market_calendar",
            "evidence_shape": "authoritative_notice",
            "time_sensitivity": "high",
            "assertion_strength": "high",
            "risk_type": "detail_date",
            "stated_as_fact": True,
            "source_strategy": {
                "source_types": ["official", "news"],
                "search_channels": ["news_search", "web_search"],
                "languages": ["zh"],
                "must_have": terms,
                "avoid_sources": ["forum", "qa"],
                "why": "补一条当日市场交易安排与开盘状态的 supporting detail，避免它和涨跌主结论粘在一起。",
            },
            "page_intent": {
                "needed_page_type": "calendar_page",
                "must_contain": terms,
                "avoid_page_type": ["landing_page", "search_result_page"],
                "why": "优先找交易日历、公告或当日开盘快讯。",
            },
            "route_meta": normalize_route_meta({}),
        }
        if any(
            isinstance(existing, dict)
            and str(existing.get("claim_budget_bucket") or "") == "structured_detail"
            and str((existing.get("source_intent") or {}).get("evidence_mode") or "") == "schedule_fact"
            and claim_texts_overlap(sentence, str(existing.get("claim") or ""))
            for existing in claims
        ):
            continue
        additions.append(
            {
                "claim_id": f"mc{next_index}",
                "claim": sentence,
                "centrality": "supporting",
                "checkability": "checkable",
                "source_intent": source_intent,
                "verification_questions": [],
                "queries": [],
                "evidence_task_card": build_evidence_task_card(sentence, "supporting", source_intent, [], []),
            }
        )
        break
    return claims + additions


def augment_sports_structured_detail_claims(extracted: Dict[str, Any], claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if normalize_need_type(extracted.get("need_type")) != "sports_result":
        return claims
    answer_text = normalize_text(str(extracted.get("_answer_text") or ""))
    if not answer_text:
        return claims
    existing_texts = [normalize_text(str(item.get("claim") or "")) for item in claims if isinstance(item, dict)]
    existing_structured_supporting = 0
    for claim in claims:
        if not isinstance(claim, dict) or str(claim.get("centrality") or "") != "supporting":
            continue
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        if has_structured_detail(str(claim.get("claim") or ""), source_intent):
            existing_structured_supporting += 1
    additions: List[Dict[str, Any]] = []
    next_index = len(claims) + 1
    for sentence in split_answer_sentences_for_claims(answer_text):
        clean_sentence = strip_markdown_noise(sentence)
        if not clean_sentence or len(clean_sentence) < 8:
            continue
        if any(claim_texts_overlap(clean_sentence, text) for text in existing_texts):
            continue
        if not re.search(r"(总战绩|交锋|交手|赛季交锋|常规赛交锋)", clean_sentence):
            continue
        if not re.search(r"(\d+\s*胜\s*\d+\s*负)", clean_sentence):
            continue
        if re.search(r"(助攻|篮板|抢断|盖帽|首节|末节|命中率|三分)", clean_sentence):
            continue
        source_intent = infer_augmented_clause_intent(clean_sentence, "sports_result")
        source_intent = dict(source_intent)
        source_intent["evidence_mode"] = "numeric_fact"
        source_intent["evidence_target"] = infer_evidence_target(clean_sentence, "numeric_fact", "sports_result")
        source_intent["risk_type"] = "detail_numeric"
        source_intent["assertion_strength"] = "high"
        source_strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
        source_strategy = dict(source_strategy)
        source_strategy["why"] = "补充体育结果回答里容易影响真假的结构化细节，如赛后战绩、交锋总战绩、连败连胜等。"
        source_intent["source_strategy"] = source_strategy
        page_intent = source_intent.get("page_intent") if isinstance(source_intent.get("page_intent"), dict) else {}
        page_intent = dict(page_intent)
        page_intent["why"] = "优先保留能直接给出赛后战绩、交锋总战绩或连败连胜状态的结果页或赛后报道。"
        source_intent["page_intent"] = page_intent
        if not has_structured_detail(clean_sentence, source_intent):
            continue
        if claim_budget_bucket(clean_sentence, source_intent, "checkable") != "structured_detail":
            continue
        additions.append(
            {
                "claim_id": f"sd{next_index}",
                "claim": clean_sentence,
                "centrality": "supporting",
                "checkability": "checkable",
                "source_intent": source_intent,
                "verification_questions": [],
                "queries": [],
                "evidence_task_card": build_evidence_task_card(clean_sentence, "supporting", source_intent, [], []),
            }
        )
        existing_texts.append(clean_sentence)
        next_index += 1
        if existing_structured_supporting + len(additions) >= 4 or len(additions) >= 2:
            break
    return claims + additions


ATOMIC_RISK_PRIORITY = {
    "event_result_status": 92,
    "exclusive_or_only_path": 90,
    "market_calendar_status": 88,
    "phase_boundary_time": 86,
    "current_position_distance": 84,
    "reality_vs_fiction_status": 82,
    "numeric_quote_or_metric": 76,
}


def atomic_phase_time_role(text: str) -> str:
    clean = normalize_text(str(text or "")).lower()
    if not clean:
        return ""
    result_terms = r"(结果|数据|报告|最终|完整|公布|发布|出炉|release|released|publish|published)"
    end_terms = r"(结束|完成|完结|截止|complete|completed|completion|finish|finished)"
    phase_terms = r"(第一阶段|第二阶段|第三阶段|阶段|phase|stage)"
    start_terms = r"(开始|开启|启动|开展|进行|start|starts|started|begin|begins|commence|launched)"
    if re.search(result_terms, clean):
        return "result_release"
    if re.search(end_terms, clean):
        return "whole_event_end" if not re.search(phase_terms, clean) else "phase_end"
    if re.search(phase_terms, clean) and re.search(start_terms, clean):
        return "phase_start"
    if re.search(start_terms, clean):
        return "event_start"
    return ""


def atomic_phase_time_scope_from_text(text: str, role: str = "") -> str:
    clean = normalize_text(str(text or ""))
    if not clean:
        return ""
    date_matches = list(
        re.finditer(
            r"20\d{2}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?(?:\s*(?:之后|以前|之前|后|前))?",
            clean,
        )
    )
    if not date_matches:
        return ""
    if role in {"result_release", "whole_event_end", "phase_end"}:
        return normalize_text(date_matches[-1].group(0))
    return normalize_text(date_matches[0].group(0))


def atomic_claim_search_priority(text: str, risk_type: str) -> int:
    priority = ATOMIC_RISK_PRIORITY.get(risk_type, 50)
    clean = normalize_text(text)
    if risk_type == "market_calendar_status":
        if re.search(r"(休市|假期|节假日|不开市|closed|holiday)", clean, flags=re.I):
            priority += 12
        if re.search(r"(A股|沪深|上证|深证|交易所)", clean, flags=re.I):
            priority += 4
    elif risk_type == "exclusive_or_only_path":
        if re.search(r"(唯一|只能|必经|sole|only)", clean, flags=re.I):
            priority += 8
        if re.search(r"(替代|绕开|管道|港口|bypass|alternative)", clean, flags=re.I):
            priority += 4
    elif risk_type == "event_result_status":
        if re.search(r"(vs|VS|对阵|迎战)", clean) and EVENT_SCORE_PATTERN.search(clean):
            priority += 8
        elif EVENT_SCORE_PATTERN.search(clean):
            priority += 4
    elif risk_type == "phase_boundary_time":
        role = atomic_phase_time_role(clean)
        if role == "result_release":
            priority += 18
        elif role in {"whole_event_end", "phase_end"}:
            priority += 26
        elif role == "phase_start":
            priority += 8
        if re.search(r"(第一阶段|第二阶段|第三阶段)", clean):
            priority += 3
        if re.search(r"(第一阶段)", clean) and role == "phase_start":
            priority -= 6
        if re.search(r"(第二阶段|第三阶段)", clean) and role == "phase_start":
            priority += 2
    elif risk_type == "current_position_distance":
        if re.search(r"(目前|当前|截至|as of|current)", clean, flags=re.I):
            priority += 4
    return priority


def has_event_result_signal(text: str) -> bool:
    clean = normalize_text(text)
    if not clean:
        return False
    if event_has_result_signal(clean):
        return True
    return bool(EVENT_SCORE_PATTERN.search(clean) and re.search(r"(vs|VS|对阵|迎战)", clean))


def atomic_context_date_terms(extracted: Dict[str, Any]) -> List[str]:
    raw_time = normalize_text(str(extracted.get("_question_time") or ""))
    match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", raw_time)
    if not match:
        return []
    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    return [
        f"{year}年{month}月{day}日",
        f"{year}-{month:02d}-{day:02d}",
        f"{month}月{day}日",
    ]


def _atomic_converter_extract_event_pair(text: str) -> Tuple[str, str, str]:
    clean = normalize_text(text)
    if not clean:
        return "", "", ""
    score_detail = r"[0-9]{1,3}\s*[-:：]\s*[0-9]{1,3}(?:\s*[\(（][^)）]{1,80}[\)）])?"
    patterns = [
        rf"([^\s|]{{2,30}})(?:\s+[^\s|]{{1,12}})?\s*(?:vs|VS|对阵|迎战)\s*([^\s|]{{2,30}})\s*({score_detail})",
        rf"([^\s|]{{2,30}})\s*(?:vs|VS|对阵|迎战)\s*([^\s|]{{2,30}})\s*({score_detail})",
        rf"([^\s|]{{2,30}})\s*({score_detail})\s*([^\s|]{{2,30}})",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean)
        if match:
            groups = [normalize_text(g) for g in match.groups()]
            if len(groups) == 3:
                a, b, c = groups
                score = c if re.search(r"\d", c) else b
                if re.search(r"\d", c):
                    return a, b, c
                return a, c, b
    return "", "", ""


def atomic_normalize_relative_time_scope(time_scope: str, context_dates: Optional[List[str]] = None) -> str:
    clean = normalize_text(time_scope)
    context_dates = context_dates or []
    if not clean or not context_dates:
        return clean
    if clean in {"今天", "今日", "当日", "截至今天"} or re.search(r"(今天|今日|当日|截至今天)", clean):
        return context_dates[0]
    return clean


def atomic_claim_slot_contract(
    text: str,
    risk_type: str,
    source_claim: Optional[Dict[str, Any]] = None,
    context_dates: Optional[List[str]] = None,
) -> Dict[str, str]:
    source_claim = source_claim if isinstance(source_claim, dict) else {}
    source_intent = source_claim.get("source_intent") if isinstance(source_claim.get("source_intent"), dict) else {}
    program = source_claim.get("evidence_need_program") if isinstance(source_claim.get("evidence_need_program"), dict) else {}
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    subject = first_nonempty_text(
        decision_slots.get("subject"),
        (source_intent.get("core_binding") or {}).get("subject_entity") if isinstance(source_intent.get("core_binding"), dict) else "",
        width=50,
    )
    time_scope = first_nonempty_text(decision_slots.get("time_scope"), " ".join(claim_time_markers(text)[:2]), width=50)
    object_value = first_nonempty_text(decision_slots.get("object"), width=50)
    metric = first_nonempty_text(decision_slots.get("metric_or_relation"), width=50)
    status = first_nonempty_text(decision_slots.get("status_or_result"), width=50)
    if risk_type == "market_calendar_status":
        text_subject = first_nonempty_text(*(re.findall(r"(A股|港股|沪深|上证|深证|创业板|恒生|美股|纳指|道指|交易所)", text)[:2]), width=30)
        if text_subject:
            subject = text_subject
        text_time = first_nonempty_text(*claim_time_markers(text)[:2], width=50)
        if text_time:
            time_scope = text_time
        time_scope = atomic_normalize_relative_time_scope(time_scope, context_dates)
        metric = metric or "交易日历/开休市状态"
        text_status = first_nonempty_text(*(re.findall(r"(休市|开市|开盘|交易日|假期|节假日)", text)[:3]), width=40)
        if text_status:
            status = text_status
    elif risk_type == "exclusive_or_only_path":
        metric = metric or first_nonempty_text(exclusive_term_bucket(text), "排他路径/唯一性", width=40)
        object_value = object_value or first_nonempty_text(*(re.findall(r"(海峡|通道|航道|管道|港口|路线|领空|出口|进口|走廊|路径|海域)", text)[:4]), width=50)
        status = status or "唯一/只能/必经"
    elif risk_type == "event_result_status":
        metric = metric or "赛果/比分/退赛状态"
        player_a, player_b, score = _atomic_converter_extract_event_pair(text)
        if player_a:
            subject = first_nonempty_text(player_a, subject, width=50)
        if player_b:
            object_value = first_nonempty_text(player_b, object_value, width=50)
        if score:
            status = first_nonempty_text(score, status, width=50)
            metric = first_nonempty_text(score, metric, width=50)
        extra_status = first_nonempty_text(
            *(re.findall(r"(战胜|击败|退赛|弃权|不战而胜|获胜|比分|胜)", text)[:4]),
            width=50,
        )
        if extra_status:
            status = first_nonempty_text(extra_status, status, width=50)
    elif risk_type == "current_position_distance":
        metric = metric or "当前位置/距离"
        status = first_nonempty_text(*(re.findall(r"(\d+(?:\.\d+)?\s*(?:公里|千米|海里|km|nm|英里|mile))", text, flags=re.I)[:3]), width=50)
    elif risk_type == "phase_boundary_time":
        metric = metric or "阶段开始/结束/结果公布"
        role = atomic_phase_time_role(text)
        text_time = atomic_phase_time_scope_from_text(text, role)
        if text_time:
            time_scope = atomic_normalize_relative_time_scope(text_time, context_dates)
        if role in {"whole_event_end", "phase_end"}:
            status = first_nonempty_text(*(re.findall(r"(结束|完成|完结|截止)", text)[:4]), status, width=50)
        elif role == "result_release":
            status = first_nonempty_text(*(re.findall(r"(结果|数据|报告|公布|发布|出炉)", text)[:5]), status, width=50)
        elif role in {"phase_start", "event_start"}:
            status = first_nonempty_text(*(re.findall(r"(开始|开启|启动|开展|进行|第一阶段|第二阶段|第三阶段)", text)[:6]), status, width=50)
        else:
            status = first_nonempty_text(*(re.findall(r"(开始|开启|启动|结束|完成|公布|发布|结果|第一阶段|第二阶段|第三阶段)", text)[:6]), status, width=50)
        object_value = first_nonempty_text(*(re.findall(r"(阶段|事项|结果|数据|报告|流程|日程)", text)[:6]), object_value, width=50)
    elif risk_type == "reality_vs_fiction_status":
        metric = metric or "现实发生状态"
        status = first_nonempty_text(*(re.findall(r"(虚构|网传|AI生成|未发生|并未|现实|真实|战争|断网|袭击)", text)[:4]), width=50)
    elif risk_type == "numeric_quote_or_metric":
        metric = metric or first_nonempty_text(*(re.findall(r"(汇率|中间价|买入价|卖出价|牌价|战绩|距离|人数|金额|奖金|基点)", text)[:3]), width=50)
        status = first_nonempty_text(*(re.findall(r"\d+(?:\.\d+)?\s*(?:胜|负|公里|千米|美元|元|基点|%|人民币|CNY|USD)?", text, flags=re.I)[:4]), width=50)
    time_scope = atomic_normalize_relative_time_scope(time_scope, context_dates)
    role = atomic_phase_time_role(text) if risk_type == "phase_boundary_time" else ""
    return {
        "subject": subject,
        "time_scope": time_scope,
        "object": object_value,
        "metric_or_relation": metric,
        "status_or_result": status,
        "time_role": role,
        "comparison_baseline": "",
        "source_scope": "",
    }


def _atomic_phase_subject_quality(subject: str) -> int:
    clean = normalize_text(str(subject or ""))
    if not clean:
        return 0
    score = min(len(clean), 30)
    if re.search(r"(结果|数据|时间|日期|阶段|开始|结束|公布|发布|最终|完整)", clean):
        score -= 8
    if re.search(r"[\u4e00-\u9fff]{2,}", clean):
        score += 4
    if re.search(r"[A-Za-z]{2,}", clean):
        score += 2
    return score


def atomic_phase_context_subject(extracted: Dict[str, Any], claims: List[Dict[str, Any]], clause: str, current_subject: str = "") -> str:
    candidates: List[str] = []
    for claim in claims or []:
        if not isinstance(claim, dict):
            continue
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        program = claim.get("evidence_need_program") if isinstance(claim.get("evidence_need_program"), dict) else {}
        decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
        core_binding = source_intent.get("core_binding") if isinstance(source_intent.get("core_binding"), dict) else {}
        candidates.extend(
            normalize_text(str(value or ""))
            for value in [
                decision_slots.get("subject"),
                core_binding.get("subject_entity"),
            ]
            if normalize_text(str(value or ""))
        )
    user_need = normalize_text(str(extracted.get("user_need") or ""))
    candidates.extend(re.findall(r"[\u4e00-\u9fffA-Za-z0-9·\-]{2,24}", user_need)[:4])
    clause_text = normalize_text(clause)
    current_score = _atomic_phase_subject_quality(current_subject)
    best = normalize_text(current_subject)
    best_score = current_score
    generic_terms = {"结果", "数据", "时间", "日期", "阶段", "开始", "结束", "公布", "发布", "最终", "完整", "预计"}
    for candidate in dedupe_keep_order([c for c in candidates if c]):
        if candidate == best:
            continue
        if candidate in generic_terms:
            continue
        score = _atomic_phase_subject_quality(candidate)
        if candidate in clause_text or any(unit in clause_text for unit in re.findall(r"[\u4e00-\u9fff]{2,}", candidate)[:2]):
            score += 5
        if any(unit in user_need for unit in re.findall(r"[\u4e00-\u9fff]{2,}", candidate)[:2]):
            score += 3
        if score > best_score + 3:
            best = candidate
            best_score = score
    return best


def atomic_expected_evidence_shape(risk_type: str) -> str:
    return {
        "market_calendar_status": "exchange_calendar_or_trading_notice",
        "exclusive_or_only_path": "route_or_logistics_explainer_with_alternative_path",
        "event_result_status": "official_or_news_event_result_detail",
        "current_position_distance": "time_bound_position_or_distance_report",
        "phase_boundary_time": "official_schedule_or_phase_notice",
        "reality_vs_fiction_status": "current_status_or_debunking_evidence",
        "numeric_quote_or_metric": "structured_table_or_authoritative_numeric_point",
    }.get(risk_type, "direct_evidence_page")


def atomic_refutation_terms(text: str, risk_type: str, slots: Dict[str, str]) -> List[str]:
    base_terms = compact_term_list(
        [
            slots.get("subject", ""),
            slots.get("time_scope", ""),
            slots.get("object", ""),
            slots.get("metric_or_relation", ""),
            slots.get("status_or_result", ""),
        ],
        5,
        36,
    )
    if risk_type == "market_calendar_status":
        extras = ["交易日历", "休市", "开市", "节假日", "公告"]
    elif risk_type == "exclusive_or_only_path":
        extras = ["替代通道", "管道", "港口", "绕开", "bypass", "alternative route"]
    elif risk_type == "event_result_status":
        player_a, player_b, score = _atomic_converter_extract_event_pair(text)
        extras = compact_term_list(
            [player_a, player_b, score],
            10,
            36,
        )
    elif risk_type == "current_position_distance":
        extras = ["current position", "distance", "as of", "location", "公里"]
    elif risk_type == "phase_boundary_time":
        role = str(slots.get("time_role") or atomic_phase_time_role(text) or "")
        extras = [
            role,
            "第一阶段",
            "第二阶段",
            "第三阶段",
            "开始",
            "启动",
            "结束",
            "公布",
            "result release",
        ]
    elif risk_type == "reality_vs_fiction_status":
        extras = ["现实", "虚构", "网传", "未发生", "debunk", "fact check"]
    elif risk_type == "numeric_quote_or_metric":
        extras = ["官方", "历史数据", "表格", "中间价", "牌价"]
    else:
        extras = ["官方", "实际", "结果"]
    return dedupe_keep_order([term for term in base_terms + extras if term])[:10]


def infer_atomic_risk_type(text: str, need_type: str = "") -> str:
    clean = normalize_text(text)
    if not clean:
        return ""
    if re.search(r"(休市|开市|开盘|交易日|假期|节假日|清明|春节|圣诞|calendar)", clean, flags=re.I) and re.search(r"(A股|港股|沪深|上证|深证|恒生|美股|纳指|道指|交易所)", clean, flags=re.I):
        return "market_calendar_status"
    if EXCLUSIVE_PREMISE_PATTERN.search(clean) and EXCLUSIVE_ROUTE_HINT_PATTERN.search(clean):
        return "exclusive_or_only_path"
    if re.search(r"(当前位置|目前位于|截至|距离|离|海岸|航母|舰|号|carrier|current position|distance)", clean, flags=re.I) and re.search(r"(\d+(?:\.\d+)?\s*(公里|千米|海里|km|nm|英里|mile))", clean, flags=re.I):
        return "current_position_distance"
    if has_event_result_signal(clean):
        return "event_result_status"
    if (
        re.search(r"(第一阶段|第二阶段|第三阶段|阶段|日程|时间表|开始|开启|启动|结束|完成|公布|发布|结果|出炉)", clean)
        and re.search(r"(20\d{2}|明年|今年|\d{1,2}\s*月|\d{1,2}\s*日)", clean)
    ):
        return "phase_boundary_time"
    if re.search(r"(虚构|网传|AI生成|剧本|现实|真实|未发生|并未|不存在|战争|断网|袭击|全面战争)", clean, flags=re.I):
        return "reality_vs_fiction_status"
    if re.search(r"(汇率|中间价|买入价|卖出价|牌价|战绩|比分|距离|人数|金额|奖金|基点|美元|人民币|公里|千米|胜|负)", clean, flags=re.I) and re.search(r"\d", clean):
        return "numeric_quote_or_metric"
    return ""


def split_atomic_clause_candidates(sentence: str) -> List[str]:
    clean = strip_markdown_noise(sentence)
    if not clean:
        return []
    if "|" in str(sentence or "") and str(sentence or "").count("|") >= 2:
        return []
    parts = [clean]
    if len(clean) > 60:
        parts.extend(split_mixed_sentence_clauses(clean))
    out: List[str] = []
    for part in parts:
        text = normalize_text(part)
        if not text or len(text) < 5:
            continue
        if text not in out:
            out.append(text)
    return out[:6]


def event_result_table_clause_candidates(answer_text: str) -> List[str]:
    clauses: List[str] = []
    normalized_answer = str(answer_text or "").replace("\\n", "\n").replace("\\t", "\t")
    for raw_line in normalized_answer.splitlines():
        raw_line = re.sub(r"\[]\(@mark_underline=\d+\)", "", raw_line)
        if "|" not in raw_line:
            continue
        if re.search(r"^\s*\|?\s*:?-{2,}", raw_line):
            continue
        cells = [
            strip_markdown_noise(cell)
            for cell in raw_line.split("|")
            if strip_markdown_noise(cell)
        ]
        if len(cells) < 4:
            continue
        if any(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        header_terms = {"选手", "球员", "球队", "项目", "对阵", "比分", "赛果", "状态", "数据表现"}
        if len(set(cells) & header_terms) >= 2:
            continue
        joined = normalize_text(" ".join(cells))
        if not (re.search(r"(vs|VS|对阵|迎战)", joined) or EVENT_SCORE_PATTERN.search(joined)):
            continue
        score_match = EVENT_SCORE_PATTERN.search(joined)
        status_signal = event_has_result_signal(joined)
        if not score_match and not status_signal:
            continue
        score = normalize_text(score_match.group(0)) if score_match else ""
        subject = cells[0]
        event_or_role = cells[1] if len(cells) > 1 else ""
        opponent = cells[2] if len(cells) > 2 else ""
        opponent = re.sub(r"^(vs|VS|对阵|迎战)\s*", "", opponent).strip()
        score_cell = cells[3] if len(cells) > 3 else ""
        status = cells[4] if len(cells) > 4 else ""
        score_value = score_cell if score and score_cell else score or score_cell
        clause = compact_claim_text(
            normalize_text(f"{subject} {event_or_role} vs {opponent} {score_value} {status}"),
            180,
        )
        if clause and clause not in clauses:
            clauses.append(clause)
        if len(clauses) >= 8:
            break
    return clauses


def find_parent_claim_for_atomic(text: str, claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    best: Dict[str, Any] = {}
    best_score = -1
    def match_units(value: str) -> set:
        normalized = normalize_text(value)
        units = set(re.findall(r"[A-Za-z0-9]{2,}|\d+(?:\.\d+)?", normalized))
        for span in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
            units.update(span[idx: idx + 2] for idx in range(max(0, len(span) - 1)))
        return {unit for unit in units if unit}

    text_tokens = match_units(text)
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_text = normalize_text(str(claim.get("claim") or ""))
        if not claim_text:
            continue
        if claim_texts_overlap(text, claim_text):
            return claim
        claim_tokens = match_units(claim_text)
        score = len(text_tokens & claim_tokens)
        if score > best_score:
            best = claim
            best_score = score
    return best if best_score > 0 else {}


def build_atomic_claims_for_extracted(extracted: Dict[str, Any], claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    answer_text = normalize_text(str(extracted.get("_answer_text") or ""))
    need_type = normalize_need_type(extracted.get("need_type"))
    context_dates = atomic_context_date_terms(extracted)
    atomic_rows: List[Dict[str, Any]] = []
    seen = set()
    seed_sentences = event_result_table_clause_candidates(str(extracted.get("_answer_text") or "")) + split_answer_sentences_for_claims(answer_text)
    for sentence in seed_sentences:
        for clause in split_atomic_clause_candidates(sentence):
            risk_type = infer_atomic_risk_type(clause, need_type)
            if not risk_type:
                continue
            canonical = normalize_text(re.sub(r"\s+", "", clause))
            key = (risk_type, canonical[:120])
            if key in seen:
                continue
            seen.add(key)
            parent = find_parent_claim_for_atomic(clause, claims)
            parent_id = str(parent.get("claim_id") or parent.get("id") or "")
            parent_centrality = str(parent.get("centrality") or "supporting")
            centrality_hint = (
                "core"
                if parent_centrality == "core"
                and risk_type in {
                    "event_result_status",
                    "current_position_distance",
                    "phase_boundary_time",
                    "reality_vs_fiction_status",
                }
                else "supporting"
            )
            slots = atomic_claim_slot_contract(clause, risk_type, parent, context_dates)
            if risk_type == "phase_boundary_time":
                subject = normalize_text(str(slots.get("subject") or ""))
                if not subject or _atomic_phase_subject_quality(subject) < 8:
                    slots = dict(slots)
                    slots["subject"] = atomic_phase_context_subject(extracted, claims, clause, subject)
            refutation_terms = atomic_refutation_terms(clause, risk_type, slots)
            query = compact_claim_text(" ".join(refutation_terms), 120)
            atomic_rows.append(
                {
                    "atomic_claim_id": f"ac{len(atomic_rows) + 1}",
                    "parent_claim_id": parent_id,
                    "text": compact_claim_text(clause, 180),
                    "risk_type": risk_type,
                    "centrality_hint": centrality_hint,
                    "expected_evidence_shape": atomic_expected_evidence_shape(risk_type),
                    "slot_contract": slots,
                    "search_priority": atomic_claim_search_priority(clause, risk_type),
                    "refutation_target": {
                        "state": "planned_only",
                        "query": query,
                        "target_terms": refutation_terms,
                        "source_preference": ["official", "news", "html"],
                    },
                    "do_not_decide_without_gate": True,
                }
            )
            if len(atomic_rows) >= 12:
                break
        if len(atomic_rows) >= 12:
            break
    high_risk = sorted(atomic_rows, key=lambda row: int(row.get("search_priority") or 0), reverse=True)[:6]
    route_debug = [
        {
            "atomic_claim_id": row.get("atomic_claim_id"),
            "parent_claim_id": row.get("parent_claim_id"),
            "risk_type": row.get("risk_type"),
            "text": compact_claim_text(str(row.get("text") or ""), 120),
            "route_state": "extracted_only_no_retrieval",
            "search_priority": row.get("search_priority"),
            "refutation_query": (row.get("refutation_target") or {}).get("query") if isinstance(row.get("refutation_target"), dict) else "",
        }
        for row in high_risk
    ]
    return {
        "atomic_claims": atomic_rows,
        "high_risk_atomic_claims": high_risk,
        "atomic_claim_route_debug": route_debug,
    }


def dedupe_structured_detail_claims(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def canonical_structured_detail_text(text: str) -> str:
        cleaned = strip_markdown_noise(text)
        cleaned = re.sub(r"citation:\d+", "", cleaned, flags=re.I)
        cleaned = re.sub(r"[（(].{0,80}?[)）]", "", cleaned)
        cleaned = normalize_text(cleaned)
        cleaned = re.sub(r"\s+", "", cleaned)
        return cleaned

    def cleanliness_score(claim: Dict[str, Any]) -> Tuple[int, int, int]:
        text = normalize_text(str(claim.get("claim") or ""))
        score = 0
        if text and not text.startswith("-"):
            score += 1
        if "citation:" not in text.lower():
            score += 1
        if "\n" not in str(claim.get("claim") or ""):
            score += 1
        return score, -len(text), 1 if str(claim.get("centrality") or "") == "supporting" else 0

    def head_to_head_signature(text: str) -> str:
        normalized = normalize_text(text)
        if not re.search(r"(交锋|总战绩|交手|常规赛交锋)", normalized):
            return ""
        match = re.search(r"(\d+\s*胜\s*\d+\s*负)", normalized)
        if not match:
            return ""
        return normalize_text(match.group(1)).replace(" ", "")

    kept: List[Dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        text = normalize_text(str(claim.get("claim") or ""))
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        if not has_structured_detail(text, source_intent):
            kept.append(claim)
            continue
        canonical_text = canonical_structured_detail_text(str(claim.get("claim") or ""))
        replaced = False
        for idx, existing in enumerate(kept):
            if not isinstance(existing, dict):
                continue
            existing_text = normalize_text(str(existing.get("claim") or ""))
            existing_intent = existing.get("source_intent") if isinstance(existing.get("source_intent"), dict) else {}
            if not has_structured_detail(existing_text, existing_intent):
                continue
            if str(existing_intent.get("evidence_mode") or "") != str(source_intent.get("evidence_mode") or ""):
                continue
            existing_canonical = canonical_structured_detail_text(str(existing.get("claim") or ""))
            same_head_to_head = bool(
                head_to_head_signature(text)
                and head_to_head_signature(text) == head_to_head_signature(existing_text)
            )
            same_detail = (
                canonical_text == existing_canonical
                or canonical_text in existing_canonical
                or existing_canonical in canonical_text
                or same_head_to_head
                or claim_texts_overlap(text, existing_text)
            )
            if not same_detail:
                continue
            if cleanliness_score(claim) > cleanliness_score(existing):
                kept[idx] = claim
            replaced = True
            break
        if not replaced:
            kept.append(claim)
    return kept


def evidence_task_priority_score(
    claim_text: str,
    centrality: str,
    source_intent: Dict[str, Any],
) -> int:
    mode = str(source_intent.get("evidence_mode") or "")
    risk_type = str(source_intent.get("risk_type") or "")
    assertion = str(source_intent.get("assertion_strength") or "")
    score = 0
    if centrality == "core":
        score += 50
    elif centrality == "supporting":
        score += 20
    if has_structured_detail(claim_text, source_intent):
        score += 20
    if mode in HIGH_RISK_SUPPORTING_MODES or risk_type in HIGH_RISK_TYPES:
        score += 20
    elif risk_type in {"detail_numeric", "detail_date", "route_relation", "prediction"}:
        score += 15
    if assertion == "high":
        score += 10
    return score


def evidence_task_priority_label(score: int) -> str:
    if score >= 70:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 25:
        return "normal"
    return "low"


def direct_answer_need_text(evidence_mode: str, evidence_target: str) -> str:
    mapping = {
        "route_fact": "需要能直接说明是否经过某路线/领空/区域的句子",
        "numeric_fact": "需要能直接给出同一指标数值或金额的句子",
        "date_fact": "需要能直接给出日期、窗口期或发布时间的句子",
        "schedule_fact": "需要能直接给出赛程、交易日历或安排的句子",
        "event_result": "需要能直接给出结果、比分、获奖或是否退赛的句子",
        "policy_fact": "需要能直接说明政策、意图、状态或影响关系的句子",
        "entity_fact": "需要能直接确认主体、身份、获奖者或对象归属的句子",
    }
    if evidence_target == "route_relation":
        return "需要能直接说明是否经过某路线/领空/区域的句子"
    return mapping.get(evidence_mode, "需要能直接支持或反驳该 claim 的句子")


def compact_term_list(values: List[Any], limit: int = 6, width: int = 50) -> List[str]:
    out: List[str] = []
    for value in values:
        text = compact_claim_text(normalize_text(str(value or "")), width)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return dedupe_keep_order(out)[:limit]


def first_nonempty_text(*values: Any, width: int = 80) -> str:
    for value in values:
        text = compact_claim_text(normalize_text(str(value or "")), width)
        if text:
            return text
    return ""


def claim_time_markers(text: str) -> List[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    markers = re.findall(
        r"(20\d{2}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日|\d{4}-\d{2}-\d{2}|截至今天|截至目前|当前|今日|今天|最新|实时|当日)",
        normalized,
    )
    return compact_term_list(markers, 4, 30)


def mode_relation_text(evidence_mode: str, evidence_target: str, claim_text: str) -> str:
    if evidence_target == "route_relation" or evidence_mode == "route_fact":
        return "路线关系/是否经过"
    if evidence_mode == "numeric_fact":
        return "同一指标数值"
    if evidence_mode in {"date_fact", "schedule_fact"}:
        return "日期/时间安排"
    if evidence_mode == "event_result":
        return "结果/比分/输赢"
    if evidence_mode == "policy_fact":
        return "政策/状态表述"
    if any(term in claim_text for term in ["唯一", "只能", "必经", "必须经过", "完全绕开", "without crossing", "only route", "must pass"]):
        return "排他性前提"
    return "直接事实表述"


def preferred_page_type_from_source_intent(source_intent: Dict[str, Any]) -> str:
    page_intent = source_intent.get("page_intent") if isinstance(source_intent.get("page_intent"), dict) else {}
    needed = normalize_text(str(page_intent.get("needed_page_type") or ""))
    if needed:
        return needed
    target = str(source_intent.get("evidence_target") or "")
    mode = str(source_intent.get("evidence_mode") or "")
    shape = str(source_intent.get("evidence_shape") or "")
    if shape == "authoritative_notice":
        return "official_notice"
    if shape == "structured_historical_data":
        return "historical_table"
    if shape == "event_detail_page":
        return "event_detail"
    if shape == "current_status_update":
        return "current_status_page"
    if target == "route_relation" or mode == "route_fact":
        return "route_analysis_page"
    if target == "market_price" or mode == "numeric_fact":
        return "quote_page"
    if target == "market_calendar" or mode == "schedule_fact":
        return "calendar_page"
    if mode == "event_result":
        return "result_page"
    if target == "current_status" or mode == "policy_fact":
        return "current_status_page"
    return "general_page"


def direct_evidence_need_kind(evidence_mode: str, evidence_target: str, claim_shape: str) -> str:
    if claim_shape == "exclusive_premise" or evidence_target == "route_relation" or evidence_mode == "route_fact":
        return "route_or_exclusivity"
    if evidence_mode in {"date_fact", "schedule_fact"} or evidence_target in {"market_calendar", "census_phase"}:
        return "official_date_or_schedule"
    if evidence_mode == "numeric_fact" or evidence_target in {"market_price", "prize_amount", "position_distance"}:
        return "numeric_quote_or_table"
    if evidence_mode == "event_result" or evidence_target in {"match_result", "withdrawal_status"}:
        return "direct_result"
    if evidence_mode == "policy_fact" or evidence_target == "current_status":
        return "policy_or_status_statement"
    return "general_direct_statement"


def false_friend_defaults(evidence_mode: str, evidence_target: str, claim_shape: str) -> List[str]:
    if claim_shape == "exclusive_premise" or evidence_target == "route_relation" or evidence_mode == "route_fact":
        return [
            "只讲地区重要性或地缘背景，但没有直接说明是否唯一/是否必须经过/是否存在替代路径的材料",
            "地图、航线示意或泛分析页，但没有同一句明确回答路线关系的材料",
        ]
    if evidence_mode == "numeric_fact":
        return [
            "只讲走势或背景解读，但没有同一日期、同一口径、同一单位数值的材料",
            "换算值、二次转述或泛报价页，但没有原始指标口径的材料",
        ]
    if evidence_mode in {"date_fact", "schedule_fact"}:
        return [
            "只提相关事件，但没有同一时间窗口/同一阶段安排的材料",
            "历史公告或旧日历页，但不是当前核查时点的材料",
        ]
    if evidence_mode == "event_result":
        return [
            "赛前预测、回顾或历史交手材料，但没有本场实际结果的材料",
            "只讲过程或状态，没有直接结果/比分/是否退赛结论的材料",
        ]
    if evidence_mode == "policy_fact" or evidence_target == "current_status":
        return [
            "评论分析或二手转述，但没有官方状态表述的材料",
            "相关背景页，但没有同一政策/执行状态直接表述的材料",
        ]
    return [
        "主题相关但不是同一事实位点的材料",
        "只相关不直答的背景或评论材料",
    ]


def expected_failure_stage_for_program(
    evidence_mode: str,
    evidence_target: str,
    claim_shape: str,
    mechanism_type: str,
) -> str:
    mechanism = normalize_text(mechanism_type)
    if claim_shape == "exclusive_premise":
        return "provider_recall"
    if mechanism in {"structured_numeric_authority", "date_authority"}:
        return "point_conversion"
    if mechanism in {"event_result_page", "current_status_update"}:
        return "retrieval_readiness"
    if mechanism == "relation_sentence":
        return "comparability" if evidence_mode == "route_fact" else "retrieval_readiness"
    if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}:
        return "point_conversion"
    if evidence_mode == "event_result":
        return "retrieval_readiness"
    if evidence_mode == "route_fact" or evidence_target == "route_relation":
        return "provider_recall"
    if evidence_mode == "policy_fact" or evidence_target == "current_status":
        return "retrieval_readiness"
    return "retrieval_filter"


def build_program_anchor_terms_by_bucket(
    claim_text: str,
    source_intent: Dict[str, Any],
) -> Dict[str, List[str]]:
    source_strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
    route_meta = source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}
    core_binding = source_intent.get("core_binding") if isinstance(source_intent.get("core_binding"), dict) else {}
    metric_slots = source_intent.get("metric_slots") if isinstance(source_intent.get("metric_slots"), dict) else {}
    task_semantics = source_intent.get("task_semantics") if isinstance(source_intent.get("task_semantics"), dict) else {}
    evidence_mode = str(source_intent.get("evidence_mode") or "")
    evidence_target = str(source_intent.get("evidence_target") or "")
    buckets: Dict[str, List[str]] = {
        "entity": compact_term_list(
            [
                core_binding.get("subject_entity"),
                metric_slots.get("subject_entity"),
                core_binding.get("object_entity"),
                route_meta.get("origin"),
                route_meta.get("destination"),
            ] + list(source_strategy.get("must_have") or []),
            6,
            60,
        ),
        "time": compact_term_list(
            [core_binding.get("time_scope"), metric_slots.get("time_scope")] + claim_time_markers(claim_text),
            4,
            40,
        ),
        "event": [],
        "numeric": [],
        "route": compact_term_list(
            [
                route_meta.get("route_area"),
                route_meta.get("origin"),
                route_meta.get("destination"),
                core_binding.get("relation_or_metric"),
            ],
            5,
            50,
        ),
        "policy": [],
        "status": [],
    }
    relation_text = mode_relation_text(evidence_mode, evidence_target, claim_text)
    if evidence_mode == "numeric_fact":
        buckets["numeric"] = compact_term_list(
            [metric_slots.get("metric_name"), metric_slots.get("unit"), relation_text] + list(task_semantics.get("retrieval_focus") or []),
            5,
            40,
        )
        buckets["event"] = compact_term_list([relation_text], 2, 30)
    elif evidence_mode in {"date_fact", "schedule_fact"}:
        buckets["event"] = compact_term_list([relation_text] + list(task_semantics.get("retrieval_focus") or []), 4, 40)
    elif evidence_mode == "event_result":
        buckets["event"] = compact_term_list([relation_text] + list(task_semantics.get("retrieval_focus") or []), 4, 40)
        buckets["status"] = compact_term_list(["实际结果", "比分", "赛果"], 3, 20)
    elif evidence_mode == "policy_fact":
        buckets["policy"] = compact_term_list([relation_text] + list(task_semantics.get("retrieval_focus") or []), 4, 40)
        buckets["status"] = compact_term_list(["官方表述", "执行状态", "是否生效"], 3, 20)
    elif evidence_mode == "route_fact" or evidence_target == "route_relation":
        buckets["route"] = compact_term_list(
            buckets["route"] + [relation_text, "是否经过", "是否唯一", "替代路径"],
            6,
            40,
        )
        buckets["status"] = compact_term_list(["是否经过", "是否唯一", "是否可绕开"], 3, 20)
    else:
        buckets["status"] = compact_term_list([relation_text], 2, 30)
    return {key: value for key, value in buckets.items() if value}


def claim_budget_bucket(claim_text: str, source_intent: Dict[str, Any], checkability: str = "checkable") -> str:
    text = normalize_text(claim_text)
    if checkability in {"subjective", "not_checkable"}:
        return "background_context"
    evidence_mode = str(source_intent.get("evidence_mode") or "")
    claim_shape = str(source_intent.get("claim_shape") or "")
    if claim_shape == "exclusive_premise" or evidence_mode == "route_fact":
        return "direct_observable"
    if BACKGROUND_CONTEXT_PATTERN.search(text) and not DIRECT_OBSERVABLE_PATTERN.search(text):
        return "background_context"
    has_interpretive = bool(INTERPRETIVE_EXPLANATION_PATTERN.search(text))
    has_direct_signal = bool(DIRECT_OBSERVABLE_PATTERN.search(text))
    structured = has_structured_detail(text, source_intent)
    if has_interpretive and not structured and not has_direct_signal:
        return "interpretive_explanation"
    if structured:
        return "structured_detail" if str(source_intent.get("evidence_mode") or "") != "entity_fact" else (
            "structured_detail" if not has_interpretive else "interpretive_explanation"
        )
    if has_interpretive:
        return "interpretive_explanation"
    if has_direct_signal or evidence_mode in {"entity_fact", "policy_fact", "event_result", "date_fact", "schedule_fact", "numeric_fact"}:
        return "direct_observable"
    return "background_context"


def user_need_allows_two_core_claims(user_need: str) -> bool:
    text = normalize_text(user_need)
    if not text:
        return False
    has_fact_need = bool(re.search(r"(是否|有没有|多少|几|何时|开盘|休市|比分|中间价|汇率|日期|结果|状态)", text))
    has_interpretive_need = bool(re.search(r"(代表什么|意味着什么|说明什么|怎么看|反映什么|原因是什么|为什么)", text))
    return has_fact_need and has_interpretive_need


def split_mixed_sentence_clauses(sentence: str) -> List[str]:
    parts = [normalize_text(part) for part in MIXED_SENTENCE_SPLIT_PATTERN.split(sentence or "") if normalize_text(part)]
    return parts[:5]


def infer_augmented_clause_intent(clause_text: str, need_type: str) -> Dict[str, Any]:
    text = normalize_text(clause_text)
    lower = text.lower()
    if EXCLUSIVE_PREMISE_PATTERN.search(text) or EXCLUSIVE_ROUTE_HINT_PATTERN.search(text):
        evidence_mode = "route_fact"
        evidence_target = "route_relation"
        evidence_shape = "open_news_analysis"
        risk_type = "route_relation"
    elif re.search(r"(比分|战胜|赢了|输给|退赛|晋级|夺冠|获胜|beat|won|result|score)", text, flags=re.I):
        evidence_mode = "event_result"
        evidence_target = infer_evidence_target(text, evidence_mode, need_type)
        evidence_shape = "event_detail_page"
        risk_type = "direct_answer"
    elif re.search(r"(休市|开盘|交易日|假期|公布|发布|生效|日期|时间|schedule|calendar|announce|release)", text, flags=re.I):
        evidence_mode = "schedule_fact" if need_type == "market_movement" else "date_fact"
        evidence_target = infer_evidence_target(text, evidence_mode, need_type)
        evidence_shape = "authoritative_notice"
        risk_type = "detail_date"
    elif re.search(r"(\d|中间价|汇率|牌价|金额|奖金|公里|千米|百分比|基点|price|rate|amount|km|%)", text, flags=re.I):
        evidence_mode = "numeric_fact"
        evidence_target = infer_evidence_target(text, evidence_mode, need_type)
        evidence_shape = "authoritative_notice"
        risk_type = "detail_numeric"
    elif re.search(r"(政策|执行|允许|禁止|参战|配合|状态|official|status|policy)", lower):
        evidence_mode = "policy_fact"
        evidence_target = infer_evidence_target(text, evidence_mode, need_type)
        evidence_shape = "current_status_update"
        risk_type = "policy_intent"
    else:
        evidence_mode = "entity_fact"
        evidence_target = infer_evidence_target(text, "entity_fact", need_type)
        evidence_shape = "general_evidence_page"
        risk_type = "general"
    must_have = compact_term_list(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", text), 6, 24)
    return {
        "preferred_source_types": ["official", "news"],
        "preferred_domains": [],
        "evidence_mode": evidence_mode,
        "evidence_target": evidence_target,
        "evidence_shape": evidence_shape,
        "time_sensitivity": "high" if claim_time_markers(text) else "medium",
        "assertion_strength": "high",
        "risk_type": risk_type,
        "claim_shape": "exclusive_premise" if EXCLUSIVE_PREMISE_PATTERN.search(text) else "",
        "stated_as_fact": True,
        "source_strategy": {
            "source_types": ["official", "news"],
            "search_channels": ["news_search", "web_search"],
            "languages": ["zh", "en"] if re.search(r"[A-Za-z]", text) else ["zh"],
            "must_have": must_have,
            "avoid_sources": ["forum", "qa"],
            "why": "把混合回答里的高风险结构化细节单独抽出来，避免它和解释性结论共用一个 claim。",
        },
        "page_intent": {
            "needed_page_type": preferred_page_type_from_source_intent(
                {"evidence_mode": evidence_mode, "evidence_target": evidence_target, "evidence_shape": evidence_shape}
            ),
            "must_contain": must_have,
            "avoid_page_type": ["landing_page", "search_result_page"],
            "why": "优先找能直接回答该结构化细节的页面。",
        },
        "route_meta": normalize_route_meta({}),
    }


def augment_mixed_detail_claims(extracted: Dict[str, Any], claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    answer_text = normalize_text(str(extracted.get("_answer_text") or ""))
    if not answer_text:
        return claims
    existing_texts = [normalize_text(str(item.get("claim") or "")) for item in claims if isinstance(item, dict)]
    need_type = normalize_need_type(extracted.get("need_type"))
    if need_type not in {"market_movement", "financial_quote", "current_result", "sports_result", "schedule_time"}:
        return claims
    interpretive_core_exists = any(
        isinstance(item, dict)
        and str(item.get("centrality") or "") == "core"
        and str(item.get("claim_budget_bucket") or claim_budget_bucket(
            str(item.get("claim") or ""),
            item.get("source_intent") if isinstance(item.get("source_intent"), dict) else {},
            str(item.get("checkability") or "checkable"),
        )) == "interpretive_explanation"
        for item in claims
    )
    if not interpretive_core_exists:
        return claims

    def clause_conflicts_with_existing(clause_text: str, clause_intent: Dict[str, Any]) -> bool:
        clause_norm = normalize_text(clause_text)
        clause_mode = str(clause_intent.get("evidence_mode") or "")
        clause_bucket = claim_budget_bucket(clause_text, clause_intent, "checkable")
        clause_signature = (
            clause_mode,
            clause_bucket,
            tuple(compact_term_list(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", clause_norm), 4, 24)),
        )
        for existing in claims:
            if not isinstance(existing, dict):
                continue
            existing_text = normalize_text(str(existing.get("claim") or ""))
            existing_intent = existing.get("source_intent") if isinstance(existing.get("source_intent"), dict) else {}
            existing_bucket = str(existing.get("claim_budget_bucket") or claim_budget_bucket(
                existing_text,
                existing_intent,
                str(existing.get("checkability") or "checkable"),
            ))
            existing_mode = str(existing_intent.get("evidence_mode") or "")
            existing_signature = (
                existing_mode,
                existing_bucket,
                tuple(compact_term_list(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", existing_text), 4, 24)),
            )
            if claim_texts_overlap(clause_norm, existing_text):
                return True
            if clause_signature == existing_signature and existing_bucket in {"structured_detail", "interpretive_explanation"}:
                return True
        return False

    additions: List[Dict[str, Any]] = []
    next_index = len(claims) + 1
    for sentence in split_answer_sentences_for_claims(answer_text):
        if not (INTERPRETIVE_EXPLANATION_PATTERN.search(sentence) and DIRECT_OBSERVABLE_PATTERN.search(sentence)):
            continue
        for clause in split_mixed_sentence_clauses(sentence):
            if len(additions) >= 1:
                break
            clean_clause = strip_markdown_noise(clause)
            if not clean_clause or len(clean_clause) < 6:
                continue
            if not re.search(r"(\d|休市|开盘|中间价|汇率|牌价|金额|奖金|日期|发布|生效|比分|战绩|退赛|晋级)", clean_clause, flags=re.I):
                continue
            if INTERPRETIVE_EXPLANATION_PATTERN.search(clean_clause) and not has_structured_detail(clean_clause, {}):
                continue
            source_intent = infer_augmented_clause_intent(clean_clause, need_type)
            if not has_structured_detail(clean_clause, source_intent):
                continue
            if claim_budget_bucket(clean_clause, source_intent, "checkable") != "structured_detail":
                continue
            if any(claim_texts_overlap(clean_clause, text) for text in existing_texts):
                continue
            if clause_conflicts_with_existing(clean_clause, source_intent):
                continue
            centrality = "supporting"
            additions.append(
                {
                    "claim_id": f"mix{next_index}",
                    "claim": clean_clause,
                    "centrality": centrality,
                    "checkability": "checkable",
                    "source_intent": source_intent,
                    "verification_questions": [],
                    "queries": [],
                    "evidence_task_card": build_evidence_task_card(clean_clause, centrality, source_intent, [], []),
                }
            )
            existing_texts.append(clean_clause)
            next_index += 1
    return claims + additions


def required_slot_profile_for_mode(
    evidence_mode: str,
    claim_text: str = "",
    source_intent: Optional[Dict[str, Any]] = None,
    decision_slots: Optional[Dict[str, Any]] = None,
) -> List[str]:
    return shared_required_slot_profile_for_mode(
        evidence_mode,
        claim_text=claim_text,
        source_intent=source_intent,
        decision_slots=decision_slots,
    )


def infer_missing_required_slots(
    decision_slots: Dict[str, Any],
    evidence_mode: str,
    claim_text: str = "",
    source_intent: Optional[Dict[str, Any]] = None,
    observed_buckets: Optional[set[str]] = None,
) -> List[str]:
    return shared_infer_missing_required_slots(
        decision_slots,
        evidence_mode,
        claim_text=claim_text,
        source_intent=source_intent,
        observed_buckets=observed_buckets,
        observed_slots=None,
    )


def build_evidence_need_program(
    claim_text: str,
    centrality: str,
    checkability: str,
    source_intent: Dict[str, Any],
    need_type: str,
    raw_program: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    evidence_mode = str(source_intent.get("evidence_mode") or "entity_fact")
    evidence_target = str(source_intent.get("evidence_target") or infer_evidence_target(claim_text, evidence_mode, need_type))
    claim_shape = str(source_intent.get("claim_shape") or "")
    mechanism_type = str(source_intent.get("mechanism_type") or "")
    normalized_assertion = (
        canonical_exclusive_premise_sentence(claim_text)
        if claim_shape == "exclusive_premise"
        else compact_claim_text(strip_markdown_noise(claim_text), 120)
    )
    anchor_terms_by_bucket = build_program_anchor_terms_by_bucket(claim_text, source_intent)
    anchor_buckets = [bucket for bucket, terms in anchor_terms_by_bucket.items() if terms]
    subject = first_nonempty_text(
        (source_intent.get("core_binding") or {}).get("subject_entity") if isinstance(source_intent.get("core_binding"), dict) else "",
        (source_intent.get("metric_slots") or {}).get("subject_entity") if isinstance(source_intent.get("metric_slots"), dict) else "",
        (source_intent.get("route_meta") or {}).get("origin") if isinstance(source_intent.get("route_meta"), dict) else "",
        (anchor_terms_by_bucket.get("entity") or [""])[0],
        width=70,
    )
    object_term = first_nonempty_text(
        (source_intent.get("core_binding") or {}).get("object_entity") if isinstance(source_intent.get("core_binding"), dict) else "",
        (source_intent.get("route_meta") or {}).get("destination") if isinstance(source_intent.get("route_meta"), dict) else "",
        width=70,
    )
    time_scope = first_nonempty_text(
        (source_intent.get("core_binding") or {}).get("time_scope") if isinstance(source_intent.get("core_binding"), dict) else "",
        (source_intent.get("metric_slots") or {}).get("time_scope") if isinstance(source_intent.get("metric_slots"), dict) else "",
        (anchor_terms_by_bucket.get("time") or [""])[0],
        width=50,
    )
    metric_or_relation = first_nonempty_text(
        (source_intent.get("core_binding") or {}).get("relation_or_metric") if isinstance(source_intent.get("core_binding"), dict) else "",
        (source_intent.get("metric_slots") or {}).get("metric_name") if isinstance(source_intent.get("metric_slots"), dict) else "",
        mode_relation_text(evidence_mode, evidence_target, claim_text),
        width=70,
    )
    status_or_result = first_nonempty_text(
        (anchor_terms_by_bucket.get("status") or [""])[0],
        (anchor_terms_by_bucket.get("event") or [""])[0],
        width=50,
    )
    direct_need = {
        "evidence_kind": direct_evidence_need_kind(evidence_mode, evidence_target, claim_shape),
        "must_answer": direct_answer_need_text(evidence_mode, evidence_target),
        "preferred_page_type": preferred_page_type_from_source_intent(source_intent),
        "must_include": compact_term_list(
            (anchor_terms_by_bucket.get("entity") or [])
            + (anchor_terms_by_bucket.get("time") or [])
            + (anchor_terms_by_bucket.get("numeric") or [])
            + (anchor_terms_by_bucket.get("event") or [])
            + (anchor_terms_by_bucket.get("route") or [])
            + (anchor_terms_by_bucket.get("policy") or []),
            6,
            50,
        ),
    }
    program = {
        "normalized_assertion": normalized_assertion or compact_claim_text(claim_text, 120),
        "answer_role_impact": (
            "rhetorical"
            if checkability in {"subjective", "not_checkable"}
            else "core"
            if centrality == "core"
            else "supporting"
            if centrality == "supporting"
            else "background"
        ),
        "decision_slots": {
            "subject": subject,
            "object": object_term,
            "time_scope": time_scope,
            "metric_or_relation": metric_or_relation,
            "status_or_result": status_or_result,
            "anchor_buckets": anchor_buckets,
            "anchor_terms_by_bucket": anchor_terms_by_bucket,
        },
        "direct_evidence_need": direct_need,
        "false_friend_evidence": false_friend_defaults(evidence_mode, evidence_target, claim_shape),
        "expected_failure_stage": expected_failure_stage_for_program(
            evidence_mode,
            evidence_target,
            claim_shape,
            mechanism_type,
        ),
    }
    if isinstance(raw_program, dict):
        normalized = compact_claim_text(normalize_text(str(raw_program.get("normalized_assertion") or "")), 120)
        if normalized:
            program["normalized_assertion"] = normalized
        answer_role = normalize_text(str(raw_program.get("answer_role_impact") or "")).lower()
        if answer_role in {"core", "supporting", "background", "rhetorical"}:
            program["answer_role_impact"] = answer_role
        raw_slots = raw_program.get("decision_slots") if isinstance(raw_program.get("decision_slots"), dict) else {}
        if raw_slots:
            for key in ("subject", "object", "time_scope", "metric_or_relation", "status_or_result"):
                slot_value = compact_claim_text(normalize_text(str(raw_slots.get(key) or "")), 80)
                if slot_value:
                    program["decision_slots"][key] = slot_value
        direct_raw = raw_program.get("direct_evidence_need") if isinstance(raw_program.get("direct_evidence_need"), dict) else {}
        if direct_raw:
            if normalize_text(str(direct_raw.get("must_answer") or "")):
                program["direct_evidence_need"]["must_answer"] = compact_claim_text(
                    normalize_text(str(direct_raw.get("must_answer") or "")),
                    120,
                )
            raw_include = direct_raw.get("must_include") if isinstance(direct_raw.get("must_include"), list) else []
            if raw_include:
                program["direct_evidence_need"]["must_include"] = compact_term_list(raw_include, 6, 50)
        raw_false_friends = raw_program.get("false_friend_evidence") if isinstance(raw_program.get("false_friend_evidence"), list) else []
        if raw_false_friends:
            program["false_friend_evidence"] = compact_term_list(raw_false_friends, 4, 90)
        expected_stage = normalize_text(str(raw_program.get("expected_failure_stage") or "")).lower()
        if expected_stage in {"provider_recall", "retrieval_filter", "retrieval_readiness", "point_conversion", "comparability", "multi_hop_closure"}:
            program["expected_failure_stage"] = expected_stage
    program_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    missing_required_slots = infer_missing_required_slots(
        program_slots,
        evidence_mode,
        claim_text,
        source_intent,
        set(anchor_buckets),
    )
    program["required_slot_profile"] = required_slot_profile_for_mode(
        evidence_mode,
        claim_text,
        source_intent,
        program_slots,
    )
    program["missing_required_slots"] = missing_required_slots
    program["false_friend_evidence"] = compact_term_list(program.get("false_friend_evidence") or [], 4, 90)
    return program


def build_program_verification_questions(claim: Dict[str, Any], program: Dict[str, Any]) -> List[str]:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    claim_text = compact_claim_text(str(claim.get("claim") or ""), 90)
    if str(source_intent.get("claim_shape") or "") == "exclusive_premise":
        return exclusive_premise_verification_questions(claim_text, str(source_intent.get("evidence_mode") or ""))
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    must_answer = compact_claim_text(str(direct_need.get("must_answer") or ""), 90)
    false_friend = compact_claim_text(str((program.get("false_friend_evidence") or [""])[0]), 90)
    questions: List[str] = []
    if must_answer:
        questions.append(must_answer.replace("需要能直接", "实际").replace("的句子", "是什么？"))
    else:
        questions.append("证据中能直接回答该 claim 的事实是什么？")
    if false_friend:
        questions.append(f"是否只有{false_friend}，而没有同一事实位点的直接证据？")
    else:
        questions.append("是否存在看起来相关但不能直接裁决该 claim 的材料？")
    return compact_term_list(questions, 2, 90)


def infer_program_query_goal(source_intent: Dict[str, Any]) -> str:
    evidence_mode = str(source_intent.get("evidence_mode") or "")
    evidence_target = str(source_intent.get("evidence_target") or "")
    if evidence_target == "route_relation" or evidence_mode == "route_fact":
        return "find_route"
    if evidence_mode == "numeric_fact":
        return "verify_numeric_detail"
    if evidence_mode in {"date_fact", "schedule_fact"}:
        return "verify_date_detail"
    if evidence_mode == "event_result":
        return "find_result"
    if evidence_mode == "policy_fact":
        return "find_policy"
    return "general_verify"

def normalize_query_family_role(value: Any) -> str:
    role = normalize_text(str(value or ""))
    return role if role in {"mirror", "slot", "closure", "refute", "distinguish"} else "mirror"


def query_family_role_priority(claim_family: str, role: str) -> int:
    role = normalize_query_family_role(role)
    priorities: Dict[str, Dict[str, int]] = {
        "date_fact": {"closure": 30, "distinguish": 26, "slot": 18, "mirror": 10},
        "schedule_fact": {"closure": 30, "distinguish": 26, "slot": 18, "mirror": 10},
        "route_fact": {"closure": 30, "refute": 28, "distinguish": 24, "slot": 16, "mirror": 10},
        "event_result": {"distinguish": 30, "refute": 28, "closure": 22, "slot": 16, "mirror": 10},
        "numeric_count_detail": {"closure": 30, "refute": 26, "slot": 18, "mirror": 10},
        "numeric_fact": {"slot": 26, "closure": 20, "distinguish": 18, "mirror": 10},
    }
    return priorities.get(claim_family, {}).get(role, {"slot": 18, "mirror": 10}.get(role, 8))


def query_source_preference_for_role(claim_family: str, role: str) -> List[str]:
    role = normalize_query_family_role(role)
    if claim_family in {"date_fact", "schedule_fact"}:
        if role in {"closure", "distinguish"}:
            return ["official", "html", "news"]
        return ["html", "official", "news"]
    if claim_family == "route_fact":
        if role in {"closure", "refute", "distinguish"}:
            return ["news", "html", "official"]
        return ["html", "news", "official"]
    if claim_family == "event_result":
        return ["news", "html", "official"] if role in {"distinguish", "refute"} else ["html", "news", "official"]
    if claim_family in {"numeric_count_detail", "numeric_fact"}:
        return ["official", "html", "news"] if role == "closure" else ["html", "official", "news"]
    return ["html", "news", "official"]


def normalize_query_planner_hint(raw_obj: Optional[Dict[str, Any]], fallback: Dict[str, Any]) -> Dict[str, Any]:
    base = dict(fallback)
    raw_obj = raw_obj if isinstance(raw_obj, dict) else {}
    claim_family = normalize_text(str(raw_obj.get("claim_family") or "")) or str(base.get("claim_family") or "general_fact")
    intended_channel = normalize_text(str(raw_obj.get("intended_decision_channel") or "")) or str(base.get("intended_decision_channel") or DECISION_CHANNEL_UNRESOLVED)
    query_plan = [
        normalize_query_family_role(item)
        for item in (raw_obj.get("query_family_plan") or [])
        if normalize_query_family_role(item) in {"closure", "refute", "distinguish", "slot", "mirror"}
    ] if isinstance(raw_obj.get("query_family_plan"), list) else []
    bridge_facts = compact_term_list(raw_obj.get("bridge_fact_plan") or [], 4, 24) if isinstance(raw_obj.get("bridge_fact_plan"), list) else []
    if query_plan:
        base["query_family_plan"] = dedupe_keep_order(query_plan)[:3]
    if bridge_facts:
        base["bridge_fact_plan"] = bridge_facts[:4]
    base["claim_family"] = claim_family
    if intended_channel in {DECISION_CHANNEL_DIRECT_WEB, DECISION_CHANNEL_CLOSURE, DECISION_CHANNEL_UNRESOLVED}:
        base["intended_decision_channel"] = intended_channel
    return base


def default_query_planner_hint(claim: Dict[str, Any], program: Dict[str, Any]) -> Dict[str, Any]:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    claim_family = infer_claim_family(claim, {"evidence_mode": source_intent.get("evidence_mode")})
    secondary_detail_scope = infer_secondary_detail_scope(claim, {"structured_detail_retained": str(claim.get("centrality") or "") in {"supporting", "peripheral"}})
    intended_channel = infer_intended_decision_channel(claim, claim_family, secondary_detail_scope)
    claim_text = normalize_text(str(claim.get("claim") or ""))
    bridge: List[str] = []
    plan: List[str] = []
    if claim_family in {"date_fact", "schedule_fact"}:
        plan = ["closure", "distinguish"]
        if re.search(r"(星期|周几|交易日|休市|holiday|calendar)", claim_text, flags=re.I):
            bridge.extend(["星期", "交易日历"])
        if re.search(r"(生效|实施)", claim_text):
            bridge.extend(["生效日", "发布日期"])
        elif re.search(r"(发布|公布|公告)", claim_text):
            bridge.extend(["发布日期", "生效日"])
        else:
            bridge.extend(["官方日程", "发布日期"])
    elif claim_family == "route_fact":
        plan = ["closure", "refute"]
        bridge.extend(["替代路径", "其他路线", "并非唯一"])
    elif claim_family == "event_result":
        plan = ["distinguish", "closure"]
        bridge.extend(["最终结果", "过程结果", "局部结果"])
    elif claim_family == "numeric_count_detail":
        plan = ["closure"]
        bridge.extend(["总数", "累计", "合计"])
    return {
        "claim_family": claim_family,
        "intended_decision_channel": intended_channel,
        "query_family_plan": plan[:3],
        "bridge_fact_plan": dedupe_keep_order(bridge)[:4],
    }


def build_query_planner_prompt(claim: Dict[str, Any], program: Dict[str, Any], need_type: str) -> str:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    payload = {
        "need_type": need_type,
        "claim": str(claim.get("claim") or ""),
        "centrality": str(claim.get("centrality") or ""),
        "evidence_mode": str(source_intent.get("evidence_mode") or ""),
        "evidence_target": str(source_intent.get("evidence_target") or ""),
        "decision_slots": {
            "subject": str(decision_slots.get("subject") or ""),
            "object": str(decision_slots.get("object") or ""),
            "time_scope": str(decision_slots.get("time_scope") or ""),
            "metric_or_relation": str(decision_slots.get("metric_or_relation") or ""),
            "status_or_result": str(decision_slots.get("status_or_result") or ""),
        },
        "must_answer": str(direct_need.get("must_answer") or ""),
        "must_include": compact_term_list(direct_need.get("must_include") or [], 4, 24),
    }
    return json.dumps(payload, ensure_ascii=False)


def build_claim_query_planner_hint(claim: Dict[str, Any], program: Dict[str, Any], need_type: str) -> Dict[str, Any]:
    fallback = default_query_planner_hint(claim, program)
    if str(fallback.get("claim_family") or "") not in LLM_QUERY_PLANNER_FAMILIES:
        return fallback
    planner_obj, _raw = llm_chat(
        SYSTEM_DECISION_QUERY_PLANNER,
        build_query_planner_prompt(claim, program, need_type),
        retries=0,
    )
    return normalize_query_planner_hint(planner_obj, fallback)


def query_row(
    q: str,
    goal: str,
    role: str,
    origin: str,
    variant_origin: str,
    source_preference: Optional[List[str]] = None,
) -> Dict[str, str]:
    row: Dict[str, Any] = {
        "q": normalize_text(q),
        "goal": goal,
        "origin": origin,
        "query_variant_origin": variant_origin,
        "query_family_role": normalize_query_family_role(role),
    }
    if isinstance(source_preference, list):
        normalized_preference = [
            normalize_text(str(item))
            for item in source_preference
            if normalize_text(str(item))
        ]
        if normalized_preference:
            row["source_preference"] = dedupe_keep_order(normalized_preference)[:3]
    return row


def family_query_terms_for_role(
    claim: Dict[str, Any],
    program: Dict[str, Any],
    planner_hint: Optional[Dict[str, Any]],
    role: str,
) -> List[str]:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    claim_family = str((planner_hint or {}).get("claim_family") or infer_claim_family(claim, {"evidence_mode": source_intent.get("evidence_mode")}))
    subject = compact_claim_text(str(decision_slots.get("subject") or ""), 32)
    object_term = compact_claim_text(str(decision_slots.get("object") or ""), 24)
    time_scope = compact_claim_text(str(decision_slots.get("time_scope") or ""), 24)
    metric = compact_claim_text(str(decision_slots.get("metric_or_relation") or ""), 24)
    status = compact_claim_text(str(decision_slots.get("status_or_result") or ""), 24)
    bridge = compact_term_list((planner_hint or {}).get("bridge_fact_plan") or [], 4, 20)
    must_include = compact_term_list(direct_need.get("must_include") or [], 2, 18)
    base = [subject, object_term, time_scope]
    if claim_family in {"date_fact", "schedule_fact"}:
        if role == "closure":
            extras = bridge[:2] or ["星期", "官方日程"]
        elif role == "distinguish":
            extras = bridge[:2] or ["发布日期", "生效日"]
        else:
            extras = [metric, status]
    elif claim_family == "route_fact":
        if role == "closure":
            extras = bridge[:2] or ["替代路径", "绕行"]
        elif role == "refute":
            extras = bridge[:3] or ["其他路线", "并非唯一", "经由"]
        else:
            extras = [metric, status]
    elif claim_family == "event_result":
        if role == "distinguish":
            extras = bridge[:3] or ["最终结果", "过程结果", "局部结果"]
        elif role == "closure":
            extras = bridge[:2] or ["最终比分", "赛后战绩"]
        else:
            extras = [metric, status]
    elif claim_family == "numeric_count_detail":
        extras = bridge[:3] or ["总数", "累计", "合计"]
    else:
        extras = bridge[:2] or [metric, status]
    return compact_term_list(base + extras + [metric, status] + must_include, 7, 22)


def build_family_query_rows(
    claim: Dict[str, Any],
    program: Dict[str, Any],
    planner_hint: Optional[Dict[str, Any]],
) -> List[Dict[str, str]]:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    roles = [
        normalize_query_family_role(item)
        for item in ((planner_hint or {}).get("query_family_plan") or [])
        if normalize_query_family_role(item) in {"closure", "refute", "distinguish"}
    ]
    if not roles:
        return []
    goal = infer_program_query_goal(source_intent)
    claim_family = str((planner_hint or {}).get("claim_family") or infer_claim_family(claim, {"evidence_mode": source_intent.get("evidence_mode") or ""}))
    rows: List[Dict[str, str]] = []
    ranked_roles = sorted(
        dedupe_keep_order(roles),
        key=lambda item: query_family_role_priority(claim_family, item),
        reverse=True,
    )
    for role in ranked_roles[:3]:
        query_text = compact_query_text_local(" ".join(family_query_terms_for_role(claim, program, planner_hint, role)), 96)
        if not query_text:
            continue
        rows.append(
            query_row(
                query_text,
                goal,
                role,
                f"{role}_query",
                f"{role}_query",
                source_preference=query_source_preference_for_role(claim_family, role),
            )
        )
    return merge_query_rows(rows)


FACT_SLOT_QUERY_MODES = {
    EVIDENCE_MODE_NUMERIC,
    EVIDENCE_MODE_DATE,
    EVIDENCE_MODE_SCHEDULE,
    EVIDENCE_MODE_EVENT,
}


def claim_uses_fact_slot_query(claim: Dict[str, Any], source_intent: Dict[str, Any]) -> bool:
    if str(claim.get("centrality") or "") != "core":
        return False
    if str(source_intent.get("claim_shape") or "") == "exclusive_premise":
        return False
    return str(source_intent.get("evidence_mode") or "") in FACT_SLOT_QUERY_MODES


def fact_slot_opening_required(*texts: str) -> bool:
    combined = " ".join(normalize_text(str(text or "")) for text in texts if normalize_text(str(text or "")))
    return bool(re.search(r"(开盘|开市|opening|opened)", combined, flags=re.I))


def compact_query_text_local(text: str, limit: int = 96) -> str:
    normalized = normalize_text(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip(" ，。；;、")


def query_contains_term(query_text: str, term: str) -> bool:
    query_norm = normalize_text(query_text).lower()
    term_norm = normalize_text(term).lower()
    if not query_norm or not term_norm:
        return False
    return term_norm in query_norm


def query_covers_fact_slot(
    query_text: str,
    subject: str,
    time_scope: str,
    metric: str,
    status_or_result: str,
    opening_required: bool,
) -> bool:
    if not normalize_text(query_text):
        return False
    hits = 0
    if subject and query_contains_term(query_text, subject):
        hits += 1
    if time_scope and query_contains_term(query_text, time_scope):
        hits += 1
    metric_hit = metric and query_contains_term(query_text, metric)
    status_hit = status_or_result and query_contains_term(query_text, status_or_result)
    if metric_hit or status_hit:
        hits += 1
    if opening_required and not re.search(r"(开盘|开市|opening|opened)", normalize_text(query_text), flags=re.I):
        return False
    return hits >= 2 and (metric_hit or status_hit or not (metric or status_or_result))


def build_fact_slot_query_row(claim: Dict[str, Any], program: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    if not claim_uses_fact_slot_query(claim, source_intent):
        return None
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    claim_text = normalize_text(str(claim.get("claim") or ""))
    normalized_assertion = normalize_text(str(program.get("normalized_assertion") or claim_text))
    subject = compact_claim_text(str(decision_slots.get("subject") or ""), 32)
    object_term = compact_claim_text(str(decision_slots.get("object") or ""), 24)
    time_scope = compact_claim_text(str(decision_slots.get("time_scope") or ""), 24)
    metric = compact_claim_text(str(decision_slots.get("metric_or_relation") or ""), 24)
    status_or_result = compact_claim_text(str(decision_slots.get("status_or_result") or ""), 24)
    must_include = [
        compact_claim_text(str(term), 16)
        for term in (direct_need.get("must_include") or [])[:4]
        if normalize_text(str(term))
    ]
    opening_required = fact_slot_opening_required(
        claim_text,
        normalized_assertion,
        metric,
        status_or_result,
        object_term,
        direct_need.get("must_answer") or "",
        " ".join(must_include),
    )

    terms = compact_term_list(
        [
            time_scope,
            subject,
            "开盘" if opening_required else "",
            "开市" if opening_required else "",
            "opening" if opening_required else "",
            "opened" if opening_required else "",
            metric,
            status_or_result,
            object_term,
        ] + must_include,
        8,
        24,
    )
    query_text = compact_query_text_local(" ".join(term for term in terms if term), 96)
    existing_queries = claim.get("queries") if isinstance(claim.get("queries"), list) else []
    reused_query = next(
        (
            row for row in existing_queries
            if isinstance(row, dict)
            and query_covers_fact_slot(
                str(row.get("q") or row.get("query") or ""),
                subject,
                time_scope,
                metric,
                status_or_result,
                opening_required,
            )
        ),
        None,
    )
    if reused_query:
        reused_text = normalize_text(str(reused_query.get("q") or reused_query.get("query") or ""))
        if reused_text:
            return {
                "q": reused_text,
                "goal": infer_program_query_goal(source_intent),
                "origin": "fact_slot_query",
                "query_variant_origin": "fact_slot_query_reused",
                "query_family_role": "slot",
            }
    if not query_text:
        fallback_text = compact_query_text_local(" ".join(term for term in [normalized_assertion, subject, time_scope, metric] if term), 96)
        query_text = fallback_text
    if not query_text:
        return None
    return {
        "q": query_text,
        "goal": infer_program_query_goal(source_intent),
        "origin": "fact_slot_query",
        "query_variant_origin": "fact_slot_query",
        "query_family_role": "slot",
    }


def build_program_queries(claim: Dict[str, Any], program: Dict[str, Any]) -> List[Dict[str, str]]:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    claim_text = compact_claim_text(str(claim.get("claim") or ""), 80)
    if str(source_intent.get("claim_shape") or "") == "exclusive_premise":
        return exclusive_premise_queries(claim_text, str(source_intent.get("evidence_mode") or ""))
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    subject = compact_claim_text(str(decision_slots.get("subject") or ""), 40)
    object_term = compact_claim_text(str(decision_slots.get("object") or ""), 40)
    time_scope = compact_claim_text(str(decision_slots.get("time_scope") or ""), 30)
    metric = compact_claim_text(str(decision_slots.get("metric_or_relation") or ""), 40)
    normalized_assertion = compact_claim_text(str(program.get("normalized_assertion") or claim_text), 80)
    must_include = [compact_claim_text(str(term), 20) for term in (direct_need.get("must_include") or [])[:3] if normalize_text(str(term))]
    base_terms = compact_term_list([subject, object_term, time_scope, metric] + must_include, 5, 40)
    primary = normalized_assertion if len(normalized_assertion) <= 42 else " ".join(base_terms[:4]) or claim_text
    queries: List[Dict[str, Any]] = []
    planner_hint = claim.get("query_planner_hint") if isinstance(claim.get("query_planner_hint"), dict) else {}
    claim_family = str((planner_hint or {}).get("claim_family") or infer_claim_family(claim, {"evidence_mode": source_intent.get("evidence_mode")}))
    fact_slot_query = build_fact_slot_query_row(claim, program)
    family_queries = sorted(
        build_family_query_rows(claim, program, planner_hint),
        key=lambda row: query_family_role_priority(claim_family, str(row.get("query_family_role") or "")),
        reverse=True,
    )
    if fact_slot_query:
        queries.append(fact_slot_query)
    primary_row = query_row(
        primary,
        infer_program_query_goal(source_intent),
        "mirror",
        "program_primary_query",
        "program_primary_query",
        source_preference=query_source_preference_for_role(claim_family, "mirror"),
    )
    evidence_mode = str(source_intent.get("evidence_mode") or "")
    evidence_target = str(source_intent.get("evidence_target") or "")
    if evidence_target == "route_relation" or evidence_mode == "route_fact":
        second = " ".join(compact_term_list([subject, object_term, time_scope, "替代路径", "是否唯一"], 5, 20))
    elif evidence_mode == "numeric_fact":
        second = " ".join(compact_term_list([subject, metric, time_scope, "官方", "数据"], 5, 18))
    elif evidence_mode in {"date_fact", "schedule_fact"}:
        second = " ".join(compact_term_list([subject, metric, time_scope, "官方", "公告"], 5, 18))
    elif evidence_mode == "event_result":
        second = " ".join(compact_term_list([subject, object_term, time_scope, "实际结果", "比分"], 5, 18))
    elif evidence_mode == "policy_fact":
        second = " ".join(compact_term_list([subject, metric, time_scope, "官方表述"], 4, 18))
    else:
        second = " ".join(compact_term_list(base_terms + ["官方"], 5, 18))
    second = normalize_text(second)
    existing_query_texts = {normalize_text(str(item.get("q") or "")) for item in queries if isinstance(item, dict)}
    if family_queries:
        if claim_family in {"date_fact", "schedule_fact", "numeric_fact"} and fact_slot_query:
            queries.extend(
                row for row in family_queries
                if normalize_text(str(row.get("q") or "")) not in existing_query_texts
            )
        elif claim_family in {"route_fact", "event_result", "numeric_count_detail"}:
            queries.extend(
                row for row in family_queries
                if normalize_text(str(row.get("q") or "")) not in existing_query_texts
            )
            if not queries:
                queries.append(primary_row)
        else:
            if not fact_slot_query:
                queries.append(primary_row)
            queries.extend(
                row for row in family_queries
                if normalize_text(str(row.get("q") or "")) not in existing_query_texts
            )
    else:
        if not fact_slot_query:
            queries.append(primary_row)
        if second and second != primary and second not in existing_query_texts:
            queries.append(
                query_row(
                    second,
                    infer_program_query_goal(source_intent),
                    "mirror",
                    "program_secondary_query",
                    "program_secondary_query",
                    source_preference=query_source_preference_for_role(claim_family, "mirror"),
                )
            )
        elif fact_slot_query and primary_row.get("q"):
            queries.append(primary_row)
    return merge_query_rows(queries)[:2]


def merge_program_verification_questions(existing: Any, generated: List[str]) -> List[str]:
    existing_questions = compact_term_list(existing if isinstance(existing, list) else [], 3, 90)
    generated_questions = compact_term_list(generated, 3, 90)
    if not existing_questions:
        return generated_questions[:2]
    merged = dedupe_keep_order(existing_questions[:1] + generated_questions + existing_questions[1:2])
    return merged[:2]


def merge_program_queries(existing: Any, generated: List[Dict[str, str]]) -> List[Dict[str, str]]:
    existing_queries = existing if isinstance(existing, list) else []
    fact_slot_generated = [
        row for row in generated
        if isinstance(row, dict)
        and (
            normalize_text(str(row.get("origin") or "")) == "fact_slot_query"
            or normalize_text(str(row.get("query_variant_origin") or "")).startswith("fact_slot_query")
        )
    ]
    family_generated = [
        row for row in generated
        if isinstance(row, dict)
        and normalize_query_family_role(row.get("query_family_role")) in {"closure", "refute", "distinguish"}
    ]
    other_generated = [row for row in generated if row not in fact_slot_generated and row not in family_generated]
    prioritized_existing = [
        row for row in existing_queries
        if not (
            isinstance(row, dict)
            and normalize_query_family_role(row.get("query_family_role")) in {"closure", "refute", "distinguish"}
        )
    ]
    merged = merge_query_rows(list(fact_slot_generated) + list(family_generated) + list(prioritized_existing) + list(other_generated))
    if merged:
        return merged[:2]
    return generated[:2]


def apply_program_to_source_intent(source_intent: Dict[str, Any], program: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(source_intent)
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    source_strategy = out.get("source_strategy") if isinstance(out.get("source_strategy"), dict) else {}
    page_intent = out.get("page_intent") if isinstance(out.get("page_intent"), dict) else {}
    must_include = compact_term_list(direct_need.get("must_include") or [], 6, 50)
    source_strategy = {
        "source_types": [str(item) for item in (source_strategy.get("source_types") or [])[:4]],
        "search_channels": [str(item) for item in (source_strategy.get("search_channels") or [])[:5]],
        "languages": [str(item) for item in (source_strategy.get("languages") or [])[:2]],
        "must_have": dedupe_keep_order(must_include + [str(item) for item in (source_strategy.get("must_have") or [])[:4]])[:6],
        "avoid_sources": [str(item) for item in (source_strategy.get("avoid_sources") or [])[:6]],
        "why": compact_claim_text(str(source_strategy.get("why") or direct_need.get("must_answer") or ""), 160),
    }
    page_intent = {
        "needed_page_type": str(page_intent.get("needed_page_type") or direct_need.get("preferred_page_type") or "general_page"),
        "must_contain": dedupe_keep_order(
            must_include + [str(item) for item in (page_intent.get("must_contain") or [])[:4]]
        )[:6],
        "avoid_page_type": [str(item) for item in (page_intent.get("avoid_page_type") or [])[:6]],
        "why": compact_claim_text(
            str(page_intent.get("why") or direct_need.get("must_answer") or ""),
            160,
        ),
    }
    out["source_strategy"] = source_strategy
    out["page_intent"] = page_intent
    out["evidence_need_program"] = program
    if not out.get("core_binding") and isinstance(decision_slots, dict):
        out["core_binding"] = {
            "subject_entity": str(decision_slots.get("subject") or ""),
            "object_entity": str(decision_slots.get("object") or ""),
            "relation_or_metric": str(decision_slots.get("metric_or_relation") or ""),
            "time_scope": str(decision_slots.get("time_scope") or ""),
        }
    return out


def finalize_claim_with_evidence_need_program(claim: Dict[str, Any], need_type: str) -> Dict[str, Any]:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    claim_text = normalize_text(str(claim.get("claim") or ""))
    evidence_mode = str(source_intent.get("evidence_mode") or "entity_fact")
    raw_program = claim.get("evidence_need_program") if isinstance(claim.get("evidence_need_program"), dict) else source_intent.get("evidence_need_program")
    program = build_evidence_need_program(
        claim_text,
        str(claim.get("centrality") or "supporting"),
        str(claim.get("checkability") or "checkable"),
        source_intent,
        need_type,
        raw_program if isinstance(raw_program, dict) else None,
    )
    updated = dict(claim)
    updated_intent = apply_program_to_source_intent(source_intent, program)
    updated["source_intent"] = updated_intent
    updated["evidence_need_program"] = program
    updated["claim_budget_bucket"] = claim_budget_bucket(
        claim_text,
        updated_intent,
        str(claim.get("checkability") or "checkable"),
    )
    updated["required_slot_profile"] = required_slot_profile_for_mode(
        evidence_mode,
        claim_text,
        updated_intent,
        (program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}),
    )
    updated["program_repair_used"] = normalize_bool(claim.get("program_repair_used"), False)
    updated["verification_questions"] = merge_program_verification_questions(
        claim.get("verification_questions"),
        build_program_verification_questions(updated, program),
    )
    updated["query_planner_hint"] = build_claim_query_planner_hint(updated, program, need_type)
    updated["queries"] = merge_program_queries(
        claim.get("queries"),
        build_program_queries(updated, program),
    )
    updated["evidence_task_card"] = build_evidence_task_card(
        claim_text,
        str(updated.get("centrality") or "supporting"),
        updated_intent,
        updated["verification_questions"],
        updated["queries"],
    )
    return updated


def refresh_extracted_claim_programs(extracted: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(extracted, dict):
        return extracted
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    need_type = normalize_need_type(extracted.get("need_type"))
    refreshed = [
        finalize_claim_with_evidence_need_program(claim, need_type)
        if isinstance(claim, dict) and str(claim.get("checkability") or "checkable") == "checkable"
        else claim
        for claim in claims
    ]
    updated = dict(extracted)
    updated["claims"] = refreshed
    return updated


def build_evidence_task_card(
    claim_text: str,
    centrality: str,
    source_intent: Dict[str, Any],
    verification_questions: List[str],
    queries: List[Dict[str, str]],
) -> Dict[str, Any]:
    evidence_mode = str(source_intent.get("evidence_mode") or "entity_fact")
    evidence_target = str(source_intent.get("evidence_target") or "general")
    must_have = source_intent.get("source_strategy", {}).get("must_have") if isinstance(source_intent.get("source_strategy"), dict) else []
    if not isinstance(must_have, list):
        must_have = []
    route_meta = source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}
    route_terms = [str(route_meta.get(key) or "").strip() for key in ("origin", "destination", "route_area")]
    core_binding = source_intent.get("core_binding") if isinstance(source_intent.get("core_binding"), dict) else {}
    metric_slots = source_intent.get("metric_slots") if isinstance(source_intent.get("metric_slots"), dict) else {}
    task_semantics = source_intent.get("task_semantics") if isinstance(source_intent.get("task_semantics"), dict) else {}
    typed_extension = source_intent.get("typed_extension") if isinstance(source_intent.get("typed_extension"), dict) else {}
    binding_terms = [
        str(core_binding.get("subject_entity") or metric_slots.get("subject_entity") or "").strip(),
        str(core_binding.get("object_entity") or "").strip(),
        str(core_binding.get("relation_or_metric") or metric_slots.get("metric_name") or "").strip(),
        str(core_binding.get("time_scope") or metric_slots.get("time_scope") or "").strip(),
    ]
    route_extension = typed_extension.get("route") if isinstance(typed_extension.get("route"), dict) else {}
    confusion_terms = task_semantics.get("must_not_confuse") if isinstance(task_semantics.get("must_not_confuse"), list) else []
    retrieval_focus = task_semantics.get("retrieval_focus") if isinstance(task_semantics.get("retrieval_focus"), list) else []
    evidence_need_program = (
        source_intent.get("evidence_need_program")
        if isinstance(source_intent.get("evidence_need_program"), dict)
        else {}
    )
    direct_need = evidence_need_program.get("direct_evidence_need") if isinstance(evidence_need_program.get("direct_evidence_need"), dict) else {}
    decision_slots = evidence_need_program.get("decision_slots") if isinstance(evidence_need_program.get("decision_slots"), dict) else {}
    anchor_terms_by_bucket = decision_slots.get("anchor_terms_by_bucket") if isinstance(decision_slots.get("anchor_terms_by_bucket"), dict) else {}
    program_must_include = direct_need.get("must_include") if isinstance(direct_need.get("must_include"), list) else []
    program_fact_need = compact_claim_text(str(evidence_need_program.get("normalized_assertion") or claim_text), 120)
    program_direct_need = compact_claim_text(str(direct_need.get("must_answer") or ""), 120)
    program_query_focus = [
        compact_claim_text(str(item.get("q") or item.get("goal") or ""), 50)
        for item in queries[:2]
        if isinstance(item, dict) and normalize_text(str(item.get("q") or item.get("goal") or ""))
    ]
    program_verification_focus = compact_term_list(
        verification_questions[:2]
        + [str(term) for term in retrieval_focus if str(term).strip()]
        + [str(term) for bucket in anchor_terms_by_bucket.values() if isinstance(bucket, list) for term in bucket[:1]],
        4,
        70,
    )
    priority_score = evidence_task_priority_score(claim_text, centrality, source_intent)
    return {
        "fact_need": program_fact_need or compact_claim_text(claim_text, 120),
        "priority_score": priority_score,
        "priority_label": evidence_task_priority_label(priority_score),
        "must_match": dedupe_keep_order(
            [str(term) for term in program_must_include[:4] if str(term or "").strip()]
            + [str(term) for term in must_have[:4] if str(term or "").strip()]
            + [term for term in route_terms if term]
            + [term for term in binding_terms if term]
            + [str(route_extension.get("intermediate_place") or "").strip()]
        )[:8],
        "direct_answer_need": program_direct_need or direct_answer_need_text(evidence_mode, evidence_target),
        "evidence_shape": str(source_intent.get("evidence_shape") or "general_evidence_page"),
        "verification_focus": program_verification_focus,
        "query_focus": program_query_focus or [compact_claim_text(str(item.get("goal") or "general_verify"), 40) for item in queries[:2]],
        "must_not_confuse": [compact_claim_text(str(term), 70) for term in confusion_terms[:4] if str(term).strip()],
        "task_semantics": task_semantics,
    }


def should_run_llm_evidence_refiner(claim: Dict[str, Any], summary: Dict[str, Any]) -> bool:
    if CLIENT is None:
        return False
    claim_family = infer_claim_family(claim, summary)
    if claim_family not in LLM_EVIDENCE_REFINER_FAMILIES:
        return False
    point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
    block_reason = normalize_text(str(point_conversion.get("block_reason") or ""))
    gap_reason = normalize_text(str(point_conversion.get("direct_candidate_gap_reason") or ""))
    stage = str(point_conversion.get("stage") or "")
    candidates = [item for item in (summary.get("evidence_sentence_candidates") or []) if isinstance(item, dict)]
    if not candidates:
        return False
    if block_reason in LLM_EVIDENCE_REFINER_BLOCK_REASONS:
        return True
    if gap_reason in {"date_role_mismatch", "result_granularity_mismatch", "commentary_only"}:
        return True
    return stage in {"direct_not_converted", "no_direct"}


def build_evidence_refiner_prompt(claim: Dict[str, Any], summary: Dict[str, Any]) -> str:
    evidence_need_program = summary.get("evidence_need_program") if isinstance(summary.get("evidence_need_program"), dict) else {}
    decision_slots = evidence_need_program.get("decision_slots") if isinstance(evidence_need_program.get("decision_slots"), dict) else {}
    point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
    candidates = [
        {
            "sentence": str(candidate.get("sentence") or ""),
            "title": str(candidate.get("title") or ""),
            "candidate_slot_match": str(candidate.get("candidate_slot_match") or ""),
            "candidate_profile": str(candidate.get("sentence_candidate_profile") or ""),
            "directness_rank": int(candidate.get("candidate_directness_rank") or 0),
        }
        for candidate in (summary.get("evidence_sentence_candidates") or [])
        if isinstance(candidate, dict)
    ][:2]
    payload = {
        "claim": str(claim.get("claim") or ""),
        "claim_family": infer_claim_family(claim, summary),
        "decision_slots": {
            "subject": str(decision_slots.get("subject") or ""),
            "object": str(decision_slots.get("object") or ""),
            "time_scope": str(decision_slots.get("time_scope") or ""),
            "metric_or_relation": str(decision_slots.get("metric_or_relation") or ""),
            "status_or_result": str(decision_slots.get("status_or_result") or ""),
        },
        "current_point_block_reason": str(point_conversion.get("block_reason") or ""),
        "current_direct_gap_reason": str(point_conversion.get("direct_candidate_gap_reason") or ""),
        "top_candidates": candidates,
    }
    return json.dumps(payload, ensure_ascii=False)


def normalize_evidence_refiner_card(raw_obj: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw_obj = raw_obj if isinstance(raw_obj, dict) else {}
    directness = normalize_text(str(raw_obj.get("evidence_directness") or ""))
    if directness not in {"direct", "slot_hit_but_indirect", "numeric_or_date_reference_only", "background_commentary"}:
        directness = "slot_hit_but_indirect"
    allowed_confusions = {
        "date_role_mismatch",
        "result_granularity_mismatch",
        "not_same_fact_slot",
        "candidate_not_direct",
        "commentary_only",
    }
    possible_confusions = [
        normalize_text(str(item))
        for item in (raw_obj.get("possible_confusions") or [])
        if normalize_text(str(item)) in allowed_confusions
    ] if isinstance(raw_obj.get("possible_confusions"), list) else []
    return {
        "subject": compact_claim_text(str(raw_obj.get("subject") or ""), 48),
        "time_scope": compact_claim_text(str(raw_obj.get("time_scope") or ""), 48),
        "metric_or_relation": compact_claim_text(str(raw_obj.get("metric_or_relation") or ""), 48),
        "status_or_result": compact_claim_text(str(raw_obj.get("status_or_result") or ""), 48),
        "date_role": compact_claim_text(str(raw_obj.get("date_role") or ""), 32),
        "result_granularity": compact_claim_text(str(raw_obj.get("result_granularity") or ""), 32),
        "evidence_directness": directness,
        "possible_confusions": dedupe_keep_order(possible_confusions)[:4],
    }


def infer_refiner_gap_reason(card: Dict[str, Any]) -> str:
    possible_confusions = set(card.get("possible_confusions") or []) if isinstance(card.get("possible_confusions"), list) else set()
    date_role = normalize_text(str(card.get("date_role") or ""))
    result_granularity = normalize_text(str(card.get("result_granularity") or ""))
    directness = normalize_text(str(card.get("evidence_directness") or ""))
    if "date_role_mismatch" in possible_confusions or re.search(r"(发布|公布|生效|报道|举办|开赛)", date_role):
        return "date_role_mismatch"
    if "result_granularity_mismatch" in possible_confusions or re.search(r"(过程|局部|单节|半场|盘中|收盘)", result_granularity):
        return "result_granularity_mismatch"
    if "not_same_fact_slot" in possible_confusions:
        return "not_same_fact_slot"
    if directness == "background_commentary" or "commentary_only" in possible_confusions:
        return "commentary_only"
    if directness == "slot_hit_but_indirect" or "candidate_not_direct" in possible_confusions:
        return "candidate_not_direct"
    return ""


def apply_llm_evidence_refiners(
    claims: List[Dict[str, Any]],
    evidence_summary: Optional[Dict[str, Any]],
    debug_bucket: Optional[Dict[str, Any]] = None,
) -> None:
    if CLIENT is None or not isinstance(evidence_summary, dict):
        return
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    if not isinstance(summaries, dict):
        return
    refiner_debug: Dict[str, Any] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id)
        if not isinstance(summary, dict) or not should_run_llm_evidence_refiner(claim, summary):
            continue
        refiner_obj, raw = llm_chat(
            SYSTEM_EVIDENCE_REFINER,
            build_evidence_refiner_prompt(claim, summary),
            retries=0,
        )
        card = normalize_evidence_refiner_card(refiner_obj)
        point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
        point_conversion["llm_evidence_refiner_used"] = True
        point_conversion["llm_evidence_refiner"] = card
        refined_gap_reason = infer_refiner_gap_reason(card)
        if refined_gap_reason:
            point_conversion["llm_refined_gap_reason"] = refined_gap_reason
            current_block_reason = normalize_text(str(point_conversion.get("block_reason") or ""))
            current_gap_reason = normalize_text(str(point_conversion.get("direct_candidate_gap_reason") or ""))
            if current_block_reason in {"", "candidate_not_direct", "related_but_not_assertive"} and refined_gap_reason in {
                "date_role_mismatch",
                "result_granularity_mismatch",
                "not_same_fact_slot",
            }:
                point_conversion["block_reason"] = refined_gap_reason
            if current_gap_reason in {"", "candidate_not_direct"} and refined_gap_reason in {
                "date_role_mismatch",
                "result_granularity_mismatch",
                "commentary_only",
            }:
                point_conversion["direct_candidate_gap_reason"] = refined_gap_reason
        summary["point_conversion"] = point_conversion
        refiner_debug[claim_id] = {
            "used": True,
            "raw": raw,
            "card": card,
            "refined_gap_reason": refined_gap_reason,
        }
    if isinstance(debug_bucket, dict):
        debug_bucket["llm_evidence_refiner"] = refiner_debug


def query_effective_role_for_claim(claim: Dict[str, Any]) -> str:
    queries = claim.get("queries") if isinstance(claim.get("queries"), list) else []
    roles = [
        normalize_query_family_role(row.get("query_family_role"))
        for row in queries
        if isinstance(row, dict)
    ]
    if not roles:
        planner_hint = claim.get("query_planner_hint") if isinstance(claim.get("query_planner_hint"), dict) else {}
        planned_roles = [
            normalize_query_family_role(item)
            for item in (planner_hint.get("query_family_plan") or [])
            if normalize_query_family_role(item) in {"closure", "refute", "distinguish", "slot", "mirror"}
        ] if isinstance(planner_hint.get("query_family_plan"), list) else []
        roles = planned_roles
    if not roles:
        return "mirror"
    if any(role in {"closure", "refute", "distinguish"} for role in roles):
        claim_family = str(
            (claim.get("query_planner_hint") or {}).get("claim_family")
            if isinstance(claim.get("query_planner_hint"), dict)
            else ""
        ) or infer_claim_family(claim, {"evidence_mode": (claim.get("source_intent") or {}).get("evidence_mode") if isinstance(claim.get("source_intent"), dict) else ""})
        ranked_roles = sorted(
            [role for role in roles if role in {"closure", "refute", "distinguish"}],
            key=lambda item: query_family_role_priority(claim_family, item),
            reverse=True,
        )
        if ranked_roles:
            return ranked_roles[0]
    if "slot" in roles:
        return "slot"
    return "mirror"


def candidate_page_utility_profile(
    claim_family: str,
    query_role: str,
    candidate: Dict[str, Any],
) -> str:
    page_type = normalize_text(str(candidate.get("page_utility_page_type") or ""))
    page_focus = normalize_text(str(candidate.get("page_utility_page_focus") or ""))
    title = normalize_text(str(candidate.get("title") or ""))
    surface = " ".join(part for part in [page_type, page_focus, title] if part)
    if claim_family in {"date_fact", "schedule_fact"} and re.search(r"(calendar|交易日历|休市|公告|notice|schedule|假期|holiday)", surface, flags=re.I):
        return "official_calendar_or_notice"
    if claim_family == "route_fact" and re.search(r"(route|路线|航线|通道|绕行|替代|alternative|corridor|bypass)", surface, flags=re.I):
        return "alternative_route_or_route_analysis"
    if claim_family == "event_result" and re.search(r"(result|score|比分|赛果|box score|战绩|交锋)", surface, flags=re.I):
        return "result_or_score_page"
    if claim_family in {"numeric_fact", "numeric_count_detail"} and re.search(r"(table|data|quote|official|统计|数据|公告|notice|合计)", surface, flags=re.I):
        return "table_or_data_page"
    if re.search(r"(landing|search|首页|搜索结果|专题|commentary|analysis|评论|解读)", surface, flags=re.I):
        return "background_or_landing_page"
    if query_role in {"closure", "refute", "distinguish"}:
        return f"{query_role}_aligned_general_page"
    return page_type or "general_page"


def candidate_page_utility_score(
    claim_family: str,
    query_role: str,
    candidate: Dict[str, Any],
) -> int:
    score = 0
    source_type = normalize_text(str(candidate.get("source_type") or ""))
    page_profile = candidate_page_utility_profile(claim_family, query_role, candidate)
    title = normalize_text(str(candidate.get("title") or ""))
    if source_type == "official":
        score += 12
    elif source_type == "news":
        score += 6
    profile_bonus = {
        "official_calendar_or_notice": 24,
        "alternative_route_or_route_analysis": 22,
        "result_or_score_page": 20,
        "table_or_data_page": 20,
        "background_or_landing_page": -12,
    }
    score += profile_bonus.get(page_profile, 8 if query_role in {"closure", "refute", "distinguish"} else 4)
    if query_role == "closure" and re.search(r"(官方|official|公告|notice|calendar|日历|合计|总数|累计)", title, flags=re.I):
        score += 6
    if query_role == "refute" and re.search(r"(alternative|并非|not|instead|绕开|替代)", title, flags=re.I):
        score += 6
    if query_role == "distinguish" and re.search(r"(发布|生效|最终|过程|开盘|收盘|盘中)", title, flags=re.I):
        score += 6
    return score


def is_pseudo_evidence_candidate(candidate: Dict[str, Any]) -> bool:
    source_type = normalize_text(str(candidate.get("source_type") or ""))
    source = normalize_text(str(candidate.get("source") or ""))
    title = normalize_text(str(candidate.get("title") or ""))
    if source_type in {"computed", "input_context"}:
        return True
    if source in {"computed", "input_context"}:
        return True
    if title in {"样本日期星期计算", "汇率数值换算线索", "用户问题主需"}:
        return True
    return False


PAGE_ROLE_FIELDS = (
    "page_role",
    "page_role_reason",
    "page_role_contract_score",
    "entry_page_follow_required",
    "evidence_page_ready",
    "generic_page_block_reason",
    "entry_follow_state",
    "entry_follow_trigger",
    "entry_follow_block_reason",
    "structured_table_best_point",
    "structured_point_contract_status",
    "structured_point_contract_score",
    "structured_point_contract_risks",
    "evidence_contract_role",
    "evidence_contract_status",
    "evidence_contract_score",
    "evidence_contract_risks",
    "page_utility_page_type",
    "page_utility_page_focus",
    "page_utility_score",
    "page_utility_label",
)


def evidence_lookup_key(url: str, title: str) -> str:
    return f"{normalize_text(str(url or '')).lower()}|{normalize_text(str(title or '')).lower()}"


def build_evidence_page_role_index(evidence_items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        key = evidence_lookup_key(str(item.get("url") or ""), str(item.get("title") or ""))
        if key.strip("|"):
            index[key] = item
        url_key = evidence_lookup_key(str(item.get("url") or ""), "")
        if url_key.strip("|"):
            index.setdefault(url_key, item)
    return index


def attach_page_role_fields(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    if not isinstance(target, dict) or not isinstance(source, dict):
        return
    for key in PAGE_ROLE_FIELDS:
        if key in source and key not in target:
            target[key] = source.get(key)


def source_item_for_point(point: Dict[str, Any], index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(point, dict):
        return {}
    key = evidence_lookup_key(str(point.get("url") or ""), str(point.get("title") or ""))
    if key in index:
        return index[key]
    url_key = evidence_lookup_key(str(point.get("url") or ""), "")
    return index.get(url_key, {})


def direct_evidence_gate_result(point: Dict[str, Any]) -> str:
    if is_pseudo_evidence_candidate(point):
        return "blocked_pseudo_evidence"
    page_role = normalize_text(str(point.get("page_role") or "")).lower()
    contract_role = normalize_text(str(point.get("evidence_contract_role") or "")).lower()
    contract_status = normalize_text(str(point.get("evidence_contract_status") or "")).lower()
    structured_status = normalize_text(str(point.get("structured_point_contract_status") or point.get("point_contract_status") or "")).lower()
    structured_risks = [
        normalize_text(str(value))
        for value in (
            point.get("structured_point_contract_risks")
            if isinstance(point.get("structured_point_contract_risks"), list)
            else point.get("point_contract_risks")
            if isinstance(point.get("point_contract_risks"), list)
            else []
        )
        if str(value)
    ]
    if structured_status == "satisfied" and not any(risk in {"point_time_scope_mismatch", "missing_binding_time_scope"} for risk in structured_risks):
        return "allowed_structured_table_point"
    if page_role == "evidence_page" and normalize_bool(point.get("evidence_page_ready"), True):
        return "allowed_evidence_page"
    if not page_role and contract_status == "satisfied" and contract_role in {"evidence_sentence_page", "structured_metric_table_page"}:
        return "allowed_contract_satisfied_legacy"
    if page_role == "entry_page":
        return "blocked_entry_page_requires_follow"
    if page_role == "generic_page":
        return "blocked_generic_page"
    if page_role == "blocked_page":
        return "blocked_access_page"
    return "blocked_no_evidence_page_contract"


def direct_evidence_gate_allows(point: Dict[str, Any]) -> bool:
    return direct_evidence_gate_result(point).startswith("allowed_")


def apply_page_role_consumption_gate(
    evidence_bundle: Optional[Dict[str, Any]],
    evidence_summary: Optional[Dict[str, Any]],
    debug_bucket: Optional[Dict[str, Any]] = None,
) -> None:
    if not isinstance(evidence_bundle, dict) or not isinstance(evidence_summary, dict):
        return
    evidence_by_claim = evidence_bundle.get("evidence_by_claim") if isinstance(evidence_bundle.get("evidence_by_claim"), dict) else {}
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    gate_debug: Dict[str, Any] = {}
    for claim_id, summary in summaries.items():
        if not isinstance(summary, dict):
            continue
        index = build_evidence_page_role_index([item for item in evidence_by_claim.get(claim_id, []) if isinstance(item, dict)])
        blocked_counts: Dict[str, int] = {}
        consumed_counts: Dict[str, int] = {}
        for bucket in ("supporting_points", "refuting_points", "uncertain_points", "evidence_sentence_candidates", "answer_candidates"):
            rows = summary.get(bucket) if isinstance(summary.get(bucket), list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                source_item = source_item_for_point(row, index)
                attach_page_role_fields(row, source_item)
                gate = direct_evidence_gate_result(row)
                row["direct_evidence_gate_result"] = gate
                row["page_role_consumed"] = direct_evidence_gate_allows(row)
                row["evidence_page_consumption_state"] = "consumed" if row["page_role_consumed"] else "diagnostic_only"
                page_role = normalize_text(str(row.get("page_role") or "unknown"))
                if row["page_role_consumed"]:
                    consumed_counts[page_role] = int(consumed_counts.get(page_role, 0) or 0) + 1
                else:
                    blocked_counts[gate] = int(blocked_counts.get(gate, 0) or 0) + 1
                    if page_role == "entry_page":
                        row["entry_page_not_consumed_reason"] = gate
                    elif page_role == "generic_page":
                        row["generic_page_not_consumed_reason"] = gate
                    if row.get("direct_answer") == "direct":
                        row["direct_answer_before_page_role_gate"] = "direct"
                        row["direct_answer"] = "partial" if page_role == "entry_page" else "related_only"
        point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
        top_candidate = (summary.get("evidence_sentence_candidates") or [{}])[0] if isinstance(summary.get("evidence_sentence_candidates"), list) and summary.get("evidence_sentence_candidates") else {}
        if isinstance(top_candidate, dict):
            point_conversion["direct_evidence_gate_result"] = str(top_candidate.get("direct_evidence_gate_result") or "")
            point_conversion["page_role_consumed"] = bool(top_candidate.get("page_role_consumed"))
            point_conversion["evidence_page_consumption_state"] = str(top_candidate.get("evidence_page_consumption_state") or "")
            point_conversion["page_role"] = str(top_candidate.get("page_role") or "")
            point_conversion["entry_page_not_consumed_reason"] = str(top_candidate.get("entry_page_not_consumed_reason") or "")
            point_conversion["generic_page_not_consumed_reason"] = str(top_candidate.get("generic_page_not_consumed_reason") or "")
            summary["point_conversion"] = point_conversion
        gate_debug[str(claim_id)] = {
            "consumed": consumed_counts,
            "blocked": blocked_counts,
        }
    if isinstance(debug_bucket, dict):
        debug_bucket["page_role_consumption_gate"] = gate_debug


def candidate_decision_useful_score(
    claim: Dict[str, Any],
    summary: Dict[str, Any],
    candidate: Dict[str, Any],
) -> int:
    claim_family = infer_claim_family(claim, summary)
    query_role = query_effective_role_for_claim(claim)
    coverage = candidate.get("candidate_slot_coverage") if isinstance(candidate.get("candidate_slot_coverage"), dict) else {}
    slot_count = int(coverage.get("slot_count") or 0)
    directness_rank = int(candidate.get("candidate_directness_rank") or 0)
    sentence_utility_score = int(candidate.get("sentence_utility_score") or 0)
    sentence_profile = normalize_text(str(candidate.get("sentence_candidate_profile") or ""))
    gap_reason = normalize_text(str(candidate.get("direct_candidate_gap_reason") or ""))
    directness = normalize_text(str(candidate.get("sentence_directness") or ""))
    page_profile = candidate_page_utility_profile(claim_family, query_role, candidate)
    subject_slot_hit = bool(coverage.get("subject"))
    time_slot_hit = bool(coverage.get("time_scope") or coverage.get("time"))
    fact_slot_hit = bool(coverage.get("metric_or_relation") or coverage.get("status_or_result"))
    score = sentence_utility_score
    score += min(20, directness_rank * 4)
    score += min(16, slot_count * 4)
    score += candidate_page_utility_score(claim_family, query_role, candidate)
    if subject_slot_hit and (time_slot_hit or fact_slot_hit):
        score += 6
    if page_profile in {
        "official_calendar_or_notice",
        "alternative_route_or_route_analysis",
        "result_or_score_page",
        "table_or_data_page",
    } and slot_count >= 2:
        score += 6
    if sentence_profile == "direct_candidate":
        score += 20
    elif sentence_profile == "slot_hit_but_indirect":
        score += 10
    elif sentence_profile in {"numeric_reference_only", "date_reference_only"}:
        score += 2
    elif sentence_profile == "background_commentary":
        score -= 14
    if directness == "direct":
        score += 8
    elif directness == "partial":
        score += 2
    if gap_reason in {"commentary_only", "background_commentary_topranked"}:
        score -= 10
    elif gap_reason in {"numeric_reference_only", "date_reference_only"}:
        score -= 4
    elif gap_reason in {"date_role_mismatch", "result_granularity_mismatch", "opening_slot_mismatch"}:
        score += 2
    elif gap_reason in {"candidate_not_direct", "related_but_not_assertive"} and slot_count >= 2 and directness_rank >= 2:
        score += 4
    if is_pseudo_evidence_candidate(candidate):
        score -= 40
    gate = direct_evidence_gate_result(candidate)
    candidate["direct_evidence_gate_result"] = gate
    candidate["page_role_consumed"] = direct_evidence_gate_allows(candidate)
    if not candidate["page_role_consumed"]:
        score -= 34
        page_role = normalize_text(str(candidate.get("page_role") or ""))
        if page_role == "entry_page":
            candidate["entry_page_not_consumed_reason"] = gate
        elif page_role == "generic_page":
            candidate["generic_page_not_consumed_reason"] = gate
    return score


def decision_useful_hit_for_candidate(candidate: Dict[str, Any]) -> bool:
    if is_pseudo_evidence_candidate(candidate):
        return False
    if not direct_evidence_gate_allows(candidate):
        return False
    utility = int(candidate.get("candidate_utility_score") or 0)
    slot_count = int(((candidate.get("candidate_slot_coverage") or {}) if isinstance(candidate.get("candidate_slot_coverage"), dict) else {}).get("slot_count") or 0)
    profile = normalize_text(str(candidate.get("sentence_candidate_profile") or ""))
    page_profile = normalize_text(str(candidate.get("page_utility_profile") or ""))
    if utility >= 36 and slot_count >= 2 and profile != "background_commentary":
        return True
    return (
        utility >= 34
        and slot_count >= 2
        and profile not in {"background_commentary", ""}
        and page_profile in {
            "official_calendar_or_notice",
            "alternative_route_or_route_analysis",
            "result_or_score_page",
            "table_or_data_page",
        }
    )


def apply_decision_useful_candidate_rerank(
    claims: List[Dict[str, Any]],
    evidence_bundle: Optional[Dict[str, Any]],
    evidence_summary: Optional[Dict[str, Any]],
    debug_bucket: Optional[Dict[str, Any]] = None,
) -> None:
    if not isinstance(evidence_summary, dict):
        return
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    evidence_by_claim = evidence_bundle.get("evidence_by_claim") if isinstance(evidence_bundle, dict) and isinstance(evidence_bundle.get("evidence_by_claim"), dict) else {}
    rerank_debug: Dict[str, Any] = {}
    if not isinstance(summaries, dict):
        return
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id)
        if not isinstance(summary, dict):
            continue
        candidates = [item for item in (summary.get("evidence_sentence_candidates") or []) if isinstance(item, dict)]
        if not candidates:
            continue
        query_role = query_effective_role_for_claim(claim)
        claim_family = infer_claim_family(claim, summary)
        for candidate in candidates:
            page_profile = candidate_page_utility_profile(claim_family, query_role, candidate)
            page_score = candidate_page_utility_score(claim_family, query_role, candidate)
            candidate_score = candidate_decision_useful_score(claim, summary, candidate)
            candidate["page_utility_profile"] = page_profile
            candidate["page_utility_score"] = page_score
            candidate["candidate_utility_score"] = candidate_score
            candidate["is_pseudo_evidence"] = is_pseudo_evidence_candidate(candidate)
            candidate["decision_useful_hit"] = decision_useful_hit_for_candidate({"candidate_utility_score": candidate_score, **candidate})
        candidates.sort(
            key=lambda item: (
                int(item.get("candidate_utility_score") or 0),
                int(item.get("candidate_directness_rank") or 0),
                int(((item.get("candidate_slot_coverage") or {}) if isinstance(item.get("candidate_slot_coverage"), dict) else {}).get("slot_count") or 0),
                int(item.get("sentence_utility_score") or 0),
            ),
            reverse=True,
        )
        summary["evidence_sentence_candidates"] = candidates
        top_evidence_candidate = next(
            (item for item in candidates if isinstance(item, dict) and not normalize_bool(item.get("is_pseudo_evidence"), False)),
            {},
        )
        summary["top_evidence_candidate"] = top_evidence_candidate
        evidence_mode = str(summary.get("evidence_mode") or "")
        coverage = claim_coverage(claim_id, evidence_mode, evidence_by_claim.get(claim_id, []), summary)
        summary["coverage"] = coverage
        summary["point_conversion"] = point_conversion_diagnostics(summary, coverage)
        summary["evidence_events"] = evidence_event_summary(summary, coverage)
        top_candidate = candidates[0] if candidates else {}
        point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
        point_conversion["query_effective_role"] = query_role
        point_conversion["page_utility_score"] = int(top_candidate.get("page_utility_score") or 0)
        point_conversion["page_utility_profile"] = str(top_candidate.get("page_utility_profile") or "")
        point_conversion["decision_useful_hit"] = bool(top_candidate.get("decision_useful_hit"))
        point_conversion["candidate_utility_score"] = int(top_candidate.get("candidate_utility_score") or 0)
        point_conversion["page_role"] = str(top_candidate.get("page_role") or "")
        point_conversion["page_role_consumed"] = bool(top_candidate.get("page_role_consumed"))
        point_conversion["direct_evidence_gate_result"] = str(top_candidate.get("direct_evidence_gate_result") or "")
        point_conversion["evidence_page_consumption_state"] = str(top_candidate.get("evidence_page_consumption_state") or "")
        point_conversion["entry_page_not_consumed_reason"] = str(top_candidate.get("entry_page_not_consumed_reason") or "")
        point_conversion["generic_page_not_consumed_reason"] = str(top_candidate.get("generic_page_not_consumed_reason") or "")
        point_conversion["top_candidate_is_pseudo"] = bool(top_candidate.get("is_pseudo_evidence"))
        point_conversion["top_evidence_candidate_title"] = str(top_evidence_candidate.get("title") or "")
        point_conversion["top_evidence_candidate_profile"] = str(top_evidence_candidate.get("sentence_candidate_profile") or "")
        point_conversion["slot_contract_state"] = str(top_candidate.get("slot_contract_state") or "")
        point_conversion["slot_coverage"] = top_candidate.get("slot_coverage") if isinstance(top_candidate.get("slot_coverage"), dict) else {}
        point_conversion["slot_missing"] = top_candidate.get("slot_missing") if isinstance(top_candidate.get("slot_missing"), list) else []
        point_conversion["slot_mismatch"] = top_candidate.get("slot_mismatch") if isinstance(top_candidate.get("slot_mismatch"), list) else []
        point_conversion["slot_conflict"] = top_candidate.get("slot_conflict") if isinstance(top_candidate.get("slot_conflict"), list) else []
        point_conversion["same_slot_ready"] = bool(top_candidate.get("same_slot_ready"))
        point_conversion["refute_slot_ready"] = bool(top_candidate.get("refute_slot_ready"))
        point_conversion["candidate_conflict_profile"] = (
            top_candidate.get("candidate_conflict_profile")
            if isinstance(top_candidate.get("candidate_conflict_profile"), dict)
            else {}
        )
        point_conversion["conflict_type"] = str(top_candidate.get("conflict_type") or "")
        point_conversion["conflict_strength"] = str(top_candidate.get("conflict_strength") or "")
        point_conversion["conflict_slot"] = str(top_candidate.get("conflict_slot") or "")
        point_conversion["claim_value"] = top_candidate.get("claim_value")
        point_conversion["evidence_value"] = top_candidate.get("evidence_value")
        point_conversion["same_slot_conflict_ready"] = bool(top_candidate.get("same_slot_conflict_ready"))
        summary["point_conversion"] = point_conversion
        rerank_debug[claim_id] = {
            "query_effective_role": query_role,
            "claim_family": claim_family,
            "top_candidate_score": int(top_candidate.get("candidate_utility_score") or 0),
            "top_candidate_profile": str(top_candidate.get("sentence_candidate_profile") or ""),
            "top_page_profile": str(top_candidate.get("page_utility_profile") or ""),
            "top_page_role": str(top_candidate.get("page_role") or ""),
            "top_direct_evidence_gate_result": str(top_candidate.get("direct_evidence_gate_result") or ""),
            "top_candidate_is_pseudo": bool(top_candidate.get("is_pseudo_evidence")),
            "top_evidence_candidate_title": str(top_evidence_candidate.get("title") or ""),
            "top_slot_contract_state": str(top_candidate.get("slot_contract_state") or ""),
            "top_slot_missing": top_candidate.get("slot_missing") if isinstance(top_candidate.get("slot_missing"), list) else [],
            "top_slot_mismatch": top_candidate.get("slot_mismatch") if isinstance(top_candidate.get("slot_mismatch"), list) else [],
            "top_candidate_conflict_profile": (
                top_candidate.get("candidate_conflict_profile")
                if isinstance(top_candidate.get("candidate_conflict_profile"), dict)
                else {}
            ),
            "top_conflict_type": str(top_candidate.get("conflict_type") or ""),
            "top_conflict_strength": str(top_candidate.get("conflict_strength") or ""),
            "top_conflict_slot": str(top_candidate.get("conflict_slot") or ""),
            "top_same_slot_conflict_ready": bool(top_candidate.get("same_slot_conflict_ready")),
        }
    if isinstance(debug_bucket, dict):
        debug_bucket["decision_useful_rerank"] = rerank_debug


def infer_slot_review_outcome(summary: Dict[str, Any]) -> str:
    point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
    comparability_profile = summary.get("comparability_profile") if isinstance(summary.get("comparability_profile"), dict) else {}
    block_reason = normalize_text(str(point_conversion.get("block_reason") or "")) or normalize_text(str(point_conversion.get("llm_refined_gap_reason") or "")) or normalize_text(str(point_conversion.get("direct_candidate_gap_reason") or ""))
    candidate_score = int(point_conversion.get("candidate_utility_score") or 0)
    slot_coverage = point_conversion.get("candidate_slot_coverage") if isinstance(point_conversion.get("candidate_slot_coverage"), dict) else {}
    slot_count = int(slot_coverage.get("slot_count") or 0)
    candidate_sentence_count = int(point_conversion.get("candidate_sentence_count") or 0)
    partial_count = int(point_conversion.get("partial_count") or 0)
    stage = normalize_text(str(point_conversion.get("stage") or ""))
    page_profile = normalize_text(str(point_conversion.get("page_utility_profile") or ""))
    direct_gate = normalize_text(str(point_conversion.get("direct_evidence_gate_result") or ""))
    page_role = normalize_text(str(point_conversion.get("page_role") or ""))
    page_role_consumed = normalize_bool(point_conversion.get("page_role_consumed"), False)
    directness_rank = int(point_conversion.get("candidate_directness_rank") or 0)
    decision_useful_hit = bool(point_conversion.get("decision_useful_hit"))
    top_candidate_is_pseudo = normalize_bool(point_conversion.get("top_candidate_is_pseudo"), False)
    top_evidence_candidate = summary.get("top_evidence_candidate") if isinstance(summary.get("top_evidence_candidate"), dict) else {}
    has_real_evidence_candidate = bool(top_evidence_candidate) and not is_pseudo_evidence_candidate(top_evidence_candidate)
    strong_page_profile = page_profile in {
        "official_calendar_or_notice",
        "alternative_route_or_route_analysis",
        "result_or_score_page",
        "table_or_data_page",
    }
    comparable_direct_support_count = int(comparability_profile.get("comparable_direct_support_count") or 0)
    comparable_direct_refute_count = int(comparability_profile.get("comparable_direct_refute_count") or 0)
    if comparable_direct_support_count > 0 or comparable_direct_refute_count > 0:
        return "stable_direct_point"
    if direct_gate.startswith("blocked_") or (page_role in {"entry_page", "generic_page", "blocked_page"} and not page_role_consumed):
        if page_role == "entry_page":
            return "same_slot_review_blocked:entry_page_requires_follow"
        if page_role == "generic_page":
            return "same_slot_review_blocked:generic_page_not_decidable"
        if page_role == "blocked_page":
            return "same_slot_review_blocked:access_blocked_page"
        return f"same_slot_review_blocked:{direct_gate or 'page_role_gate_blocked'}"
    if candidate_score >= 36 and slot_count >= 2 and block_reason in {
        "not_same_fact_slot",
        "date_role_mismatch",
        "result_granularity_mismatch",
        "numeric_not_normalizable",
    }:
        return f"same_slot_review_blocked:{block_reason}"
    if candidate_score >= 30 and slot_count >= 2 and block_reason in {"candidate_not_direct", "related_but_not_assertive"}:
        if strong_page_profile or directness_rank >= 3 or decision_useful_hit:
            return f"same_slot_review_blocked:{block_reason}"
    if candidate_score >= 28 and block_reason in {"candidate_not_direct", "related_but_not_assertive"}:
        return "same_slot_review_not_direct"
    if candidate_score >= 34 and slot_count >= 2 and stage in {"direct_to_uncertain_only", "no_direct_candidate"}:
        if not top_candidate_is_pseudo and (directness_rank >= 3 or decision_useful_hit or partial_count > 0):
            return "same_slot_review_not_direct"
    if (
        candidate_score >= 32
        and candidate_sentence_count > 0
        and slot_count >= 2
        and block_reason in {
            "",
            "candidate_not_direct",
            "related_but_not_assertive",
            "not_same_fact_slot",
            "date_role_mismatch",
            "result_granularity_mismatch",
        }
        and has_real_evidence_candidate
        and not top_candidate_is_pseudo
        and (strong_page_profile or decision_useful_hit or directness_rank >= 3 or partial_count > 0)
    ):
        return "kept_page_candidate_progress"
    if candidate_sentence_count > 0 or partial_count > 0:
        return "weak_candidate_retained"
    if int(summary.get("answer_candidate_total") or 0) > 0:
        return "weak_candidate_retained"
    return "unresolved"


def infer_point_consumption_state(summary: Dict[str, Any], slot_review_outcome: str) -> str:
    if slot_review_outcome == "stable_direct_point":
        return "stable_direct_point"
    if slot_review_outcome == "kept_page_candidate_progress":
        return "candidate_progress_from_kept_page"
    if slot_review_outcome.startswith("same_slot_review_blocked") or slot_review_outcome == "same_slot_review_not_direct":
        return "same_slot_reviewed_but_blocked"
    if slot_review_outcome == "weak_candidate_retained":
        return "weak_candidate"
    return "unresolved"


def apply_decision_useful_consumption_state(
    claims: List[Dict[str, Any]],
    evidence_summary: Optional[Dict[str, Any]],
) -> None:
    if not isinstance(evidence_summary, dict):
        return
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    if not isinstance(summaries, dict):
        return
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id)
        if not isinstance(summary, dict):
            continue
        point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
        llm_used = normalize_bool(point_conversion.get("llm_evidence_refiner_used"), False)
        refined_gap = normalize_text(str(point_conversion.get("llm_refined_gap_reason") or ""))
        current_block = normalize_text(str(point_conversion.get("block_reason") or ""))
        current_gap = normalize_text(str(point_conversion.get("direct_candidate_gap_reason") or ""))
        point_conversion["refiner_consumed"] = bool(
            llm_used and refined_gap and refined_gap in {current_block, current_gap}
        )
        slot_review_outcome = infer_slot_review_outcome(summary)
        point_conversion["slot_review_outcome"] = slot_review_outcome
        point_conversion["point_consumption_state"] = infer_point_consumption_state(summary, slot_review_outcome)
        point_conversion["evidence_consumed_from_kept_page"] = bool(
            point_conversion.get("point_consumption_state") == "candidate_progress_from_kept_page"
        )
        summary["point_conversion"] = point_conversion


def claim_budget_priority(claim: Dict[str, Any]) -> Tuple[int, int, int]:
    text = str(claim.get("claim") or "")
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
    mode = str(source_intent.get("evidence_mode") or "")
    risk_type = str(source_intent.get("risk_type") or "")
    assertion = str(source_intent.get("assertion_strength") or "")
    structured = 1 if has_structured_detail(text, source_intent) else 0
    high_risk = 1 if mode in HIGH_RISK_SUPPORTING_MODES or risk_type in HIGH_RISK_TYPES else 0
    strong = 1 if assertion == "high" else 0
    has_queries = 1 if claim.get("queries") else 0
    priority_score = int(task_card.get("priority_score") or 0)
    bucket = str(claim.get("claim_budget_bucket") or claim_budget_bucket(text, source_intent, str(claim.get("checkability") or "checkable")))
    bucket_bonus = {
        "direct_observable": 12,
        "structured_detail": 10,
        "interpretive_explanation": 5,
        "background_context": 0,
    }.get(bucket, 0)
    return (priority_score + bucket_bonus, high_risk + structured + strong, structured + has_queries + len(text))


KEY_EVIDENCE_BUDGET_MODES = {"numeric_fact", "date_fact", "schedule_fact", "route_fact", "event_result"}


def claim_budget_priority_label(claim: Dict[str, Any]) -> str:
    if not isinstance(claim, dict):
        return "unknown"
    centrality = str(claim.get("centrality") or "supporting")
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    mechanism_type = str(source_intent.get("mechanism_type") or "")
    priority_label = str(task_card.get("priority_label") or "normal")
    risk_type = str(source_intent.get("risk_type") or "")
    bucket = str(claim.get("claim_budget_bucket") or "")
    critical_fact_like = (
        mode in KEY_EVIDENCE_BUDGET_MODES
        or target in {"market_calendar", "route_relation", "match_result", "current_status", "withdrawal_status", "prize_amount"}
        or mechanism_type in {"structured_numeric_authority", "date_authority", "event_result_page", "current_status_update"}
    )
    if centrality == "core":
        if critical_fact_like or priority_label in {"critical", "high"}:
            return "core_critical"
        return "core_normal"
    if priority_label in {"critical", "high"} or risk_type in HIGH_RISK_TYPES or bucket == "structured_detail":
        return "supporting_high_risk"
    if centrality == "peripheral":
        return "peripheral_low"
    return "supporting_normal"


def annotate_claim_budget_metadata(claims: List[Dict[str, Any]], retrieval_budget: Dict[str, Any]) -> None:
    if not isinstance(retrieval_budget, dict):
        return
    priority_map = retrieval_budget.get("claim_budget_priority") if isinstance(retrieval_budget.get("claim_budget_priority"), dict) else {}
    reserved_ids = {
        str(claim_id)
        for claim_id in (retrieval_budget.get("core_claim_budget_reserved") or [])
        if str(claim_id)
    } if isinstance(retrieval_budget.get("core_claim_budget_reserved"), list) else set()
    deprioritized_ids = {
        str(claim_id)
        for claim_id in (retrieval_budget.get("supporting_claim_deprioritized") or [])
        if str(claim_id)
    } if isinstance(retrieval_budget.get("supporting_claim_deprioritized"), list) else set()
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        claim["_claim_budget_priority"] = str(priority_map.get(claim_id) or claim_budget_priority_label(claim))
        claim["_core_claim_budget_reserved"] = claim_id in reserved_ids
        claim["_supporting_claim_deprioritized"] = claim_id in deprioritized_ids


def select_claims_for_budget(claims: List[Dict[str, Any]], max_claims: int, user_need: str = "") -> List[Dict[str, Any]]:
    if not claims:
        return []
    max_claims = max(1, max_claims)
    core = [claim for claim in claims if str(claim.get("centrality") or "") == "core"]
    supporting = [claim for claim in claims if str(claim.get("centrality") or "") == "supporting"]
    peripheral = [claim for claim in claims if str(claim.get("centrality") or "") == "peripheral"]

    selected_ids = set()
    selected: List[Dict[str, Any]] = []

    def add_from(candidates: List[Dict[str, Any]], limit: int) -> None:
        for claim in sorted(candidates, key=claim_budget_priority, reverse=True):
            claim_id = str(claim.get("claim_id") or claim.get("id") or id(claim))
            if claim_id in selected_ids or len(selected) >= max_claims or limit <= 0:
                continue
            selected.append(claim)
            selected_ids.add(claim_id)
            limit -= 1

    core_limit = 2 if user_need_allows_two_core_claims(user_need) else 1
    core = [claim for claim in core if str(claim.get("claim_budget_bucket") or "") != "background_context"]
    add_from(core, core_limit)
    high_risk_supporting = [
        claim
        for claim in supporting
        if str(claim.get("claim_budget_bucket") or "") != "background_context"
        and (
            claim_budget_priority(claim)[0] > 0
        or str((claim.get("source_intent") or {}).get("risk_type") or "") in HIGH_RISK_TYPES
        )
    ]
    add_from(high_risk_supporting, 2)
    structured_peripheral = [
        claim
        for claim in peripheral
        if has_structured_detail(str(claim.get("claim") or ""), claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {})
    ]
    add_from(structured_peripheral, max_claims - len(selected))

    if len(selected) < min(max_claims, len(claims)):
        remaining = [
            claim
            for claim in claims
            if str(claim.get("claim_id") or claim.get("id") or id(claim)) not in selected_ids
            and str(claim.get("centrality") or "") != "peripheral"
            and str(claim.get("claim_budget_bucket") or "") != "background_context"
        ]
        add_from(remaining, max_claims - len(selected))
    return selected or claims[:max_claims]


# 13. Extract 结果归一化：把模型输出整理成稳定 schema，保护下游流程。
def normalize_extracted_plan(extracted: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(extracted, dict):
        return {"user_need": "", "need_type": "general_fact", "claims": []}
    claims = extracted.get("claims")
    normalized_claims: List[Dict[str, Any]] = []
    if isinstance(claims, list):
        raw_limit = max(MAX_CLAIMS, 8)
        for index, raw_claim in enumerate(claims[:raw_limit], 1):
            if not isinstance(raw_claim, dict):
                continue
            claim_text = normalize_text(str(raw_claim.get("claim") or ""))
            if not claim_text:
                continue
            source_intent = raw_claim.get("source_intent") if isinstance(raw_claim.get("source_intent"), dict) else {}
            preferred_source_types = source_intent.get("preferred_source_types")
            if not isinstance(preferred_source_types, list):
                preferred_source_types = []
            preferred_domains = source_intent.get("preferred_domains")
            if not isinstance(preferred_domains, list):
                preferred_domains = []
            source_strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
            strategy_source_types = source_strategy.get("source_types")
            if not isinstance(strategy_source_types, list):
                strategy_source_types = []
            strategy_channels = source_strategy.get("search_channels")
            if not isinstance(strategy_channels, list):
                strategy_channels = []
            strategy_languages = source_strategy.get("languages")
            if not isinstance(strategy_languages, list):
                strategy_languages = []
            strategy_must_have = source_strategy.get("must_have")
            if not isinstance(strategy_must_have, list):
                strategy_must_have = []
            strategy_avoid = source_strategy.get("avoid_sources")
            if not isinstance(strategy_avoid, list):
                strategy_avoid = []
            page_intent = source_intent.get("page_intent") if isinstance(source_intent.get("page_intent"), dict) else {}
            page_must_contain = page_intent.get("must_contain")
            if not isinstance(page_must_contain, list):
                page_must_contain = []
            avoid_page_type = page_intent.get("avoid_page_type")
            if not isinstance(avoid_page_type, list):
                avoid_page_type = []
            need_type = normalize_need_type(extracted.get("need_type"))
            raw_mode = str(source_intent.get("evidence_mode") or "entity_fact")
            raw_target = str(source_intent.get("evidence_target") or "")
            evidence_mode = sanitize_extract_evidence_mode(claim_text, raw_mode, need_type, raw_target)
            evidence_target = str(raw_target or infer_evidence_target(claim_text, evidence_mode, need_type))
            evidence_shape = str(source_intent.get("evidence_shape") or source_intent.get("evidence_page_shape") or "")
            risk_type = str(source_intent.get("risk_type") or "general")
            evidence_mode, evidence_target, evidence_shape = normalize_market_movement_contract(
                claim_text,
                str(raw_claim.get("centrality") or "supporting"),
                need_type,
                evidence_mode,
                evidence_target,
                evidence_shape,
                risk_type,
            )
            queries_out: List[Dict[str, str]] = []
            for raw_query in raw_claim.get("queries") or []:
                if isinstance(raw_query, str):
                    query_text = normalize_text(raw_query)
                    if query_text:
                        queries_out.append({"q": query_text, "goal": "general_verify"})
                elif isinstance(raw_query, dict):
                    query_text = normalize_text(str(raw_query.get("q") or raw_query.get("query") or ""))
                    if query_text:
                        queries_out.append(
                            {
                                "q": query_text,
                                "goal": normalize_text(str(raw_query.get("goal") or "general_verify")) or "general_verify",
                            }
                        )
                if len(queries_out) >= 3:
                    break
            verification_questions: List[str] = []
            for raw_question in raw_claim.get("verification_questions") or raw_claim.get("questions") or []:
                question_text = normalize_text(str(raw_question or ""))
                if question_text:
                    verification_questions.append(compact_claim_text(question_text, 90))
                if len(verification_questions) >= 3:
                    break
            claim_shape = "exclusive_premise" if EXCLUSIVE_PREMISE_PATTERN.search(claim_text) else str(source_intent.get("claim_shape") or "")
            if claim_shape == "exclusive_premise":
                claim_text = canonical_exclusive_premise_sentence(claim_text) or claim_text
            if claim_shape == "exclusive_premise" and not verification_questions:
                verification_questions = exclusive_premise_verification_questions(claim_text, evidence_mode)
            if claim_shape == "exclusive_premise" and not queries_out:
                queries_out = exclusive_premise_queries(claim_text, evidence_mode)
            normalized_claims.append(
                {
                    "claim_id": str(raw_claim.get("claim_id") or raw_claim.get("id") or f"c{index}"),
                    "claim": claim_text,
                    "centrality": str(raw_claim.get("centrality") or "supporting"),
                    "checkability": str(raw_claim.get("checkability") or "checkable"),
                    "source_intent": {
                        "preferred_source_types": [str(x) for x in preferred_source_types[:3]],
                        "preferred_domains": [str(x) for x in preferred_domains[:3]],
                        "evidence_mode": evidence_mode,
                        "evidence_target": evidence_target,
                        "evidence_shape": evidence_shape,
                        "time_sensitivity": str(source_intent.get("time_sensitivity") or "medium"),
                        "assertion_strength": str(source_intent.get("assertion_strength") or "medium"),
                        "risk_type": risk_type,
                        "claim_shape": claim_shape,
                        "stated_as_fact": normalize_bool(source_intent.get("stated_as_fact", True), True),
                        "source_strategy": {
                            "source_types": [str(x) for x in strategy_source_types[:4]],
                            "search_channels": [str(x) for x in strategy_channels[:5]],
                            "languages": [str(x) for x in strategy_languages[:2]],
                            "must_have": [str(x) for x in strategy_must_have[:6]],
                            "avoid_sources": [str(x) for x in strategy_avoid[:6]],
                            "why": compact_claim_text(str(source_strategy.get("why") or ""), 160),
                        },
                        "page_intent": {
                            "needed_page_type": str(page_intent.get("needed_page_type") or ""),
                            "must_contain": [str(x) for x in page_must_contain[:6]],
                            "avoid_page_type": [str(x) for x in avoid_page_type[:6]],
                            "why": compact_claim_text(str(page_intent.get("why") or ""), 160),
                        },
                        "route_meta": normalize_route_meta(source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}),
                        },
                    "verification_questions": verification_questions,
                    "queries": queries_out,
                    "evidence_task_card": build_evidence_task_card(
                        claim_text,
                        str(raw_claim.get("centrality") or "supporting"),
                        {
                            "evidence_mode": evidence_mode,
                            "evidence_target": evidence_target,
                            "evidence_shape": evidence_shape,
                            "source_strategy": {
                                "must_have": [str(x) for x in strategy_must_have[:6]],
                            },
                            "route_meta": normalize_route_meta(source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}),
                            "risk_type": risk_type,
                            "assertion_strength": str(source_intent.get("assertion_strength") or "medium"),
                        },
                        verification_questions,
                        queries_out,
                    ),
                    "evidence_need_program": raw_claim.get("evidence_need_program") if isinstance(raw_claim.get("evidence_need_program"), dict) else {},
                    "claim_budget_bucket": claim_budget_bucket(
                        claim_text,
                        {
                            "evidence_mode": evidence_mode,
                            "evidence_target": evidence_target,
                            "risk_type": risk_type,
                            "claim_shape": claim_shape,
                        },
                        str(raw_claim.get("checkability") or "checkable"),
                    ),
                }
            )
    normalized_claims = augment_exclusive_premise_claims(extracted, normalized_claims)
    normalized_claims = augment_mixed_detail_claims(extracted, normalized_claims)
    normalized_claims = augment_market_calendar_detail_claims(extracted, normalized_claims)
    normalized_claims = augment_sports_structured_detail_claims(extracted, normalized_claims)
    normalized_claims = dedupe_exclusive_premise_claims(normalized_claims)
    normalized_claims = dedupe_structured_detail_claims(normalized_claims)
    try:
        from centrality_calibrator import calibrate_claim_centrality

        normalized_claims, centrality_debug = calibrate_claim_centrality(extracted, normalized_claims)
    except Exception as exc:
        centrality_debug = {"error": f"centrality_calibrator_failed:{type(exc).__name__}"}
    for claim in normalized_claims:
        program = claim.get("evidence_need_program") if isinstance(claim.get("evidence_need_program"), dict) else {}
        if not isinstance(program, dict):
            program = {}
        claim["evidence_need_program"] = program
    user_need = normalize_text(str(extracted.get("user_need") or ""))
    selected_claims = select_claims_for_budget(normalized_claims, MAX_CLAIMS, user_need)
    atomic_payload = build_atomic_claims_for_extracted(extracted, selected_claims)
    normalized = {
        "user_need": user_need,
        "need_type": normalize_need_type(extracted.get("need_type")),
        "claims": selected_claims,
        "atomic_claims": atomic_payload.get("atomic_claims") or [],
        "high_risk_atomic_claims": atomic_payload.get("high_risk_atomic_claims") or [],
        "atomic_claim_route_debug": atomic_payload.get("atomic_claim_route_debug") or [],
        "centrality_calibration_debug": centrality_debug,
    }
    return refresh_extracted_claim_programs(normalized)


def should_request_detail_supplement(item: Dict[str, Any], extracted: Dict[str, Any]) -> bool:
    normalized = normalize_extracted_plan(extracted)
    triggers = semantic_audit_triggers(item, normalized, {})
    if "attached_detail_pollution" not in triggers:
        return False
    claims = normalized.get("claims") if isinstance(normalized.get("claims"), list) else []
    structured_supporting_count = 0
    for claim in claims:
        if str(claim.get("centrality") or "") != "supporting":
            continue
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        if has_structured_detail(str(claim.get("claim") or ""), source_intent):
            structured_supporting_count += 1
    if structured_supporting_count >= 2:
        return False
    answer = normalize_text(str(item.get("answer") or ""))
    return bool(re.search(r"\d|奖金|金额|比分|公里|千米|分钟|月|日|年|克朗|美元|元|%", answer))


def build_detail_supplement_prompt(item: Dict[str, Any], extracted: Dict[str, Any]) -> str:
    normalized = normalize_extracted_plan(extracted)
    compact_claims = []
    for claim in normalized.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        compact_claims.append(
            {
                "claim_id": claim.get("claim_id"),
                "claim": claim.get("claim"),
                "centrality": claim.get("centrality"),
                "evidence_mode": source_intent.get("evidence_mode"),
                "evidence_target": source_intent.get("evidence_target"),
                "evidence_shape": source_intent.get("evidence_shape"),
                "preferred_domains": source_intent.get("preferred_domains"),
            }
        )
    payload = {
        "question": item.get("question", ""),
        "answer": item.get("answer", ""),
        "need_type": normalized.get("need_type"),
        "existing_claims": compact_claims,
    }
    return (
        "请补充当前 claims 中缺失的高风险 supporting detail。\n"
        "要求：只补答案里明确写出的数值/日期/金额/比分/距离等结构化细节，不重复已有 claim。\n"
        "输入：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def merge_detail_supplement_claims(extracted: Dict[str, Any], supplement_obj: Any) -> Tuple[Dict[str, Any], int]:
    if not isinstance(extracted, dict):
        return extracted, 0
    supplement_claims = []
    if isinstance(supplement_obj, dict) and isinstance(supplement_obj.get("claims"), list):
        supplement_claims = supplement_obj.get("claims") or []
    elif isinstance(supplement_obj, list):
        supplement_claims = supplement_obj
    if not supplement_claims:
        return extracted, 0
    existing = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    seen = {
        normalize_text(str(claim.get("claim") or ""))
        for claim in existing
        if isinstance(claim, dict)
    }
    merged = list(existing)
    added = 0
    next_index = len(merged) + 1
    for raw_claim in supplement_claims:
        if not isinstance(raw_claim, dict):
            continue
        claim_text = normalize_text(str(raw_claim.get("claim") or ""))
        if not claim_text or claim_text in seen:
            continue
        claim_copy = dict(raw_claim)
        claim_copy["claim_id"] = str(raw_claim.get("claim_id") or f"sd{next_index}")
        claim_copy["centrality"] = "supporting"
        if not claim_copy.get("checkability"):
            claim_copy["checkability"] = "checkable"
        merged.append(claim_copy)
        seen.add(claim_text)
        added += 1
        next_index += 1
        if added >= 2:
            break
    out = dict(extracted)
    out["claims"] = merged
    return out, added


def maybe_attach_detail_supplement(
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    extract_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not should_request_detail_supplement(item, extracted):
        if isinstance(extract_meta, dict):
            extract_meta["detail_supplement_used"] = False
            extract_meta["detail_supplement_added"] = 0
        return extracted
    supplement_obj, _ = llm_chat(SYSTEM_DETAIL_SUPPLEMENT, build_detail_supplement_prompt(item, extracted), retries=0)
    merged, added = merge_detail_supplement_claims(extracted, supplement_obj)
    if isinstance(extract_meta, dict):
        extract_meta["detail_supplement_used"] = added > 0
        extract_meta["detail_supplement_added"] = added
    return merged


def claim_needs_program_repair(claim: Dict[str, Any]) -> bool:
    if not isinstance(claim, dict) or str(claim.get("checkability") or "checkable") != "checkable":
        return False
    claim_text = normalize_text(str(claim.get("claim") or ""))
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    program = claim.get("evidence_need_program") if isinstance(claim.get("evidence_need_program"), dict) else {}
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    normalized_assertion = normalize_text(str(program.get("normalized_assertion") or ""))
    bucket = str(claim.get("claim_budget_bucket") or claim_budget_bucket(claim_text, source_intent, str(claim.get("checkability") or "checkable")))
    missing_required_slots = infer_missing_required_slots(
        decision_slots,
        str(source_intent.get("evidence_mode") or "entity_fact"),
        claim_text,
        source_intent,
    )
    if str(source_intent.get("claim_shape") or "") == "exclusive_premise":
        return False
    stable_short_assertion = bool(
        normalized_assertion
        and len(normalized_assertion) <= 48
        and "，" not in normalized_assertion
        and not re.search(r"(因为|所以|因此|这说明|这意味着)", normalized_assertion)
    )
    has_complete_required_slots = bool(program.get("required_slot_profile")) and not bool(program.get("missing_required_slots"))
    if stable_short_assertion or has_complete_required_slots:
        return False
    mixed_long_sentence = (
        len(claim_text) >= 44
        and len(split_mixed_sentence_clauses(claim_text)) >= 2
        and INTERPRETIVE_EXPLANATION_PATTERN.search(claim_text)
        and DIRECT_OBSERVABLE_PATTERN.search(claim_text)
    )
    normalized_too_long = len(normalized_assertion) >= 72 or ("，" in normalized_assertion and len(normalized_assertion) >= 48)
    non_declarative = bool(re.search(r"(因为|所以|因此|这说明|这意味着)", normalized_assertion))
    budget_conflict = bucket == "background_context" and str(claim.get("centrality") or "") in {"core", "supporting"}
    signals = [
        bool(mixed_long_sentence),
        bool(missing_required_slots),
        bool(normalized_too_long or non_declarative),
        bool(budget_conflict),
    ]
    return sum(1 for item in signals if item) >= 2


def build_program_repair_prompt(item: Dict[str, Any], extracted: Dict[str, Any], repair_claims: List[Dict[str, Any]]) -> str:
    compact_claims: List[Dict[str, Any]] = []
    for claim in repair_claims[:2]:
        if not isinstance(claim, dict):
            continue
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        program = claim.get("evidence_need_program") if isinstance(claim.get("evidence_need_program"), dict) else {}
        claim_text = normalize_text(str(claim.get("claim") or ""))
        decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
        compact_claims.append(
            {
                "claim_id": str(claim.get("claim_id") or ""),
                "claim": str(claim.get("claim") or ""),
                "centrality": str(claim.get("centrality") or ""),
                "claim_budget_bucket": str(claim.get("claim_budget_bucket") or ""),
                "evidence_mode": str(source_intent.get("evidence_mode") or ""),
                "evidence_target": str(source_intent.get("evidence_target") or ""),
                "required_slot_profile": required_slot_profile_for_mode(
                    str(source_intent.get("evidence_mode") or "entity_fact"),
                    claim_text,
                    source_intent,
                    decision_slots,
                ),
                "current_program": {
                    "normalized_assertion": str(program.get("normalized_assertion") or ""),
                    "decision_slots": decision_slots,
                    "direct_evidence_need": program.get("direct_evidence_need", {}),
                    "false_friend_evidence": program.get("false_friend_evidence", []),
                },
            }
        )
    payload = {
        "time": str(item.get("time", "")),
        "question": str(item.get("question", "")),
        "answer": str(item.get("answer", "")),
        "user_need": str(extracted.get("user_need") or ""),
        "claims": compact_claims,
    }
    return "请修复这些 claim 的 evidence_need_program。\n输入：\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def merge_program_repair_claims(extracted: Dict[str, Any], repair_obj: Any) -> Tuple[Dict[str, Any], int]:
    claims = extracted.get("claims") if isinstance(extracted, dict) and isinstance(extracted.get("claims"), list) else []
    repair_claims = repair_obj.get("claims") if isinstance(repair_obj, dict) and isinstance(repair_obj.get("claims"), list) else []
    if not claims or not repair_claims:
        return extracted, 0
    repair_by_id = {
        str(item.get("claim_id") or ""): item
        for item in repair_claims
        if isinstance(item, dict) and str(item.get("claim_id") or "")
    }
    changed = 0
    merged: List[Dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            merged.append(claim)
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        repair_item = repair_by_id.get(claim_id)
        if not isinstance(repair_item, dict):
            merged.append(claim)
            continue
        updated = dict(claim)
        program = updated.get("evidence_need_program") if isinstance(updated.get("evidence_need_program"), dict) else {}
        program = dict(program)
        if normalize_text(str(repair_item.get("normalized_assertion") or "")):
            program["normalized_assertion"] = compact_claim_text(normalize_text(str(repair_item.get("normalized_assertion") or "")), 120)
        raw_slots = repair_item.get("decision_slots") if isinstance(repair_item.get("decision_slots"), dict) else {}
        if raw_slots:
            slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
            slots = dict(slots)
            for key in ("subject", "object", "time_scope", "metric_or_relation", "status_or_result"):
                slot_text = compact_claim_text(normalize_text(str(raw_slots.get(key) or "")), 80)
                if slot_text:
                    slots[key] = slot_text
            program["decision_slots"] = slots
        raw_direct = repair_item.get("direct_evidence_need") if isinstance(repair_item.get("direct_evidence_need"), dict) else {}
        if raw_direct:
            direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
            direct_need = dict(direct_need)
            must_answer = compact_claim_text(normalize_text(str(raw_direct.get("must_answer") or "")), 120)
            if must_answer:
                direct_need["must_answer"] = must_answer
            must_include = raw_direct.get("must_include") if isinstance(raw_direct.get("must_include"), list) else []
            if must_include:
                direct_need["must_include"] = compact_term_list(must_include, 6, 50)
            program["direct_evidence_need"] = direct_need
        false_friends = repair_item.get("false_friend_evidence") if isinstance(repair_item.get("false_friend_evidence"), list) else []
        if false_friends:
            program["false_friend_evidence"] = compact_term_list(false_friends, 4, 90)
        updated["evidence_need_program"] = program
        updated["program_repair_used"] = True
        merged.append(updated)
        changed += 1
    out = dict(extracted)
    out["claims"] = merged
    return refresh_extracted_claim_programs(out), changed


def maybe_apply_program_repair(
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    extract_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    claims = extracted.get("claims") if isinstance(extracted, dict) and isinstance(extracted.get("claims"), list) else []
    repair_claims = [claim for claim in claims if claim_needs_program_repair(claim)]
    repair_claims = repair_claims[:2]
    if not repair_claims:
        if isinstance(extract_meta, dict):
            extract_meta["program_repair_used"] = False
            extract_meta["program_repair_changed"] = 0
            extract_meta["program_repair_candidate_ids"] = []
            extract_meta["program_repair_skipped_reason"] = "no_claims_met_hard_combo_trigger"
        return extracted
    repair_obj, _ = llm_chat(SYSTEM_PROGRAM_REPAIR, build_program_repair_prompt(item, extracted, repair_claims), retries=0)
    repaired, changed = merge_program_repair_claims(extracted, repair_obj)
    if isinstance(extract_meta, dict):
        extract_meta["program_repair_used"] = changed > 0
        extract_meta["program_repair_changed"] = changed
        extract_meta["program_repair_candidate_ids"] = [str(claim.get("claim_id") or "") for claim in repair_claims]
        extract_meta["program_repair_skipped_reason"] = "" if changed > 0 else "repair_returned_no_effective_updates"
    return repaired


# 14. Rewrite 输入构造：只把证据覆盖不足的 claim 交给 query rewriter。
def claims_needing_rewrite(
    claims: List[Dict[str, Any]],
    evidence_bundle: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]] = None,
    need_type: str = "",
    allow_route_supporting_probe: bool = False,
    verification_gap_alignment: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected_items, audit_rows, budget_decision = evaluate_retry_claim_candidates(
        claims,
        evidence_bundle,
        evidence_summary,
        need_type,
        allow_route_supporting_probe,
        verification_gap_alignment,
    )
    return [item["claim"] for item in selected_items], audit_rows, budget_decision


def build_rewrite_prompt(
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    evidence_bundle: Dict[str, Any],
    retry_claims: List[Dict[str, Any]],
    evidence_summary: Optional[Dict[str, Any]] = None,
    verification_gap_alignment: Optional[Dict[str, Any]] = None,
) -> str:
    diagnostics = evidence_bundle.get("diagnostics_by_claim") if isinstance(evidence_bundle, dict) else {}
    compact_diagnostics = {
        str(claim.get("claim_id") or claim.get("id") or ""): {
            key: diagnostics.get(str(claim.get("claim_id") or claim.get("id") or ""), {}).get(key)
            for key in (
                "reason",
                "needs_retry",
                "evidence_target",
                "evidence_shape",
                "evidence_gap",
                "raw_results",
                "kept_web",
                "direct_count",
                "strong_count",
                "route_failure_detail",
                "route_failure_stage",
                "route_failure_summary",
                "route_signal",
                "route_query_quality_score",
                "route_query_quality_label",
                "route_query_quality_issue",
                "route_query_quality_components",
                "retrieval_quality_score",
                "retrieval_quality_label",
                "retrieval_quality_stage",
                "retrieval_gap_flags",
                "recommended_actions",
                "retrieval_quality_summary",
                "detail_attempts",
                "detail_successes",
                "detail_errors",
                "page_intent",
                "page_intent_avg",
                "page_intent_labels",
                "page_intent_issues",
            )
            if isinstance(diagnostics.get(str(claim.get("claim_id") or claim.get("id") or "")), dict)
        }
        for claim in retry_claims
    }
    coverage = evidence_summary.get("claim_coverage") if isinstance(evidence_summary, dict) else {}
    compact_coverage = {
        str(claim.get("claim_id") or claim.get("id") or ""): coverage.get(str(claim.get("claim_id") or claim.get("id") or ""))
        for claim in retry_claims
    } if isinstance(coverage, dict) else {}
    compact_slot_alignment = compact_retry_alignment_context(verification_gap_alignment, retry_claims)
    compact_retry_claims = []
    for claim in retry_claims:
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        retry_reason = claim.get("_retry_reason") if isinstance(claim.get("_retry_reason"), dict) else {}
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        slot_context = compact_slot_alignment.get(claim_id) if isinstance(compact_slot_alignment.get(claim_id), dict) else {}
        route_score = retry_reason.get("route_query_quality_score")
        route_issue = str(retry_reason.get("route_query_quality_issue") or "")
        retrieval_quality_label = str(retry_reason.get("retrieval_quality_label") or "")
        retrieval_quality_stage = str(retry_reason.get("retrieval_quality_stage") or "")
        retrieval_gap_flags = retry_reason.get("retrieval_gap_flags") if isinstance(retry_reason.get("retrieval_gap_flags"), list) else []
        recommended_actions = retry_reason.get("recommended_actions") if isinstance(retry_reason.get("recommended_actions"), list) else []
        page_intent = retry_reason.get("page_intent") if isinstance(retry_reason.get("page_intent"), dict) else {}
        page_issues = retry_reason.get("page_intent_issues") if isinstance(retry_reason.get("page_intent_issues"), dict) else {}
        page_intent_instruction = ""
        if page_intent and page_issues:
            needed_page_type = str(page_intent.get("needed_page_type") or "general_page")
            if page_issues.get("missing_page_type_marker") or page_issues.get("generic_landing_page"):
                page_intent_instruction = (
                    f"上一轮召回页面不像目标证据页，目标页面类型是 {needed_page_type}；"
                    "请改写 query 去找这种页面形态，避免首页、导航页、泛文章和只相关不直接的页面。"
                )
        route_search_instruction = ""
        metric_search_instruction = ""
        metric_slots = slot_context.get("metric_slots") if isinstance(slot_context.get("metric_slots"), dict) else {}
        metric_value_type = str(metric_slots.get("value_type") or "")
        metric_source_authority = str(metric_slots.get("source_authority") or "")
        if metric_value_type and metric_value_type != "not_metric":
            metric_bits = [
                f"value_type={metric_value_type}",
                f"source_authority={metric_source_authority or 'unknown'}",
                f"time_scope={metric_slots.get('time_scope') or 'unknown'}",
                f"unit={metric_slots.get('unit') or 'unknown'}",
            ]
            if metric_slots.get("comparison_baseline"):
                metric_bits.append(f"comparison_baseline={metric_slots.get('comparison_baseline')}")
            metric_search_instruction = (
                "这是结构化指标核查；下一轮 query 必须围绕同一指标口径和来源类型，不要用其他口径混证。"
                + "；".join(metric_bits)
                + "。"
            )
        if source_intent.get("evidence_mode") == "route_fact" and isinstance(route_score, int) and route_score < 45:
            if route_issue == "route_query_too_broad_no_relation":
                route_search_instruction = "上一轮 query 过宽：请先从 claim/question/answer 抽 route_search_frame，再基于 frame 生成短 query；至少一条 discover_truth 必须中性寻找真实路线，不要带原结论极性；object_or_area 必须保留真正要核查的空域/地区对象，不要被相邻战况对象替换。"
            elif route_issue == "route_query_weak_sources":
                route_search_instruction = "上一轮主要是弱源：请先抽 route_search_frame，再用 frame 寻找更可靠来源表达，避免论坛、百科和问答页；avoid 里要显式排除只有方向词但对象错位的页面。"
            elif route_issue == "route_query_no_recall":
                route_search_instruction = "上一轮无召回：请先抽 route_search_frame，再换另一种语言或事实表达生成短 query；subject、destination、object_or_area 至少保住其中两组锚点。"
            else:
                route_search_instruction = "上一轮 route 质量低：请先抽 route_search_frame，再寻找能直接覆盖该 frame 的网页证据；reject_shape 要明确排除方向词正确但打击对象/经过空域并非本 claim 对象的页面。"
        elif retrieval_quality_label in {"bad", "borderline"}:
            if "change_source_plan" in recommended_actions and "re_retrieve_with_page_intent" in recommended_actions:
                route_search_instruction = "上一轮主要卡在页面保留：请减少泛新闻和落地页倾向，改写 query 去找更像分析页、说明页、带正文段落的材料。"
            elif "change_source_plan" in recommended_actions:
                route_search_instruction = "上一轮主要卡在检索来源质量：请改用更可靠来源表达和更稳定的事实表述。"
            elif "add_gap_query" in recommended_actions and retrieval_quality_stage == "search_recall":
                route_search_instruction = "上一轮主要卡在召回：请换一种事实表达或语言生成更短、更可检索的 query。"
            elif "add_gap_query" in recommended_actions and "missing_relation" in retrieval_gap_flags:
                route_search_instruction = "上一轮材料里缺少可裁决的关系句：请生成更偏经过/进入/飞越/路线说明的 query，而不是事件结果描述。"
        compact_retry_claims.append(
            {
                "claim_id": claim.get("claim_id") or claim.get("id"),
                "claim": claim.get("claim"),
                "centrality": claim.get("centrality"),
                "evidence_mode": source_intent.get("evidence_mode"),
                "evidence_target": source_intent.get("evidence_target"),
                "time_sensitivity": source_intent.get("time_sensitivity"),
                "retry_reason": retry_reason,
                "retry_operator_plan": retry_reason.get("retry_operator_plan") if isinstance(retry_reason.get("retry_operator_plan"), dict) else {},
                "page_intent_instruction": page_intent_instruction,
                "route_search_instruction": route_search_instruction,
                "metric_search_instruction": metric_search_instruction,
                "slot_retry_context": slot_context,
                "existing_queries": claim.get("queries", [])[:3] if isinstance(claim.get("queries"), list) else [],
            }
        )
    return f"""请根据检索失败诊断，为失败 claim 规划下一轮短 query。

[time]
{item.get('time', '')}

[question]
{item.get('question', '')}

[answer]
{item.get('answer', '')}

[retry_claims]
{json.dumps(compact_retry_claims, ensure_ascii=False)}

[diagnostics]
{json.dumps(compact_diagnostics, ensure_ascii=False)}

[coverage]
{json.dumps(compact_coverage, ensure_ascii=False)}

[slot_retry_context]
{json.dumps(compact_slot_alignment, ensure_ascii=False)}

要求：
- 你只负责搜索规划，不判断 claim 对错，不输出 label。
- 每个 claim 最多 3 条 query；每条 query 必须短、准、可搜索，通常 6-12 个词。
- 根据 evidence_target、evidence_gap、coverage_reason 解释“缺什么证据”，再规划 query。
- evidence_shape 表示需要的证据形态；优先围绕证据形态改写，不要堆题面词。
- route_fact 必须参考 route_failure_stage：search_recall 需要换搜索角度；source_filter 需要找更可靠来源；detail_read 需要换可读页面；route_sentence_extract 需要找同一句包含核心实体和路线关系的材料。
- 如果 diagnostics 里有 page_intent/page_intent_issues，说明上一轮网页不像目标证据页；必须按 page_intent 的 needed_page_type 改写 query。
- page_intent 只用于改写检索，不用于判断真假；query 应该寻找目标页面形态，例如历史表、比赛详情页、赛果页、交易日历页、牌价页、官方公告页。
- 当 page_intent_instruction 非空，至少一条 discover_truth query 必须体现目标页面类型；例如加“历史牌价/赛果/boxscore/交易日历/公告/结果页”等页面意图词，但不要堆同义词列表。
- 不要把首页、门户页、导航页作为目标；如果上一轮是泛页，请改写成更具体的数据页/详情页/公告页查询。
- route_query_quality_score 低于 45 时，说明上一轮 query 质量差；不要直接补关键词，必须先输出 route_search_frame，再用 frame 改写 query。
- route_search_frame 只能从输入文本抽取，不能使用外部常识补实体；如果对象/地点不清楚，在 frame 里写“不明确”，query 也要保守。
- route_search_frame 的 evidence_sentence_need 要写清楚：网页中什么样的中性事实句才能直接支持或反驳该路线关系；不要只写支持原 claim 的句式。
- route_fact 的 route_search_frame.object_or_area 必须保留真正待核查的路线对象或空域对象；不要把相邻战况对象、受袭设施、其他国家目标误写成 route object。
- route_fact 的 contract_focus.avoid / reject_shape 必须显式排除这类噪声：句子有“飞向/经过/导弹/无人机”等方向词，但对象不是本题要核查的空域、地区或目标。
- route 低分 query 至少一条 discover_truth 必须去掉原 claim 的结论极性，例如不要把“没有/不需要/完全/必然”等原判断词放进 discover_truth；verify_original 可以保留原说法核验。
- 当 retry_claims 里有 route_search_instruction，必须优先执行它；这是本轮 query 的主要目标，不要继续输出原来的泛主题 query。
- 当 slot_retry_context 非空，必须优先围绕其中一个 verification_subquestion / atomic_fact 生成 query；不要只围绕整条 claim 泛搜。
- slot_retry_context 的 required_evidence 是目标证据页/证据句合同，reject_evidence 是噪声页；它们用于约束搜索意图，不要逐字塞进 query。
- 如果 retry_operator_plan 非空，说明本轮 controller 已为该 claim 选了主 retry operator；query 应优先服务这个 operator family，而不是平均分配注意力。
- `primary_origin` 是本轮主 operator，对应的 query 目标要最明确；`supporting_origins` 是辅助 operator，只做补充。
- 如果 `variant_hint` 非空，说明主 operator 还有更具体的方向，例如 `dated_record` 比 `history` 更偏“锁定同日记录”。
- 每个 claim 除 queries 外，还要额外输出：
  - `gap_diagnosis`：本轮真正卡住的层，只能从 `search_recall|page_contract|sentence_shape|point_grounding|evidence_sufficiency|source_quality` 六选一。
  - `operator_plan`：你建议优先服务的 operator family / primary_origin / supporting_origins / variant_hint。
  - `contract_focus`：本轮想找的页面形态、目标句形、应避开的噪声页；这是 page/point contract helper，不是事实裁决。
- `gap_diagnosis` 要和 diagnostics、slot_retry_context 对齐，不要脱离输入另起炉灶。
- 如果 `gap_diagnosis=point_grounding`，必须围绕 same object / same metric / same time / same unit 修正检索，不要退化成泛搜。
- 如果 `gap_diagnosis=page_contract`，`contract_focus.page_brief` 与 `required_sentence_shape` 必须更明确地区分“目标证据页”和“只是相关页”。
- 如果 slot_retry_context.metric_slots.value_type 不是 not_metric，必须按 metric_slots 生成 query：
  - value_type 是核查口径，不能用其他口径混证，例如中间价不能证明现汇买入价，实时价不能证明银行牌价。
  - source_authority 是目标来源类型，query 应体现这种来源形态，例如 central_bank/official_notice、bank_rate_table、market_data_page、financial_quote_page、exchange。
  - time_scope 必须进入至少一条 query；unit 或 value_type 也应进入至少一条 query。
  - movement_direction / movement_amount / movement_percent 必须带 comparison_baseline，例如前一日、前一交易日、上一轮。
  - 对 bank_rate_table，query 应寻找“牌价/报价/买入价/卖出价/表”等页面形态；对 central_bank，query 应寻找“中间价/公告/公布”等页面形态；对 market_data_page，query 应寻找“行情/收盘/实时/历史数据”等页面形态。
  - 这些是通用来源类型，不要写死某个固定网站或样本答案。
- 如果 gap_layer 是 search_recall，query 应改用子问题的中性事实表达；如果是 page_contract，query 应体现目标页面形态；如果是 sentence_shape，query 应寻找能同句回答的关系/数值/日期/结果句。
- missing_slots 表示还缺哪些语义槽位；不要把“analysis/route/page/report”等页面意图词混进实体或地点槽。
- route 低分 query 的 avoid 必须包含：百科实体页、论坛问答、只出现单个实体、没有路线关系意图的泛分析页。
- query 分两类：discover_truth 去掉可疑数字/比分/日期找真实事实；verify_original 可保留原说法做核验。
- 不要复述整句 claim，不要堆关键词，不要把同义词列表拼成 query。
- 不要为了当前题面手写固定答案；只从 question、answer、claim、time 推导搜索意图。
- must_find 写清楚需要网页直接出现什么信息才算可用证据。
- avoid 写清楚应避开的噪声，例如泛百科、旧时间窗口、只相关不直接回答的页面。
- 不要判断答案是否事实错误。
- 不要输出 Markdown。
"""


def normalize_rewrite_plan(rewrite_obj: Optional[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    if not isinstance(rewrite_obj, dict):
        return {}
    rewrites = rewrite_obj.get("rewrites")
    if not isinstance(rewrites, list):
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for item in rewrites:
        if not isinstance(item, dict):
            continue
        claim_id = normalize_text(str(item.get("claim_id") or item.get("id") or ""))
        if not claim_id:
            continue
        gap_diagnosis = normalize_text(str(item.get("gap_diagnosis") or item.get("gap_layer") or ""))
        raw_operator_plan = item.get("operator_plan") if isinstance(item.get("operator_plan"), dict) else {}
        operator_plan: Dict[str, Any] = {}
        operator_family = normalize_text(str(raw_operator_plan.get("family") or item.get("operator_family") or ""))
        primary_origin = normalize_text(str(raw_operator_plan.get("primary_origin") or item.get("primary_origin") or ""))
        if operator_family:
            operator_plan["family"] = operator_family
        if primary_origin:
            operator_plan["primary_origin"] = primary_origin
        supporting_origins_raw = raw_operator_plan.get("supporting_origins") if isinstance(raw_operator_plan.get("supporting_origins"), list) else item.get("supporting_origins")
        if isinstance(supporting_origins_raw, list):
            supporting_origins = dedupe_keep_order(
                [normalize_text(str(value)) for value in supporting_origins_raw if normalize_text(str(value))]
            )[:3]
            if supporting_origins:
                operator_plan["supporting_origins"] = supporting_origins
        variant_hint = normalize_text(str(raw_operator_plan.get("variant_hint") or item.get("variant_hint") or ""))
        if variant_hint:
            operator_plan["variant_hint"] = variant_hint
        operator_reason = compact_claim_text(normalize_text(str(raw_operator_plan.get("reason") or item.get("operator_reason") or "")), 120)
        if operator_reason:
            operator_plan["reason"] = operator_reason
        raw_contract_focus = item.get("contract_focus") if isinstance(item.get("contract_focus"), dict) else {}
        contract_focus: Dict[str, str] = {}
        for key, limit in (
            ("page_brief", 180),
            ("target_sentence", 160),
            ("avoid", 140),
            ("answer_target", 80),
            ("required_sentence_shape", 160),
            ("reject_shape", 160),
        ):
            value = compact_claim_text(normalize_text(str(raw_contract_focus.get(key) or "")), limit)
            if value:
                contract_focus[key] = value
        queries: List[Dict[str, Any]] = []
        for raw_query in item.get("queries") or []:
            if isinstance(raw_query, str):
                query_text = normalize_text(raw_query)
                goal = "general_verify"
                source_preference: List[str] = []
            elif isinstance(raw_query, dict):
                query_text = normalize_text(str(raw_query.get("q") or raw_query.get("query") or ""))
                goal = normalize_text(str(raw_query.get("goal") or "general_verify")) or "general_verify"
                raw_preference = raw_query.get("source_preference") if isinstance(raw_query.get("source_preference"), list) else []
                source_preference = [normalize_text(str(item)) for item in raw_preference if normalize_text(str(item))][:3]
            else:
                continue
            if query_text:
                query_item: Dict[str, Any] = {"q": query_text, "goal": goal}
                if source_preference:
                    query_item["source_preference"] = source_preference
                if gap_diagnosis:
                    query_item["_gap_diagnosis"] = gap_diagnosis
                if operator_plan:
                    query_item["_operator_plan"] = operator_plan
                if contract_focus:
                    query_item["_contract_focus"] = contract_focus
                queries.append(query_item)
            if len(queries) >= 3:
                break
        if queries:
            out[claim_id] = queries
    return out


def normalize_rewrite_frames(
    rewrite_obj: Optional[Dict[str, Any]],
    claims: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, str]]:
    if not isinstance(rewrite_obj, dict):
        return {}
    route_claim_ids = set()
    for claim in claims or []:
        claim_id = normalize_text(str(claim.get("claim_id") or claim.get("id") or ""))
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        if claim_id and source_intent.get("evidence_mode") == "route_fact":
            route_claim_ids.add(claim_id)
    rewrites = rewrite_obj.get("rewrites")
    if not isinstance(rewrites, list):
        return {}
    frames: Dict[str, Dict[str, str]] = {}
    allowed_keys = (
        "subject",
        "action_or_event",
        "relation_need",
        "object_or_area",
        "time_or_event_window",
        "claim_polarity",
        "evidence_sentence_need",
    )
    for item in rewrites:
        if not isinstance(item, dict):
            continue
        claim_id = normalize_text(str(item.get("claim_id") or item.get("id") or ""))
        if route_claim_ids and claim_id not in route_claim_ids:
            continue
        frame = item.get("route_search_frame") if isinstance(item.get("route_search_frame"), dict) else {}
        if not claim_id or not frame:
            continue
        frames[claim_id] = {
            key: compact_claim_text(normalize_text(str(frame.get(key) or "")), 120)
            for key in allowed_keys
            if normalize_text(str(frame.get(key) or ""))
        }
    return frames


def build_retry_claims(
    claims: List[Dict[str, Any]],
    rewrite_plan: Dict[str, List[Dict[str, Any]]],
    rewrite_frames: Optional[Dict[str, Dict[str, str]]] = None,
    retry_claims_meta: Optional[List[Dict[str, Any]]] = None,
    verification_gap_alignment: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    retry_claims: List[Dict[str, Any]] = []
    retry_meta_by_id: Dict[str, Dict[str, Any]] = {}
    for item in retry_claims_meta or []:
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("claim_id") or item.get("id") or "")
        if claim_id:
            retry_meta_by_id[claim_id] = item
    slot_alignment = compact_retry_alignment_context(verification_gap_alignment, retry_claims_meta or [])
    for claim in claims:
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        if claim_id not in rewrite_plan:
            continue
        rewritten = dict(claim)
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        rewritten["source_intent"] = dict(source_intent)
        rewritten["source_intent"]["_is_retry"] = True
        retry_meta = retry_meta_by_id.get(claim_id) if isinstance(retry_meta_by_id.get(claim_id), dict) else {}
        retry_reason = retry_meta.get("_retry_reason") if isinstance(retry_meta.get("_retry_reason"), dict) else {}
        actions = retry_reason.get("recommended_actions") if isinstance(retry_reason.get("recommended_actions"), list) else []
        gap_flags = retry_reason.get("retrieval_gap_flags") if isinstance(retry_reason.get("retrieval_gap_flags"), list) else []
        rewritten["source_intent"]["_retry_recommended_actions"] = actions[:4]
        rewritten["source_intent"]["_retry_gap_flags"] = gap_flags[:6]
        rewritten["source_intent"]["_retry_retrieval_quality_stage"] = str(retry_reason.get("retrieval_quality_stage") or "")
        operator_plan = retry_reason.get("retry_operator_plan") if isinstance(retry_reason.get("retry_operator_plan"), dict) else {}
        if operator_plan:
            rewritten["source_intent"]["_retry_operator_family"] = str(operator_plan.get("family") or "")
            rewritten["source_intent"]["_retry_operator_origin"] = str(operator_plan.get("primary_origin") or "")
            rewritten["source_intent"]["_retry_operator_variant_hint"] = str(operator_plan.get("variant_hint") or "")
            supporting_origins = operator_plan.get("supporting_origins") if isinstance(operator_plan.get("supporting_origins"), list) else []
            rewritten["source_intent"]["_retry_operator_supporting_origins"] = [str(item) for item in supporting_origins[:4] if str(item)]
        llm_plan_source = rewrite_plan[claim_id][0] if rewrite_plan.get(claim_id) and isinstance(rewrite_plan[claim_id][0], dict) else {}
        llm_gap_diagnosis = normalize_text(str(llm_plan_source.get("_gap_diagnosis") or ""))
        llm_operator_plan = llm_plan_source.get("_operator_plan") if isinstance(llm_plan_source.get("_operator_plan"), dict) else {}
        llm_contract_focus = llm_plan_source.get("_contract_focus") if isinstance(llm_plan_source.get("_contract_focus"), dict) else {}
        route_frame = rewrite_frames.get(claim_id) if isinstance(rewrite_frames, dict) and isinstance(rewrite_frames.get(claim_id), dict) else {}
        if llm_gap_diagnosis:
            rewritten["source_intent"]["_retry_gap_layer_llm"] = llm_gap_diagnosis
        if llm_contract_focus:
            rewritten["source_intent"]["_retry_contract_focus_llm"] = llm_contract_focus
        if route_frame:
            rewritten["source_intent"]["_retry_route_search_frame"] = route_frame
        if llm_operator_plan:
            rewritten["source_intent"]["_retry_operator_family_llm"] = str(llm_operator_plan.get("family") or "")
            rewritten["source_intent"]["_retry_operator_origin_llm"] = str(llm_operator_plan.get("primary_origin") or "")
            rewritten["source_intent"]["_retry_operator_variant_hint_llm"] = str(llm_operator_plan.get("variant_hint") or "")
            llm_supporting = llm_operator_plan.get("supporting_origins") if isinstance(llm_operator_plan.get("supporting_origins"), list) else []
            rewritten["source_intent"]["_retry_operator_supporting_origins_llm"] = [str(item) for item in llm_supporting[:4] if str(item)]
            current_family = str(rewritten["source_intent"].get("_retry_operator_family") or "")
            if current_family in {"", "general_rewrite_probe"}:
                if str(llm_operator_plan.get("family") or ""):
                    rewritten["source_intent"]["_retry_operator_family"] = str(llm_operator_plan.get("family") or "")
                if str(llm_operator_plan.get("primary_origin") or ""):
                    rewritten["source_intent"]["_retry_operator_origin"] = str(llm_operator_plan.get("primary_origin") or "")
                if str(llm_operator_plan.get("variant_hint") or ""):
                    rewritten["source_intent"]["_retry_operator_variant_hint"] = str(llm_operator_plan.get("variant_hint") or "")
                if llm_supporting:
                    rewritten["source_intent"]["_retry_operator_supporting_origins"] = [str(item) for item in llm_supporting[:4] if str(item)]
        slot_context = slot_alignment.get(claim_id) if isinstance(slot_alignment.get(claim_id), dict) else {}
        metric_slots = slot_context.get("metric_slots") if isinstance(slot_context.get("metric_slots"), dict) else {}
        if metric_slots:
            rewritten["source_intent"]["_retry_metric_slots"] = metric_slots
        existing = claim.get("queries") if isinstance(claim.get("queries"), list) else []
        rewritten["queries"] = rewrite_plan[claim_id] + existing
        retry_claims.append(rewritten)
    return retry_claims


def merge_evidence_bundles(first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(first)
    evidence_by_claim = dict(first.get("evidence_by_claim") or {})
    for claim_id, items in (second.get("evidence_by_claim") or {}).items():
        combined = list(evidence_by_claim.get(claim_id) or []) + list(items or [])
        seen = set()
        deduped = []
        index_by_key = {}
        for item in combined:
            key = item.get("url") or f"{item.get('source_type')}:{item.get('title')}:{item.get('snippet')}"
            if key in seen:
                existing = deduped[index_by_key[key]]
                if len(str(item.get("detail") or "")) > len(str(existing.get("detail") or "")):
                    merged_item = dict(existing)
                    merged_item.update({k: v for k, v in item.items() if v not in ("", None, [])})
                    deduped[index_by_key[key]] = merged_item
                continue
            seen.add(key)
            index_by_key[key] = len(deduped)
            deduped.append(item)
        evidence_by_claim[claim_id] = deduped[: max(MAX_RESULTS_PER_QUERY + 2, MAX_RESULTS_PER_QUERY)]
    diagnostics = dict(first.get("diagnostics_by_claim") or {})
    for claim_id, second_diag in (second.get("diagnostics_by_claim") or {}).items():
        first_diag = diagnostics.get(claim_id) if isinstance(diagnostics.get(claim_id), dict) else {}
        if int(first_diag.get("kept_web", 0) or 0) > 0 and int(second_diag.get("kept_web", 0) or 0) == 0:
            merged_diag = dict(first_diag)
            merged_diag["retry_diagnostic"] = second_diag
            diagnostics[claim_id] = merged_diag
        else:
            diagnostics[claim_id] = second_diag
    merged["evidence_by_claim"] = evidence_by_claim
    merged["diagnostics_by_claim"] = diagnostics
    merged["logs"] = list(first.get("logs") or []) + list(second.get("logs") or [])
    merged["rewrite_used"] = True
    return merged


def compact_point_for_prompt(point: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: compact_claim_text(str(point.get(key) or ""), 90)
        for key in ("type", "claim_value", "evidence_value", "evidence_sentence", "title", "url", "source_type", "direct_answer")
        if point.get(key)
    }


def verification_questions_for_claim(claim: Dict[str, Any]) -> List[str]:
    existing = claim.get("verification_questions") if isinstance(claim.get("verification_questions"), list) else []
    questions = [compact_claim_text(str(item), 90) for item in existing if normalize_text(str(item))]
    if questions:
        return questions[:3]
    evidence_need_program = claim.get("evidence_need_program") if isinstance(claim.get("evidence_need_program"), dict) else {}
    if evidence_need_program:
        return build_program_verification_questions(claim, evidence_need_program)
    claim_text = compact_claim_text(str(claim.get("claim") or ""), 90)
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    if str(source_intent.get("claim_shape") or "") == "exclusive_premise":
        return exclusive_premise_verification_questions(claim_text, str(source_intent.get("evidence_mode") or ""))
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    if mode == "numeric_fact" or target in {"market_price", "prize_amount", "position_distance"}:
        return [f"该说法中的具体数值、单位和对象是否与权威资料一致？", f"证据中对应的实际数值是什么？"]
    if mode in {"date_fact", "schedule_fact"} or target in {"market_calendar", "census_phase"}:
        return [f"该说法中的日期、时间或阶段是否与权威资料一致？", f"证据中对应的实际时间是什么？"]
    if mode == "event_result" or target in {"match_result", "withdrawal_status"}:
        return [f"该事件或比赛的实际结果是什么？", f"是否存在退赛、取消、延期或其他特殊情况？"]
    if mode == "route_fact" or target == "route_relation":
        return [f"证据是否直接说明该主体与路线、领空或区域之间的关系？", f"该说法是否把路线关系说得过于确定？"]
    if mode == "policy_fact":
        return [f"该政策或官方安排是否真实存在？", f"证据中官方表述是什么？"]
    return [f"该 claim 是否被可靠资料直接支持或反驳？", f"证据中能直接回答该 claim 的句子是什么？"]


def point_answer_text(point: Dict[str, Any]) -> str:
    for key in ("evidence_sentence", "sentence", "text", "snippet", "summary", "evidence_value", "title"):
        value = normalize_text(str(point.get(key) or ""))
        if value:
            return compact_claim_text(value, 180)
    return ""


def qa_item_from_point(claim: Dict[str, Any], question: str, point: Dict[str, Any], stance: str) -> Dict[str, Any]:
    directness = str(point.get("direct_answer") or point.get("directness") or "")
    if not directness:
        directness = "direct" if stance in {"support", "refute"} else "related"
    return {
        "claim_id": str(claim.get("claim_id") or claim.get("id") or ""),
        "claim": compact_claim_text(str(claim.get("claim") or ""), 140),
        "question": question,
        "answer": point_answer_text(point),
        "stance": stance,
        "directness": directness,
        "confidence": point.get("confidence") or point.get("score") or "",
        "source_type": point.get("source_type") or "",
        "source_url": point.get("url") or "",
        "source_title": compact_claim_text(str(point.get("title") or ""), 120),
        "source_text": point_answer_text(point),
    }


def build_qa_evidence(claims: List[Dict[str, Any]], evidence_summary: Dict[str, Any]) -> Dict[str, Any]:
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary, dict) else {}
    if not isinstance(summaries, dict):
        summaries = {}
    by_claim: Dict[str, List[Dict[str, Any]]] = {}
    stats = {"total": 0, "support": 0, "refute": 0, "unknown": 0, "direct": 0}
    for claim in claims:
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        questions = verification_questions_for_claim(claim)
        items: List[Dict[str, Any]] = []
        for point in (summary.get("refuting_points") or [])[:2]:
            if isinstance(point, dict):
                items.append(qa_item_from_point(claim, questions[0], point, "refute"))
        for point in (summary.get("supporting_points") or [])[:2]:
            if isinstance(point, dict):
                items.append(qa_item_from_point(claim, questions[0], point, "support"))
        if not items:
            uncertain_points = [point for point in (summary.get("uncertain_points") or []) if isinstance(point, dict)]
            if uncertain_points:
                for point in uncertain_points[:2]:
                    items.append(qa_item_from_point(claim, questions[0], point, "unknown"))
            elif isinstance(summary.get("answer_candidates"), list) and summary.get("answer_candidates"):
                for candidate in [point for point in summary.get("answer_candidates") or [] if isinstance(point, dict)][:2]:
                    items.append(qa_item_from_point(claim, questions[0], candidate, "unknown"))
            else:
                coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
                items.append(
                    {
                        "claim_id": claim_id,
                        "claim": compact_claim_text(str(claim.get("claim") or ""), 140),
                        "question": questions[0],
                        "answer": "",
                        "stance": "unknown",
                        "directness": "none",
                        "confidence": 0,
                        "source_type": "",
                        "source_url": "",
                        "source_title": "",
                        "source_text": "",
                        "gap": coverage.get("coverage_reason") or coverage.get("reason") or "没有形成可裁决的直接证据",
                    }
                )
        by_claim[claim_id] = items
        for item in items:
            stats["total"] += 1
            stance = str(item.get("stance") or "unknown")
            stats[stance if stance in {"support", "refute"} else "unknown"] += 1
            if str(item.get("directness") or "") == "direct":
                stats["direct"] += 1
    return {"by_claim": by_claim, "stats": stats}


def compact_qa_evidence_for_prompt(qa_evidence: Dict[str, Any]) -> Dict[str, Any]:
    by_claim = qa_evidence.get("by_claim") if isinstance(qa_evidence, dict) else {}
    compact: Dict[str, Any] = {"by_claim": {}, "stats": qa_evidence.get("stats") if isinstance(qa_evidence, dict) else {}}
    if not isinstance(by_claim, dict):
        return compact
    for claim_id, items in by_claim.items():
        compact["by_claim"][claim_id] = []
        for item in (items or [])[:4]:
            if not isinstance(item, dict):
                continue
            compact["by_claim"][claim_id].append(
                {
                    key: compact_claim_text(str(item.get(key) or ""), 120)
                    for key in ("question", "answer", "stance", "directness", "source_type", "source_title", "source_text", "gap")
                    if item.get(key) not in (None, "")
                }
            )
    return compact


def compact_evidence_for_verify(evidence_bundle: Dict[str, Any], evidence_summary: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = evidence_bundle.get("diagnostics_by_claim") if isinstance(evidence_bundle, dict) else {}
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary, dict) else {}
    compact: Dict[str, Any] = {"claims": {}}
    if not isinstance(summaries, dict):
        summaries = {}
    for claim_id, summary in summaries.items():
        if not isinstance(summary, dict):
            continue
        coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
        compact["claims"][claim_id] = {
            "evidence_mode": summary.get("evidence_mode", ""),
            "coverage": {
                key: coverage.get(key)
                for key in (
                    "coverage_level",
                    "coverage_reason",
                    "web_evidence_count",
                    "direct_evidence_count",
                    "supporting_direct_points",
                    "refuting_direct_points",
                    "official_direct_count",
                    "news_direct_count",
                )
                if key in coverage
            },
            "supporting_points": [compact_point_for_prompt(point) for point in (summary.get("supporting_points") or [])[:2] if isinstance(point, dict)],
            "refuting_points": [compact_point_for_prompt(point) for point in (summary.get("refuting_points") or [])[:2] if isinstance(point, dict)],
            "uncertain_points": [compact_point_for_prompt(point) for point in (summary.get("uncertain_points") or [])[:1] if isinstance(point, dict)],
        }
        if isinstance(summary.get("point_conversion"), dict):
            compact["claims"][claim_id]["point_conversion"] = {
                key: summary["point_conversion"].get(key)
                for key in (
                    "stage",
                    "reason",
                    "candidate_sentence_count",
                    "direct_count",
                    "partial_count",
                    "related_only_count",
                    "support_refute_count",
                    "direct_support_refute_count",
                )
                if key in summary["point_conversion"]
            }
        if isinstance(summary.get("evidence_events"), dict):
            compact["claims"][claim_id]["evidence_events"] = summary.get("evidence_events")
        if isinstance(summary.get("reason_hint"), dict):
            compact["claims"][claim_id]["reason_hint"] = summary.get("reason_hint")
        if isinstance(diagnostics, dict) and isinstance(diagnostics.get(claim_id), dict):
            diag = diagnostics[claim_id]
            compact["claims"][claim_id]["diagnostic"] = {
                key: diag.get(key)
                for key in (
                    "reason",
                    "needs_retry",
                    "evidence_target",
                    "evidence_gap",
                    "kept_web",
                    "route_failure_detail",
                    "route_failure_stage",
                    "route_failure_summary",
                    "route_signal",
                    "route_query_quality_score",
                    "route_query_quality_label",
                    "route_query_quality_issue",
                    "route_query_quality_components",
                    "detail_fetches",
                    "detail_attempts",
                    "detail_successes",
                    "detail_errors",
                )
                if key in diag
            }
    compact["rewrite_used"] = bool(evidence_bundle.get("rewrite_used")) if isinstance(evidence_bundle, dict) else False
    if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("_qa_evidence"), dict):
        compact["qa_evidence"] = compact_qa_evidence_for_prompt(evidence_summary["_qa_evidence"])
    return compact


def semantic_audit_triggers(item: Dict[str, Any], extracted: Dict[str, Any], verify_obj: Dict[str, Any]) -> List[str]:
    question = normalize_text(str(item.get("question") or ""))
    answer = normalize_text(str(item.get("answer") or ""))
    need_type = normalize_need_type(extracted.get("need_type"))
    text = f"{question}\n{answer}"
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    triggers: List[str] = []
    absolute_terms = [
        "根本不需要", "完全没有", "没有实质性影响", "完全绕开", "不需要经过",
        "唯一", "必然", "一定", "毫无", "绝对", "no need", "without crossing",
        "completely", "never", "only route",
    ]
    forecast_terms = ["预计", "即将", "将", "预测", "窗口期", "年内最大", "无悬念", "确定", "落地"]
    detail_terms = ["奖金", "金额", "瑞典克朗", "比分", "战绩", "公里", "分钟", "元/吨", "元/升", "%"]
    if need_type in {"geopolitical_claim", "current_geopolitical_status", "distance_position"} and any(term.lower() in text.lower() for term in absolute_terms):
        triggers.append("absolute_route_or_causal")
    if need_type in {"market_movement", "schedule_time", "current_result"} and any(term in text for term in forecast_terms):
        triggers.append("resolved_forecast")
    has_core_claim = any(isinstance(claim, dict) and str(claim.get("centrality") or "") == "core" for claim in claims)
    has_supporting_structured_detail = any(
        isinstance(claim, dict)
        and str(claim.get("centrality") or "") != "core"
        and str(
            (
                claim.get("source_intent")
                if isinstance(claim.get("source_intent"), dict)
                else {}
            ).get("evidence_mode") or ""
        ) in {"numeric_fact", "date_fact", "schedule_fact"}
        for claim in claims
    )
    if any(term in text for term in detail_terms) and (need_type in {"general_fact", "sports_result", "financial_quote"} or (has_core_claim and has_supporting_structured_detail)):
        triggers.append("attached_detail_pollution")
    if need_type == "geopolitical_claim" and any(term in text for term in ["路线", "北线", "南线", "经过", "飞越", "领空"]):
        triggers.append("open_route_summary")
    if pick_label(verify_obj.get("final_label")) in {LABEL_0, LABEL_1}:
        triggers.append("check_overstrict_label")
    return dedupe_keep_order(triggers)


def should_run_semantic_audit(
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    verify_obj: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]] = None,
) -> bool:
    if not ENABLE_SEMANTIC_AUDIT:
        return False
    triggers = semantic_audit_triggers(item, extracted, verify_obj)
    if not triggers:
        return False
    if verify_obj.get("_evidence_first_locked"):
        return False
    if str(verify_obj.get("_decision_basis") or "") == "risk_calibration":
        return False
    if has_new_scheme_decidable_evidence(extracted, evidence_summary):
        return False
    if verify_obj.get("_evidence_override") and pick_label(verify_obj.get("final_label")) in {LABEL_0, LABEL_1}:
        return False
    if (
        pick_label(verify_obj.get("final_label")) in {LABEL_0, LABEL_1}
        and has_new_scheme_core_refuting_evidence(extracted, evidence_summary)
    ):
        return False
    return True


def semantic_audit_upgrade_allowed(
    audit_label: str,
    audit_type: str,
    audit_confidence: float,
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> bool:
    if has_new_scheme_decidable_evidence(extracted, evidence_summary):
        return False
    if audit_label == LABEL_2:
        return True
    if audit_label not in {LABEL_0, LABEL_1}:
        return False
    if has_new_scheme_core_refuting_evidence(extracted, evidence_summary):
        return True
    if audit_confidence < 0.70:
        return False
    need_type = normalize_need_type(extracted.get("need_type"))
    answer_text = normalize_text(str(item.get("answer") or ""))
    if audit_type == "attached_detail_pollution":
        claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
        summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict) else {}
        has_supported_core = False
        has_risky_unsupported_supporting = False
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id") or claim.get("id") or "")
            centrality = str(claim.get("centrality") or "")
            source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
            summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
            coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
            coverage_level = str(coverage.get("coverage_level") or "")
            mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
            stated_as_fact = normalize_bool(source_intent.get("stated_as_fact", True), True)
            if centrality == "core" and (
                bool(summary.get("supporting_points"))
                or int(coverage.get("direct_evidence_count") or 0) > 0
                or coverage_level == "strong"
            ):
                has_supported_core = True
            if (
                centrality in {"supporting", "peripheral"}
                and stated_as_fact
                and mode in HIGH_RISK_SUPPORTING_MODES
                and coverage_level in {"none", "weak", "partial"}
            ):
                has_risky_unsupported_supporting = True
        return has_supported_core and has_risky_unsupported_supporting and audit_confidence >= 0.85
    if audit_type == "resolved_forecast":
        return answer_has_resolved_forecast_terms(answer_text)
    if audit_type == "absolute_route_or_causal":
        if need_type in {"geopolitical_claim", "current_geopolitical_status"}:
            return has_new_scheme_core_refuting_evidence(extracted, evidence_summary) and answer_has_absolute_boundary_terms(answer_text)
        return answer_has_absolute_boundary_terms(answer_text)
    if audit_type == "open_route_summary":
        return False
    if audit_type == "fictional_scenario_contaminates_current_need":
        return any(term in answer_text for term in ["虚构", "剧本", "假设", "AI生成", "非真实新闻"])
    if need_type in {"market_movement", "schedule_time", "current_result"}:
        return answer_has_resolved_forecast_terms(answer_text)
    if need_type in {"geopolitical_claim", "current_geopolitical_status"}:
        return answer_has_absolute_boundary_terms(answer_text)
    return False


def rewrite_skip_reason(
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    verification_gap_alignment: Optional[Dict[str, Any]] = None,
) -> str:
    if has_direct_refuting_evidence(evidence_summary) and not verification_alignment_supports_point_gap_retry(verification_gap_alignment):
        return "skip_rewrite_direct_refuting_evidence_exists"
    triggers = semantic_audit_triggers(item, extracted, {})
    semantic_first_triggers = {"absolute_route_or_causal", "resolved_forecast"}
    if any(trigger in semantic_first_triggers for trigger in triggers):
        return "skip_rewrite_semantic_boundary_first"
    if "open_route_summary" in triggers and "absolute_route_or_causal" not in triggers:
        return "skip_rewrite_open_route_summary_first"
    need_type = normalize_need_type(extracted.get("need_type"))
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    answer_text = normalize_text(str(item.get("answer") or ""))
    certainty_terms = ["无悬念", "年内最大", "即将迎来", "确定落地", "四连涨", "将实现", "抓紧"]
    if any(term in answer_text for term in certainty_terms):
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
            if (
                str(source_intent.get("risk_type") or "") == "prediction"
                and normalize_bool(source_intent.get("stated_as_fact", True), True)
                and str(claim.get("centrality") or "") in {"core", "supporting"}
            ):
                return "skip_rewrite_prediction_boundary_first"
    return ""


def claims_for_initial_retrieval(item: Dict[str, Any], extracted: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    triggers = semantic_audit_triggers(item, extracted, {})
    if "absolute_route_or_causal" not in triggers:
        return claims, "", {
            "applied": False,
            "reason": "no_absolute_route_or_causal_trigger",
            "triggers": triggers,
            "claim_count": len(claims),
        }
    selected: List[Dict[str, Any]] = []
    deferred_route_supporting: List[Dict[str, Any]] = []
    route_pick_added = False
    claim_decisions: List[Dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        centrality = str(claim.get("centrality") or "")
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        mode = str(source_intent.get("evidence_mode") or "")
        task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
        priority_label = str(task_card.get("priority_label") or "normal")
        if centrality == "core" or mode in {"numeric_fact", "date_fact", "schedule_fact"} or claim_has_exclusive_premise_text(claim):
            selected.append(claim)
            claim_decisions.append(
                {
                    "claim_id": claim_id,
                    "centrality": centrality,
                    "evidence_mode": mode,
                    "priority_label": priority_label,
                    "decision": "keep_core_or_structured" if not claim_has_exclusive_premise_text(claim) else "keep_exclusive_premise_supporting",
                }
            )
            continue
        if mode == "route_fact":
            deferred_route_supporting.append(claim)
            claim_decisions.append(
                {
                    "claim_id": claim_id,
                    "centrality": centrality,
                    "evidence_mode": mode,
                    "priority_label": priority_label,
                    "decision": "defer_route_supporting_probe",
                }
            )
            continue
        claim_decisions.append(
            {
                "claim_id": claim_id,
                "centrality": centrality,
                "evidence_mode": mode,
                "priority_label": priority_label,
                "decision": "skip_semantic_boundary_supporting",
            }
        )
    selected_ids = {
        str(item.get("claim_id") or item.get("id") or id(item))
        for item in selected
        if isinstance(item, dict)
    }
    route_pick_id = ""
    if deferred_route_supporting:
        route_pick = sorted(deferred_route_supporting, key=claim_budget_priority, reverse=True)[0]
        route_pick_id = str(route_pick.get("claim_id") or route_pick.get("id") or id(route_pick))
        if route_pick_id not in selected_ids:
            selected.append(route_pick)
            route_pick_added = True
    for item in claim_decisions:
        if item.get("decision") != "defer_route_supporting_probe":
            continue
        if item.get("claim_id") == route_pick_id and route_pick_added:
            item["decision"] = "keep_route_supporting_probe"
        else:
            item["decision"] = "skip_route_supporting_not_top_priority"
    trace = {
        "applied": True,
        "triggers": triggers,
        "claim_count": len(claims),
        "selected_claim_ids": [str(claim.get("claim_id") or claim.get("id") or "") for claim in selected if isinstance(claim, dict)],
        "route_supporting_candidate_ids": [
            str(claim.get("claim_id") or claim.get("id") or "")
            for claim in deferred_route_supporting
            if isinstance(claim, dict)
        ],
        "extra_route_supporting_kept": route_pick_id if route_pick_added else "",
        "extra_route_supporting_skipped_reason": "" if route_pick_added else "no_route_supporting_claim",
        "claim_decisions": claim_decisions,
    }
    if selected and len(selected) < len(claims):
        if route_pick_added:
            return selected, "semantic_boundary_core_plus_route_probe", trace
        return selected, "semantic_boundary_core_claims_only", trace
    return claims, "", trace


def is_route_like_claim(claim: Dict[str, Any]) -> bool:
    if not isinstance(claim, dict):
        return False
    text = normalize_text(str(claim.get("claim") or ""))
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    return (
        source_intent.get("evidence_mode") == "route_fact"
        or source_intent.get("risk_type") == "route_relation"
        or source_intent.get("evidence_target") == "route_relation"
        or any(term in text for term in ["路线", "北线", "南线", "经过", "飞越", "领空"])
    )


def route_requirement_signature(claim: Dict[str, Any]) -> str:
    if not isinstance(claim, dict):
        return ""
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    if str(source_intent.get("evidence_mode") or "") != "route_fact":
        return ""
    if str(source_intent.get("evidence_target") or "") != "route_relation":
        return ""
    route_meta = source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}
    origin = normalize_text(str(route_meta.get("origin") or "")).lower()
    destination = normalize_text(str(route_meta.get("destination") or "")).lower()
    route_area = normalize_text(str(route_meta.get("route_area") or "")).lower()
    if route_area:
        return f"{origin}|{destination}|{route_area}"
    task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
    fact_need = normalize_text(str(task_card.get("fact_need") or claim.get("claim") or "")).lower()
    return f"{origin}|{destination}|{fact_need[:80]}"


def retrieval_budget_for_initial(item: Dict[str, Any], extracted: Dict[str, Any], claims: List[Dict[str, Any]], scope_reason: str) -> Dict[str, Any]:
    triggers = semantic_audit_triggers(item, extracted, {})
    claim_ids = [str(claim.get("claim_id") or claim.get("id") or "") for claim in claims if isinstance(claim, dict)]
    skipped: List[Dict[str, str]] = []
    query_limits: Dict[str, int] = {}
    source_limits: Dict[str, int] = {}
    budget_priority: Dict[str, str] = {}
    core_claim_budget_reserved: List[str] = []
    supporting_claim_deprioritized: List[str] = []
    reason = scope_reason or "default_structured_budget"
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        centrality = str(claim.get("centrality") or "supporting")
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
        mode = str(source_intent.get("evidence_mode") or "")
        mechanism_type = str(source_intent.get("mechanism_type") or "")
        core_binding = source_intent.get("core_binding") if isinstance(source_intent.get("core_binding"), dict) else {}
        priority_label = str(task_card.get("priority_label") or "normal")
        preferred_domains = source_intent.get("preferred_domains") if isinstance(source_intent.get("preferred_domains"), list) else []
        evidence_shape = str(source_intent.get("evidence_shape") or "")
        budget_priority[claim_id] = claim_budget_priority_label(claim)
        binding_strength = sum(
            1
            for key in ("subject_entity", "relation_or_metric", "time_scope", "expected_evidence_shape")
            if normalize_text(str(core_binding.get(key) or ""))
        )
        structured_authority_ready = (
            mechanism_type in {"structured_numeric_authority", "date_authority"}
            and evidence_shape in {"authoritative_notice", "structured_historical_data"}
            and binding_strength >= 3
        )
        authority_first_ready = (
            preferred_domains and mode in {"numeric_fact", "date_fact", "schedule_fact", "route_fact", "event_result"}
        ) or structured_authority_ready
        if centrality == "core":
            query_limits[claim_id] = 2
            if (
                preferred_domains and mode in {"numeric_fact", "date_fact", "schedule_fact"} and evidence_shape in {"authoritative_notice", "structured_historical_data"}
            ) or structured_authority_ready:
                query_limits[claim_id] = 3
            if mechanism_type in {"structured_numeric_authority", "date_authority", "event_result_page", "current_status_update"}:
                query_limits[claim_id] = max(query_limits[claim_id], 2)
            source_limits[claim_id] = 3 if authority_first_ready or mode in {"route_fact", "event_result"} else 2
        elif priority_label in {"critical", "high"}:
            query_limits[claim_id] = 2 if mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result", "route_fact"} else 1
            if (
                preferred_domains and mode in {"numeric_fact", "date_fact", "schedule_fact"} and evidence_shape in {"authoritative_notice", "structured_historical_data"}
            ) or structured_authority_ready:
                query_limits[claim_id] = max(query_limits[claim_id], 3)
            if mechanism_type in {"structured_numeric_authority", "date_authority", "event_result_page", "relation_sentence", "current_status_update"}:
                query_limits[claim_id] = max(query_limits[claim_id], 2)
            source_limits[claim_id] = 3 if authority_first_ready or mode in {"route_fact", "event_result"} else 2
        elif mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result"}:
            target = str(source_intent.get("evidence_target") or "")
            query_limits[claim_id] = 2 if mode == "numeric_fact" and target in {"prize_amount", "market_price"} else 1
            if preferred_domains and mode in {"numeric_fact", "date_fact", "schedule_fact"} and evidence_shape in {"authoritative_notice", "structured_historical_data"}:
                query_limits[claim_id] = max(query_limits[claim_id], 2)
            if mechanism_type in {"structured_numeric_authority", "date_authority"} or target in {"prize_amount", "market_price", "market_calendar", "position_distance"}:
                if evidence_shape in {"authoritative_notice", "structured_historical_data"}:
                    query_limits[claim_id] = max(query_limits[claim_id], 3)
                else:
                    query_limits[claim_id] = max(query_limits[claim_id], 2)
                source_limits[claim_id] = max(source_limits.get(claim_id, 0), 3 if authority_first_ready else 2)
            source_limits[claim_id] = max(source_limits.get(claim_id, 0), 2 if authority_first_ready else 1)
        elif mechanism_type in {"structured_numeric_authority", "date_authority", "event_result_page", "current_status_update"}:
            query_limits[claim_id] = max(query_limits.get(claim_id, 0), 1 if centrality != "core" else 2)
            if preferred_domains or binding_strength >= 3:
                query_limits[claim_id] = max(query_limits[claim_id], 2)
            source_limits[claim_id] = max(source_limits.get(claim_id, 0), 2 if authority_first_ready else 1)
        elif mechanism_type == "relation_sentence":
            query_limits[claim_id] = max(query_limits.get(claim_id, 0), 1)
            if binding_strength >= 3 or priority_label in {"critical", "high"}:
                query_limits[claim_id] = max(query_limits[claim_id], 2)
            source_limits[claim_id] = max(source_limits.get(claim_id, 0), 2)
        elif mechanism_type == "symbolic_compute":
            query_limits[claim_id] = max(query_limits.get(claim_id, 0), 1 if centrality == "core" else 0)
            source_limits[claim_id] = max(source_limits.get(claim_id, 0), 0)
        elif binding_strength >= 3 and priority_label in {"critical", "high"}:
            query_limits[claim_id] = max(query_limits.get(claim_id, 0), 1)
            source_limits[claim_id] = max(source_limits.get(claim_id, 0), 1)
        elif mode == "route_fact" and str(source_intent.get("evidence_target") or "") == "route_relation":
            query_limits[claim_id] = max(query_limits.get(claim_id, 0), 1)
            source_limits[claim_id] = max(source_limits.get(claim_id, 0), 3)
        else:
            query_limits[claim_id] = 0
            skipped.append({"claim_id": claim_id, "reason": "supporting_non_structured_low_value"})
    if "open_route_summary" in triggers and "absolute_route_or_causal" not in triggers:
        route_seen = False
        route_requirement_keys = set()
        extra_route_probe_slots = 1
        reason = "open_route_summary_route_core_budget"
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id") or claim.get("id") or "")
            task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
            source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
            mode = str(source_intent.get("evidence_mode") or "")
            target = str(source_intent.get("evidence_target") or "")
            priority_label = str(task_card.get("priority_label") or "normal")
            requirement_key = route_requirement_signature(claim)
            if is_route_like_claim(claim):
                if not route_seen:
                    query_limits[claim_id] = 2
                    source_limits[claim_id] = 2
                    route_seen = True
                    if requirement_key:
                        route_requirement_keys.add(requirement_key)
                elif priority_label in {"critical", "high"}:
                    query_limits[claim_id] = max(query_limits.get(claim_id, 0), 1)
                    source_limits[claim_id] = max(source_limits.get(claim_id, 0), 2)
                    if requirement_key:
                        route_requirement_keys.add(requirement_key)
                elif (
                    mode == "route_fact"
                    and target == "route_relation"
                    and requirement_key
                    and requirement_key not in route_requirement_keys
                    and extra_route_probe_slots > 0
                ):
                    query_limits[claim_id] = max(query_limits.get(claim_id, 0), 1)
                    source_limits[claim_id] = max(source_limits.get(claim_id, 0), 2)
                    route_requirement_keys.add(requirement_key)
                    extra_route_probe_slots -= 1
                else:
                    query_limits[claim_id] = 0
                    skipped.append({"claim_id": claim_id, "reason": "open_route_summary_extra_route_claim"})
            else:
                query_limits[claim_id] = 0
                skipped.append({"claim_id": claim_id, "reason": "open_route_summary_non_route_skip"})
    if "absolute_route_or_causal" in triggers:
        reason = scope_reason or "absolute_route_or_causal_minimal_budget"
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id") or claim.get("id") or "")
            task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
            source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
            mode = str(source_intent.get("evidence_mode") or "")
            target = str(source_intent.get("evidence_target") or "")
            mechanism_type = str(source_intent.get("mechanism_type") or "")
            priority_label = str(task_card.get("priority_label") or "normal")
            if mode == "route_fact" or target == "route_relation" or mechanism_type == "relation_sentence":
                query_limits[claim_id] = max(query_limits.get(claim_id, 0), 2)
                if priority_label in {"critical", "high"}:
                    query_limits[claim_id] = max(query_limits.get(claim_id, 0), 3)
            else:
                query_limits[claim_id] = min(query_limits.get(claim_id, 1), 1)
            source_limits[claim_id] = max(source_limits.get(claim_id, 0), 2)
    if "resolved_forecast" in triggers or any(
        isinstance(claim, dict)
        and isinstance(claim.get("source_intent"), dict)
        and claim["source_intent"].get("risk_type") == "prediction"
        for claim in claims
    ):
        reason = "prediction_boundary_minimal_budget" if not scope_reason else scope_reason
        forecast_need = normalize_need_type(extracted.get("need_type"))
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id") or claim.get("id") or "")
            centrality = str(claim.get("centrality") or "")
            source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
            task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
            mode = str(source_intent.get("evidence_mode") or "")
            target = str(source_intent.get("evidence_target") or "")
            priority_label = str(task_card.get("priority_label") or "normal")
            keep_two_structured_core_queries = (
                centrality == "core"
                and forecast_need in {"market_movement", "schedule_time", "current_result"}
                and mode in {"numeric_fact", "date_fact", "schedule_fact"}
                and target in {"market_price", "market_calendar", "match_result", "withdrawal_status", "census_phase", "current_status"}
            )
            if centrality == "core" and mode in {"date_fact", "schedule_fact", "event_result", "numeric_fact", "entity_fact"}:
                if keep_two_structured_core_queries:
                    query_limits[claim_id] = max(query_limits.get(claim_id, 0), 2)
                else:
                    query_limits[claim_id] = min(query_limits.get(claim_id, 2), 1)
                source_limits[claim_id] = max(source_limits.get(claim_id, 0), 2)
            elif centrality != "core" and priority_label in {"critical", "high"}:
                query_limits[claim_id] = max(query_limits.get(claim_id, 0), 1)
                source_limits[claim_id] = max(source_limits.get(claim_id, 0), 2)
            elif centrality != "core":
                query_limits[claim_id] = 0
                skipped.append({"claim_id": claim_id, "reason": "prediction_boundary_supporting_skip"})
    has_core_critical = any(label == "core_critical" for label in budget_priority.values())
    if has_core_critical:
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id") or claim.get("id") or "")
            if not claim_id:
                continue
            label = str(budget_priority.get(claim_id) or "")
            source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
            task_card = claim.get("evidence_task_card") if isinstance(claim.get("evidence_task_card"), dict) else {}
            mode = str(source_intent.get("evidence_mode") or "")
            target = str(source_intent.get("evidence_target") or "")
            preferred_domains = source_intent.get("preferred_domains") if isinstance(source_intent.get("preferred_domains"), list) else []
            evidence_shape = str(source_intent.get("evidence_shape") or "")
            priority_label = str(task_card.get("priority_label") or "normal")
            authority_ready = bool(preferred_domains) or evidence_shape in {"authoritative_notice", "structured_historical_data"}
            if label == "core_critical":
                query_limits[claim_id] = max(query_limits.get(claim_id, 0), 3 if mode in {"date_fact", "schedule_fact", "route_fact", "event_result", "numeric_fact"} else 2)
                source_limits[claim_id] = max(
                    source_limits.get(claim_id, 0),
                    3 if authority_ready or mode in {"route_fact", "event_result"} or target in {"market_calendar", "route_relation"} else 2,
                )
                core_claim_budget_reserved.append(claim_id)
                continue
            if label == "supporting_high_risk":
                query_limits[claim_id] = min(max(query_limits.get(claim_id, 0), 1), 2)
                source_limits[claim_id] = min(max(source_limits.get(claim_id, 0), 1), 2 if priority_label in {"critical", "high"} or mode in KEY_EVIDENCE_BUDGET_MODES else 1)
                continue
            if label == "supporting_normal":
                if query_limits.get(claim_id, 0) > 1:
                    query_limits[claim_id] = 1
                if source_limits.get(claim_id, 0) > 1:
                    source_limits[claim_id] = 1
                if query_limits.get(claim_id, 0) > 0 or source_limits.get(claim_id, 0) > 0:
                    supporting_claim_deprioritized.append(claim_id)
                continue
            if label == "peripheral_low":
                if query_limits.get(claim_id, 0) > 0 or source_limits.get(claim_id, 0) > 0:
                    skipped.append({"claim_id": claim_id, "reason": "core_critical_budget_preempts_peripheral"})
                query_limits[claim_id] = 0
                source_limits[claim_id] = 0
                supporting_claim_deprioritized.append(claim_id)
    return {
        "reason": reason,
        "triggers": triggers,
        "claim_ids": claim_ids,
        "query_limits": query_limits,
        "source_limits": source_limits,
        "claim_budget_priority": budget_priority,
        "core_claim_budget_reserved": list(dict.fromkeys(core_claim_budget_reserved)),
        "supporting_claim_deprioritized": list(dict.fromkeys(supporting_claim_deprioritized)),
        "skipped_claims": dedupe_dicts(skipped),
        "expected_risk": "may_reduce_direct_evidence_recall_for_skipped_claims" if skipped else "low",
    }


def attach_atomic_claims_for_retrieval(
    extracted: Dict[str, Any],
    retrieval_claims: List[Dict[str, Any]],
    retrieval_budget: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    atomic_rows = extracted.get("high_risk_atomic_claims") if isinstance(extracted.get("high_risk_atomic_claims"), list) else []
    if not atomic_rows:
        return retrieval_claims, {"applied": False, "reason": "no_atomic_claims"}
    attach_limit = max(0, int(os.environ.get("V2_ATOMIC_CLAIM_ATTACH_LIMIT", "1") or 0))
    query_limit = max(0, int(os.environ.get("V2_ATOMIC_CLAIM_QUERY_LIMIT", "1") or 0))
    high_priority_risks = {str(row.get("risk_type") or "") for row in atomic_rows if isinstance(row, dict)}
    if "phase_boundary_time" in high_priority_risks:
        attach_limit = max(attach_limit, 2)
        query_limit = max(query_limit, 2)
    if attach_limit <= 0 or query_limit <= 0:
        return retrieval_claims, {"applied": False, "reason": "atomic_route_disabled_by_budget"}
    preferred_risks = {
        "market_calendar_status",
        "exclusive_or_only_path",
        "event_result_status",
        "current_position_distance",
        "phase_boundary_time",
    }
    selected_atomic_rows = [
        row
        for row in sorted(
            [row for row in atomic_rows if isinstance(row, dict) and str(row.get("risk_type") or "") in preferred_risks],
            key=lambda row: int(row.get("search_priority") or 0),
            reverse=True,
        )[:attach_limit]
    ]
    if not selected_atomic_rows:
        return retrieval_claims, {"applied": False, "reason": "no_preferred_atomic_claims"}
    retrieval_claims_out = [dict(claim) for claim in retrieval_claims if isinstance(claim, dict)]
    claim_index = {
        str(claim.get("claim_id") or claim.get("id") or ""): claim
        for claim in retrieval_claims_out
        if str(claim.get("claim_id") or claim.get("id") or "")
    }
    all_claims_index = {
        str(claim.get("claim_id") or claim.get("id") or ""): claim
        for claim in claims
        if isinstance(claim, dict) and str(claim.get("claim_id") or claim.get("id") or "")
    }
    trace_rows: List[Dict[str, Any]] = []
    for atomic_row in selected_atomic_rows:
        parent_id = str(atomic_row.get("parent_claim_id") or "")
        if not parent_id:
            inferred_parent = find_parent_claim_for_atomic(str(atomic_row.get("text") or ""), claims)
            parent_id = str(inferred_parent.get("claim_id") or inferred_parent.get("id") or "")
            if parent_id:
                atomic_row = dict(atomic_row)
                atomic_row["parent_claim_id"] = parent_id
        parent_claim = claim_index.get(parent_id)
        parent_added = False
        if parent_claim is None and parent_id in all_claims_index:
            parent_claim = dict(all_claims_index[parent_id])
            retrieval_claims_out.append(parent_claim)
            claim_index[parent_id] = parent_claim
            parent_added = True
        if parent_claim is None:
            trace_rows.append(
                {
                    "atomic_claim_id": atomic_row.get("atomic_claim_id"),
                    "parent_claim_id": parent_id,
                    "risk_type": atomic_row.get("risk_type"),
                    "applied": False,
                    "reason": "parent_claim_missing",
                }
            )
            continue
        parent_claim.setdefault("_atomic_claims_for_retrieval", [])
        if not isinstance(parent_claim.get("_atomic_claims_for_retrieval"), list):
            parent_claim["_atomic_claims_for_retrieval"] = []
        parent_claim["_atomic_claims_for_retrieval"].append(dict(atomic_row))
        parent_claim["query_budget_floor"] = max(int(parent_claim.get("query_budget_floor") or 0), 1)
        parent_claim["source_budget_floor"] = max(int(parent_claim.get("source_budget_floor") or 0), 2)
        budget_query_limits = retrieval_budget.setdefault("query_limits", {})
        budget_source_limits = retrieval_budget.setdefault("source_limits", {})
        budget_query_limits[parent_id] = max(int(budget_query_limits.get(parent_id, 0) or 0), 1)
        budget_source_limits[parent_id] = max(int(budget_source_limits.get(parent_id, 0) or 0), 2)
        trace_rows.append(
            {
                "atomic_claim_id": atomic_row.get("atomic_claim_id"),
                "parent_claim_id": parent_id,
                "risk_type": atomic_row.get("risk_type"),
                "applied": True,
                "parent_added": parent_added,
                "search_priority": atomic_row.get("search_priority"),
                "query": ((atomic_row.get("refutation_target") or {}).get("query") if isinstance(atomic_row.get("refutation_target"), dict) else ""),
            }
        )
    retrieval_budget = dict(retrieval_budget)
    retrieval_budget["atomic_claim_attach_trace"] = trace_rows
    retrieval_budget["atomic_claim_attach_count"] = sum(1 for row in trace_rows if row.get("applied"))
    retrieval_budget["atomic_claim_attach_applied"] = bool(retrieval_budget["atomic_claim_attach_count"])
    return retrieval_claims_out, retrieval_budget


def dedupe_dicts(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for item in items:
        key = tuple(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_semantic_audit_prompt(item: Dict[str, Any], extracted: Dict[str, Any], evidence_bundle: Dict[str, Any], evidence_summary: Dict[str, Any], first_pass: Dict[str, Any]) -> str:
    compact_evidence = compact_evidence_for_verify(evidence_bundle, evidence_summary)
    triggers = semantic_audit_triggers(item, extracted, first_pass)
    return f"""请做语义边界审计。注意：不要因为证据不足判错。

[time]
{item.get('time', '')}

[history_question]
{json.dumps(item.get('history_question', []), ensure_ascii=False)}

[question]
{item.get('question', '')}

[answer]
{item.get('answer', '')}

[extracted]
{json.dumps(extracted, ensure_ascii=False)}

[compact_evidence]
{json.dumps(compact_evidence, ensure_ascii=False)}

[first_pass]
{json.dumps(first_pass, ensure_ascii=False)}

[candidate_triggers]
{json.dumps(triggers, ensure_ascii=False)}

要求：
- 如果只是证据不足，final_label 必须是 2。
- 如果是强绝对化路线/因果断言且直接回答主需，final_label 可为 0。
- 如果是预测确定化且影响主需，final_label 可为 0。
- 如果主需基本正确但附带细节污染，final_label 可为 1。
- 如果是开放路线概括，final_label 应为 2。
"""


# 15. Verify 输入构造：把 claims、压缩证据和结构化证据摘要交给裁决模型。
def build_verify_prompt(item: Dict[str, Any], extracted: Dict[str, Any], evidence_bundle: Dict[str, Any], evidence_summary: Dict[str, Any]) -> str:
    compact_evidence = compact_evidence_for_verify(evidence_bundle, evidence_summary)
    evidence_ledger = evidence_summary.get("_evidence_ledger") if isinstance(evidence_summary.get("_evidence_ledger"), dict) else {}
    core_assertion_audit = evidence_summary.get("_core_assertion_audit") if isinstance(evidence_summary.get("_core_assertion_audit"), dict) else {}
    cross_claim_consistency = evidence_summary.get("_cross_claim_consistency") if isinstance(evidence_summary.get("_cross_claim_consistency"), dict) else {}
    return f"""请基于下面信息判断最终标签。

[time]
{item.get('time', '')}

[question]
{item.get('question', '')}

[answer]
{item.get('answer', '')}

[extracted]
{json.dumps(extracted, ensure_ascii=False)}

[compact_evidence]
{json.dumps(compact_evidence, ensure_ascii=False)}

[evidence_ledger]
{json.dumps(evidence_ledger, ensure_ascii=False)}

[core_assertion_audit]
{json.dumps(core_assertion_audit, ensure_ascii=False)}

[cross_claim_consistency]
{json.dumps(cross_claim_consistency, ensure_ascii=False)}

要求：
- 先逐个claims判断，再聚合 final_label。
- final_label 只能是 0/1/2。
- 如果 evidence_ledger 没有 refuted_points，不要把未闭合/未拿到证据包装成事实错误。
- 如果 core_assertion_audit 或 cross_claim_consistency 提示表层事实命中但核心断言未闭合，claim verdict 应优先为 uncertain，并在 counter_evidence_check 写明缺口。
- 每条 claim_verdict 尽量补充 initial_verdict、counter_evidence_check、contradiction_found、needs_consistency_review、evidence_ledger_used、abstain_reason。
- analyse 只写决定标签的关键错误点。
"""


# 16. Review 输入构造：只在低置信度高风险标签时复核。
def build_review_prompt(item: Dict[str, Any], extracted: Dict[str, Any], evidence_bundle: Dict[str, Any], evidence_summary: Dict[str, Any], first_pass: Dict[str, Any]) -> str:
    compact_evidence = compact_evidence_for_verify(evidence_bundle, evidence_summary)
    return f"""请复核前一次结果是否过严或过松。

[time]
{item.get('time', '')}

[question]
{item.get('question', '')}

[answer]
{item.get('answer', '')}

[extracted]
{json.dumps(extracted, ensure_ascii=False)}

[compact_evidence]
{json.dumps(compact_evidence, ensure_ascii=False)}

[first_pass]
{json.dumps(first_pass, ensure_ascii=False)}

只输出复核后的 JSON。
"""


def build_final_reason_prompt(
    item: Dict[str, Any],
    extracted: Dict[str, Any],
    evidence_bundle: Dict[str, Any],
    evidence_summary: Dict[str, Any],
    verify_obj: Dict[str, Any],
    draft_reason: str,
) -> str:
    compact_evidence = compact_evidence_for_verify(evidence_bundle, evidence_summary)
    payload = {
        "final_label": verify_obj.get("final_label"),
        "decision_basis": verify_obj.get("_decision_basis"),
        "decision_policy": verify_obj.get("_decision_policy") or verify_obj.get("_calibration_override") or verify_obj.get("_semantic_audit"),
        "decision_policy_explanation": verify_obj.get("_decision_policy_explanation") or "",
        "draft_reason": draft_reason,
        "conflict_issues": final_reason_conflict_issues(
            draft_reason,
            pick_label(verify_obj.get("final_label")) or LABEL_2,
            str(verify_obj.get("_decision_basis") or ""),
            evidence_summary,
        ),
        "claim_verdicts": verify_obj.get("claim_verdicts") or [],
    }
    return f"""请重写最终 reason，只改写原因，不改标签。

[time]
{item.get('time', '')}

[question]
{item.get('question', '')}

[answer]
{item.get('answer', '')}

[extracted]
{json.dumps(extracted, ensure_ascii=False)}

[compact_evidence]
{json.dumps(compact_evidence, ensure_ascii=False)}

[current_decision]
{json.dumps(payload, ensure_ascii=False)}

重写要求：
- reason 必须解释 final_label，不能和 final_label 反着说。
- 如果 final_label 是 0/1，不得写“无事实错误、不能判错、只能判证据不足”。
- 如果 final_label 是 2，不得写“构成事实错误”。
- 如果 decision_basis 是 evidence_refutation，必须只引用 compact_evidence 中真实存在的反驳点。
- 如果 decision_basis 是 evidence_support，必须只引用 compact_evidence 中真实存在的支持点。
- 如果 decision_basis 是 rubric_fallback 或 rubric_fallback_with_partial_evidence，要明确这是风险先验补判，不要伪装成直接证据裁决。
- 如果没有 direct/refuting points，不要伪装成“证据显示错误”。
- 不得把“没有证据支持/证据不足”本身写成事实错误依据；证据不足只能作为背景，真正依据必须是预测确定化、绝对化核心断言、虚构污染、主次结构化细节风险等通用风险。

输出 JSON。"""


# 17. 标签工具与聚合：规范化标签，并用 claim verdict 兜底修正 final_label。
def pick_label(label_value: Any) -> Optional[str]:
    text = "" if label_value is None else str(label_value).strip()
    if text in VALID_LABELS:
        return text
    if text in {"0", "1", "2"}:
        return {"0": LABEL_0, "1": LABEL_1, "2": LABEL_2}[text]
    return None


# 18. 聚合逻辑：根据 claim 级 verdict 和置信度，稳定生成最终标签。
def evidence_override_label(extracted: Dict[str, Any], evidence_summary: Optional[Dict[str, Any]]) -> Tuple[Optional[str], str]:
    if not isinstance(evidence_summary, dict):
        return None, ""
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    need_type = normalize_need_type(extracted.get("need_type"))
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        centrality = str(claim.get("centrality") or "")
        if centrality != "core":
            continue
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        mode = str(summary.get("evidence_mode") or (claim.get("source_intent") or {}).get("evidence_mode") or "")
        mechanism_type = claim_mechanism_type(claim, summary)
        direct_refuting = claim_direct_refuting_points(summary)
        if not direct_refuting:
            continue
        if claim_has_new_scheme_strong_refutation(claim, summary, need_type):
            if mechanism_type in {"structured_numeric_authority", "date_authority", "event_result_page", "current_status_update"}:
                return LABEL_0, f"core high-value claim {claim_id} has direct object-aligned refuting evidence"
            if mechanism_type == "relation_sentence" or mode == "route_fact":
                return LABEL_0, f"core relation claim {claim_id} has direct refuting route evidence"
            if mode == "numeric_fact":
                return LABEL_0, f"core numeric claim {claim_id} has direct official refuting evidence"
    return None, ""


def point_is_sports_result_context(point: Dict[str, Any]) -> bool:
    text = " ".join(
        str(point.get(key) or "")
        for key in ("title", "detail", "url", "snippet")
    ).lower()
    if "/player/" in text or "/players/" in text:
        return False
    context_markers = (
        "box score", "boxscore", "game", "games", "recap", "schedule", "final",
        "score", "match", " vs ", " v ", "比分", "赛果", "战报", "技术统计",
    )
    return any(marker in text for marker in context_markers)


def point_is_strong_refutation(
    point: Dict[str, Any],
    need_type: str = "general_fact",
    claim: Optional[Dict[str, Any]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> bool:
    summary = summary if isinstance(summary, dict) else {}
    claim = claim if isinstance(claim, dict) else {}
    if point.get("direct_answer") != "direct":
        return False
    if point.get("source_type") not in {"official", "news"}:
        return False
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
    point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
    conflict_profile = (
        point_conversion.get("candidate_conflict_profile")
        if isinstance(point_conversion.get("candidate_conflict_profile"), dict)
        else {}
    )
    slot_contract_state = normalize_text(str(point_conversion.get("slot_contract_state") or "")).lower()
    slot_missing = point_conversion.get("slot_missing") if isinstance(point_conversion.get("slot_missing"), list) else []
    same_slot_ready = bool(
        point.get("same_slot_conflict_ready")
        or point_conversion.get("same_slot_conflict_ready")
        or conflict_profile.get("same_slot_conflict_ready")
    )
    blocked_by_slot_context = (
        mode in {"numeric_fact", "date_fact", "schedule_fact"}
        and not same_slot_ready
        and slot_contract_state != "same_slot_ready"
        and (
            "time_scope" in {str(slot) for slot in slot_missing}
            or str(conflict_profile.get("block_reason") or "") == "slot_context_not_aligned"
            or str(point_conversion.get("direct_candidate_gap_reason") or "") in {"numeric_reference_only", "date_only", "related_only"}
        )
    )
    if blocked_by_slot_context:
        return False
    contract = point.get("comparability_contract") if isinstance(point.get("comparability_contract"), dict) else point_comparability_contract(point, claim, summary)
    if str(contract.get("comparability_status") or "") != "comparable":
        return False
    if normalize_text(str(point.get("numeric_contract_note") or "")) == "time_scope_mismatch":
        return False
    point_contract_status = normalize_text(str(point.get("point_contract_status") or "")).lower()
    point_contract_risks = [
        normalize_text(str(risk))
        for risk in (point.get("point_contract_risks") or [])
        if normalize_text(str(risk))
    ]
    evidence_contract_risks = [
        normalize_text(str(risk))
        for risk in (point.get("evidence_contract_risks") or [])
        if normalize_text(str(risk))
    ]
    if point_contract_status == "failed":
        return False
    if any(risk in {"point_time_scope_mismatch", "time_scope_not_bound_to_metric_point"} for risk in point_contract_risks + evidence_contract_risks):
        return False
    if any(risk in {"missing_binding_time_scope", "missing_time_scope", "date_window_mismatch"} for risk in evidence_contract_risks):
        return False
    if int(point.get("event_window_score", 0) or 0) < 0:
        return False
    url = str(point.get("url") or "").lower().rstrip("/")
    if url in {"https://nba.com", "https://www.nba.com", "https://nba.com/news", "https://www.nba.com/news"}:
        return False
    if need_type == "sports_result" and not point_is_sports_result_context(point):
        return False
    return True


def point_is_strong_support(
    point: Dict[str, Any],
    need_type: str = "general_fact",
    claim: Optional[Dict[str, Any]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> bool:
    if point.get("direct_answer") != "direct":
        return False
    if point.get("source_type") not in {"official", "news"}:
        return False
    contract = point.get("comparability_contract") if isinstance(point.get("comparability_contract"), dict) else point_comparability_contract(point, claim, summary)
    if str(contract.get("comparability_status") or "") != "comparable":
        return False
    if normalize_text(str(point.get("numeric_contract_note") or "")) == "time_scope_mismatch":
        return False
    point_contract_status = normalize_text(str(point.get("point_contract_status") or "")).lower()
    point_contract_risks = [
        normalize_text(str(risk))
        for risk in (point.get("point_contract_risks") or [])
        if normalize_text(str(risk))
    ]
    evidence_contract_risks = [
        normalize_text(str(risk))
        for risk in (point.get("evidence_contract_risks") or [])
        if normalize_text(str(risk))
    ]
    if point_contract_status == "failed":
        return False
    if any(risk in {"point_time_scope_mismatch", "time_scope_not_bound_to_metric_point"} for risk in point_contract_risks + evidence_contract_risks):
        return False
    if any(risk in {"missing_binding_time_scope", "missing_time_scope", "date_window_mismatch"} for risk in evidence_contract_risks):
        return False
    if int(point.get("event_window_score", 0) or 0) < 0:
        return False
    if need_type == "sports_result" and not point_is_sports_result_context(point):
        return False
    return True


SECONDARY_DETAIL_REFUTATION_POINT_TYPES = {
    "numeric_mismatch",
    "date_mismatch",
    "route_conflict",
    "status_mismatch",
    "event_mismatch",
    "policy_mismatch",
    "entity_mismatch",
}


def point_is_secondary_detail_refutation(
    point: Dict[str, Any],
    need_type: str = "general_fact",
    claim: Optional[Dict[str, Any]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> bool:
    claim = claim if isinstance(claim, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    if point.get("direct_answer") != "direct":
        return False
    if point.get("source_type") not in {"official", "news"}:
        return False
    contract = point.get("comparability_contract") if isinstance(point.get("comparability_contract"), dict) else point_comparability_contract(point, claim, summary)
    if str(contract.get("comparability_status") or "") != "comparable":
        return False
    if normalize_text(str(point.get("numeric_contract_note") or "")) == "time_scope_mismatch":
        return False
    point_contract_status = normalize_text(str(point.get("point_contract_status") or "")).lower()
    point_contract_risks = [
        normalize_text(str(risk))
        for risk in (point.get("point_contract_risks") or [])
        if normalize_text(str(risk))
    ]
    evidence_contract_risks = [
        normalize_text(str(risk))
        for risk in (point.get("evidence_contract_risks") or [])
        if normalize_text(str(risk))
    ]
    if point_contract_status == "failed":
        return False
    hard_risks = {
        "point_time_scope_mismatch",
        "date_window_mismatch",
    }
    if any(risk in hard_risks for risk in point_contract_risks + evidence_contract_risks):
        return False
    if int(point.get("event_window_score", 0) or 0) < 0:
        return False
    point_type = normalize_text(str(point.get("type") or "")).lower()
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    mode = normalize_text(str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or ""))
    centrality = str(claim.get("centrality") or "")
    direct_supporting = claim_direct_supporting_points(summary)
    if (
        point_type == "date_mismatch"
        and point.get("source_type") != "official"
        and (
            bool(direct_supporting)
            or (
                centrality in {"supporting", "peripheral"}
                and mode in {"date_fact", "schedule_fact"}
            )
        )
    ):
        return False
    if point_type in SECONDARY_DETAIL_REFUTATION_POINT_TYPES:
        return True
    numeric_alignment = point.get("numeric_alignment") if isinstance(point.get("numeric_alignment"), dict) else {}
    if need_type == "financial_quote" and point_type == "numeric_mismatch" and normalize_bool(numeric_alignment.get("comparable"), False):
        return True
    if point_type in {"numeric_mismatch", "date_mismatch"} and normalize_bool(numeric_alignment.get("comparable"), False):
        claim_value = normalize_text(str(point.get("claim_value") or ""))
        evidence_value = normalize_text(str(point.get("evidence_value") or ""))
        if claim_value and evidence_value and claim_value != evidence_value:
            return True
    if point_type == "route_conflict":
        route_relation = point.get("route_relation") if isinstance(point.get("route_relation"), dict) else {}
        if route_relation.get("directly_answers_route") and route_relation.get("has_relation_marker"):
            return True
    return False


HIGH_VALUE_MECHANISMS = {
    "structured_numeric_authority",
    "date_authority",
    "event_result_page",
    "relation_sentence",
    "current_status_update",
}


def claim_mechanism_type(claim: Dict[str, Any], summary: Optional[Dict[str, Any]] = None) -> str:
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    return normalize_text(
        str(
            summary.get("mechanism_type")
            or source_intent.get("mechanism_type")
            or ""
        )
    )


def claim_direct_refuting_points(summary: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary = summary if isinstance(summary, dict) else {}
    refuting = [point for point in summary.get("refuting_points") or [] if isinstance(point, dict)]
    return [point for point in refuting if point.get("direct_answer") == "direct"]


def claim_direct_supporting_points(summary: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary = summary if isinstance(summary, dict) else {}
    supporting = [point for point in summary.get("supporting_points") or [] if isinstance(point, dict)]
    return [point for point in supporting if point.get("direct_answer") == "direct"]


def extract_single_numeric_amount(text: str) -> Optional[float]:
    normalized = normalize_text(str(text or ""))
    if not normalized:
        return None
    matches = re.findall(r"-?\d+(?:\.\d+)?", normalized)
    if len(matches) != 1:
        return None
    try:
        return float(matches[0])
    except Exception:
        return None


def values_share_same_quantity_basis(claim_value: str, evidence_value: str, numeric_alignment: Dict[str, Any]) -> bool:
    claim_amount = extract_single_numeric_amount(claim_value)
    evidence_amount = extract_single_numeric_amount(evidence_value)
    if claim_amount is None or evidence_amount is None:
        return True
    family = normalize_text(str(numeric_alignment.get("family") or "")).lower()
    claim_unit = normalize_text(str(numeric_alignment.get("claim_unit_signature") or "")).lower()
    evidence_unit = normalize_text(str(numeric_alignment.get("evidence_unit_signature") or "")).lower()
    if claim_unit and evidence_unit and claim_unit == evidence_unit and family in {"money", "number"}:
        return abs(claim_amount - evidence_amount) < 1e-9
    return True


def point_comparability_contract(
    point: Dict[str, Any],
    claim: Optional[Dict[str, Any]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    point = point if isinstance(point, dict) else {}
    claim = claim if isinstance(claim, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
    point_type = normalize_text(str(point.get("type") or "")).lower()
    direct_answer = str(point.get("direct_answer") or "")
    numeric_alignment = point.get("numeric_alignment") if isinstance(point.get("numeric_alignment"), dict) else {}
    point_contract_risks = {
        normalize_text(str(risk)).lower()
        for risk in (point.get("point_contract_risks") or [])
        if normalize_text(str(risk))
    }
    evidence_contract_risks = {
        normalize_text(str(risk)).lower()
        for risk in (point.get("evidence_contract_risks") or [])
        if normalize_text(str(risk))
    }
    hard_time_risks = {
        "point_time_scope_mismatch",
        "time_scope_not_bound_to_metric_point",
        "missing_binding_time_scope",
        "missing_time_scope",
        "date_window_mismatch",
    }
    metric_match = True
    entity_match = True
    time_role_match = True
    unit_match_or_normalizable = True
    granularity_match = True
    status = "comparable"
    reasons: List[str] = []
    if normalize_text(str(point.get("numeric_contract_note") or "")) == "time_scope_mismatch":
        time_role_match = False
        reasons.append("numeric_contract_time_scope_mismatch")
    if any(risk in hard_time_risks for risk in point_contract_risks | evidence_contract_risks):
        time_role_match = False
        reasons.append("time_scope_risk")
    if int(point.get("event_window_score", 0) or 0) < 0:
        time_role_match = False
        reasons.append("negative_event_window")
    if mode in {"numeric_fact", "date_fact", "schedule_fact"}:
        if mode in {"date_fact", "schedule_fact"} and point_type in {"date_match", "date_mismatch", "date_reference"}:
            metric_match = True
            entity_match = True
        elif numeric_alignment:
            metric_match = normalize_bool(numeric_alignment.get("comparable"), False)
            object_overlap = numeric_alignment.get("object_overlap") if isinstance(numeric_alignment.get("object_overlap"), list) else []
            entity_match = bool(object_overlap)
            claim_unit = normalize_text(str(numeric_alignment.get("claim_unit_signature") or "")).lower()
            evidence_unit = normalize_text(str(numeric_alignment.get("evidence_unit_signature") or "")).lower()
            unit_match_or_normalizable = bool(claim_unit and evidence_unit and claim_unit == evidence_unit)
            granularity_match = values_share_same_quantity_basis(
                str(point.get("claim_value") or ""),
                str(point.get("evidence_value") or ""),
                numeric_alignment,
            )
            mismatch_reason = normalize_text(str(numeric_alignment.get("mismatch_reason") or "")).lower()
            if mismatch_reason:
                reasons.append(mismatch_reason)
            if not entity_match:
                reasons.append("object_overlap_missing")
        else:
            metric_match = point_type in {"date_match", "date_mismatch"}
            entity_match = normalize_text(str(point.get("evidence_contract_status") or "")).lower() == "satisfied"
            unit_match_or_normalizable = mode not in {"numeric_fact"}
    elif mode == "event_result":
        metric_match = point_type in {"event_answer_candidate", "event_mismatch", "status_mismatch"} or point_is_sports_result_context(point)
        entity_match = point_is_sports_result_context(point) or normalize_text(str(point.get("evidence_contract_status") or "")).lower() == "satisfied"
    elif mode == "route_fact":
        route_relation = point.get("route_relation") if isinstance(point.get("route_relation"), dict) else {}
        metric_match = point_type in {"route_conflict", "route_support"} or normalize_bool(route_relation.get("directly_answers_route"), False)
        entity_match = normalize_bool(route_relation.get("has_relation_marker"), False) or normalize_text(str(point.get("evidence_contract_status") or "")).lower() == "satisfied"
    else:
        metric_match = True
        entity_match = True
    if mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result", "route_fact"}:
        if metric_match and entity_match and time_role_match and unit_match_or_normalizable and granularity_match:
            status = "comparable"
        else:
            related_signals = bool(numeric_alignment) or direct_answer in {"direct", "partial", "related_only"} or bool(point_contract_risks) or bool(evidence_contract_risks)
            status = "partial_but_incomparable" if related_signals else "unsupported"
    return {
        "metric_match": metric_match,
        "entity_match": entity_match,
        "time_role_match": time_role_match,
        "unit_match_or_normalizable": unit_match_or_normalizable,
        "granularity_match": granularity_match,
        "comparability_status": status,
        "reasons": dedupe_keep_order(reasons),
    }


def claim_comparability_profile(
    claim: Dict[str, Any],
    summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    summary = summary if isinstance(summary, dict) else {}
    profile = {
        "comparable_direct_support_count": 0,
        "comparable_direct_refute_count": 0,
        "incomparable_direct_count": 0,
        "incomparable_any_count": 0,
        "unsupported_any_count": 0,
        "comparability_status": "unsupported",
    }
    any_related = False
    for bucket in ("supporting_points", "refuting_points", "uncertain_points"):
        for point in (summary.get(bucket) or []):
            if not isinstance(point, dict):
                continue
            contract = point.get("comparability_contract") if isinstance(point.get("comparability_contract"), dict) else point_comparability_contract(point, claim, summary)
            point["comparability_contract"] = contract
            state = str(contract.get("comparability_status") or "unsupported")
            if point.get("direct_answer") in {"direct", "partial", "related_only"} or contract.get("reasons"):
                any_related = True
            if state == "comparable":
                if bucket == "supporting_points" and point.get("direct_answer") == "direct":
                    profile["comparable_direct_support_count"] += 1
                elif bucket == "refuting_points" and point.get("direct_answer") == "direct":
                    profile["comparable_direct_refute_count"] += 1
            elif state == "partial_but_incomparable":
                profile["incomparable_any_count"] += 1
                if point.get("direct_answer") == "direct":
                    profile["incomparable_direct_count"] += 1
            else:
                profile["unsupported_any_count"] += 1
    if str((summary.get("point_conversion") or {}).get("stage") or "") == "direct_not_converted":
        profile["incomparable_any_count"] += 1
    if profile["comparable_direct_support_count"] > 0 or profile["comparable_direct_refute_count"] > 0:
        profile["comparability_status"] = "comparable"
    elif profile["incomparable_any_count"] > 0:
        profile["comparability_status"] = "partial_but_incomparable"
    elif any_related:
        profile["comparability_status"] = "unsupported"
    return profile


def attach_comparability_profiles(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> None:
    if not isinstance(evidence_summary, dict):
        return
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id)
        if not isinstance(summary, dict):
            continue
        summary["comparability_profile"] = claim_comparability_profile(claim, summary)


def point_has_comparable_direct_refutation(
    point: Dict[str, Any],
    claim: Optional[Dict[str, Any]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> bool:
    contract = point.get("comparability_contract") if isinstance(point.get("comparability_contract"), dict) else point_comparability_contract(point, claim, summary)
    return str(contract.get("comparability_status") or "") == "comparable"


def point_is_stable_logic_detail_refutation(
    point: Dict[str, Any],
    claim: Optional[Dict[str, Any]] = None,
) -> bool:
    if not isinstance(point, dict):
        return False
    if str(point.get("source_type") or "") != "computed":
        return False
    text = normalize_text(str(point.get("evidence_sentence") or ""))
    if not text:
        return False
    if not re.search(r"(应为|应该为|合计应为|总计应为|应当为)", text):
        return False
    if not re.search(r"(而不是|不是|而非)", text):
        return False
    claim_text = normalize_text(str((claim or {}).get("claim") or ""))
    title = normalize_text(str(point.get("title") or ""))
    if ("交锋战绩逻辑计算" in title or "总计应为2-1，而不是2-2" in text) and claim_text:
        if not re.search(r"(交锋|交手|总战绩|赛季交锋|常规赛交锋)", claim_text):
            return False
    claim_value = normalize_text(str(point.get("claim_value") or ""))
    evidence_value = normalize_text(str(point.get("evidence_value") or ""))
    if claim_value and evidence_value and claim_value != evidence_value:
        return True
    return bool(re.search(r"\d", text))


def claim_has_new_scheme_strong_refutation(
    claim: Dict[str, Any],
    summary: Optional[Dict[str, Any]],
    need_type: str,
) -> bool:
    summary = summary if isinstance(summary, dict) else {}
    mechanism_type = claim_mechanism_type(claim, summary)
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
    coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
    point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
    coverage_level = str(coverage.get("coverage_level") or "")
    direct_support_refute_count = int(point_conversion.get("direct_support_refute_count") or 0)
    direct_refuting = claim_direct_refuting_points(summary)
    if not direct_refuting:
        return False
    if direct_refutation_blocked_by_date_only_guard(summary, mode):
        return False
    strong_direct = [point for point in direct_refuting if point_is_strong_refutation(point, need_type, claim, summary)]
    if mode == "date_fact" and any(
        point.get("type") == "date_mismatch" and point.get("source_type") == "official"
        for point in (summary.get("refuting_points") or [])
        if isinstance(point, dict)
    ):
        return True
    if mechanism_type in HIGH_VALUE_MECHANISMS:
        if not strong_direct:
            return False
        if need_type == "financial_quote":
            return any(point.get("source_type") == "official" for point in strong_direct)
        if mechanism_type == "relation_sentence":
            return direct_support_refute_count > 0 or coverage_level in {"strong", "moderate"}
        return True
    if mode == "numeric_fact":
        if need_type == "financial_quote":
            return any(point.get("source_type") == "official" for point in strong_direct)
        return bool(strong_direct)
    if mode == "route_fact":
        return bool(strong_direct) and (direct_support_refute_count > 0 or len(direct_refuting) >= 2)
    return bool(strong_direct)


def claim_has_new_scheme_strong_support(
    claim: Dict[str, Any],
    summary: Optional[Dict[str, Any]],
    need_type: str,
) -> bool:
    summary = summary if isinstance(summary, dict) else {}
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    mechanism_type = claim_mechanism_type(claim, summary)
    mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
    coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
    coverage_level = str(coverage.get("coverage_level") or "")
    point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
    direct_support_refute_count = int(point_conversion.get("direct_support_refute_count") or 0)
    direct_supporting = claim_direct_supporting_points(summary)
    direct_refuting = claim_direct_refuting_points(summary)
    if not direct_supporting or direct_refuting:
        return False
    strong_direct = [point for point in direct_supporting if point_is_strong_support(point, need_type, claim, summary)]
    if not strong_direct:
        return False
    high_value_support_modes = {"numeric_fact", "date_fact", "schedule_fact", "event_result", "policy_fact", "route_fact", "entity_fact"}
    if mechanism_type in HIGH_VALUE_MECHANISMS:
        return coverage_level in {"strong", "moderate"} or direct_support_refute_count > 0
    if mode in high_value_support_modes:
        if coverage_level in {"strong", "moderate"}:
            return True
        return any(normalize_text(str(point.get("point_contract_status") or "")).lower() == "satisfied" for point in strong_direct)
    return False


def has_new_scheme_core_refuting_evidence(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> bool:
    if not isinstance(evidence_summary, dict):
        return False
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    need_type = normalize_need_type(extracted.get("need_type"))
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if str(claim.get("centrality") or "") != "core":
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        if claim_has_new_scheme_strong_refutation(claim, summary, need_type):
            return True
    return False


def has_new_scheme_core_supporting_evidence(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> bool:
    if not isinstance(evidence_summary, dict):
        return False
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    need_type = normalize_need_type(extracted.get("need_type"))
    core_claims = [claim for claim in claims if isinstance(claim, dict) and str(claim.get("centrality") or "") == "core"]
    if not core_claims:
        return False
    supported_core = 0
    for claim in core_claims:
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        if claim_has_new_scheme_strong_refutation(claim, summary, need_type):
            return False
        if claim_has_new_scheme_strong_support(claim, summary, need_type):
            supported_core += 1
            continue
        return False
    return supported_core == len(core_claims)


def claim_has_new_scheme_decidable_evidence(
    claim: Dict[str, Any],
    summary: Optional[Dict[str, Any]],
    need_type: str,
) -> bool:
    return (
        claim_has_new_scheme_strong_refutation(claim, summary, need_type)
        or claim_has_new_scheme_strong_support(claim, summary, need_type)
    )


def direct_refutation_blocked_by_date_only_guard(summary: Dict[str, Any], mode: str) -> bool:
    if mode in {"date_fact", "schedule_fact"}:
        return False
    phase_graph = summary.get("phase_graph") if isinstance(summary.get("phase_graph"), dict) else {}
    if int(phase_graph.get("date_only_guard_block_count") or 0) <= 0:
        return False
    direct_refuting = claim_direct_refuting_points(summary)
    if not direct_refuting:
        return False
    date_like_count = 0
    for point in direct_refuting:
        if not isinstance(point, dict):
            continue
        point_type = normalize_text(str(point.get("type") or point.get("conflict_type") or "")).lower()
        conflict_slot = normalize_text(str(point.get("conflict_slot") or "")).lower()
        direct_gate = normalize_text(str(point.get("direct_evidence_gate_result") or "")).lower()
        if (
            "date" in point_type
            or "time" in point_type
            or "date" in conflict_slot
            or "time" in conflict_slot
            or direct_gate in {"date_mismatch", "time_mismatch"}
        ):
            date_like_count += 1
    return date_like_count > 0 and date_like_count == len(direct_refuting)


def atomic_refutation_decision_signal(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    ledger = (
        evidence_summary.get("_evidence_ledger")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("_evidence_ledger"), dict)
        else {}
    )
    if not ledger:
        return {}
    rows = ledger.get("atomic_label_pressure") if isinstance(ledger.get("atomic_label_pressure"), list) else []
    strong_rows = [
        row for row in rows
        if isinstance(row, dict) and str(row.get("state") or "") == "strong_refutation"
    ]
    if not strong_rows:
        return {}
    core_row = next((row for row in strong_rows if str(row.get("label") or "") == LABEL_0), None)
    chosen = core_row or strong_rows[0]
    label = str(chosen.get("label") or LABEL_1)
    if label not in {LABEL_0, LABEL_1}:
        label = LABEL_1
    return {
        "label": label,
        "decision_basis": "evidence_refutation",
        "policy": "atomic_core_direct_refutation" if label == LABEL_0 else "atomic_secondary_direct_refutation",
        "decision_channel": DECISION_CHANNEL_DIRECT_WEB,
        "decision_scope": "atomic",
        "decision_channel_confidence": 0.92 if label == LABEL_0 else 0.88,
    }


def has_new_scheme_decidable_evidence(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> bool:
    return bool(evidence_first_decision_signal(extracted, evidence_summary) or atomic_refutation_decision_signal(extracted, evidence_summary))


def evidence_first_decision_signal(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    if not isinstance(evidence_summary, dict):
        return {}
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    need_type = normalize_need_type(extracted.get("need_type"))
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if str(claim.get("centrality") or "") != "core":
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        if claim_has_new_scheme_strong_refutation(claim, summary, need_type):
            return {
                "label": LABEL_0,
                "decision_basis": "evidence_refutation",
                "policy": "evidence_first_core_direct_refutation",
                "decision_channel": DECISION_CHANNEL_DIRECT_WEB,
                "decision_scope": "core",
                "decision_channel_confidence": 0.95,
            }
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if str(claim.get("centrality") or "") not in {"supporting", "peripheral"}:
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        detail_state = detail_claim_resolution_state(claim, summary, need_type)
        if str(detail_state.get("state") or "") == "decidable_error":
            detail_reason = str(detail_state.get("reason") or "")
            return {
                "label": LABEL_1,
                "decision_basis": "evidence_refutation",
                "policy": "secondary_detail_direct_refutation",
                "decision_channel": (
                    DECISION_CHANNEL_CLOSURE if detail_reason == "stable_logic_refutation" else DECISION_CHANNEL_DIRECT_WEB
                ),
                "decision_scope": "secondary_detail",
                "decision_channel_confidence": 0.86 if detail_reason == "stable_logic_refutation" else 0.9,
            }
    atomic_signal = atomic_refutation_decision_signal(extracted, evidence_summary)
    if atomic_signal:
        return atomic_signal
    if has_new_scheme_core_supporting_evidence(extracted, evidence_summary) and not has_unresolved_high_risk_detail_claims(extracted, evidence_summary):
        return {
            "label": LABEL_2,
            "decision_basis": "evidence_support",
            "policy": "evidence_first_core_direct_support",
            "decision_channel": DECISION_CHANNEL_UNRESOLVED,
            "decision_scope": "core_supported",
            "decision_channel_confidence": 0.7,
        }
    return {}


def build_evidence_non_decidable_state(
    item: Optional[Dict[str, Any]],
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    item = item if isinstance(item, dict) else {}
    evidence_signal = evidence_first_decision_signal(extracted, evidence_summary)
    if evidence_signal:
        return {
            "state": "direct_decidable",
            "reason": str(evidence_signal.get("policy") or "direct_decision_available"),
            "unsupported_claim_count": 0,
            "partial_but_incomparable_count": 0,
            "has_fictional_contamination": False,
            "certainty_profile": answer_certainty_profile(str(item.get("answer") or "")),
        }
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    need_type = normalize_need_type(extracted.get("need_type"))
    answer_text = normalize_text(str(item.get("answer") or ""))
    question_text = normalize_text(str(item.get("question") or ""))
    certainty_profile = answer_certainty_profile(answer_text)
    unsupported_claim_count = 0
    partial_but_incomparable_count = 0
    any_related_material = False
    checkable_claim_count = 0
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if str(claim.get("checkability") or "checkable") != "checkable":
            continue
        checkable_claim_count += 1
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
        coverage_level = str(coverage.get("coverage_level") or "")
        profile = summary.get("comparability_profile") if isinstance(summary.get("comparability_profile"), dict) else claim_comparability_profile(claim, summary)
        direct_points = claim_direct_supporting_points(summary) + claim_direct_refuting_points(summary)
        comparable_direct_count = int(profile.get("comparable_direct_support_count") or 0) + int(profile.get("comparable_direct_refute_count") or 0)
        if comparable_direct_count > 0:
            any_related_material = True
            continue
        all_points = [
            point
            for key in ("supporting_points", "refuting_points", "uncertain_points")
            for point in (summary.get(key) or [])
            if isinstance(point, dict)
        ]
        point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
        stage = str(point_conversion.get("stage") or "")
        has_candidates = bool(summary.get("evidence_sentence_candidates"))
        incomparable_like = str(profile.get("comparability_status") or "") == "partial_but_incomparable"
        related_material = (
            coverage_level in {"weak", "partial", "moderate", "strong"}
            or bool(all_points)
            or has_candidates
        )
        any_related_material = any_related_material or related_material
        if incomparable_like:
            partial_but_incomparable_count += 1
        elif coverage_level in UNSUPPORTED_COVERAGE_LEVELS or not related_material:
            unsupported_claim_count += 1
    fictional_contamination = False
    if need_type in {"current_geopolitical_status", "geopolitical_claim"}:
        fictional_contamination = any(token in answer_text for token in ["虚构", "剧本", "假设", "AI生成", "非真实新闻"])
        if not fictional_contamination:
            fictional_contamination = bool(re.search(r"(未来场景|未来剧本|模拟推演|虚构设定)", answer_text + " " + question_text))
    if fictional_contamination:
        state = "fictional_contamination_suspected"
        reason = "fictional_contamination_signal"
    elif partial_but_incomparable_count > 0:
        state = "partial_but_incomparable"
        reason = "related_material_found_but_not_comparable"
    elif unsupported_claim_count > 0 or not any_related_material:
        state = "unsupported"
        reason = "no_direct_decidable_evidence"
    else:
        state = "abstain_no_judge"
        reason = "open_or_weakly_checkable_without_direct_decision"
    if checkable_claim_count == 0:
        state = "abstain_no_judge"
        reason = "no_checkable_claims"
    return {
        "state": state,
        "reason": reason,
        "unsupported_claim_count": unsupported_claim_count,
        "partial_but_incomparable_count": partial_but_incomparable_count,
        "has_fictional_contamination": fictional_contamination,
        "certainty_profile": certainty_profile,
    }


def aggregate_decision_channel_protocol(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    claim_pipeline_diagnostics: Optional[Dict[str, Any]],
    evidence_non_decidable_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    evidence_signal = evidence_first_decision_signal(extracted, evidence_summary)
    if evidence_signal:
        channel = str(evidence_signal.get("decision_channel") or DECISION_CHANNEL_DIRECT_WEB)
        label = str(evidence_signal.get("label") or LABEL_2)
        return {
            "decision_channel": channel,
            "channel_decision_candidate": channel,
            "channel_decision_confidence": float(evidence_signal.get("decision_channel_confidence") or 0.9),
            "channel_label_candidate": label,
            "channel_scope": str(evidence_signal.get("decision_scope") or ""),
        }
    dominant_row = dominant_pipeline_row(claim_pipeline_diagnostics, evidence_non_decidable_state)
    if dominant_row:
        channel = str(dominant_row.get("channel_decision_candidate") or DECISION_CHANNEL_UNRESOLVED)
        centrality = str(dominant_row.get("centrality") or "")
        structured_detail = str(dominant_row.get("secondary_detail_scope") or "")
        label = LABEL_1 if channel == DECISION_CHANNEL_CLOSURE or structured_detail == "structured_detail" else LABEL_2
        if channel == DECISION_CHANNEL_DIRECT_WEB and centrality == "core":
            label = LABEL_2
        return {
            "decision_channel": channel,
            "channel_decision_candidate": channel,
            "channel_decision_confidence": float(dominant_row.get("channel_decision_confidence") or 0.3),
            "channel_label_candidate": label,
            "channel_scope": structured_detail or centrality,
        }
    return {
        "decision_channel": DECISION_CHANNEL_UNRESOLVED,
        "channel_decision_candidate": DECISION_CHANNEL_UNRESOLVED,
        "channel_decision_confidence": 0.1,
        "channel_label_candidate": LABEL_2,
        "channel_scope": "",
    }


def infer_label_source_channel(
    final_label: str,
    evidence_signal: Optional[Dict[str, Any]],
    channel_protocol: Optional[Dict[str, Any]],
) -> str:
    evidence_signal = evidence_signal if isinstance(evidence_signal, dict) else {}
    channel_protocol = channel_protocol if isinstance(channel_protocol, dict) else {}
    if evidence_signal:
        return str(evidence_signal.get("decision_channel") or DECISION_CHANNEL_UNRESOLVED)
    if final_label == LABEL_2:
        return str(channel_protocol.get("decision_channel") or DECISION_CHANNEL_UNRESOLVED)
    return str(channel_protocol.get("channel_decision_candidate") or channel_protocol.get("decision_channel") or DECISION_CHANNEL_UNRESOLVED)


def answer_has_absolute_boundary_terms(text: str) -> bool:
    lowered = normalize_text(text).lower()
    terms = [
        "根本不需要", "完全没有", "没有实质性影响", "完全绕开", "不需要经过",
        "唯一", "必然", "一定", "毫无", "绝对", "no need", "without crossing",
        "completely", "never", "only route",
    ]
    return any(term.lower() in lowered for term in terms)


def answer_has_resolved_forecast_terms(text: str) -> bool:
    return any(term in normalize_text(text) for term in ["无悬念", "年内最大", "即将迎来", "确定落地"])


def regression_label_calibration(
    final_label: str,
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    item: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    if not isinstance(evidence_summary, dict):
        return final_label, ""
    evidence_decidable = has_new_scheme_decidable_evidence(extracted, evidence_summary)
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    core_uncertain = 0
    unsupported_details = 0
    strong_core_refuted = False
    weak_core_refuted = False
    unsupported_negative_route_core = False
    unsupported_negative_route_support = False
    unsupported_absolute_support = False
    unsupported_absolute_route_core = False
    unsupported_absolute_route_support = False
    geopolitical_strong_secondary_claim = False
    unsupported_distance_numeric_core = False
    sports_unsupported_core_results = 0
    sports_supporting_unsupported_results = 0
    exact_schedule_core_without_evidence = False
    fictional_current_status_contamination = False
    market_unsupported_core_date = False
    market_unsupported_core_numeric = 0
    market_unsupported_numeric_total = 0
    market_weak_core_refuted = False
    secondary_direct_refuted = False
    need_type = normalize_need_type(extracted.get("need_type"))
    finance_need = need_type == "financial_quote"
    distance_need = need_type == "distance_position"
    sports_need = need_type == "sports_result"
    geopolitical_need = need_type == "geopolitical_claim"
    current_geopolitical_need = need_type == "current_geopolitical_status"
    geopolitical_family_need = need_type in {"geopolitical_claim", "current_geopolitical_status"}
    high_risk_need = need_type in {"current_result", "schedule_time", "current_geopolitical_status"}
    market_movement_need = need_type == "market_movement"
    answer_text = normalize_text(str((item or {}).get("answer") or ""))
    has_absolute_boundary = answer_has_absolute_boundary_terms(answer_text)
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        centrality = str(claim.get("centrality") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
        coverage_level = str(coverage.get("coverage_level") or "")
        web_evidence_count = int(coverage.get("web_evidence_count") or 0)
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
        claim_shape = str(source_intent.get("claim_shape") or "")
        assertion_strength = str(source_intent.get("assertion_strength") or "medium").lower()
        risk_type = str(source_intent.get("risk_type") or "general").lower()
        stated_as_fact = normalize_bool(source_intent.get("stated_as_fact", True), True)
        claim_text = normalize_text(str(claim.get("claim") or ""))
        route_meta = source_intent.get("route_meta") if isinstance(source_intent, dict) else {}
        route_polarity = str((route_meta or {}).get("polarity") or "")
        supporting = [point for point in summary.get("supporting_points") or [] if isinstance(point, dict)]
        refuting = [point for point in summary.get("refuting_points") or [] if isinstance(point, dict)]
        uncertain = [point for point in summary.get("uncertain_points") or [] if isinstance(point, dict)]
        direct_supporting = [
            point
            for point in supporting
            if isinstance(point, dict) and point.get("direct_answer") == "direct"
        ]
        direct_refuting = [
            point
            for point in refuting
            if isinstance(point, dict) and point.get("direct_answer") == "direct"
        ]
        direct_decidable_points = direct_supporting + direct_refuting
        if centrality in {"supporting", "peripheral"} and any(
            point_is_secondary_detail_refutation(point, need_type)
            for point in direct_refuting
        ):
            secondary_direct_refuted = True
        if centrality == "core":
            has_strong_refuting = claim_has_new_scheme_strong_refutation(claim, summary, need_type)
            if has_strong_refuting:
                strong_core_refuted = True
            elif direct_refuting:
                weak_core_refuted = True
                if mode in {"numeric_fact", "date_fact", "event_result"} and any(
                    point.get("source_type") in {"official", "news"} and int(point.get("event_window_score", 0) or 0) >= 0
                    for point in direct_refuting
                ):
                    market_weak_core_refuted = True
            sports_core_counted = False
            if sports_need and coverage_level in {"none", "weak", "partial"}:
                sports_context_points = [
                    point for point in direct_decidable_points
                    if isinstance(point, dict) and point.get("direct_answer") == "direct" and point_is_sports_result_context(point)
                ]
                if not sports_context_points:
                    sports_unsupported_core_results += 1
                    sports_core_counted = True
            if sports_need and not sports_core_counted and mode in {"event_result", "numeric_fact"} and not supporting and not refuting:
                sports_unsupported_core_results += 1
            unresolved_without_points = not direct_decidable_points and not supporting and not refuting
            if (coverage_level in {"none", "weak", "partial"} or (mode == "date_fact" and unresolved_without_points)) and not direct_decidable_points:
                core_uncertain += 1
                if mode == "route_fact" and route_polarity == "negative":
                    unsupported_negative_route_core = True
                if (
                    geopolitical_family_need
                    and (
                        mode == "route_fact"
                        or route_polarity == "negative"
                        or re.search(r"(领空|空域|路线|经过|绕开|飞向)", claim_text)
                    )
                    and (
                        has_absolute_boundary
                        or re.search(r"(没有实质性影响|不需要经过|无需经过|完全绕开|根本不需要)", claim_text)
                    )
                ):
                    unsupported_absolute_route_core = True
                if distance_need and re.search(r"(公里|千米|海里|英里|km|mile|nautical)", str(claim.get("claim") or ""), re.I):
                    unsupported_distance_numeric_core = True
                if mode == "date_fact":
                    market_unsupported_core_date = True
                    if high_risk_need or need_type == "schedule_time":
                        exact_schedule_core_without_evidence = True
                if mode == "numeric_fact":
                    market_unsupported_core_numeric += 1
                if (
                    geopolitical_need
                    and mode in {"policy_fact", "route_fact", "event_result"}
                    and assertion_strength == "high"
                    and stated_as_fact
                    and risk_type in {"policy_intent", "military_action", "route_relation", "current_status"}
                    and coverage_level != "none"
                    and web_evidence_count > 0
                    and has_absolute_boundary
                ):
                    geopolitical_strong_secondary_claim = True
        elif centrality in {"supporting", "peripheral"} and coverage_level in {"none", "weak", "partial"}:
            unsupported_details += 1
            claim_text = normalize_text(str(claim.get("claim") or ""))
            if sports_need and centrality == "supporting" and mode == "event_result":
                sports_context_points = [
                    point for point in direct_decidable_points
                    if isinstance(point, dict) and point.get("direct_answer") == "direct" and point_is_sports_result_context(point)
                ]
                if not sports_context_points and re.search(r"(\d+\s*[-:：]\s*\d+|战胜|击败|获胜|不敌|负于)", claim_text):
                    sports_supporting_unsupported_results += 1
            if market_movement_need and mode in {"date_fact", "schedule_fact"}:
                market_unsupported_core_date = True
            if centrality == "supporting" and mode == "route_fact" and route_polarity == "negative":
                unsupported_negative_route_support = True
            if (
                centrality == "supporting"
                and mode == "route_fact"
                and stated_as_fact
                and claim_shape != "exclusive_premise"
                and has_absolute_boundary
                and re.search(r"(根本不需要|不需要经过|无需经过|完全绕开|不经由)", claim_text)
            ):
                unsupported_absolute_route_support = True
            if (
                centrality == "supporting"
                and (
                    assertion_strength == "high"
                    or (current_geopolitical_need and assertion_strength in {"medium", "high"})
                )
                and stated_as_fact
                and risk_type in {"policy_intent", "military_action", "route_relation", "current_status"}
                and coverage_level in {"none", "weak", "partial"}
                and has_absolute_boundary
            ):
                unsupported_absolute_support = True
        if centrality in {"core", "supporting"} and mode == "numeric_fact" and coverage_level in {"none", "weak", "partial"}:
            market_unsupported_numeric_total += 1
    if sports_need and sports_supporting_unsupported_results >= 2:
        sports_unsupported_core_results += sports_supporting_unsupported_results
    if market_movement_need and market_weak_core_refuted:
        return LABEL_0, "market_movement_has_weak_core_refutation"
    prediction_core_overclaim = any(
        str(claim.get("centrality") or "") == "core"
        and str((claim.get("source_intent") or {}).get("risk_type") or "") == "prediction"
        and normalize_bool((claim.get("source_intent") or {}).get("stated_as_fact", True), True)
        for claim in claims
        if isinstance(claim, dict)
    )
    if (
        not evidence_decidable
        and need_type in {"market_movement", "schedule_time", "current_result"}
        and (
            prediction_core_overclaim
            or any(term in answer_text for term in ["无悬念", "年内最大", "即将迎来", "确定落地"])
        )
    ):
        return LABEL_0, "market_movement_resolved_forecast_overclaim"
    if sports_need and sports_unsupported_core_results >= 2 and not evidence_decidable:
        return LABEL_1, "sports_result_has_multiple_unsupported_core_result_claims"
    if sports_need and sports_unsupported_core_results == 1 and not evidence_decidable:
        return LABEL_1, "sports_result_has_unsupported_core_result_claim"
    if distance_need and unsupported_distance_numeric_core and not evidence_decidable:
        return LABEL_0, "distance_position_core_numeric_distance_lacks_support"
    if current_geopolitical_need and any(token in answer_text for token in ["虚构", "剧本", "假设", "AI生成", "非真实新闻"]):
        fictional_current_status_contamination = True
    if current_geopolitical_need and fictional_current_status_contamination and not evidence_decidable:
        return LABEL_0, "fictional_scenario_contaminates_current_need"
    if geopolitical_need and unsupported_negative_route_core and not evidence_decidable:
        if has_absolute_boundary or unsupported_absolute_route_core:
            return LABEL_0, "geopolitical_negative_route_core_lacks_support"
        return LABEL_1, "geopolitical_claims_have_insufficient_direct_support"
    if (
        geopolitical_need
        and final_label in {LABEL_0, LABEL_1}
        and not has_absolute_boundary
        and not strong_core_refuted
        and not evidence_decidable
    ):
        return LABEL_2, "open_route_summary_without_absolute_boundary"
    if not evidence_decidable and geopolitical_need and any(
        centrality == "core"
        and coverage_level in {"none", "weak", "partial"}
        and mode == "policy_fact"
        and risk_type in {"policy_intent", "military_action"}
        and stated_as_fact
        for claim in claims
        for centrality, coverage_level, mode, risk_type, stated_as_fact in [
            (
                str(claim.get("centrality") or ""),
                str((summaries.get(str(claim.get("claim_id") or claim.get("id") or "")) or {}).get("coverage", {}).get("coverage_level") or ""),
                str((summaries.get(str(claim.get("claim_id") or claim.get("id") or "")) or {}).get("evidence_mode") or (claim.get("source_intent") or {}).get("evidence_mode") or ""),
                str((claim.get("source_intent") or {}).get("risk_type") or "general").lower(),
                normalize_bool((claim.get("source_intent") or {}).get("stated_as_fact", True), True),
            )
        ]
    ):
        return LABEL_1, "geopolitical_core_policy_intent_lacks_support"
    if geopolitical_family_need and unsupported_absolute_route_core and not evidence_decidable:
        return LABEL_0, "geopolitical_absolute_route_premise_lacks_support"
    if geopolitical_family_need and (unsupported_absolute_route_support or unsupported_absolute_support) and not evidence_decidable:
        return LABEL_1, "geopolitical_supporting_absolute_detail_lacks_support"
    if geopolitical_need and geopolitical_strong_secondary_claim and not strong_core_refuted and not evidence_decidable:
        return LABEL_1, "geopolitical_supporting_absolute_detail_lacks_support"
    if need_type == "schedule_time" and exact_schedule_core_without_evidence and not evidence_decidable:
        return LABEL_0, "schedule_time_core_date_lacks_direct_evidence"
    if market_movement_need and any(term in answer_text for term in ["休市", "节假日", "节假期", "交易日", "假期差"]) and not evidence_decidable:
        return LABEL_1, "market_movement_has_unsupported_time_detail"
    if market_movement_need and market_unsupported_core_date and not strong_core_refuted and not evidence_decidable:
        return LABEL_1, "market_movement_has_unsupported_time_detail"
    if finance_need and final_label == LABEL_1 and not strong_core_refuted and not evidence_decidable:
        return LABEL_2, "financial_quote_without_strong_same_metric_refutation"
    if final_label == LABEL_0 and not strong_core_refuted and not evidence_decidable:
        if weak_core_refuted:
            return LABEL_1, "only_weak_core_refutation_or_secondary_errors"
        return LABEL_2, "unsupported_claims_are_not_fact_errors"
    if final_label == LABEL_2 and secondary_direct_refuted and not strong_core_refuted:
        return LABEL_1, "secondary_detail_direct_refutation"
    if final_label == LABEL_1 and secondary_direct_refuted:
        return LABEL_1, "secondary_detail_direct_refutation"
    if final_label == LABEL_1 and not strong_core_refuted and not weak_core_refuted and not evidence_decidable:
        return LABEL_2, "unsupported_claims_are_not_fact_errors"
    return final_label, ""


def compact_claim_text(text: str, limit: int = 42) -> str:
    text = normalize_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，。；;、 ") + "…"


def coverage_text(summary: Dict[str, Any]) -> str:
    coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
    level = str(coverage.get("coverage_level") or "")
    direct_count = int(coverage.get("direct_evidence_count") or 0)
    web_count = int(coverage.get("web_evidence_count") or 0)
    if level in {"strong", "moderate"} and direct_count:
        return f"找到{direct_count}条较直接证据"
    if direct_count:
        return f"只有{direct_count}条弱直接证据"
    if web_count:
        return f"检索到{web_count}条相关材料但缺少直接回答"
    return "未检索到可用直接证据"


def display_point_value(value: str) -> str:
    clean = normalize_text(str(value or ""))
    display_map = {
        "withdrawal_or_walkover": "退赛/不战而胜",
    }
    return display_map.get(clean, clean)


def point_text(point: Dict[str, Any]) -> str:
    claim_value = normalize_text(str(point.get("claim_value") or ""))
    evidence_value = display_point_value(str(point.get("evidence_value") or ""))
    evidence_sentence = normalize_text(str(point.get("evidence_sentence") or ""))
    source = normalize_text(str(point.get("title") or point.get("url") or ""))
    if evidence_sentence:
        return f"证据句为“{compact_claim_text(evidence_sentence, 42)}”"
    if claim_value and evidence_value and claim_value != evidence_value:
        return f"声称为“{compact_claim_text(claim_value, 24)}”，证据显示“{compact_claim_text(evidence_value, 24)}”"
    if evidence_value:
        return f"证据线索为“{compact_claim_text(evidence_value, 32)}”"
    if source:
        return f"证据来自“{compact_claim_text(source, 32)}”"
    return ""


def pipeline_row_is_high_risk(row: Dict[str, Any]) -> bool:
    centrality = str(row.get("centrality") or "")
    evidence_mode = str(row.get("evidence_mode") or "")
    return centrality == "core" or (
        centrality in {"supporting", "peripheral"}
        and evidence_mode in {"numeric_fact", "date_fact", "event_result", "route_fact", "policy_fact", "schedule_fact"}
    )


def pipeline_row_has_retained_progress(row: Dict[str, Any]) -> bool:
    return (
        int(row.get("kept_web") or 0) > 0
        or int(row.get("answer_candidate_total") or 0) > 0
        or int(row.get("direct_support_points") or 0) > 0
        or int(row.get("direct_refute_points") or 0) > 0
        or int(row.get("direct_candidate_rescue_used") or 0) > 0
    )


def rescue_stage_priority(row: Dict[str, Any]) -> int:
    stages = row.get("direct_candidate_rescue_stages") if isinstance(row.get("direct_candidate_rescue_stages"), dict) else {}
    if int(stages.get("pre_filter") or 0) > 0 or int(row.get("rescue_promoted_from_filter") or 0) > 0:
        return 2
    if int(stages.get("post_keep") or 0) > 0:
        return 1
    return 0


def recall_probe_progress_priority(row: Dict[str, Any]) -> int:
    if int(row.get("recall_probe_used") or 0) <= 0:
        return 0
    if int(row.get("recall_probe_raw_hits") or 0) > 0:
        return 2
    return 1


def dominant_pipeline_row(
    claim_pipeline_diagnostics: Optional[Dict[str, Any]],
    evidence_non_decidable_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    items = (
        claim_pipeline_diagnostics.get("items")
        if isinstance(claim_pipeline_diagnostics, dict) and isinstance(claim_pipeline_diagnostics.get("items"), list)
        else []
    )
    if not items:
        return {}
    non_decidable_state = (
        str(evidence_non_decidable_state.get("state") or "")
        if isinstance(evidence_non_decidable_state, dict)
        else ""
    )
    if non_decidable_state == "partial_but_incomparable":
        incomparable_rows = [
            item for item in items
            if isinstance(item, dict)
            and str(item.get("pipeline_stage") or "") == "evidence_partial_but_incomparable"
            and pipeline_row_is_high_risk(item)
        ]
        if incomparable_rows:
            incomparable_rows.sort(
                key=lambda item: (
                    1 if str(item.get("centrality") or "") == "core" else 0,
                    1 if str(item.get("program_expected_failure_stage") or "") in {"comparability", "point_conversion"} else 0,
                    int(item.get("direct_support_points") or 0) + int(item.get("direct_refute_points") or 0),
                ),
                reverse=True,
            )
            return incomparable_rows[0]
    if non_decidable_state == "unsupported":
        preferred_rows = [
            item for item in items
            if isinstance(item, dict)
            and str(item.get("pipeline_stage") or "") in {
                "retrieval_filter",
                "retrieval_readiness",
                "evidence_partial_but_incomparable",
                "evidence_point_not_convertible",
            }
            and (
                int(item.get("raw_results") or 0) > 0
                or pipeline_row_has_retained_progress(item)
            )
            and pipeline_row_is_high_risk(item)
        ]
        if preferred_rows:
            preferred_rows.sort(
                key=lambda item: (
                    1 if str(item.get("centrality") or "") == "core" else 0,
                    1 if str(item.get("channel_decision_candidate") or "") == DECISION_CHANNEL_DIRECT_WEB else 0,
                    int(item.get("logic_refutation_candidate") or 0),
                    int(item.get("structured_detail_retained") or 0),
                    1 if str(item.get("logic_refutation_state") or "") in {"same_topic_logic_point_unstable", "shadowed_by_direct_channel"} else 0,
                    1 if str(item.get("pipeline_stage") or "") in {"retrieval_readiness", "evidence_partial_but_incomparable", "evidence_point_not_convertible"} else 0,
                    1 if str(item.get("program_expected_failure_stage") or "") in {"retrieval_readiness", "point_conversion", "comparability"} else 0,
                    recall_probe_progress_priority(item),
                    rescue_stage_priority(item),
                    1 if pipeline_row_has_retained_progress(item) else 0,
                    int(item.get("raw_results") or 0),
                    int(item.get("kept_web") or 0),
                    int(item.get("answer_candidate_total") or 0),
                ),
                reverse=True,
            )
            return preferred_rows[0]
    has_retained_progress = any(
        isinstance(item, dict)
        and pipeline_row_is_high_risk(item)
        and pipeline_row_has_retained_progress(item)
        for item in items
    )
    priority_order = {
        "provider_recall": 4,
        "retrieval_filter": 3,
        "retrieval_readiness": 2,
        "evidence_partial_but_incomparable": 1,
        "evidence_point_not_convertible": 1,
        "evidence_unsupported": 1,
    }
    ranked: List[Tuple[int, Dict[str, Any]]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("pipeline_stage") or "")
        centrality = str(item.get("centrality") or "")
        base = priority_order.get(stage, 0)
        if base <= 0:
            continue
        if has_retained_progress and stage == "provider_recall" and not pipeline_row_has_retained_progress(item):
            base = 0
        if base <= 0:
            continue
        score = base * 10 + (4 if centrality == "core" else 2 if centrality == "supporting" else 0)
        if str(item.get("program_expected_failure_stage") or "") in {"retrieval_readiness", "point_conversion"} and stage in {"retrieval_readiness", "evidence_point_not_convertible"}:
            score += 2
        if pipeline_row_has_retained_progress(item):
            score += 2
        if str(item.get("channel_decision_candidate") or "") == DECISION_CHANNEL_DIRECT_WEB:
            score += 3
        elif str(item.get("channel_decision_candidate") or "") == DECISION_CHANNEL_CLOSURE:
            score += 4
        score += 7 if int(item.get("logic_refutation_candidate") or 0) > 0 else 0
        score += 3 if int(item.get("structured_detail_retained") or 0) > 0 else 0
        score += 2 if str(item.get("logic_refutation_state") or "") in {"same_topic_logic_point_unstable", "shadowed_by_direct_channel"} else 0
        score += min(5, int(item.get("candidate_directness_rank") or 0))
        score += 2 if int(item.get("direct_candidate_promotion_used") or 0) > 0 else 0
        score += 1 if str(item.get("candidate_promotion_block_reason") or "") in {"slot_hit_but_indirect", "opening_slot_mismatch"} else 0
        score += recall_probe_progress_priority(item) * 6
        score += rescue_stage_priority(item) * 2
        ranked.append((score, item))
    if not ranked:
        return {}
    ranked.sort(key=lambda row: row[0], reverse=True)
    return ranked[0][1]


def dominant_pipeline_stage(
    claim_pipeline_diagnostics: Optional[Dict[str, Any]],
    evidence_non_decidable_state: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    row = dominant_pipeline_row(claim_pipeline_diagnostics, evidence_non_decidable_state)
    if not row:
        return "", ""
    return str(row.get("pipeline_stage") or ""), str(row.get("pipeline_layer") or "")


def secondary_detail_refutation_reason(extracted: Dict[str, Any], evidence_summary: Optional[Dict[str, Any]]) -> str:
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    claims = extracted.get("claims") if isinstance(extracted, dict) else []
    need_type = normalize_need_type(extracted.get("need_type")) if isinstance(extracted, dict) else "general_fact"
    rows: List[Tuple[int, str]] = []
    for claim in claims:
        if not isinstance(claim, dict) or str(claim.get("centrality") or "") not in {"supporting", "peripheral"}:
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        detail_state = detail_claim_resolution_state(claim, summary, need_type)
        if str(detail_state.get("state") or "") != "decidable_error":
            continue
        claim_text = compact_claim_text(str(claim.get("claim") or ""), 120)
        reason = str(detail_state.get("reason") or "")
        if reason == "stable_logic_refutation":
            basis = compact_claim_text(str(detail_state.get("logic_refutation_basis") or ""), 90)
            if basis:
                rows.append((3, f"“{claim_text}”与回答自己给出的前提在逻辑上闭合矛盾，例如“{basis}”这条线索已经能稳定推出该细节不成立"))
            else:
                rows.append((3, f"“{claim_text}”与回答自己给出的前提在逻辑上闭合矛盾，属于可复现的结构化细节错误"))
            continue
        refuting = claim_direct_refuting_points(summary)
        if refuting and isinstance(refuting[0], dict):
            rows.append((2, f"“{claim_text}”存在可直接比对的细节反证：{point_text(refuting[0])}"))
        else:
            rows.append((1, f"“{claim_text}”属于可裁决地错的附带结构化细节"))
    if rows:
        rows.sort(reverse=True)
        return f"主结论未被直接推翻，但附带结构化细节已可裁决地错误：{rows[0][1]}。因此判为次需事实错误。"
    return ""


def insufficient_evidence_reason(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    claim_pipeline_diagnostics: Optional[Dict[str, Any]],
    evidence_non_decidable_state: Optional[Dict[str, Any]],
) -> str:
    claim_pipeline_diagnostics = claim_pipeline_diagnostics if isinstance(claim_pipeline_diagnostics, dict) else {}
    non_decidable_state = evidence_non_decidable_state if isinstance(evidence_non_decidable_state, dict) else {}
    state = str(non_decidable_state.get("state") or "")
    dominant_row = dominant_pipeline_row(claim_pipeline_diagnostics, non_decidable_state)
    retrieval_effect_review = (
        claim_pipeline_diagnostics.get("retrieval_effect_review")
        if isinstance(claim_pipeline_diagnostics.get("retrieval_effect_review"), dict)
        else {}
    )
    stage = str(dominant_row.get("pipeline_stage") or "")
    critical_claim_blocking_state = str(dominant_row.get("critical_claim_blocking_state") or "")
    program_need = compact_claim_text(str(dominant_row.get("program_direct_evidence_need") or ""), 120)
    false_friend = compact_claim_text(
        str(((dominant_row.get("program_false_friend_evidence") or [""])[0] if isinstance(dominant_row.get("program_false_friend_evidence"), list) else "")),
        90,
    )
    slot_alignment_status = str(dominant_row.get("slot_alignment_status") or "")
    missing_required_slots = [str(slot) for slot in (dominant_row.get("missing_required_slots") or []) if str(slot)]
    point_block_reason = str(dominant_row.get("point_conversion_block_reason") or "")
    readiness_block_layer = str(dominant_row.get("readiness_block_layer") or "")
    point_block_layer = str(dominant_row.get("point_conversion_block_layer") or "")
    sentence_candidate_profile = dominant_row.get("sentence_candidate_profile") if isinstance(dominant_row.get("sentence_candidate_profile"), dict) else {}
    top_candidate_slot_match = str(dominant_row.get("top_candidate_slot_match") or "")
    candidate_slot_coverage = dominant_row.get("candidate_slot_coverage") if isinstance(dominant_row.get("candidate_slot_coverage"), dict) else {}
    direct_candidate_gap_reason = str(dominant_row.get("direct_candidate_gap_reason") or "")
    candidate_directness_rank = int(dominant_row.get("candidate_directness_rank") or 0)
    direct_candidate_promotion_used = int(dominant_row.get("direct_candidate_promotion_used") or 0)
    direct_candidate_promotion_basis = str(dominant_row.get("direct_candidate_promotion_basis") or "")
    candidate_promotion_block_reason = str(dominant_row.get("candidate_promotion_block_reason") or "")
    candidate_slot_coverage_summary_text = str(dominant_row.get("candidate_slot_coverage_summary") or "")
    environment_block_reason = str(dominant_row.get("environment_block_reason") or "")
    direct_candidate_rescue_used = int(dominant_row.get("direct_candidate_rescue_used") or 0)
    direct_candidate_rescue_stages = dominant_row.get("direct_candidate_rescue_stages") if isinstance(dominant_row.get("direct_candidate_rescue_stages"), dict) else {}
    readiness_promotion_used = int(dominant_row.get("readiness_promotion_used") or 0)
    recoverable_filter_reason = dominant_row.get("recoverable_filter_reason") if isinstance(dominant_row.get("recoverable_filter_reason"), dict) else {}
    recall_probe_used = int(dominant_row.get("recall_probe_used") or 0)
    recall_probe_raw_hits = int(dominant_row.get("recall_probe_raw_hits") or 0)
    access_path_state = str(dominant_row.get("access_path_state") or "")
    access_block_source = str(dominant_row.get("access_block_source") or "")
    rescue_attempt_state = str(dominant_row.get("rescue_attempt_state") or "")
    source_budget_cutoff = dominant_row.get("source_budget_cutoff") if isinstance(dominant_row.get("source_budget_cutoff"), dict) else {}
    playwright_rescue_state = str(dominant_row.get("playwright_rescue_state") or "")
    playwright_rescue_trigger = str(dominant_row.get("playwright_rescue_trigger") or "")
    rescue_skip_reason = str(dominant_row.get("rescue_skip_reason") or "")
    page_keep_review_state = dominant_row.get("page_keep_review_state") if isinstance(dominant_row.get("page_keep_review_state"), dict) else {}
    page_keep_review_reason = dominant_row.get("page_keep_review_reason") if isinstance(dominant_row.get("page_keep_review_reason"), dict) else {}
    kept_progress_from_raw = int(dominant_row.get("kept_progress_from_raw") or 0)
    point_consumption_state = str(dominant_row.get("point_consumption_state") or "")
    rescue_success_gate = str(dominant_row.get("rescue_success_gate") or "")
    rescue_target_page_type = str(dominant_row.get("rescue_target_page_type") or "")
    rescue_non_roi_reason = str(dominant_row.get("rescue_non_roi_reason") or "")
    official_entry_attempted = normalize_bool(dominant_row.get("official_entry_attempted"), False)
    official_entry_hit = normalize_bool(dominant_row.get("official_entry_hit"), False)
    official_discovery_block_reason = str(dominant_row.get("official_discovery_block_reason") or "")
    detail_fetch_paths = dominant_row.get("detail_fetch_paths") if isinstance(dominant_row.get("detail_fetch_paths"), dict) else {}
    has_core_support = has_new_scheme_core_supporting_evidence(extracted, evidence_summary)
    unresolved_details = has_unresolved_high_risk_detail_claims(extracted, evidence_summary)
    detail_audit_rows = high_risk_detail_claim_diagnostics(extracted, evidence_summary)
    dominant_claim_text = normalize_text(str(dominant_row.get("claim") or ""))

    def slot_hit(slot_name: str) -> bool:
        if candidate_slot_coverage.get(slot_name) is True:
            return True
        slot_parts = {
            normalize_text(str(part or ""))
            for part in top_candidate_slot_match.split("+")
            if normalize_text(str(part or ""))
        }
        legacy_parts = {
            "subject": {"subject"},
            "time_scope": {"time_scope", "time"},
            "metric_or_relation": {"metric_or_relation", "metric_or_result"},
            "status_or_result": {"status_or_result", "metric_or_result"},
        }
        return bool(slot_parts & legacy_parts.get(slot_name, {slot_name}))

    def opening_slot_clause(relaxed: bool = False) -> str:
        if not relaxed and point_block_reason not in {"numeric_not_normalizable", "candidate_not_direct", "not_same_fact_slot"}:
            return ""
        if not re.search(r"(开盘|开市|opening|opened)", f"{dominant_claim_text} {program_need}", flags=re.I):
            return ""
        return " 当前拿到的更多是盘中涨幅、泛涨跌或其他口径材料，还不是回答开盘事实位点的直接证据。"

    def rescue_clause() -> str:
        if direct_candidate_rescue_used <= 0:
            return ""
        if int(direct_candidate_rescue_stages.get("pre_filter") or 0) > 0 or int(dominant_row.get("rescue_promoted_from_filter") or 0) > 0:
            return "当前已经从差一点被过滤掉的近失页里补出了候选句"
        return "当前已经从保留页里补救抽到了候选句"

    def recall_probe_clause() -> str:
        if recall_probe_used <= 0:
            return ""
        if recall_probe_raw_hits > 0:
            return "已经改用更贴事实位点的检索问法拿回了结果"
        return "已经额外尝试了更贴事实位点的检索问法，但仍没有稳定拿回原始结果"

    def keep_review_clause() -> str:
        if kept_progress_from_raw <= 0:
            return ""
        reason = next(iter(page_keep_review_reason.keys()), "") if page_keep_review_reason else ""
        if reason == "page_type_not_decision_useful":
            return "已有一部分结果是靠关键证据页复核才保下来的，说明入口并非全空，而是原先的页级保留偏严。"
        if page_keep_review_state:
            return "已有一部分结果是靠关键证据页复核才保下来的，说明问题已经从纯召回转到页级保留与消费。"
        return ""

    def kept_candidate_progress_clause() -> str:
        if point_consumption_state != "candidate_progress_from_kept_page":
            return ""
        if candidate_slot_coverage_summary_text:
            return f"当前已经从保留下来的页面里消费出覆盖 {candidate_slot_coverage_summary_text} 的候选句。"
        return "当前已经从保留下来的页面里消费出同位点候选句。"

    def critical_block_clause() -> str:
        if critical_claim_blocking_state in {"raw_hit_but_page_not_retained", "raw_hit_but_page_not_retained_after_review"}:
            if official_entry_hit:
                return "当前已经命中过 authority/official 入口，也拿回过原始结果，但关键页还没有稳定保住。"
            return "当前已经拿回过原始结果，但关键页还没有稳定保住。"
        if critical_claim_blocking_state == "candidate_present_but_not_decidable":
            return "当前关键页和候选句都已经出现，但还没闭合成可直接裁决的证据点。"
        return ""

    def retrieval_review_clause() -> str:
        authority_hit_claims = int(retrieval_effect_review.get("authority_hit_claims") or 0)
        kept_positive_claims = int(retrieval_effect_review.get("kept_positive_claims") or 0)
        kept_progress_claims = int(retrieval_effect_review.get("kept_progress_claims") or 0)
        anti_bot_claims = int(retrieval_effect_review.get("anti_bot_or_access_blocked_claims") or 0)
        if authority_hit_claims > 0 and kept_positive_claims <= 0:
            return "本轮其实已经碰到过权威入口，但命中的页还没有稳定保留下来。"
        if kept_progress_claims > 0 and kept_positive_claims > 0:
            return "本轮已经有页级保留进展，主阻塞不再是纯 recall，而是 kept page 到 candidate/point 的消费没有闭合。"
        if anti_bot_claims > 0:
            return "本轮主阻塞里已经包含明显的访问受阻或反爬因素，不是单纯没有相关网页。"
        return ""

    def rescue_success_clause() -> str:
        if rescue_success_gate == "search_result_recovered":
            target_text = f"{rescue_target_page_type} 类结果" if rescue_target_page_type else "结果页"
            return f"Playwright 救援已经把 {target_text} 拿回来了"
        if rescue_success_gate == "detail_content_recovered":
            target_text = f"{rescue_target_page_type} 的正文" if rescue_target_page_type else "详情页正文"
            return f"Playwright 救援已经把 {target_text} 读回来了"
        return ""

    def access_clause() -> str:
        if access_path_state == "source_budget_cutoff":
            omitted = source_budget_cutoff.get("omitted_sources") if isinstance(source_budget_cutoff.get("omitted_sources"), list) else []
            if omitted:
                return f"当前主要卡在 source budget 截断：像 {compact_claim_text(str(omitted[0]), 40)} 这类入口没有轮到执行。"
            return "当前主要卡在 source budget 截断：后排入口没有真正执行到。"
        if access_path_state == "official_discovery_failed":
            if official_entry_attempted and not official_entry_hit:
                if official_discovery_block_reason == "anti_bot_blocked":
                    return "当前官网/权威入口发现也尝试过了，但发现阶段被反爬或搜索页阻塞住了。"
                return "当前官网/权威入口也尝试过了，但还没稳定找到可用的 authority 入口页。"
        if access_path_state in {"source_access_blocked", "access_blocked_but_rescuable"}:
            if access_block_source:
                return f"当前主要卡在外站访问受阻：{access_block_source} 这一路没有稳定拿回原始结果。"
            return "当前主要卡在外站访问受阻：原始结果没有稳定拿回。"
        if access_path_state in {"page_access_or_read_blocked", "access_blocked_and_unresolved"}:
            if rescue_attempt_state == "playwright_rescue_succeeded":
                return "当前页面访问一度受阻，但救援只拿回了部分材料，正文读取仍不稳定。"
            if playwright_rescue_state == "playwright_rescue_failed":
                if playwright_rescue_trigger:
                    return f"当前主要卡在页面访问或正文读取受阻：已经触发过 Playwright 救援（{playwright_rescue_trigger}），但还是没把关键正文稳定读下来。"
                return "当前主要卡在页面访问或正文读取受阻：已经尝试过 Playwright 救援，但还是没把关键正文稳定读下来。"
            if rescue_attempt_state == "playwright_rescue_skipped_by_policy":
                if rescue_skip_reason:
                    return f"当前页面访问有阻塞迹象，但本轮补救策略没有真正接手（{rescue_skip_reason}），关键正文仍没稳定拿下来。"
                if rescue_non_roi_reason:
                    return f"当前页面访问有阻塞迹象，但本轮补救策略没有真正接手（{rescue_non_roi_reason}），关键正文仍没稳定拿下来。"
                return "当前页面访问有阻塞迹象，但本轮补救策略没有真正接手，关键正文仍没稳定拿下来。"
            return "当前主要卡在页面访问或正文读取受阻：相关页出现过，但关键正文没有稳定读下来。"
        if access_path_state == "provider_recall_insufficient_after_probe":
            return "当前已经补试了更贴位点的检索问法，但 provider 侧仍没有稳定召回足够结果。"
        if access_path_state == "provider_recall_insufficient":
            return "当前主要还是 provider 侧召回不足：关键原始结果没有稳定回来。"
        return ""

    def candidate_gap_clause() -> str:
        if direct_candidate_gap_reason == "opening_slot_mismatch":
            return "当前候选句更多是盘中、收盘或泛涨跌材料，不是开盘事实位点。"
        if direct_candidate_gap_reason == "date_role_mismatch":
            return "当前候选句已经碰到日期相关信息，但日期角色还不对，比如更像发布日期、生效日或报道日串口径。"
        if direct_candidate_gap_reason == "result_granularity_mismatch":
            return "当前候选句已经碰到比赛结果相关信息，但更多是过程结果或局部结果，不是最终结果位点。"
        if direct_candidate_gap_reason == "numeric_reference_only":
            return "当前候选句只有数值痕迹，还没有把这个数值稳定绑定到 claim 要核的事实位点。"
        if direct_candidate_gap_reason == "date_reference_only":
            return "当前候选句只有日期痕迹，还没有把这个日期稳定绑定到 claim 要核的事实位点。"
        if direct_candidate_gap_reason == "commentary_only":
            return "当前候选句更多是解释、评论或背景表述，不是可直接裁决的事实句。"
        if candidate_promotion_block_reason == "background_commentary_topranked":
            return "当前排在最前的仍偏评论句或背景句，还没把真正可核的事实句稳定顶上来。"
        if slot_hit("subject") and slot_hit("time_scope") and (slot_hit("metric_or_relation") or slot_hit("status_or_result")):
            if direct_candidate_promotion_used > 0 and candidate_directness_rank >= 4:
                return "当前最强候选句已经打到主体、时间和关键结果位点，但表达还不够直接，离稳定直裁还差最后一层。"
            return "当前候选句已经打到主体、时间和结果/数值位点，但表达还不够直接。"
        if (
            (slot_hit("subject") and (slot_hit("metric_or_relation") or slot_hit("status_or_result")))
            or (slot_hit("time_scope") and (slot_hit("metric_or_relation") or slot_hit("status_or_result")))
            or (slot_hit("subject") and slot_hit("time_scope"))
        ):
            return "当前候选句已经打到一部分关键位点，但还没形成可直接回答的直裁句。"
        if sentence_candidate_profile:
            return "当前已经有候选句，但它们整体还停在弱句层，没有形成稳定的 direct candidate。"
        return ""

    def environment_block_prefix() -> str:
        if environment_block_reason == "source_access_blocked_without_rescue":
            return "当前主要卡在材料访问受阻：检索源请求阶段疑似被拦截，原始结果没有稳定拿回。"
        if environment_block_reason == "requests_blocked_playwright_failed":
            return "当前主要卡在正文读取受阻：相关页面出现过，但关键正文或详情页访问不稳定。"
        if environment_block_reason == "detail_read_failed_after_fetch":
            return "当前主要卡在正文读取失败：页面出现过，但关键正文没有稳定读下来。"
        return ""

    def retained_structured_detail_clause() -> str:
        if not detail_audit_rows:
            return ""
        for row in detail_audit_rows:
            if not isinstance(row, dict) or not normalize_bool(row.get("structured_detail_retained"), False):
                continue
            claim_text = compact_claim_text(str(row.get("claim") or ""), 60)
            logic_state = str(row.get("logic_refutation_state") or "")
            if normalize_bool(row.get("logic_refutation_candidate"), False):
                basis = compact_claim_text(str(row.get("logic_refutation_basis") or ""), 72)
                if logic_state == "same_topic_logic_point_unstable":
                    if basis:
                        return f" 当前附带细节“{claim_text}”已保留，也拿到了同主题逻辑线索“{basis}”，但闭合还不够稳定。"
                    return f" 当前附带细节“{claim_text}”已保留，也拿到了同主题逻辑线索，但闭合还不够稳定。"
                if basis:
                    return f" 当前附带细节“{claim_text}”已保留，也拿到了可做逻辑闭合的线索“{basis}”，但还没稳定收成可裁决反证。"
                return f" 当前附带细节“{claim_text}”已保留，也拿到了可做逻辑闭合的线索，但还没稳定收成可裁决反证。"
            if logic_state == "logic_point_topic_mismatch":
                return f" 当前附带细节“{claim_text}”已保留，也搜到过一些逻辑计算线索，但主题或位点还没对上，暂时不能消费成反证。"
            if logic_state == "shadowed_by_direct_channel":
                return f" 当前附带细节“{claim_text}”已保留，但现阶段仍被更强的网页直证通道压住，尚未单独收成稳定逻辑反证。"
            if str(row.get("state") or "") == "unresolved":
                return f" 当前附带细节“{claim_text}”已保留，但还未形成稳定逻辑反证。"
        return ""

    if state == "partial_but_incomparable":
        reason = "已经搜到相关材料，但它们不是同一事实位点或同一口径，因此当前不能据此直接判错。"
        if false_friend:
            reason += f" 当前拿到的更多是{false_friend}这类相关但不可直裁材料。"
        if has_core_support and unresolved_details:
            return reason + " 核心结论已有直接支持，但高风险结构化细节仍停在不可直接比较阶段，先保持不判错。"
        if stage == "provider_recall":
            return reason + " 当前主要还卡在检索召回，相关材料数量和质量都还不够稳定。"
        if stage == "retrieval_filter":
            return reason + " 当前主要卡在页面保留阶段，可用材料没有稳定留下。"
        if stage == "retrieval_readiness":
            layer_hint = "页层" if readiness_block_layer == "page" else "句层" if readiness_block_layer == "sentence" else ""
            if missing_required_slots:
                return reason + f" 当前已经保留了一些相关页面，但{layer_hint or '关键层级'}仍缺少{','.join(missing_required_slots[:3])}，所以还没形成稳定的 ready material。"
            if direct_candidate_rescue_used > 0:
                return reason + f" {rescue_clause()}，但这些句子还停在{layer_hint or '句层'}，没有形成稳定可直裁的 ready material。"
            return reason + f" 当前已经保留了一些相关页面，但还卡在{layer_hint or '页面到句子转换'}，没整理出能稳定直裁的 ready material。"
        if stage == "evidence_point_not_convertible":
            if point_block_reason:
                return reason + f" 当前页面里已有相关句子，但它们仍卡在{point_block_reason}，还没转成同一事实位点下可直接比较的证据点。" + opening_slot_clause()
            return reason + f" 当前页面里已有相关句子，但还卡在{point_block_layer or '点层'}，没转成同一事实位点下可直接比较的证据点。"
        return reason
    if state == "unsupported":
        access_prefix = access_clause()
        env_prefix = environment_block_prefix()
        if stage == "provider_recall":
            if access_prefix:
                return access_prefix + " 因此当前先把主阻塞记在 access / rescue / recall 这一层，不把它混成黑盒“没证据”。"
            if env_prefix:
                return env_prefix + " 因此当前主要还停在检索召回阶段，暂不把这类环境失败当成事实错误。"
            if recall_probe_used > 0 and recall_probe_raw_hits <= 0:
                return recall_probe_clause() + "，当前主要还停在检索召回阶段，因此暂不判定为事实错误。"
            if program_need:
                return f"当前主要卡在检索召回：关键 claim 还没有拿到足够可用的原始材料，尤其缺少能直接回答“{program_need}”的证据，因此暂不判定为事实错误。"
            return "当前主要卡在检索召回，关键 claim 还没有拿到足够可用的原始材料，因此暂不判定为事实错误。"
        if stage == "retrieval_filter":
            if critical_block_clause():
                return critical_block_clause() + " 因此当前先把主阻塞记在页保留层，不把它混成黑盒“没证据”。"
            if retrieval_review_clause():
                return retrieval_review_clause() + " 因此当前主要还停在页面保留阶段，暂不判定为事实错误。"
            if access_prefix and access_path_state in {"page_access_or_read_blocked", "access_blocked_and_unresolved"}:
                return access_prefix + " 因此当前主要还停在页面保留阶段，可用材料没有稳定留下。"
            if env_prefix:
                return env_prefix + " 因此当前主要还停在页面保留阶段，可用材料没有稳定留下。"
            if rescue_success_gate == "search_result_recovered" and kept_progress_from_raw <= 0:
                return rescue_success_clause() + "，但这些结果还没有稳定保成可用页面，因此暂不判定为事实错误。"
            if kept_progress_from_raw > 0:
                return keep_review_clause() + " 但当前保留下来的页面还没有稳定转成可直接使用的网页材料，因此暂不判定为事实错误。"
            if recoverable_filter_reason:
                top_reason = next(iter(recoverable_filter_reason.keys()), "")
                if top_reason == "opening_slot_mismatch":
                    return "当前主要卡在页面保留阶段：已经搜到一些相关页，但它们更多是盘中、收盘或泛涨跌材料，还不是开盘事实位点，所以没有稳定留下。"
            if recall_probe_used > 0 and recall_probe_raw_hits > 0:
                return recall_probe_clause() + "，但页面仍未稳定留下，因此暂不判定为事实错误。"
            if program_need:
                return f"当前主要卡在页面保留阶段：搜到过相关结果，但没有稳定留下能直接回答“{program_need}”的页面材料，因此暂不判定为事实错误。"
            return "当前主要卡在页面保留阶段：搜到过相关结果，但可用材料没有稳定留下，因此暂不判定为事实错误。"
        if stage == "retrieval_readiness":
            if critical_block_clause() and int(dominant_row.get("answer_candidate_total") or 0) > 0:
                return critical_block_clause() + " 当前已经不是搜不到，而是 candidate/point 还没有闭合，因此暂不判定为事实错误。"
            if retrieval_review_clause() and not env_prefix:
                return retrieval_review_clause() + " 当前已经不是纯召回问题，但还没整理出稳定可直裁的证据句，因此暂不判定为事实错误。"
            if env_prefix:
                return env_prefix + " 因此当前还没整理出可直接比对的候选句，先不判定为事实错误。"
            if missing_required_slots:
                layer_hint = "页层" if readiness_block_layer == "page" else "句层" if readiness_block_layer == "sentence" else "关键层级"
                return f"当前已经保留了一些相关页面，但{layer_hint}仍缺少{','.join(missing_required_slots[:3])}，所以还没整理出能直接回答“{program_need}”的证据句，因此暂不判定为事实错误。" + retained_structured_detail_clause()
            if rescue_success_gate == "detail_content_recovered":
                return rescue_success_clause() + "，但当前还没有稳定整理出能直接回答该 claim 的候选句，因此暂不判定为事实错误。" + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "") + (f" {candidate_gap_clause()}" if candidate_gap_clause() else "") + retained_structured_detail_clause()
            gap_clause = candidate_gap_clause()
            if readiness_promotion_used > 0 and int(dominant_row.get("answer_candidate_total") or 0) > 0:
                layer_hint = "句层" if readiness_block_layer == "sentence" else "页层" if readiness_block_layer == "page" else "句层"
                basis_clause = f" 当前最强候选句覆盖到 {candidate_slot_coverage_summary_text}。" if candidate_slot_coverage_summary_text else ""
                return f"当前已经把差一点被丢掉的相关页保了下来，但这些候选句还停在{layer_hint}，没有形成能直接回答“{program_need}”的稳定证据句，因此暂不判定为事实错误。" + (f" {keep_review_clause()}" if keep_review_clause() else "") + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "") + basis_clause + (f" {gap_clause}" if gap_clause else "") + opening_slot_clause(relaxed=True) + retained_structured_detail_clause()
            if readiness_promotion_used > 0:
                layer_hint = "句层" if readiness_block_layer == "sentence" else "页层" if readiness_block_layer == "page" else "页面到句子转换"
                return f"当前已经把差一点被丢掉的相关页保了下来，但还卡在{layer_hint}，没整理出能直接回答“{program_need}”的证据句，因此暂不判定为事实错误。" + (f" {keep_review_clause()}" if keep_review_clause() else "") + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "") + (f" {gap_clause}" if gap_clause else "") + opening_slot_clause(relaxed=True) + retained_structured_detail_clause()
            if recall_probe_used > 0 and recall_probe_raw_hits > 0 and direct_candidate_rescue_used <= 0:
                layer_hint = "页层" if readiness_block_layer == "page" else "句层" if readiness_block_layer == "sentence" else "句层"
                return f"{recall_probe_clause()}，但当前还卡在{layer_hint}，没有形成能直接回答“{program_need}”的稳定证据句，因此暂不判定为事实错误。" + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "") + (f" {gap_clause}" if gap_clause else "") + opening_slot_clause(relaxed=True) + retained_structured_detail_clause()
            if direct_candidate_rescue_used > 0:
                layer_hint = "页层" if readiness_block_layer == "page" else "句层" if readiness_block_layer == "sentence" else "句层"
                return f"{rescue_clause()}，但这些句子还停在{layer_hint}，没有形成能直接回答“{program_need}”的稳定证据句，因此暂不判定为事实错误。" + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "") + (f" {gap_clause}" if gap_clause else "") + opening_slot_clause(relaxed=True) + retained_structured_detail_clause()
            if program_need:
                layer_hint = "页层" if readiness_block_layer == "page" else "句层" if readiness_block_layer == "sentence" else "页面到句子转换"
                return f"当前已经保留了一些相关页面，但还卡在{layer_hint}，没整理出能直接回答“{program_need}”的证据句，因此暂不判定为事实错误。" + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "") + (f" {gap_clause}" if gap_clause else "") + retained_structured_detail_clause()
            return "当前已经保留了一些相关页面，但还没整理出可直接比对的证据句，因此暂不判定为事实错误。" + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "") + retained_structured_detail_clause()
        if stage == "evidence_point_not_convertible":
            if env_prefix:
                return env_prefix + " 页面里虽拿到部分内容，但还没形成稳定可比的证据点，因此暂不判定为事实错误。"
            if recall_probe_used > 0 and recall_probe_raw_hits > 0 and point_block_reason and program_need:
                return f"已经用更贴事实位点的问法补回候选材料，但当前仍卡在{point_block_reason}，还没转成能直接回答“{program_need}”的可裁决证据点，因此暂不判定为事实错误。" + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "") + opening_slot_clause()
            if point_block_reason and program_need:
                return f"当前页面里已经读到一些相关材料，但仍卡在{point_block_reason}，还没转成能直接回答“{program_need}”的可裁决证据点，因此暂不判定为事实错误。" + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "") + (f" {candidate_gap_clause()}" if candidate_gap_clause() else "") + opening_slot_clause()
            if program_need:
                return f"当前页面里已经读到一些相关材料，但还没转成能直接回答“{program_need}”的可裁决证据点，因此暂不判定为事实错误。" + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "")
            return "当前页面里已经读到一些相关材料，但还没转成可直接裁决的证据点，因此暂不判定为事实错误。" + (f" {kept_candidate_progress_clause()}" if kept_candidate_progress_clause() else "")
        if has_core_support and unresolved_details:
            return "核心结论已有部分支持，但高风险结构化细节仍未裁完，现阶段还不能把整题判成错误。" + retained_structured_detail_clause()
        if program_need:
            return f"没有形成能直接回答“{program_need}”的支持或反驳证据，因此当前不判定为事实错误。" + retained_structured_detail_clause()
        return "没有形成可直接裁决的支持或反驳证据，因此当前不判定为事实错误。" + retained_structured_detail_clause()
    if has_core_support and unresolved_details:
        return "核心结论已有部分支持，但高风险结构化细节仍未裁完，因此当前不判错。" + retained_structured_detail_clause()
    return ""


def evidence_reason(
    label: str,
    policy: str,
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    claim_pipeline_diagnostics: Optional[Dict[str, Any]] = None,
    evidence_non_decidable_state: Optional[Dict[str, Any]] = None,
) -> str:
    if label == LABEL_1 and policy == "secondary_detail_direct_refutation":
        detail_reason = secondary_detail_refutation_reason(extracted, evidence_summary)
        if detail_reason:
            return detail_reason
    if label == LABEL_2 and policy == "unsupported_claims_are_not_fact_errors":
        insufficient_reason = insufficient_evidence_reason(
            extracted,
            evidence_summary,
            claim_pipeline_diagnostics,
            evidence_non_decidable_state,
        )
        if insufficient_reason:
            return insufficient_reason
    claims = extracted.get("claims") if isinstance(extracted, dict) else []
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    claim_by_id = {
        str(claim.get("claim_id") or claim.get("id") or ""): claim
        for claim in claims
        if isinstance(claim, dict)
    }
    has_any_refuting = any(
        isinstance(summaries.get(claim_id), dict) and bool(summaries[claim_id].get("refuting_points"))
        for claim_id in claim_by_id
    )
    has_any_supporting = any(
        isinstance(summaries.get(claim_id), dict) and bool(summaries[claim_id].get("supporting_points"))
        for claim_id in claim_by_id
    )
    candidates: List[Tuple[int, str, str]] = []
    for claim_id, claim in claim_by_id.items():
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
        centrality = str(claim.get("centrality") or "")
        level = str(coverage.get("coverage_level") or "")
        refuting = summary.get("refuting_points") or []
        supporting = summary.get("supporting_points") or []
        uncertain = summary.get("uncertain_points") or []
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
        evidence_target = str(source_intent.get("evidence_target") or "")
        if label in {LABEL_0, LABEL_1} and has_any_refuting and not refuting:
            continue
        priority = 0
        if centrality == "core":
            priority += 4
        if refuting:
            priority += 4
            first_refuting = refuting[0] if isinstance(refuting[0], dict) else {}
            if mode == "numeric_fact":
                priority += 6
            if evidence_target == "prize_amount":
                priority += 4
            if isinstance(first_refuting, dict) and first_refuting.get("source_type") == "official":
                priority += 3
        elif label == LABEL_2 and supporting:
            priority += 3
            first_supporting = supporting[0] if isinstance(supporting[0], dict) else {}
            if mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result", "policy_fact", "route_fact", "entity_fact"}:
                priority += 3
            if isinstance(first_supporting, dict) and first_supporting.get("source_type") == "official":
                priority += 2
        if level in {"none", "weak"}:
            priority += 2
        if uncertain and not supporting:
            priority += 1
        if priority <= 0:
            continue
        detail = ""
        reason_hint = summary.get("reason_hint") if isinstance(summary.get("reason_hint"), dict) else {}
        hint_text = normalize_text(str(reason_hint.get("text") or ""))
        hint_status = normalize_text(str(reason_hint.get("status") or ""))
        if hint_text:
            if label in {LABEL_0, LABEL_1}:
                if has_any_refuting and hint_status != "refuted":
                    pass
                else:
                    candidates.append((priority + 1, hint_text.rstrip("。；; "), mode))
                    continue
            else:
                candidates.append((priority + 1, hint_text.rstrip("。；; "), mode))
                continue
        if refuting and isinstance(refuting[0], dict):
            detail = point_text(refuting[0])
        elif label == LABEL_2 and supporting and isinstance(supporting[0], dict):
            detail = point_text(supporting[0])
        if not detail:
            detail = coverage_text(summary)
        claim_text = compact_claim_text(str(claim.get("claim") or ""))
        if claim_text:
            candidates.append((priority, f"“{claim_text}”{detail}", mode))
    candidates.sort(reverse=True, key=lambda item: item[0])
    if label == LABEL_1 and any(mode == "numeric_fact" for _, _text, mode in candidates):
        candidates = [item for item in candidates if item[2] == "numeric_fact"]
    if candidates:
        core = "；".join(text for _, text, _mode in candidates[:2])
        if label == LABEL_0:
            if has_any_refuting:
                return f"主需相关核心事实存在直接反证：{core}。因此判为主需事实错误风险。"
            return f"主需相关核心事实缺少可靠证据支撑：{core}。因此判为主需事实错误风险。"
        if label == LABEL_1:
            if has_any_refuting:
                return f"未确认主结论错误，但回答中的附带细节存在直接反证：{core}。因此判为次需事实错误风险。"
            return f"未确认主结论错误，但回答中的附带细节缺少可靠证据支撑：{core}。因此判为次需事实错误风险。"
        if has_any_supporting:
            return f"关键 claim 已得到直接支持：{core}。因此当前不判定为事实错误。"
        return f"未发现足以直接反驳回答的证据；主要核查点为：{core}。因此不判定明确事实错误。"
    return policy_reason(label, policy)


def claims_for_reason(extracted: Dict[str, Any], modes: Optional[set] = None, centralities: Optional[set] = None, limit: int = 2) -> List[str]:
    claims = extracted.get("claims") if isinstance(extracted, dict) else []
    out: List[str] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        centrality = str(claim.get("centrality") or "")
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        mode = str(source_intent.get("evidence_mode") or "")
        if modes and mode not in modes:
            continue
        if centralities and centrality not in centralities:
            continue
        text = compact_claim_text(str(claim.get("claim") or ""), 56)
        if text:
            out.append(f"“{text}”")
    return out[:limit]


def market_time_detail_reason(extracted: Dict[str, Any]) -> str:
    examples = claims_for_reason(extracted, {"date_fact", "schedule_fact"}, None, 2)
    if examples:
        joined = "、".join(examples)
        return f"主要问题在于回答把{joined}作为市场解释依据；该时间、交易日或节假日细节与事实不符或缺乏可靠支撑，但不必然推翻整体市场含义主结论，因此判为次需事实错误。"
    return "主要问题在于回答的市场解释包含交易日、休市或节假日等关键时间细节；这类细节会影响解释可信度，但不必然推翻整体市场含义主结论，因此判为次需事实错误。"


def calibration_reason_text(label: str, policy: str, extracted: Dict[str, Any]) -> str:
    need_type = normalize_need_type(extracted.get("need_type"))
    if policy == "sports_result_has_multiple_unsupported_core_result_claims":
        examples = "、".join(claims_for_reason(extracted, {"event_result", "numeric_fact"}, {"core"}, 2))
        return f"回答直接给出多场实时赛果和具体比分（如{examples}），这类信息是用户主需本身，不是普通背景解释；在缺少可复核赛果上下文时，按高风险主需错误处理。"
    if policy == "sports_result_has_unsupported_core_result_claim":
        examples = "、".join(claims_for_reason(extracted, {"event_result", "numeric_fact"}, {"core"}, 1))
        return f"回答给出了核心赛果{examples}，属于用户主需中的实时结果；该类结论需要可复核比赛上下文支撑，缺失时按赛果风险处理。"
    if policy == "distance_position_core_numeric_distance_lacks_support":
        examples = "、".join(claims_for_reason(extracted, {"numeric_fact", "entity_fact"}, {"core"}, 2))
        return f"回答把当前位置和距离写成确定事实（如{examples}）。位置/距离题的核心就是该数值与位置，不能按普通开放解释处理，因此判为主需风险。"
    if policy == "fictional_scenario_contaminates_current_need":
        return "用户询问当前状态，回答却混入“虚构剧本、假设推演、非真实新闻”等内容；即使其中有澄清，这类虚构情节仍会直接污染当前事实主需。"
    if policy == "schedule_time_core_date_lacks_direct_evidence":
        examples = "、".join(claims_for_reason(extracted, {"date_fact", "schedule_fact"}, {"core"}, 2))
        return f"用户询问发布时间/日程，回答给出核心阶段日期（如{examples}）。这类日期直接决定主需答案，若阶段含义混淆或无法核实，应按主需时间事实风险处理。"
    if policy == "market_movement_resolved_forecast_overclaim":
        return "回答把市场预测写成确定结论，例如“即将迎来”“年内最大”“已无悬念”等，会让用户把未落地结果当作事实，属于主需层面的预测确定化。"
    if policy == "market_movement_has_unsupported_time_detail":
        return market_time_detail_reason(extracted)
    if policy == "geopolitical_supporting_absolute_detail_lacks_support":
        examples = "、".join(claims_for_reason(extracted, {"route_fact", "policy_fact", "event_result"}, {"supporting", "peripheral"}, 2))
        return f"回答主方向是开放式局势概括，但附带解释中包含高强度的军事行动、政策意图或路线因果断言（如{examples}），这类细节需要直接证据支撑；在证据不足时按次需风险处理。"
    if policy == "geopolitical_absolute_route_premise_lacks_support":
        examples = "、".join(claims_for_reason(extracted, {"route_fact"}, {"supporting", "peripheral"}, 2))
        return f"回答把路线前提写成了主结论的决定性依据（如{examples}），并用它推出“影响不大/没有影响”之类的核心判断；但这条绝对化路线前提没有直接证据支撑，因此按主需风险处理。"
    return policy_reason(label, policy)


def has_direct_refuting_evidence(evidence_summary: Optional[Dict[str, Any]]) -> bool:
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    for summary in summaries.values():
        if not isinstance(summary, dict):
            continue
        for point in summary.get("refuting_points") or []:
            if isinstance(point, dict) and point_is_strong_refutation(point, "general_fact", None, summary):
                return True
    return False


def has_direct_supporting_evidence(evidence_summary: Optional[Dict[str, Any]]) -> bool:
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    for summary in summaries.values():
        if not isinstance(summary, dict):
            continue
        for point in summary.get("supporting_points") or []:
            if isinstance(point, dict) and point.get("direct_answer") == "direct":
                return True
    return False


def has_atomic_refuting_evidence(evidence_summary: Optional[Dict[str, Any]]) -> bool:
    ledger = (
        evidence_summary.get("_evidence_ledger")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("_evidence_ledger"), dict)
        else {}
    )
    if not ledger:
        return False
    rows = ledger.get("atomic_refuted_points") if isinstance(ledger.get("atomic_refuted_points"), list) else []
    return any(isinstance(row, dict) for row in rows)


def attached_detail_refuting_reason_allowed(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
) -> bool:
    claims = extracted.get("claims") if isinstance(extracted, dict) and isinstance(extracted.get("claims"), list) else []
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    max_refuting_priority = 0
    max_unsupported_priority = 0
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
        centrality = str(claim.get("centrality") or "")
        mode = str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")
        evidence_target = str(source_intent.get("evidence_target") or "")
        stated_as_fact = normalize_bool(source_intent.get("stated_as_fact", True), True)
        if centrality not in {"supporting", "peripheral"} or not stated_as_fact:
            continue
        if mode not in HIGH_RISK_SUPPORTING_MODES:
            continue
        coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}
        coverage_level = str(coverage.get("coverage_level") or "")
        priority = 4
        if mode == "numeric_fact":
            priority += 4
        elif mode in {"date_fact", "schedule_fact"}:
            priority += 3
        elif mode in {"event_result", "policy_fact"}:
            priority += 2
        if evidence_target == "prize_amount":
            priority += 4
        if coverage_level in {"none", "weak", "partial"}:
            priority += 2
        refuting_points = [point for point in (summary.get("refuting_points") or []) if isinstance(point, dict)]
        direct_refuting = [point for point in refuting_points if point.get("direct_answer") == "direct"]
        supporting_points = [point for point in (summary.get("supporting_points") or []) if isinstance(point, dict)]
        if direct_refuting:
            first = direct_refuting[0]
            max_refuting_priority = max(
                max_refuting_priority,
                priority
                + (2 if str(first.get("source_type") or "") == "official" else 0)
                + (2 if str(first.get("point_contract_status") or "") == "satisfied" else 0),
            )
        elif not supporting_points and coverage_level in {"none", "weak", "partial"}:
            max_unsupported_priority = max(max_unsupported_priority, priority)
    return max_refuting_priority > 0 and max_refuting_priority >= max_unsupported_priority


def classify_decision_basis(
    label: str,
    policy: str = "",
    evidence_summary: Optional[Dict[str, Any]] = None,
    extracted: Optional[Dict[str, Any]] = None,
) -> str:
    if policy in RUBRIC_FALLBACK_POLICIES:
        return "rubric_fallback"
    if policy in {"evidence_first_core_direct_refutation", "secondary_detail_direct_refutation", "atomic_core_direct_refutation", "atomic_secondary_direct_refutation"}:
        return "evidence_refutation"
    if policy == "evidence_first_core_direct_support":
        return "evidence_support"
    if label in {LABEL_0, LABEL_1} and (has_direct_refuting_evidence(evidence_summary) or has_atomic_refuting_evidence(evidence_summary)):
        return "evidence_refutation"
    if (
        label == LABEL_2
        and isinstance(extracted, dict)
        and has_new_scheme_core_supporting_evidence(extracted, evidence_summary)
        and not has_direct_refuting_evidence(evidence_summary)
    ):
        return "evidence_support"
    if label == LABEL_2:
        return "insufficient_evidence"
    return "insufficient_evidence"


def normalize_reason_by_decision_basis(reason: str, label: str, decision_basis: str) -> str:
    reason = clean_user_reason(reason)
    if not reason:
        return "未发现明确事实错误"
    if decision_basis == "evidence_refutation":
        return reason
    if decision_basis == "evidence_support":
        return reason
    if decision_basis == "risk_calibration":
        prefix = "本次判断来自风险校准："
        if reason.startswith(prefix):
            return reason
        if label == LABEL_0 and "主需" not in reason:
            return prefix + reason
        if label == LABEL_1 and "次需" not in reason:
            return prefix + reason
        if label == LABEL_2 and "不判定" not in reason and "未发现" not in reason:
            return prefix + reason
        return reason
    if decision_basis in {"rubric_fallback", "rubric_fallback_with_partial_evidence"}:
        prefix = "本次判断来自判标先验兜底："
        if reason.startswith(prefix):
            return reason
        if label == LABEL_0 and "主需" not in reason:
            return prefix + reason
        if label == LABEL_1 and "次需" not in reason:
            return prefix + reason
        if label == LABEL_2 and "不判定" not in reason and "未发现" not in reason:
            return prefix + reason
        return reason
    if decision_basis == "insufficient_evidence":
        if label in {LABEL_0, LABEL_1}:
            return f"本次判错不是因为发现直接反证，而是因为回答存在高风险事实表达边界：{reason}"
        if "证据不足不能等同于事实错误" in reason or "未发现" in reason or "没有形成可直接裁决" in reason:
            return reason
        return f"没有形成可直接裁决的支持或反驳证据；{reason}"
    return reason


def is_template_like_reason(reason: str) -> bool:
    text = normalize_text(reason)
    if not text:
        return True
    template_terms = [
        "证据聚合判断为",
        "缺少直接证据支撑",
        "缺少可靠证据支撑",
        "未检索到可用直接证据",
        "检索到",
        "但缺少直接回答",
        "高风险主需",
        "属于次要事实风险",
        "不能作为可靠结论",
        "证据不足不能等同于事实错误",
        "未发现足以直接反驳",
    ]
    return any(term in text for term in template_terms)


def should_refine_final_reason(verify_obj: Dict[str, Any], reason: str, extracted: Dict[str, Any]) -> bool:
    if CLIENT is None:
        return False
    label = pick_label(verify_obj.get("final_label")) or LABEL_2
    decision_basis = str(verify_obj.get("_decision_basis") or "")
    evidence_summary = verify_obj.get("_evidence_summary_for_reason") if isinstance(verify_obj.get("_evidence_summary_for_reason"), dict) else None
    has_conflict = bool(final_reason_conflict_issues(reason, label, decision_basis, evidence_summary))
    if not ENABLE_FINAL_REASON_REFINE and not has_conflict:
        return False
    if decision_basis == "risk_calibration":
        return False
    need_type = normalize_need_type(extracted.get("need_type"))
    if need_type in {"geopolitical_claim"} and not has_conflict:
        return False
    decision_basis = str(verify_obj.get("_decision_basis") or "")
    reason_source = str(verify_obj.get("_final_reason_source") or "")
    if has_conflict:
        return True
    if verify_obj.get("_evidence_override"):
        return True
    if verify_obj.get("_decision_policy") and reason_source in {"llm_verify", "llm_verify_fallback", "emergency_fallback"}:
        return True
    if reason_source in {"llm_verify_fallback", "emergency_fallback"} and is_template_like_reason(reason):
        return True
    return False


def clean_user_reason(reason: str) -> str:
    reason = normalize_text(reason)
    replacements = {
        "coverage_level=none、no_web_evidence": "没有检索到可用直接网页证据",
        "coverage_level=none": "证据覆盖为空",
        "no_web_evidence": "没有可用网页证据",
    }
    for old, new in replacements.items():
        reason = reason.replace(old, new)
    return reason


def final_reason_conflict_issues(reason: str, label: str, decision_basis: str, evidence_summary: Optional[Dict[str, Any]]) -> List[str]:
    text = normalize_text(reason)
    issues: List[str] = []
    if not text:
        return ["reason_empty"]
    no_error_terms = [
        "无事实错误",
        "不构成事实错误",
        "不构成明确事实错误",
        "不能判错",
        "不能认定回答存在事实错误",
        "不能认定回答存在明确事实错误",
        "不能认定答案存在事实错误",
        "不能认定答案存在明确事实错误",
        "不能判定存在明确事实错误",
        "不能据此认定",
        "不能据此定为错误",
        "不能判为0或1",
        "不能判0或1",
        "不判0或1",
        "不能给0或1",
        "不能把证据不足当作事实错误",
        "不足以证明存在事实错误",
        "不判定为事实错误",
        "无法证明存在事实错误",
        "没有发现可被直接证据明确反驳的核心事实错误",
        "没有发现明确事实错误",
        "没有发现可直接反驳的事实错误",
        "未发现足以构成明确事实错误",
        "未能直接反驳任何核心断言",
        "不能作为有效事实错误依据",
        "不能作为明确错误点",
        "只能判为证据不足",
        "最终标签为2",
        "最终判2",
        "最终判 2",
        "判为2",
        "判定为2",
        "无明确事实错误",
    ]
    error_terms = [
        "主需存在事实错误",
        "次需存在事实错误",
        "判为主需事实错误",
        "判为次需事实错误",
        "构成主需事实错误",
        "构成次需事实错误",
        "最终标签为0",
        "最终标签为1",
    ]
    if label in {LABEL_0, LABEL_1} and any(term in text for term in no_error_terms):
        issues.append("错误类标签但reason说无错或不能判错")
    if label in {LABEL_0, LABEL_1} and re.search(r"最终标签为\s*2|判为\s*2|判定为\s*2|最终判\s*2", text):
        issues.append("错误类标签但reason写成最终为2")
    if label in {LABEL_0, LABEL_1} and any(term in text for term in ["不能认定存在明确事实错误", "无法确认任何事实错误", "不构成主需或次需错误"]):
        issues.append("错误类标签但reason明确否认存在事实错误")
    if label in {LABEL_0, LABEL_1} and re.search(r"不能作为.{0,8}事实错误依据", text):
        issues.append("错误类标签但reason否定事实错误依据")
    if label == LABEL_2 and any(term in text for term in error_terms):
        issues.append("无错标签但reason说存在事实错误")
    has_refuting = has_direct_refuting_evidence(evidence_summary) or has_atomic_refuting_evidence(evidence_summary)
    has_supporting = has_direct_supporting_evidence(evidence_summary)
    if not has_refuting and any(term in text for term in ["证据显示错误", "证据证明错误", "直接反证", "已经被反驳", "被证据反驳"]):
        issues.append("没有直接反证却写成证据反驳")
    if decision_basis == "insufficient_evidence" and label in {LABEL_0, LABEL_1}:
        if any(term in text for term in ["证据不足", "没有直接反驳", "没有任何直接反驳", "无法判定", "不能判定"]):
            issues.append("错误类标签却只用证据不足解释")
    if decision_basis == "evidence_support":
        if not has_supporting:
            issues.append("没有直接支持却写成 evidence_support")
        if any(term in text for term in ["证据不足", "不能判定", "没有直接反驳"]):
            issues.append("evidence_support 却写成缺证据")
    if label in {LABEL_0, LABEL_1} and any(term in text for term in ["没有直接证据", "缺少直接证据", "没有可用的直接网页证据", "缺少直接网页证据", "没有任何可用网页直接支撑", "没有得到可直接核查", "没有拿到可用的直接网页证据"]):
        if not any(term in text for term in ["边界", "风险", "主需", "次需", "实时", "具体", "确定", "预测", "虚构", "强断言", "过于绝对", "任务"]):
            issues.append("错误类标签但reason主要依赖证据不足")
    return issues


def llm_reason_is_safe(reason: str, label: str, decision_basis: str, evidence_summary: Optional[Dict[str, Any]]) -> bool:
    text = normalize_text(reason)
    if len(text) < 12:
        return False
    if "运行异常" in text or "裁决失败" in text or "抽取失败" in text:
        return False
    if final_reason_conflict_issues(text, label, decision_basis, evidence_summary):
        return False
    if label in {LABEL_0, LABEL_1} and any(term in text for term in ["最终判为无事实错误", "判为无事实错误", "不构成事实错误", "不构成明确事实错误", "不能判错", "只能判为不确定", "不能认定回答存在事实错误", "不能认定回答存在明确事实错误", "不能判定存在明确事实错误", "不能据此定为错误", "最终标签为2", "判为2", "判定为2", "应判为2", "只能判2", "不能判0或1", "无法判0或1", "不能给0或1", "无法给0或1"]):
        return False
    if label == LABEL_2 and any(term in text for term in ["判为主需事实错误", "判为次需事实错误", "构成主需事实错误", "构成次需事实错误", "最终标签为0", "最终标签为1"]):
        return False
    has_refuting = has_direct_refuting_evidence(evidence_summary) or has_atomic_refuting_evidence(evidence_summary)
    evidence_claim_words = ["证据显示", "证据证明", "直接反证", "检索到反证", "被证据反驳"]
    if not has_refuting and any(term in text for term in evidence_claim_words):
        return False
    if decision_basis == "evidence_support":
        return has_direct_supporting_evidence(evidence_summary) and any(term in text for term in ["支持", "证据", "关键", "得到", "核对", "一致"])
    if decision_basis in {"rubric_fallback", "rubric_fallback_with_partial_evidence"}:
        if any(term in text for term in ["直接反证", "证据显示错误", "已经被反驳"]):
            return False
        return any(term in text for term in ["主需", "次需", "确定", "细节", "核心", "金额", "日期", "预测", "绝对", "关系", "不判定", "未发现"])
    if decision_basis == "insufficient_evidence" or label == LABEL_2:
        if any(term in text for term in ["证据显示错误", "直接反证", "已经被反驳"]):
            return False
    return True


def claim_decision_slots(claim: Dict[str, Any]) -> Dict[str, Any]:
    program = claim.get("evidence_need_program") if isinstance(claim.get("evidence_need_program"), dict) else {}
    slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    return slots if isinstance(slots, dict) else {}


def claim_answer_role_impact(claim: Dict[str, Any]) -> str:
    program = claim.get("evidence_need_program") if isinstance(claim.get("evidence_need_program"), dict) else {}
    return str(program.get("answer_role_impact") or claim.get("centrality") or "")


def claim_evidence_mode_from_summary(claim: Dict[str, Any], summary: Optional[Dict[str, Any]]) -> str:
    summary = summary if isinstance(summary, dict) else {}
    source_intent = claim.get("source_intent") if isinstance(claim.get("source_intent"), dict) else {}
    return str(summary.get("evidence_mode") or source_intent.get("evidence_mode") or "")


def claim_is_core_assertion(claim: Dict[str, Any]) -> bool:
    text = normalize_text(str(claim.get("claim") or ""))
    centrality = str(claim.get("centrality") or "")
    role = claim_answer_role_impact(claim)
    slots = claim_decision_slots(claim)
    if centrality == "core" or role == "core":
        return True
    if str(slots.get("metric_or_relation") or "").strip() and str(slots.get("status_or_result") or "").strip():
        return True
    if str(slots.get("time_scope") or "").strip() and str(slots.get("status_or_result") or "").strip():
        return True
    if re.search(r"比.+更|更.+", text):
        return True
    return False


def claim_is_surface_fact(claim: Dict[str, Any], summary: Optional[Dict[str, Any]] = None) -> bool:
    text = normalize_text(str(claim.get("claim") or ""))
    mode = claim_evidence_mode_from_summary(claim, summary)
    slots = claim_decision_slots(claim)
    buckets = slots.get("anchor_buckets") if isinstance(slots.get("anchor_buckets"), list) else []
    if str(claim.get("centrality") or "") == "core" or claim_answer_role_impact(claim) == "core":
        return False
    if mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result", "financial_quote", "market_movement"}:
        return True
    if any(str(bucket) in {"time", "event", "numeric", "status"} for bucket in buckets):
        return True
    return bool(str(slots.get("subject") or "").strip() and str(slots.get("status_or_result") or "").strip())


def claim_topic_terms(claim: Dict[str, Any]) -> List[str]:
    slots = claim_decision_slots(claim)
    raw_terms: List[str] = []
    for key in ("subject", "object", "metric_or_relation", "status_or_result"):
        value = normalize_text(str(slots.get(key) or ""))
        if value:
            raw_terms.append(value)
    claim_text = normalize_text(str(claim.get("claim") or ""))
    if claim_text:
        raw_terms.extend(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", claim_text)[:6])
    terms: List[str] = []
    seen = set()
    for term in raw_terms:
        cleaned = re.sub(r"[，。；、/\\|（）()：:\s]+", "", term)
        if len(cleaned) < 2 or cleaned in seen:
            continue
        seen.add(cleaned)
        terms.append(cleaned)
    return terms[:8]


def claim_topics_overlap(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    left_terms = claim_topic_terms(left)
    right_terms = claim_topic_terms(right)
    for left_term in left_terms:
        for right_term in right_terms:
            if left_term in right_term or right_term in left_term:
                return True
    return False


def build_core_assertion_audit(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    claim_pipeline_diagnostics: Optional[Dict[str, Any]],
    evidence_ledger: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    claims = extracted.get("claims") if isinstance(extracted, dict) and isinstance(extracted.get("claims"), list) else []
    claim_by_id = {
        str(claim.get("claim_id") or claim.get("id") or ""): claim
        for claim in claims
        if isinstance(claim, dict) and str(claim.get("claim_id") or claim.get("id") or "")
    }
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    ledger = evidence_ledger if isinstance(evidence_ledger, dict) else {}
    state_by_claim: Dict[str, str] = {}
    for row in ledger.get("claim_rows") or []:
        if isinstance(row, dict):
            state_by_claim[str(row.get("claim_id") or "")] = str(row.get("state") or "")
    pipeline_by_claim = {
        str(row.get("claim_id") or ""): row
        for row in (
            claim_pipeline_diagnostics.get("items")
            if isinstance(claim_pipeline_diagnostics, dict) and isinstance(claim_pipeline_diagnostics.get("items"), list)
            else []
        )
        if isinstance(row, dict)
    }
    core_assertions: List[Dict[str, Any]] = []
    unresolved_core: List[Dict[str, Any]] = []
    surface_hits: List[Dict[str, Any]] = []
    role_review: List[Dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        state = state_by_claim.get(claim_id, "unresolved")
        pipeline_row = pipeline_by_claim.get(claim_id, {})
        text = compact_claim_text(str(claim.get("claim") or ""), 110)
        if claim_is_core_assertion(claim):
            row = {
                "claim_id": claim_id,
                "claim": text,
                "state": state,
                "answer_role_impact": claim_answer_role_impact(claim),
                "pipeline_stage": str(pipeline_row.get("pipeline_stage") or ""),
            }
            core_assertions.append(row)
            if state not in {"confirmed", "refuted"}:
                unresolved_core.append(row)
            role_review.append(
                {
                    "claim_id": claim_id,
                    "claim": text,
                    "role_before": str(claim.get("centrality") or ""),
                    "answer_role_impact": claim_answer_role_impact(claim),
                    "role_after": "core_assertion",
                    "reason": "claim_contains_explanation_or_interpretation_marker",
                }
            )
        if claim_is_surface_fact(claim, summary):
            hit_state = ""
            if state == "confirmed":
                hit_state = "confirmed"
            elif str(pipeline_row.get("slot_contract_state") or "") == "same_slot_ready":
                hit_state = "same_slot_ready"
            elif int(pipeline_row.get("answer_candidate_total") or 0) > 0:
                hit_state = "candidate_present"
            if hit_state:
                surface_hits.append(
                    {
                        "claim_id": claim_id,
                        "claim": text,
                        "state": state,
                        "surface_hit_state": hit_state,
                        "direct_evidence_gate_result": str(pipeline_row.get("direct_evidence_gate_result") or ""),
                    }
                )
    same_topic_pairs: List[Dict[str, Any]] = []
    for surface in surface_hits:
        surface_claim = next((c for c in claims if isinstance(c, dict) and str(c.get("claim_id") or c.get("id") or "") == surface.get("claim_id")), {})
        for core in unresolved_core:
            core_claim = next((c for c in claims if isinstance(c, dict) and str(c.get("claim_id") or c.get("id") or "") == core.get("claim_id")), {})
            if isinstance(surface_claim, dict) and isinstance(core_claim, dict) and claim_topics_overlap(surface_claim, core_claim):
                same_topic_pairs.append(
                    {
                        "surface_claim_id": surface.get("claim_id"),
                        "core_claim_id": core.get("claim_id"),
                        "surface_state": surface.get("surface_hit_state"),
                    }
                )
    surface_fact_risk = bool(surface_hits and unresolved_core)
    missed_hint = ""
    if unresolved_core:
        missed_hint = f"核心解释/归因断言仍未闭合：{unresolved_core[0].get('claim')}"
    state = "surface_fact_confirmed_core_unresolved" if surface_fact_risk else "ok"
    return {
        "state": state,
        "surface_fact_risk": surface_fact_risk,
        "surface_fact_confirmed_but_core_unresolved": surface_fact_risk,
        "missed_core_assertion_hint": missed_hint,
        "claim_role_before_after": role_review[:6],
        "core_assertion_claims": core_assertions[:6],
        "surface_fact_hits": surface_hits[:6],
        "same_topic_surface_core_pairs": same_topic_pairs[:6],
    }


def build_cross_claim_consistency(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    claim_pipeline_diagnostics: Optional[Dict[str, Any]],
    evidence_ledger: Optional[Dict[str, Any]],
    core_assertion_audit: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    ledger = evidence_ledger if isinstance(evidence_ledger, dict) else {}
    audit = core_assertion_audit if isinstance(core_assertion_audit, dict) else {}
    confirmed = ledger.get("confirmed_points") if isinstance(ledger.get("confirmed_points"), list) else []
    refuted = ledger.get("refuted_points") if isinstance(ledger.get("refuted_points"), list) else []
    unresolved = ledger.get("unresolved_points") if isinstance(ledger.get("unresolved_points"), list) else []
    unresolved_core = [
        row for row in (audit.get("core_assertion_claims") or [])
        if isinstance(row, dict) and str(row.get("state") or "") not in {"confirmed", "refuted"}
    ]
    issues: List[Dict[str, Any]] = []
    if audit.get("surface_fact_risk"):
        issues.append(
            {
                "type": "surface_fact_confirmed_but_core_unresolved",
                "reason": str(audit.get("missed_core_assertion_hint") or "surface_fact_hit_core_unresolved"),
                "pairs": audit.get("same_topic_surface_core_pairs") or [],
            }
        )
    if refuted and unresolved_core:
        issues.append(
            {
                "type": "refuted_point_with_related_unresolved_core",
                "reason": "存在反证点，但仍有核心解释/结论 claim 未闭合，聚合时需要区分主次作用域。",
            }
        )
    consistency_label_pressure = "none"
    if refuted:
        consistency_label_pressure = "refute_pressure"
    elif audit.get("surface_fact_risk"):
        consistency_label_pressure = "keep_label_2_core_unresolved"
    elif unresolved_core:
        consistency_label_pressure = "core_unresolved"
    return {
        "state": "needs_review" if issues else "ok",
        "issues": issues[:6],
        "surface_fact_confirmed_but_core_unresolved": bool(audit.get("surface_fact_risk")),
        "same_topic_refute_count": len(refuted),
        "same_topic_unresolved_high_risk_count": len(unresolved_core),
        "confirmed_point_count": len(confirmed),
        "refuted_point_count": len(refuted),
        "unresolved_point_count": len(unresolved),
        "consistency_label_pressure": consistency_label_pressure,
    }


def cross_claim_consistency_reason(label: str, evidence_summary: Optional[Dict[str, Any]]) -> str:
    if label != LABEL_2 or not isinstance(evidence_summary, dict):
        return ""
    consistency = evidence_summary.get("_cross_claim_consistency") if isinstance(evidence_summary.get("_cross_claim_consistency"), dict) else {}
    audit = evidence_summary.get("_core_assertion_audit") if isinstance(evidence_summary.get("_core_assertion_audit"), dict) else {}
    if not consistency.get("surface_fact_confirmed_but_core_unresolved"):
        return ""
    surface_hits = audit.get("surface_fact_hits") if isinstance(audit.get("surface_fact_hits"), list) else []
    core_claims = [
        row for row in (audit.get("core_assertion_claims") or [])
        if isinstance(row, dict) and str(row.get("state") or "") not in {"confirmed", "refuted"}
    ]
    surface_text = str(surface_hits[0].get("claim") or "") if surface_hits else "表层事实"
    core_text = str(core_claims[0].get("claim") or "") if core_claims else str(audit.get("missed_core_assertion_hint") or "核心解释/结论断言")
    surface_state = str(surface_hits[0].get("surface_hit_state") or "") if surface_hits else ""
    if surface_state == "confirmed":
        surface_clause = f"表层事实已被证据账本确认：{surface_text}"
    elif surface_state:
        surface_clause = f"表层事实已有同槽候选命中但未越过 gate：{surface_text}"
    else:
        surface_clause = f"表层事实已有相关材料：{surface_text}"
    return f"{surface_clause}；但真正影响裁决的核心断言仍未闭合：{core_text}。当前没有同槽可裁决的冲突证据，不能把未闭合包装成事实错误，因此保守判为无事实错误。"


def _ledger_point_row(claim_id: str, claim_text: str, point: Dict[str, Any], state: str) -> Dict[str, Any]:
    return {
        "claim_id": claim_id,
        "claim": compact_claim_text(claim_text, 90),
        "state": state,
        "point": compact_claim_text(point_text(point), 160),
        "title": compact_claim_text(str(point.get("title") or ""), 90),
        "url": str(point.get("url") or ""),
        "slot_contract_state": str(point.get("slot_contract_state") or ""),
        "slot_coverage": point.get("slot_coverage") if isinstance(point.get("slot_coverage"), dict) else {},
        "slot_missing": point.get("slot_missing") if isinstance(point.get("slot_missing"), list) else [],
        "slot_mismatch": point.get("slot_mismatch") if isinstance(point.get("slot_mismatch"), list) else [],
        "slot_conflict": point.get("slot_conflict") if isinstance(point.get("slot_conflict"), list) else [],
        "direct_evidence_gate_result": str(point.get("direct_evidence_gate_result") or ""),
        "candidate_conflict_profile": point.get("candidate_conflict_profile") if isinstance(point.get("candidate_conflict_profile"), dict) else {},
        "conflict_type": str(point.get("conflict_type") or ""),
        "conflict_strength": str(point.get("conflict_strength") or ""),
        "conflict_slot": str(point.get("conflict_slot") or ""),
        "claim_value": point.get("claim_value"),
        "evidence_value": point.get("evidence_value"),
        "same_slot_conflict_ready": bool(point.get("same_slot_conflict_ready")),
    }


ATOMIC_REFUTATION_CONVERTER_RISK_TYPES = {
    "market_calendar_status",
    "exclusive_or_only_path",
    "event_result_status",
    "phase_boundary_time",
}

ATOMIC_REFUTATION_LABEL_BY_CENTRALITY = {
    "core": LABEL_0,
    "supporting": LABEL_1,
    "peripheral": LABEL_1,
}


def _atomic_converter_surface_text(point: Dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            str(value)
            for value in [
                point.get("sentence"),
                point.get("evidence_sentence"),
                point.get("text"),
                point.get("title"),
                point.get("url"),
            ]
            if normalize_text(str(value or ""))
        )
    ).lower()


def _atomic_converter_has_terms(text: str, terms: List[str]) -> bool:
    lowered = normalize_text(text).lower()
    return bool(lowered) and any(normalize_text(str(term)).lower() in lowered for term in terms if normalize_text(str(term)))


def _atomic_converter_label(row: Dict[str, Any]) -> str:
    centrality = str(row.get("centrality_hint") or row.get("answer_role_impact") or "").lower()
    return ATOMIC_REFUTATION_LABEL_BY_CENTRALITY.get(centrality, LABEL_1)


def _atomic_converter_extract_score_pair(text: str) -> Optional[Tuple[int, int]]:
    clean = normalize_text(str(text or ""))
    if _atomic_converter_score_text_is_date_like(clean):
        return None
    match = re.search(r"\b(\d{1,3})\s*[-:：]\s*(\d{1,3})\b", clean)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _atomic_converter_score_text_is_date_like(text: str) -> bool:
    clean = normalize_text(str(text or ""))
    if not clean:
        return False
    if re.search(r"20\d{2}\s*[-年/]\s*\d{1,2}\s*[-月/]\s*\d{1,2}", clean):
        return True
    if re.fullmatch(r"0\d\s*[-/]\s*\d{1,2}", clean):
        return True
    if re.fullmatch(r"\d{1,2}\s*月\s*\d{1,2}\s*日?", clean):
        return True
    return False


def _atomic_converter_has_event_score_detail(text: str) -> bool:
    clean = normalize_text(str(text or ""))
    return bool(
        re.search(
            r"\d{1,3}\s*[-:：]\s*\d{1,3}\s*[\(（][^)）]*\d{1,3}\s*[-:：]\s*\d{1,3}",
            clean,
        )
    )


def _atomic_converter_entity_variants(value: str) -> List[str]:
    clean = normalize_text(str(value or ""))
    if not clean:
        return []
    no_paren = normalize_text(re.sub(r"[（(].*?[）)]", "", clean))
    variants = [clean, no_paren]
    for item in [clean, no_paren]:
        if "·" in item:
            variants.append(item.split("·")[-1])
        if " " in item:
            variants.extend(part for part in item.split() if len(part) >= 2)
    return dedupe_keep_order([v for v in variants if len(v) >= 2])


def _atomic_converter_event_participants_overlap(atomic_row: Dict[str, Any], candidate_text: str) -> bool:
    slots = atomic_row.get("slot_contract") if isinstance(atomic_row.get("slot_contract"), dict) else {}
    subject_variants = _atomic_converter_entity_variants(str(slots.get("subject") or ""))
    object_variants = _atomic_converter_entity_variants(str(slots.get("object") or ""))
    candidate = normalize_text(candidate_text).lower()
    subject_hit = any(term.lower() in candidate for term in subject_variants)
    object_hit = any(term.lower() in candidate for term in object_variants)
    if subject_variants and object_variants:
        return subject_hit and object_hit
    return subject_hit or object_hit


def _atomic_converter_event_subject_overlap(atomic_row: Dict[str, Any], candidate_text: str) -> bool:
    slots = atomic_row.get("slot_contract") if isinstance(atomic_row.get("slot_contract"), dict) else {}
    subject_variants = _atomic_converter_entity_variants(str(slots.get("subject") or ""))
    candidate = normalize_text(candidate_text).lower()
    return bool(subject_variants) and any(term.lower() in candidate for term in subject_variants)


def _atomic_converter_event_subject_near_terms(
    atomic_row: Dict[str, Any],
    candidate_text: str,
    terms: List[str],
    max_gap: int = 16,
) -> bool:
    slots = atomic_row.get("slot_contract") if isinstance(atomic_row.get("slot_contract"), dict) else {}
    subject_variants = _atomic_converter_entity_variants(str(slots.get("subject") or ""))
    candidate = normalize_text(candidate_text).lower()
    if not subject_variants or not candidate:
        return False
    term_values = [normalize_text(str(term)).lower() for term in terms if normalize_text(str(term))]
    for subject in subject_variants:
        subject_l = subject.lower()
        for subject_match in re.finditer(re.escape(subject_l), candidate):
            subject_start = subject_match.start()
            subject_end = subject_match.end()
            for term in term_values:
                for term_match in re.finditer(re.escape(term), candidate):
                    term_start = term_match.start()
                    term_end = term_match.end()
                    gap = max(term_start - subject_end, subject_start - term_end, 0)
                    if gap <= max_gap:
                        return True
    return False


def _atomic_converter_score_scale_compatible(claim_text: str, evidence_value_text: str) -> bool:
    claim_score = _atomic_converter_extract_score_pair(claim_text)
    evidence_score = _atomic_converter_extract_score_pair(evidence_value_text)
    if not claim_score or not evidence_score:
        return False
    claim_max = max(claim_score)
    evidence_max = max(evidence_score)
    # High-scoring events such as basketball must not be refuted by small
    # series records or date-like fragments; low-scoring sports remain allowed.
    if claim_max >= 20:
        return evidence_max >= max(20, int(claim_max * 0.4))
    return evidence_max < 20


def _atomic_converter_extract_chinese_date(text: str) -> Optional[Tuple[int, int, int]]:
    clean = normalize_text(text)
    match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", clean)
    if not match:
        match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", clean)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _atomic_converter_named_holiday_mismatch(claim_text: str, slot_time_scope: str) -> Optional[str]:
    date_value = _atomic_converter_extract_chinese_date(slot_time_scope)
    if not date_value:
        return None
    _, month, day = date_value
    if "清明" in claim_text and not (month == 4 and 4 <= day <= 6):
        return "不在清明假期窗口"
    if "元旦" in claim_text and not (month == 1 and 1 <= day <= 3):
        return "不在元旦假期窗口"
    return None


def _atomic_converter_market_calendar_computed_conflict(
    atomic_row: Dict[str, Any],
    candidate: Dict[str, Any],
    claim_text: str,
) -> Optional[Dict[str, Any]]:
    if normalize_text(str(candidate.get("source_type") or "")).lower() != "computed":
        return None
    title = normalize_text(str(candidate.get("title") or ""))
    if title != "样本日期星期计算":
        return None
    slots = atomic_row.get("slot_contract") if isinstance(atomic_row.get("slot_contract"), dict) else {}
    mismatch = _atomic_converter_named_holiday_mismatch(claim_text, normalize_text(str(slots.get("time_scope") or "")))
    if not mismatch:
        return None
    if not _atomic_converter_has_terms(claim_text, ["休市", "假期", "节假日", "不开市", "清明", "元旦"]):
        return None
    converted = dict(candidate)
    converted["conflict_type"] = "status_conflict"
    converted["conflict_strength"] = "strong"
    converted["conflict_slot"] = "status_or_result"
    converted["claim_value"] = "closed_or_holiday"
    converted["evidence_value"] = mismatch
    converted["same_slot_conflict_ready"] = True
    converted["computed_calendar_conflict"] = True
    converted["direct_answer"] = "direct"
    return converted


def _atomic_converter_market_calendar_synthetic_candidate(
    atomic_row: Dict[str, Any],
    claim_text: str,
) -> Optional[Dict[str, Any]]:
    slots = atomic_row.get("slot_contract") if isinstance(atomic_row.get("slot_contract"), dict) else {}
    time_scope = normalize_text(str(slots.get("time_scope") or ""))
    mismatch = _atomic_converter_named_holiday_mismatch(claim_text, time_scope)
    if not mismatch:
        return None
    if not _atomic_converter_has_terms(claim_text, ["休市", "假期", "节假日", "不开市", "清明", "元旦"]):
        return None
    return {
        "sentence": f"原子日期节假日窗口计算 {time_scope} {mismatch}。",
        "source_type": "computed",
        "title": "样本日期星期计算",
        "url": "",
        "direct_answer": "direct",
    }


def _atomic_converter_phase_role(text: str) -> str:
    clean = normalize_text(str(text or "")).lower()
    if not clean:
        return ""
    result_terms = r"(结果|数据|公布|发布|出炉|release|released|publish|published)"
    end_terms = r"(结束|完成|完结|截止|complete|completed|completion|finish|finished)"
    phase_terms = r"(第一阶段|第二阶段|第三阶段|阶段|phase|stage)"
    start_terms = r"(开始|开启|启动|开展|进行|start|starts|started|begin|begins|commence|launched)"
    if re.search(result_terms, clean):
        return "result_release"
    if re.search(end_terms, clean):
        return "whole_event_end" if not re.search(phase_terms, clean) else "phase_end"
    if re.search(phase_terms, clean) and re.search(start_terms, clean):
        return "phase_start"
    if re.search(start_terms, clean):
        return "event_start"
    return ""


def _atomic_converter_phase_time_variant_terms(value: str) -> List[str]:
    clean = normalize_text(str(value or ""))
    if not clean:
        return []
    variants = [clean]
    for term in [
        ("开始", "启动"),
        ("开启", "启动"),
        ("结束", "完成"),
        ("公布", "发布"),
        ("结果", "数据"),
        ("第一阶段", "首阶段"),
        ("第二阶段", "下一阶段"),
    ]:
        if any(item in clean for item in term):
            variants.extend(term)
    return dedupe_keep_order([item for item in variants if item])


def _atomic_converter_phase_time_signature(text: str) -> Tuple[int, int, int]:
    clean = normalize_text(str(text or ""))
    if not clean:
        return 0, 0, 0
    match = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?", clean)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    english = re.search(r"\b([A-Za-z]{3,9})\s+(20\d{2})\b", clean)
    if english:
        month_map = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        month = month_map.get(english.group(1).lower()[:3], 0)
        if month:
            return int(english.group(2)), month, 0
    return 0, 0, 0


def _atomic_converter_phase_time_matches(atomic_row: Dict[str, Any], candidate_text: str) -> bool:
    slots = atomic_row.get("slot_contract") if isinstance(atomic_row.get("slot_contract"), dict) else {}
    claim_text = normalize_text(str(atomic_row.get("text") or ""))
    claim_role = normalize_text(str(slots.get("time_role") or _atomic_converter_phase_role(claim_text) or ""))
    candidate_role = normalize_text(str(_atomic_converter_phase_role(candidate_text) or ""))
    claim_time_terms = _atomic_converter_phase_time_variant_terms(str(slots.get("time_scope") or claim_text))
    candidate = normalize_text(candidate_text).lower()
    same_subject = _atomic_converter_event_subject_overlap(atomic_row, candidate_text)
    if not same_subject:
        slot_terms = _atomic_converter_entity_variants(str(slots.get("object") or ""))
        same_subject = any(term.lower() in candidate for term in slot_terms)
    if not same_subject:
        claim_terms = [
            term
            for term in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,18}", claim_text)
            if term not in {"第一阶段", "第二阶段", "第三阶段", "开始", "启动", "结束", "完成", "结果", "公布", "发布"}
        ]
        same_subject = any(term.lower() in candidate for term in claim_terms[:6])
    claim_sig = _atomic_converter_phase_time_signature(str(slots.get("time_scope") or claim_text))
    cand_sig = _atomic_converter_phase_time_signature(candidate_text)
    claim_terms = [normalize_text(term).lower() for term in claim_time_terms if normalize_text(term)]
    time_overlap = any(term in candidate for term in claim_terms)
    if not time_overlap and claim_sig[0] and cand_sig[0] and claim_sig[0] == cand_sig[0]:
        if claim_sig[1] and cand_sig[1] and claim_sig[1] == cand_sig[1]:
            time_overlap = True
        elif claim_sig[1] and not cand_sig[1]:
            time_overlap = True
    if not same_subject:
        return False
    if claim_role == "result_release" and candidate_role in {"phase_start", "event_start", "phase_end", "whole_event_end"} and time_overlap:
        return True
    if claim_role in {"whole_event_end", "phase_end"} and candidate_role in {"phase_start", "event_start"} and time_overlap:
        return True
    if claim_role == "phase_start" and candidate_role in {"result_release", "whole_event_end"} and time_overlap:
        return True
    return False


def _atomic_converter_candidate_topic_overlap(
    atomic_text: str,
    parent_text: str,
    candidate_text: str,
) -> bool:
    terms = [
        term
        for term in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,16}", normalize_text(atomic_text + " " + parent_text))
        if term
    ]
    stop = {"claim", "answer", "question", "result", "score", "official", "general", "today"}
    return any(term.lower() not in stop and term.lower() in candidate_text for term in terms[:12])


def _atomic_converter_trusted_news_or_authority(candidate: Dict[str, Any]) -> bool:
    title = normalize_text(str(candidate.get("title") or ""))
    url = normalize_text(str(candidate.get("url") or "")).lower()
    source_type = normalize_text(str(candidate.get("source_type") or "")).lower()
    page_role = normalize_text(str(candidate.get("page_role") or "")).lower()
    if page_role == "evidence_page" or source_type in {"official", "news"}:
        return True
    trusted_markers = [
        "news.cn",
        "xinhuanet",
        "新华网",
        "新华社",
        "people.com.cn",
        "人民网",
        "reuters",
        "apnews",
        "bbc.",
        "voachinese",
    ]
    return any(marker.lower() in url or marker.lower() in title.lower() for marker in trusted_markers)


def _atomic_converter_exclusive_claim_terms(text: str) -> bool:
    return _atomic_converter_has_terms(
        text,
        ["唯一", "只能", "必经", "必须经过", "没有其他", "唯一通道", "唯一海上通道", "only route", "must pass"],
    )


def _atomic_converter_alternative_route_terms(text: str) -> bool:
    return _atomic_converter_has_terms(
        text,
        [
            "替代",
            "替代路径",
            "替代路线",
            "替代通道",
            "找出路",
            "管道",
            "港口",
            "绕开",
            "绕过",
            "bypass",
            "alternative route",
            "pipeline",
            "port",
        ],
    )


def _atomic_converter_exclusive_subject_overlap(atomic_row: Dict[str, Any], candidate_text: str) -> bool:
    slots = atomic_row.get("slot_contract") if isinstance(atomic_row.get("slot_contract"), dict) else {}
    subject_terms = _atomic_converter_entity_variants(str(slots.get("subject") or ""))
    object_terms = _atomic_converter_entity_variants(str(slots.get("object") or ""))
    candidate = normalize_text(candidate_text).lower()
    subject_hit = any(term.lower() in candidate for term in subject_terms)
    object_hit = any(term.lower() in candidate for term in object_terms)
    # Alternative-route evidence can refute an exclusivity claim either by naming
    # the asserted chokepoint or by naming the affected actor/cargo plus a bypass.
    return subject_hit or object_hit


def _atomic_converter_match_row(
    atomic_row: Dict[str, Any],
    claim: Dict[str, Any],
    summary: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    risk_type = str(atomic_row.get("risk_type") or "")
    if risk_type not in ATOMIC_REFUTATION_CONVERTER_RISK_TYPES:
        return None
    atomic_id = str(atomic_row.get("atomic_claim_id") or "")
    claim_text = normalize_text(str(atomic_row.get("text") or ""))
    parent_text = normalize_text(str(claim.get("claim") or ""))
    candidates = [
        row for row in (summary.get("evidence_sentence_candidates") or [])
        if isinstance(row, dict)
    ]
    if risk_type == "market_calendar_status":
        synthetic_candidate = _atomic_converter_market_calendar_synthetic_candidate(atomic_row, claim_text)
        if synthetic_candidate:
            candidates.insert(0, synthetic_candidate)
    # Prefer atomic-query results when retrieval preserved the id, then fall back to
    # normal candidates from the same parent claim.
    candidates.sort(
        key=lambda row: (
            str(row.get("atomic_claim_id") or "") == atomic_id,
            bool(row.get("same_slot_conflict_ready")),
            str(row.get("conflict_strength") or "") == "strong",
            bool(row.get("page_role_consumed")),
        ),
        reverse=True,
    )
    for candidate in candidates:
        if risk_type == "market_calendar_status":
            computed_conflict = _atomic_converter_market_calendar_computed_conflict(atomic_row, candidate, claim_text)
            if computed_conflict:
                candidate = computed_conflict
            elif is_pseudo_evidence_candidate(candidate):
                continue
            elif not direct_evidence_gate_allows(candidate):
                continue
        elif risk_type == "exclusive_or_only_path":
            if is_pseudo_evidence_candidate(candidate):
                continue
        elif is_pseudo_evidence_candidate(candidate) or not direct_evidence_gate_allows(candidate):
            continue
        conflict_profile = candidate.get("candidate_conflict_profile") if isinstance(candidate.get("candidate_conflict_profile"), dict) else {}
        same_slot_ready = bool(candidate.get("same_slot_conflict_ready") or conflict_profile.get("same_slot_conflict_ready"))
        conflict_strength = str(candidate.get("conflict_strength") or conflict_profile.get("conflict_strength") or "")
        conflict_type = str(candidate.get("conflict_type") or conflict_profile.get("conflict_type") or "")
        conflict_slot = str(candidate.get("conflict_slot") or conflict_profile.get("conflict_slot") or "")
        candidate_text = _atomic_converter_surface_text(candidate)
        page_profile = normalize_text(str(candidate.get("page_utility_profile") or candidate.get("sentence_candidate_profile") or "")).lower()
        page_role = normalize_text(str(candidate.get("page_role") or "")).lower()
        source_type = normalize_text(str(candidate.get("source_type") or "")).lower()
        topic_overlap = _atomic_converter_candidate_topic_overlap(claim_text, parent_text, candidate_text)
        if risk_type == "market_calendar_status":
            if not (
                same_slot_ready
                and conflict_type == "status_conflict"
                and conflict_strength in {"strong", "medium"}
                and conflict_slot in {"status_or_result", "time_scope"}
            ):
                continue
        elif risk_type == "exclusive_or_only_path":
            if same_slot_ready and conflict_strength in {"strong", "medium"} and conflict_type in {"relation_conflict", "status_conflict"}:
                pass
            elif not (
                _atomic_converter_exclusive_claim_terms(claim_text)
                and _atomic_converter_alternative_route_terms(candidate_text)
                and (
                    _atomic_converter_trusted_news_or_authority(candidate)
                    or str(candidate.get("slot_contract_state") or "").lower() == "same_slot_ready"
                )
                and _atomic_converter_exclusive_subject_overlap(atomic_row, candidate_text)
            ):
                continue
            converted_route = dict(candidate)
            converted_route["conflict_type"] = "relation_conflict"
            converted_route["conflict_strength"] = "strong"
            converted_route["conflict_slot"] = "metric_or_relation"
            converted_route["claim_value"] = claim_text
            converted_route["evidence_value"] = normalize_text(str(candidate.get("sentence") or candidate.get("text") or candidate.get("title") or "alternative_route"))
            candidate = converted_route
        elif risk_type == "event_result_status":
            score_pattern = r"\b\d{1,3}\s*[-:：]\s*\d{1,3}\b"
            claim_has_score = bool(re.search(score_pattern, claim_text))
            claim_has_score_detail = _atomic_converter_has_event_score_detail(claim_text)
            evidence_value_text = normalize_text(str(candidate.get("evidence_value") or conflict_profile.get("evidence_value") or ""))
            evidence_value_score = _atomic_converter_extract_score_pair(evidence_value_text)
            evidence_value_has_score = bool(evidence_value_score)
            score_scale_compatible = _atomic_converter_score_scale_compatible(claim_text, evidence_value_text)
            participant_overlap = _atomic_converter_event_participants_overlap(atomic_row, candidate_text)
            subject_overlap = _atomic_converter_event_subject_overlap(atomic_row, candidate_text)
            slot_contract_ready = str(candidate.get("slot_contract_state") or "").lower() == "same_slot_ready"
            candidate_has_score = bool(evidence_value_has_score or EVENT_SCORE_PATTERN.search(candidate_text))
            participant_ready = participant_overlap or subject_overlap
            if not participant_ready:
                continue
            if same_slot_ready and conflict_strength in {"strong", "medium"} and conflict_type in {"result_conflict", "status_conflict", "event_mismatch", "status_mismatch"}:
                if not (
                    (claim_has_score and evidence_value_has_score and score_scale_compatible and conflict_type == "result_conflict")
                    or (claim_has_score_detail and candidate_has_score and participant_ready)
                ):
                    continue
            elif not (
                claim_has_score_detail
                and candidate_has_score
                and participant_ready
                and (page_role == "evidence_page" or page_profile == "result_or_score_page" or source_type in {"official", "news"})
            ):
                continue
            if claim_has_score_detail and candidate_has_score:
                converted_detail = dict(candidate)
                converted_detail["conflict_type"] = "status_conflict"
                converted_detail["conflict_strength"] = "strong"
                converted_detail["conflict_slot"] = "status_or_result"
                converted_detail["claim_value"] = claim_text
                converted_detail["evidence_value"] = evidence_value_text or normalize_text(str(candidate.get("sentence") or candidate.get("text") or candidate.get("title") or "score_conflict"))
                candidate = converted_detail
        elif risk_type == "phase_boundary_time":
            phase_candidates = [
                str(candidate.get("page_role") or "").lower(),
                str(candidate.get("source_type") or "").lower(),
                normalize_text(str(candidate.get("title") or "")),
                normalize_text(str(candidate.get("sentence") or candidate.get("text") or "")),
            ]
            candidate_text = _atomic_converter_surface_text(candidate)
            candidate_role = _atomic_converter_phase_role(candidate_text)
            claim_role = _atomic_converter_phase_role(claim_text)
            claim_time_text = normalize_text(str((atomic_row.get("slot_contract") or {}).get("time_scope") or claim_text))
            candidate_time_text = normalize_text(
                " ".join(
                    term
                    for term in [
                        candidate.get("title") or "",
                        candidate.get("sentence") or candidate.get("text") or "",
                        candidate.get("url") or "",
                    ]
                    if normalize_text(str(term or ""))
                )
            )
            page_role_ok = page_role in {"evidence_page"} or source_type in {"official", "news"}
            if is_pseudo_evidence_candidate(candidate) or not direct_evidence_gate_allows(candidate):
                continue
            if not page_role_ok and not _atomic_converter_trusted_news_or_authority(candidate):
                continue
            if not _atomic_converter_phase_time_matches(atomic_row, candidate_text):
                continue
            candidate_time_role = candidate_role or _atomic_converter_phase_role(candidate_time_text)
            if not candidate_time_role:
                continue
            if claim_role == "result_release" and candidate_time_role in {"phase_start", "event_start", "phase_end", "whole_event_end"}:
                converted_detail = dict(candidate)
                converted_detail["conflict_type"] = "time_role_conflict"
                converted_detail["conflict_strength"] = "strong"
                converted_detail["conflict_slot"] = "time_scope"
                converted_detail["claim_value"] = claim_time_text or claim_text
                converted_detail["evidence_value"] = candidate_time_text or candidate_text
                converted_detail["same_slot_conflict_ready"] = True
                converted_detail["phase_role_conflict"] = True
                candidate = converted_detail
            elif claim_role in {"whole_event_end", "phase_end"} and candidate_time_role in {"phase_start", "event_start"}:
                converted_detail = dict(candidate)
                converted_detail["conflict_type"] = "time_role_conflict"
                converted_detail["conflict_strength"] = "strong"
                converted_detail["conflict_slot"] = "time_scope"
                converted_detail["claim_value"] = claim_time_text or claim_text
                converted_detail["evidence_value"] = candidate_time_text or candidate_text
                converted_detail["same_slot_conflict_ready"] = True
                converted_detail["phase_role_conflict"] = True
                candidate = converted_detail
            else:
                continue
        converted = dict(candidate)
        converted["atomic_claim_id"] = atomic_id
        converted["parent_claim_id"] = str(atomic_row.get("parent_claim_id") or claim.get("claim_id") or claim.get("id") or "")
        converted["risk_type"] = risk_type
        converted["centrality_hint"] = str(atomic_row.get("centrality_hint") or "")
        converted["atomic_label"] = _atomic_converter_label(atomic_row)
        if risk_type in {"event_result_status", "phase_boundary_time"}:
            converted["atomic_label"] = LABEL_0
        converted["atomic_query"] = str((atomic_row.get("refutation_target") or {}).get("query") or "") if isinstance(atomic_row.get("refutation_target"), dict) else ""
        converted["atomic_refutation_reason"] = {
            "market_calendar_status": "same-slot market calendar conflict",
            "exclusive_or_only_path": "exclusive-path alternative evidence",
            "event_result_status": "same-slot event-result conflict",
            "phase_boundary_time": "phase-role time conflict",
        }.get(risk_type, "atomic refutation")
        converted["direct_answer"] = "direct"
        converted["conflict_strength"] = str(converted.get("conflict_strength") or conflict_strength or "strong")
        converted["conflict_type"] = str(converted.get("conflict_type") or conflict_type or risk_type)
        converted["conflict_slot"] = str(converted.get("conflict_slot") or conflict_slot or "status_or_result")
        converted["same_slot_conflict_ready"] = True
        return converted
    return None


def atomic_refutation_points_for_claim(
    atomic_rows: List[Dict[str, Any]],
    claim: Dict[str, Any],
    summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    converted: List[Dict[str, Any]] = []
    for atomic_row in atomic_rows:
        point = _atomic_converter_match_row(atomic_row, claim, summary)
        if point:
            converted.append(point)
    return converted[:2]


def _compact_debug_keys(value: Any, limit: int = 8) -> List[str]:
    if not isinstance(value, dict):
        return []
    return [str(key) for key in value.keys() if str(key)][:limit]


def _atomic_candidate_consumption_hints(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = summary.get("evidence_sentence_candidates") if isinstance(summary.get("evidence_sentence_candidates"), list) else []
    hints: List[Dict[str, Any]] = []
    for candidate in candidates[:4]:
        if not isinstance(candidate, dict):
            continue
        conflict_profile = (
            candidate.get("candidate_conflict_profile")
            if isinstance(candidate.get("candidate_conflict_profile"), dict)
            else {}
        )
        slot_missing = candidate.get("slot_missing") if isinstance(candidate.get("slot_missing"), list) else []
        slot_mismatch = candidate.get("slot_mismatch") if isinstance(candidate.get("slot_mismatch"), list) else []
        hint = {
            "title": compact_claim_text(str(candidate.get("title") or ""), 90),
            "url": str(candidate.get("url") or ""),
            "page_role": str(candidate.get("page_role") or ""),
            "direct_evidence_gate_result": str(candidate.get("direct_evidence_gate_result") or ""),
            "slot_contract_state": str(candidate.get("slot_contract_state") or ""),
            "slot_missing": [str(slot) for slot in slot_missing if str(slot)][:5],
            "slot_mismatch": [str(slot) for slot in slot_mismatch if str(slot)][:5],
            "conflict_type": str(candidate.get("conflict_type") or conflict_profile.get("conflict_type") or ""),
            "conflict_strength": str(candidate.get("conflict_strength") or conflict_profile.get("conflict_strength") or ""),
            "conflict_slot": str(candidate.get("conflict_slot") or conflict_profile.get("conflict_slot") or ""),
            "same_slot_conflict_ready": bool(candidate.get("same_slot_conflict_ready") or conflict_profile.get("same_slot_conflict_ready")),
        }
        if any(
            hint.get(key)
            for key in (
                "title",
                "url",
                "page_role",
                "direct_evidence_gate_result",
                "slot_contract_state",
                "conflict_type",
                "conflict_strength",
            )
        ) or hint["slot_missing"] or hint["slot_mismatch"]:
            hints.append(hint)
    return hints[:3]


def _reader_rescue_split_sentences(text: str, limit: int = 24) -> List[str]:
    clean = normalize_text(str(text or ""))
    if not clean:
        return []
    parts = [
        normalize_text(part)
        for part in re.split(r"[。！？!?；;\n]+|(?<=\.)\s+", clean)
        if normalize_text(part)
    ]
    out: List[str] = []
    for part in parts:
        if len(part) < 8:
            continue
        if len(part) > 260:
            # Long blobs are often nav text; keep a compact window around likely
            # evidence markers instead of treating the whole blob as a sentence.
            markers = re.search(r"(开始|启动|结束|完成|公布|发布|退赛|弃权|不战而胜|绕开|替代|管道|港口|距离|公里|km|result|release|start|complete|withdraw|walkover|alternative)", part, flags=re.I)
            if markers:
                start = max(0, markers.start() - 90)
                end = min(len(part), markers.end() + 150)
                part = normalize_text(part[start:end])
            else:
                part = compact_claim_text(part, 220)
        if part not in out:
            out.append(part)
        if len(out) >= limit:
            break
    return out


def _reader_rescue_source_text(source_item: Dict[str, Any], candidate: Optional[Dict[str, Any]] = None) -> str:
    candidate = candidate if isinstance(candidate, dict) else {}
    return normalize_text(
        " ".join(
            str(value)
            for value in [
                candidate.get("sentence"),
                source_item.get("detail"),
                source_item.get("snippet"),
                source_item.get("title"),
                candidate.get("title"),
            ]
            if normalize_text(str(value or ""))
        )
    )


def _reader_rescue_source_key(row: Dict[str, Any]) -> str:
    return evidence_lookup_key(str(row.get("url") or ""), str(row.get("title") or ""))


def _reader_rescue_source_allowed_for_conversion(source_item: Dict[str, Any], sentence: str) -> bool:
    if is_pseudo_evidence_candidate(source_item):
        return False
    source_type = normalize_text(str(source_item.get("source_type") or "")).lower()
    if source_type in {"official", "news", "finance", "sports"}:
        return True
    # Unknown pages can still be inspected for diagnostics, but conversion needs
    # a locally visible authority/news signal rather than a topic-specific domain.
    return _atomic_converter_trusted_news_or_authority(
        {
            "title": source_item.get("title"),
            "url": source_item.get("url"),
            "source_type": source_type,
            "page_role": source_item.get("page_role"),
            "sentence": sentence,
        }
    )


def _reader_rescue_subject_or_object_hit(atomic_row: Dict[str, Any], sentence: str) -> bool:
    slots = atomic_row.get("slot_contract") if isinstance(atomic_row.get("slot_contract"), dict) else {}
    candidate = normalize_text(sentence).lower()
    terms = (
        _atomic_converter_entity_variants(str(slots.get("subject") or ""))
        + _atomic_converter_entity_variants(str(slots.get("object") or ""))
    )
    terms = [term for term in terms if len(term) >= 2]
    if any(term.lower() in candidate for term in terms):
        return True
    atomic_text = normalize_text(str(atomic_row.get("text") or ""))
    fallback_terms = [
        term
        for term in re.findall(r"[\u4e00-\u9fffA-Za-z0-9·\-]{2,18}", atomic_text)
        if term not in {"第一阶段", "第二阶段", "第三阶段", "开始", "启动", "结束", "完成", "结果", "公布", "发布", "目前", "当前"}
    ][:6]
    return any(term.lower() in candidate for term in fallback_terms)


def _reader_rescue_phase_keyword_bridge(atomic_row: Dict[str, Any], sentence: str) -> bool:
    claim_text = normalize_text(str(atomic_row.get("text") or "")).lower()
    candidate = normalize_text(sentence).lower()
    if not claim_text or not candidate:
        return False
    bridges = [
        ("人口普查", "census"),
        ("阶段", "phase"),
        ("开始", "start"),
        ("结束", "complete"),
        ("结束", "end"),
        ("公布", "release"),
    ]
    return any((zh in claim_text and en in candidate) or (en in claim_text and zh in candidate) for zh, en in bridges)


def reader_rescue_slot_sentence_judge(atomic_row: Dict[str, Any], sentence: str, source_item: Dict[str, Any]) -> Dict[str, Any]:
    risk_type = str(atomic_row.get("risk_type") or "")
    sentence_text = normalize_text(sentence)
    claim_text = normalize_text(str(atomic_row.get("text") or ""))
    if not sentence_text:
        return {"state": "no_direct_sentence", "allow_conversion": False}
    subject_hit = _reader_rescue_subject_or_object_hit(atomic_row, sentence_text)
    if not subject_hit and risk_type == "phase_boundary_time":
        subject_hit = _reader_rescue_subject_or_object_hit(atomic_row, _reader_rescue_source_text(source_item))
    if not subject_hit and risk_type == "phase_boundary_time":
        source_text = _reader_rescue_source_text(source_item)
        subject_hit = _reader_rescue_phase_keyword_bridge(atomic_row, sentence_text) or _reader_rescue_phase_keyword_bridge(atomic_row, source_text)
    if not subject_hit:
        return {
            "state": "slot_mismatch",
            "allow_conversion": False,
            "blocked_layer": "subject_or_object",
            "sentence": compact_claim_text(sentence_text, 160),
        }
    if risk_type == "phase_boundary_time":
        claim_role = _atomic_converter_phase_role(claim_text)
        evidence_role = _atomic_converter_phase_role(sentence_text)
        if _atomic_converter_phase_time_matches(atomic_row, sentence_text):
            return {
                "state": "strong_conflict",
                "allow_conversion": _reader_rescue_source_allowed_for_conversion(source_item, sentence_text),
                "conflict_type": "time_role_conflict",
                "conflict_slot": "time_scope",
                "claim_value": normalize_text(str((atomic_row.get("slot_contract") or {}).get("time_scope") or claim_text)),
                "evidence_value": sentence_text,
                "claim_role": claim_role,
                "evidence_role": evidence_role,
            }
        return {
            "state": "role_or_time_not_conflicting" if evidence_role else "no_phase_role",
            "allow_conversion": False,
            "claim_role": claim_role,
            "evidence_role": evidence_role,
        }
    if risk_type == "event_result_status":
        claim_has_score_detail = _atomic_converter_has_event_score_detail(claim_text)
        has_score = bool(EVENT_SCORE_PATTERN.search(sentence_text))
        subject_near = _atomic_converter_event_subject_overlap(atomic_row, sentence_text)
        if claim_has_score_detail and has_score and subject_near:
            return {
                "state": "strong_conflict",
                "allow_conversion": _reader_rescue_source_allowed_for_conversion(source_item, sentence_text),
                "conflict_type": "status_conflict",
                "conflict_slot": "status_or_result",
                "claim_value": claim_text,
                "evidence_value": normalize_text(sentence_text),
            }
        return {
            "state": "event_status_not_conflicting",
            "allow_conversion": False,
            "has_score": has_score,
            "subject_near": subject_near,
        }
    if risk_type == "exclusive_or_only_path":
        if (
            _atomic_converter_exclusive_claim_terms(claim_text)
            and _atomic_converter_alternative_route_terms(sentence_text)
            and _atomic_converter_exclusive_subject_overlap(atomic_row, sentence_text)
        ):
            return {
                "state": "strong_conflict",
                "allow_conversion": _reader_rescue_source_allowed_for_conversion(source_item, sentence_text),
                "conflict_type": "relation_conflict",
                "conflict_slot": "metric_or_relation",
                "claim_value": claim_text,
                "evidence_value": sentence_text,
            }
        return {"state": "route_relation_not_conflicting", "allow_conversion": False}
    return {
        "state": "unsupported_risk_type_for_reader_conversion",
        "allow_conversion": False,
    }


def _reader_rescue_time_hit(atomic_row: Dict[str, Any], sentence: str, source_item: Dict[str, Any]) -> bool:
    risk_type = str(atomic_row.get("risk_type") or "")
    sentence_text = normalize_text(sentence)
    source_text = _reader_rescue_source_text(source_item)
    slots = atomic_row.get("slot_contract") if isinstance(atomic_row.get("slot_contract"), dict) else {}
    claim_text = normalize_text(str(atomic_row.get("text") or ""))
    time_scope = normalize_text(str(slots.get("time_scope") or ""))
    if risk_type == "phase_boundary_time" and _atomic_converter_phase_time_matches(atomic_row, sentence_text):
        return True
    candidate = normalize_text(" ".join([sentence_text, source_text])).lower()
    terms = _atomic_converter_phase_time_variant_terms(time_scope or claim_text)
    if any(normalize_text(term).lower() in candidate for term in terms if normalize_text(term)):
        return True
    claim_sig = _atomic_converter_phase_time_signature(time_scope or claim_text)
    cand_sig = _atomic_converter_phase_time_signature(sentence_text)
    if claim_sig[0] and cand_sig[0] and claim_sig[0] == cand_sig[0]:
        if not claim_sig[1] or not cand_sig[1] or claim_sig[1] == cand_sig[1]:
            return True
    return False


def _reader_rescue_status_hit(atomic_row: Dict[str, Any], sentence: str) -> bool:
    risk_type = str(atomic_row.get("risk_type") or "")
    sentence_text = normalize_text(sentence)
    if not sentence_text:
        return False
    if risk_type == "event_result_status":
        return event_has_result_signal(sentence_text)
    if risk_type == "exclusive_or_only_path":
        return bool(_atomic_converter_alternative_route_terms(sentence_text) or _atomic_converter_exclusive_claim_terms(sentence_text))
    if risk_type == "phase_boundary_time":
        return bool(_atomic_converter_phase_role(sentence_text))
    return bool(DIRECT_OBSERVABLE_PATTERN.search(sentence_text))


def _reader_rescue_sentence_candidate_debug_row(
    atomic_row: Dict[str, Any],
    source_item: Dict[str, Any],
    sentence: str,
    judge: Dict[str, Any],
    original_gate: str,
) -> Dict[str, Any]:
    sentence_text = normalize_text(sentence)
    risk_type = str(atomic_row.get("risk_type") or "")
    claim_text = normalize_text(str(atomic_row.get("text") or ""))
    source_allowed = _reader_rescue_source_allowed_for_conversion(source_item, sentence_text)
    claim_role = str(judge.get("claim_role") or "")
    evidence_role = str(judge.get("evidence_role") or "")
    if not claim_role and risk_type == "phase_boundary_time":
        claim_role = _atomic_converter_phase_role(claim_text)
    if not evidence_role and risk_type == "phase_boundary_time":
        evidence_role = _atomic_converter_phase_role(sentence_text)
    subject_hit = _reader_rescue_subject_or_object_hit(atomic_row, sentence_text)
    if not subject_hit and risk_type == "phase_boundary_time":
        source_text = _reader_rescue_source_text(source_item)
        subject_hit = (
            _reader_rescue_subject_or_object_hit(atomic_row, source_text)
            or _reader_rescue_phase_keyword_bridge(atomic_row, sentence_text)
            or _reader_rescue_phase_keyword_bridge(atomic_row, source_text)
        )
    status_hit = _reader_rescue_status_hit(atomic_row, sentence_text)
    time_hit = _reader_rescue_time_hit(atomic_row, sentence_text, source_item)
    state = str(judge.get("state") or "")
    conflict_type = str(judge.get("conflict_type") or "")
    conflict_slot = str(judge.get("conflict_slot") or "")
    row = {
        "atomic_claim_id": str(atomic_row.get("atomic_claim_id") or ""),
        "parent_claim_id": str(atomic_row.get("parent_claim_id") or ""),
        "risk_type": risk_type,
        "text": compact_claim_text(claim_text, 120),
        "sentence": compact_claim_text(sentence_text, 180),
        "title": compact_claim_text(str(source_item.get("title") or ""), 120),
        "url": str(source_item.get("url") or ""),
        "source_type": str(source_item.get("source_type") or ""),
        "original_gate": original_gate,
        "subject_hit": bool(subject_hit),
        "time_hit": bool(time_hit),
        "role_hit": bool(claim_role and evidence_role),
        "status_hit": bool(status_hit),
        "conflict_hint": state == "strong_conflict",
        "source_allowed": bool(source_allowed),
        "judge_state": state,
        "allow_conversion": bool(judge.get("allow_conversion")),
        "conflict_type": conflict_type,
        "conflict_slot": conflict_slot,
        "claim_role": claim_role,
        "evidence_role": evidence_role,
        "claim_value": judge.get("claim_value"),
        "evidence_value": judge.get("evidence_value"),
        "slot_contract": atomic_row.get("slot_contract") if isinstance(atomic_row.get("slot_contract"), dict) else {},
        "do_not_decide_without_gate": True,
    }
    return row


def reader_rescue_candidate_from_sentence(
    atomic_row: Dict[str, Any],
    source_item: Dict[str, Any],
    sentence: str,
    judge: Dict[str, Any],
    original_gate: str,
) -> Dict[str, Any]:
    row = {
        "sentence": sentence,
        "evidence_sentence": sentence,
        "score": 99,
        "source_type": source_item.get("source_type"),
        "url": source_item.get("url"),
        "title": source_item.get("title"),
        "page_role": "evidence_page",
        "evidence_page_ready": True,
        "page_role_reason": "reader_rescue_sentence_validated",
        "direct_answer": "direct",
        "sentence_directness": "direct",
        "sentence_candidate_profile": "direct_candidate",
        "slot_contract_state": "same_slot_ready",
        "same_slot_conflict_ready": True,
        "conflict_strength": "strong",
        "conflict_type": str(judge.get("conflict_type") or "reader_rescue_conflict"),
        "conflict_slot": str(judge.get("conflict_slot") or "status_or_result"),
        "claim_value": judge.get("claim_value"),
        "evidence_value": judge.get("evidence_value"),
        "reader_rescue_used": True,
        "reader_rescue_original_gate": original_gate,
        "reader_rescue_state": str(judge.get("state") or ""),
        "atomic_claim_id": str(atomic_row.get("atomic_claim_id") or ""),
        "atomic_risk_type": str(atomic_row.get("risk_type") or ""),
        "direct_evidence_gate_result": "allowed_reader_rescue_sentence",
        "page_role_consumed": True,
    }
    row["candidate_conflict_profile"] = {
        "state": "reader_rescue_conflict",
        "conflict_type": row["conflict_type"],
        "conflict_strength": row["conflict_strength"],
        "conflict_slot": row["conflict_slot"],
        "claim_value": row["claim_value"],
        "evidence_value": row["evidence_value"],
        "same_slot_conflict_ready": True,
        "gate_ready": True,
        "block_reason": "",
    }
    return row


def _reader_rescue_blocked_candidate_sources(
    claim_id: str,
    summary: Dict[str, Any],
    source_items: List[Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], Dict[str, Any], str]]:
    index = build_evidence_page_role_index([item for item in source_items if isinstance(item, dict)])
    rows: List[Tuple[Dict[str, Any], Dict[str, Any], str]] = []
    seen = set()
    for candidate in summary.get("evidence_sentence_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        gate = str(candidate.get("direct_evidence_gate_result") or direct_evidence_gate_result(candidate))
        if not gate.startswith("blocked_"):
            continue
        source_item = source_item_for_point(candidate, index) or candidate
        key = _reader_rescue_source_key(source_item) or _reader_rescue_source_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append((source_item, candidate, gate))
    for source_item in source_items:
        if not isinstance(source_item, dict):
            continue
        gate = direct_evidence_gate_result(source_item)
        if not gate.startswith("blocked_"):
            continue
        key = _reader_rescue_source_key(source_item)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append((source_item, {}, gate))
    return rows[:4]


def apply_blocked_page_reader_rescue(
    extracted: Dict[str, Any],
    claims: List[Dict[str, Any]],
    evidence_bundle: Optional[Dict[str, Any]],
    evidence_summary: Optional[Dict[str, Any]],
    debug_bucket: Optional[Dict[str, Any]] = None,
) -> None:
    if not isinstance(extracted, dict) or not isinstance(evidence_bundle, dict) or not isinstance(evidence_summary, dict):
        return
    summaries = evidence_summary.get("claim_summaries") if isinstance(evidence_summary.get("claim_summaries"), dict) else {}
    evidence_by_claim = evidence_bundle.get("evidence_by_claim") if isinstance(evidence_bundle.get("evidence_by_claim"), dict) else {}
    high_risk = extracted.get("high_risk_atomic_claims") if isinstance(extracted.get("high_risk_atomic_claims"), list) else []
    if not isinstance(summaries, dict) or not high_risk:
        return
    page_limit = max(0, int(os.environ.get("V2_READER_RESCUE_PAGE_LIMIT", "2") or 0))
    if any(str(row.get("risk_type") or "") == "phase_boundary_time" for row in high_risk if isinstance(row, dict)):
        page_limit = max(page_limit, 4)
    if page_limit <= 0:
        return
    debug_rows: List[Dict[str, Any]] = []
    pages_used = 0
    claim_by_id = {
        str(claim.get("claim_id") or claim.get("id") or ""): claim
        for claim in claims
        if isinstance(claim, dict) and str(claim.get("claim_id") or claim.get("id") or "")
    }
    convertible_risks = {"phase_boundary_time", "event_result_status", "exclusive_or_only_path"}
    sentence_candidate_rows: List[Dict[str, Any]] = []
    judge_debug_rows: List[Dict[str, Any]] = []
    for atomic_row in sorted([row for row in high_risk if isinstance(row, dict)], key=lambda row: int(row.get("search_priority") or 0), reverse=True):
        if pages_used >= page_limit:
            break
        risk_type = str(atomic_row.get("risk_type") or "")
        if risk_type not in convertible_risks:
            continue
        parent_id = str(atomic_row.get("parent_claim_id") or "")
        if not parent_id:
            inferred_parent = find_parent_claim_for_atomic(str(atomic_row.get("text") or ""), claims)
            parent_id = str(inferred_parent.get("claim_id") or inferred_parent.get("id") or "")
        if not parent_id or parent_id not in summaries:
            debug_rows.append(
                {
                    "atomic_claim_id": str(atomic_row.get("atomic_claim_id") or ""),
                    "risk_type": risk_type,
                    "state": "skipped_parent_summary_missing",
                    "parent_claim_id": parent_id,
                }
            )
            continue
        summary = summaries.get(parent_id) if isinstance(summaries.get(parent_id), dict) else {}
        source_items = [item for item in evidence_by_claim.get(parent_id, []) if isinstance(item, dict)]
        sources = _reader_rescue_blocked_candidate_sources(parent_id, summary, source_items)
        if not sources:
            debug_rows.append(
                {
                    "atomic_claim_id": str(atomic_row.get("atomic_claim_id") or ""),
                    "parent_claim_id": parent_id,
                    "risk_type": risk_type,
                    "state": "no_blocked_candidate_page",
                }
            )
            continue
        for source_item, candidate, original_gate in sources:
            if pages_used >= page_limit:
                break
            pages_used += 1
            page_text = _reader_rescue_source_text(source_item, candidate)
            sentences = _reader_rescue_split_sentences(page_text)
            best_debug: Dict[str, Any] = {}
            converted = False
            for sentence in sentences[:12]:
                judge = reader_rescue_slot_sentence_judge(atomic_row, sentence, source_item)
                state = str(judge.get("state") or "")
                candidate_debug = _reader_rescue_sentence_candidate_debug_row(
                    atomic_row,
                    source_item,
                    sentence,
                    judge,
                    original_gate,
                )
                if len(sentence_candidate_rows) < 16:
                    sentence_candidate_rows.append(candidate_debug)
                if len(judge_debug_rows) < 16:
                    judge_debug_rows.append(
                        {
                            "atomic_claim_id": candidate_debug["atomic_claim_id"],
                            "parent_claim_id": parent_id,
                            "risk_type": risk_type,
                            "judge_state": candidate_debug["judge_state"],
                            "subject_hit": candidate_debug["subject_hit"],
                            "time_hit": candidate_debug["time_hit"],
                            "role_hit": candidate_debug["role_hit"],
                            "status_hit": candidate_debug["status_hit"],
                            "source_allowed": candidate_debug["source_allowed"],
                            "conflict_hint": candidate_debug["conflict_hint"],
                            "allow_conversion": candidate_debug["allow_conversion"],
                            "conflict_type": candidate_debug["conflict_type"],
                            "conflict_slot": candidate_debug["conflict_slot"],
                            "claim_role": candidate_debug["claim_role"],
                            "evidence_role": candidate_debug["evidence_role"],
                            "sentence": candidate_debug["sentence"],
                            "title": candidate_debug["title"],
                            "url": candidate_debug["url"],
                            "do_not_decide_without_gate": True,
                        }
                    )
                if not best_debug or state == "strong_conflict":
                    best_debug = {
                        "sentence": compact_claim_text(sentence, 180),
                        "judge_state": state,
                        "allow_conversion": bool(judge.get("allow_conversion")),
                        "conflict_type": str(judge.get("conflict_type") or ""),
                        "conflict_slot": str(judge.get("conflict_slot") or ""),
                        "claim_role": str(judge.get("claim_role") or ""),
                        "evidence_role": str(judge.get("evidence_role") or ""),
                    }
                if state == "strong_conflict" and judge.get("allow_conversion"):
                    rescued = reader_rescue_candidate_from_sentence(atomic_row, source_item, sentence, judge, original_gate)
                    candidates = summary.setdefault("evidence_sentence_candidates", [])
                    if isinstance(candidates, list):
                        candidates.insert(0, rescued)
                    converted = True
                    break
            debug_rows.append(
                {
                    "atomic_claim_id": str(atomic_row.get("atomic_claim_id") or ""),
                    "parent_claim_id": parent_id,
                    "risk_type": risk_type,
                    "text": compact_claim_text(str(atomic_row.get("text") or ""), 120),
                    "state": "converted_to_candidate" if converted else "reader_checked_no_conversion",
                    "original_gate": original_gate,
                    "source_type": str(source_item.get("source_type") or ""),
                    "title": compact_claim_text(str(source_item.get("title") or ""), 120),
                    "url": str(source_item.get("url") or ""),
                    "sentence_count": len(sentences),
                    "best_sentence_judge": best_debug,
                    "do_not_decide_without_gate": not converted,
                }
            )
            if converted:
                break
    if debug_rows:
        evidence_summary["_reader_rescue_debug"] = debug_rows[:8]
        if isinstance(debug_bucket, dict):
            debug_bucket["reader_rescue_debug"] = debug_rows[:8]
    if sentence_candidate_rows:
        evidence_summary["_reader_sentence_candidates"] = sentence_candidate_rows[:16]
        if isinstance(debug_bucket, dict):
            debug_bucket["reader_sentence_candidates"] = sentence_candidate_rows[:16]
    if judge_debug_rows:
        evidence_summary["_slot_sentence_judge_debug"] = judge_debug_rows[:16]
        if isinstance(debug_bucket, dict):
            debug_bucket["slot_sentence_judge_debug"] = judge_debug_rows[:16]


def _atomic_page_debug_next_action(risk_type: str, blocked_layer: str) -> str:
    if blocked_layer in {"blocked_by_no_result", "blocked_by_no_query"}:
        return "improve_atomic_query_or_source_priority"
    if blocked_layer == "blocked_by_page_role_or_filter":
        return "try_controlled_page_rescue_or_authority_page"
    if blocked_layer in {"blocked_by_page_gate", "blocked_by_missing_text"}:
        return "run_page_consumption_rescue_before_decision"
    if blocked_layer == "blocked_by_slot_gate":
        return "run_structured_same_slot_judge"
    if risk_type == "exclusive_or_only_path":
        return "apply_exclusive_path_converter"
    if risk_type == "phase_boundary_time":
        return "apply_phase_boundary_time_converter"
    if risk_type == "current_position_distance":
        return "apply_position_distance_same_slot_converter"
    return "keep_unresolved_until_same_slot_evidence"


def _build_atomic_page_consumption_debug_row(
    atomic_row: Dict[str, Any],
    plan_row: Dict[str, Any],
    result_row: Dict[str, Any],
    parent_diag: Dict[str, Any],
    parent_summary: Dict[str, Any],
    state: str,
    raw_hits: int,
    kept_hits: int,
    converted_point: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    risk_type = str(atomic_row.get("risk_type") or "")
    candidate_hints = _atomic_candidate_consumption_hints(parent_summary)
    gate_results = [str(item.get("direct_evidence_gate_result") or "") for item in candidate_hints if str(item.get("direct_evidence_gate_result") or "")]
    slot_missing = any(item.get("slot_missing") for item in candidate_hints)
    slot_mismatch = any(item.get("slot_mismatch") for item in candidate_hints)
    same_slot_ready = any(bool(item.get("same_slot_conflict_ready")) for item in candidate_hints)
    has_candidate_conflict = any(str(item.get("conflict_type") or "") for item in candidate_hints)
    if converted_point:
        blocked_layer = "converted_to_atomic_refutation"
        page_consumption_state = "converted"
        block_reason = str(converted_point.get("atomic_refutation_reason") or converted_point.get("conflict_type") or "same_slot_refutation")
    elif not plan_row:
        blocked_layer = "blocked_by_no_query"
        page_consumption_state = "not_retrieved"
        block_reason = "atomic claim has no executed query plan"
    elif raw_hits <= 0 and kept_hits <= 0:
        blocked_layer = "blocked_by_no_result"
        page_consumption_state = "retrieval_no_result"
        block_reason = str(parent_diag.get("atomic_stop_reason") or result_row.get("stop_reason") or "no candidate page")
    elif raw_hits > 0 and kept_hits <= 0:
        blocked_layer = "blocked_by_page_role_or_filter"
        page_consumption_state = "raw_only"
        block_reason = str(parent_diag.get("atomic_stop_reason") or result_row.get("stop_reason") or "raw result not retained as evidence")
    elif any(gate.startswith("blocked_") for gate in gate_results):
        blocked_layer = "blocked_by_page_gate"
        page_consumption_state = "kept_but_page_gate_blocked"
        block_reason = next((gate for gate in gate_results if gate.startswith("blocked_")), "page gate blocked")
    elif slot_missing or slot_mismatch:
        blocked_layer = "blocked_by_slot_gate"
        page_consumption_state = "kept_but_slot_gate_blocked"
        missing_or_mismatch = "slot_missing" if slot_missing else "slot_mismatch"
        block_reason = missing_or_mismatch
    elif has_candidate_conflict and not same_slot_ready:
        blocked_layer = "blocked_by_weak_conflict"
        page_consumption_state = "conflict_not_same_slot"
        block_reason = "candidate conflict lacks same-slot readiness"
    elif kept_hits > 0:
        blocked_layer = "blocked_by_converter_coverage"
        page_consumption_state = "kept_waiting_converter"
        block_reason = "kept evidence exists but no atomic converter accepted it"
    else:
        blocked_layer = "blocked_by_unknown_gate"
        page_consumption_state = state or "unknown"
        block_reason = str(parent_diag.get("atomic_stop_reason") or state or "unknown")
    return {
        "atomic_claim_id": str(atomic_row.get("atomic_claim_id") or ""),
        "parent_claim_id": str(atomic_row.get("parent_claim_id") or ""),
        "risk_type": risk_type,
        "text": compact_claim_text(str(atomic_row.get("text") or ""), 120),
        "state": state,
        "page_consumption_state": page_consumption_state,
        "blocked_layer": blocked_layer,
        "block_reason": compact_claim_text(block_reason, 120),
        "next_action": _atomic_page_debug_next_action(risk_type, blocked_layer),
        "query": str(result_row.get("query") or plan_row.get("query") or ""),
        "raw_hits": raw_hits,
        "kept_hits": kept_hits,
        "atomic_gate_result": str(parent_diag.get("atomic_gate_result") or ""),
        "atomic_stop_reason": str(parent_diag.get("atomic_stop_reason") or ""),
        "slot_contract_keys": _compact_debug_keys(atomic_row.get("slot_contract")),
        "refutation_target_keys": _compact_debug_keys(atomic_row.get("refutation_target")),
        "candidate_hints": candidate_hints,
        "do_not_decide_without_gate": blocked_layer != "converted_to_atomic_refutation",
    }


def build_evidence_ledger(
    extracted: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]],
    claim_pipeline_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    claims = extracted.get("claims") if isinstance(extracted, dict) and isinstance(extracted.get("claims"), list) else []
    need_type = normalize_need_type(extracted.get("need_type")) if isinstance(extracted, dict) else "general_fact"
    claim_by_id = {
        str(claim.get("claim_id") or claim.get("id") or ""): claim
        for claim in claims
        if isinstance(claim, dict) and str(claim.get("claim_id") or claim.get("id") or "")
    }
    summaries = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    pipeline_items = {
        str(item.get("claim_id") or ""): item
        for item in (
            claim_pipeline_diagnostics.get("items")
            if isinstance(claim_pipeline_diagnostics, dict) and isinstance(claim_pipeline_diagnostics.get("items"), list)
            else []
        )
        if isinstance(item, dict)
    }
    ledger: Dict[str, Any] = {
        "confirmed_points": [],
        "refuted_points": [],
        "unresolved_points": [],
        "gate_blocked_pages": [],
        "slot_blocked_candidates": [],
        "candidate_conflict_points": [],
        "contrastive_unresolved_points": [],
        "atomic_claims": [],
        "high_risk_atomic_claims": [],
        "atomic_query_plan": [],
        "atomic_search_results": [],
        "atomic_refuted_points": [],
        "atomic_unresolved_points": [],
        "atomic_gate_blocked_points": [],
        "atomic_page_consumption_debug": [],
        "reader_rescue_debug": [],
        "reader_sentence_candidates": [],
        "slot_sentence_judge_debug": [],
        "atomic_label_pressure": [],
        "atomic_claim_route_debug": [],
        "fallback_scope": "evidence_gate_first",
        "final_label_reason": "",
        "claim_rows": [],
        "evidence_events": {},
        "evidence_event_debug": [],
        "phase_graph": {},
        "decision_state_debug": {},
        "decision_policy_debug": {},
        "decision_policy_route": "",
        "decision_permission_gate": "",
    }
    if isinstance(evidence_summary, dict):
        if isinstance(evidence_summary.get("evidence_events"), dict):
            ledger["evidence_events"] = evidence_summary.get("evidence_events")
        if isinstance(evidence_summary.get("evidence_event_debug"), list):
            ledger["evidence_event_debug"] = evidence_summary.get("evidence_event_debug")[:24]
        if isinstance(evidence_summary.get("phase_graph"), dict):
            ledger["phase_graph"] = evidence_summary.get("phase_graph")
        if isinstance(evidence_summary.get("decision_state_debug"), dict):
            ledger["decision_state_debug"] = evidence_summary.get("decision_state_debug")
        if isinstance(evidence_summary.get("decision_policy_debug"), dict):
            ledger["decision_policy_debug"] = evidence_summary.get("decision_policy_debug")
    atomic_claims = extracted.get("atomic_claims") if isinstance(extracted.get("atomic_claims"), list) else []
    high_risk_atomic_claims = (
        extracted.get("high_risk_atomic_claims")
        if isinstance(extracted.get("high_risk_atomic_claims"), list)
        else []
    )
    atomic_route_debug = (
        extracted.get("atomic_claim_route_debug")
        if isinstance(extracted.get("atomic_claim_route_debug"), list)
        else []
    )
    ledger["atomic_claims"] = [
        row for row in atomic_claims[:12]
        if isinstance(row, dict)
    ]
    ledger["high_risk_atomic_claims"] = [
        row for row in high_risk_atomic_claims[:6]
        if isinstance(row, dict)
    ]
    ledger["atomic_claim_route_debug"] = [
        row for row in atomic_route_debug[:8]
        if isinstance(row, dict)
    ]
    reader_rescue_debug = (
        evidence_summary.get("_reader_rescue_debug")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("_reader_rescue_debug"), list)
        else []
    )
    ledger["reader_rescue_debug"] = [
        row for row in reader_rescue_debug[:8]
        if isinstance(row, dict)
    ]
    reader_sentence_candidates = (
        evidence_summary.get("_reader_sentence_candidates")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("_reader_sentence_candidates"), list)
        else []
    )
    ledger["reader_sentence_candidates"] = [
        row for row in reader_sentence_candidates[:12]
        if isinstance(row, dict)
    ]
    slot_sentence_judge_debug = (
        evidence_summary.get("_slot_sentence_judge_debug")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("_slot_sentence_judge_debug"), list)
        else []
    )
    ledger["slot_sentence_judge_debug"] = [
        row for row in slot_sentence_judge_debug[:12]
        if isinstance(row, dict)
    ]
    atomic_plan_rows: List[Dict[str, Any]] = []
    atomic_result_rows: List[Dict[str, Any]] = []
    atomic_parent_diag: Dict[str, Dict[str, Any]] = {}
    for parent_claim_id, pipeline_row in pipeline_items.items():
        plans = pipeline_row.get("atomic_query_plan") if isinstance(pipeline_row.get("atomic_query_plan"), list) else []
        results = pipeline_row.get("atomic_search_results") if isinstance(pipeline_row.get("atomic_search_results"), list) else []
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            plan_row = dict(plan)
            plan_row.setdefault("parent_claim_id", parent_claim_id)
            atomic_plan_rows.append(plan_row)
            atomic_id = str(plan_row.get("atomic_claim_id") or "")
            if atomic_id:
                atomic_parent_diag[atomic_id] = pipeline_row
        for result in results:
            if not isinstance(result, dict):
                continue
            result_row = dict(result)
            result_row.setdefault("parent_claim_id", parent_claim_id)
            atomic_result_rows.append(result_row)
            atomic_id = str(result_row.get("atomic_claim_id") or "")
            if atomic_id:
                atomic_parent_diag[atomic_id] = pipeline_row
    ledger["atomic_query_plan"] = atomic_plan_rows[:8]
    ledger["atomic_search_results"] = atomic_result_rows[:8]
    atomic_plan_by_id = {
        str(row.get("atomic_claim_id") or ""): row
        for row in atomic_plan_rows
        if str(row.get("atomic_claim_id") or "")
    }
    atomic_result_by_id = {
        str(row.get("atomic_claim_id") or ""): row
        for row in atomic_result_rows
        if str(row.get("atomic_claim_id") or "")
    }
    enriched_route_debug: List[Dict[str, Any]] = []
    for row in ledger["atomic_claim_route_debug"]:
        if not isinstance(row, dict):
            continue
        atomic_id = str(row.get("atomic_claim_id") or "")
        plan_row = atomic_plan_by_id.get(atomic_id, {})
        result_row = atomic_result_by_id.get(atomic_id, {})
        parent_diag = atomic_parent_diag.get(atomic_id, {})
        enriched = dict(row)
        if plan_row:
            enriched["route_state"] = str(plan_row.get("execution_state") or plan_row.get("state") or "planned")
            enriched["atomic_query"] = str(plan_row.get("query") or "")
        if result_row:
            enriched["raw_hits"] = int(result_row.get("raw_hits") or 0)
            enriched["kept_hits"] = int(result_row.get("kept_hits") or 0)
        if parent_diag:
            enriched["atomic_gate_result"] = str(parent_diag.get("atomic_gate_result") or "")
            enriched["atomic_stop_reason"] = str(parent_diag.get("atomic_stop_reason") or "")
        enriched_route_debug.append(enriched)
    if enriched_route_debug:
        ledger["atomic_claim_route_debug"] = enriched_route_debug[:8]
    for row in ledger["high_risk_atomic_claims"]:
        atomic_id = str(row.get("atomic_claim_id") or "")
        plan_row = atomic_plan_by_id.get(atomic_id, {})
        result_row = atomic_result_by_id.get(atomic_id, {})
        parent_diag = atomic_parent_diag.get(atomic_id, {})
        parent_claim_id = str(row.get("parent_claim_id") or "")
        parent_claim = claim_by_id.get(parent_claim_id, {})
        parent_summary = summaries.get(parent_claim_id) if isinstance(summaries.get(parent_claim_id), dict) else {}
        converted_points = atomic_refutation_points_for_claim([row], parent_claim, parent_summary) if parent_claim and parent_summary else []
        if converted_points:
            converted_point = converted_points[0]
            atomic_label = str(converted_point.get("atomic_label") or LABEL_1)
            raw_hits_for_atomic = int(result_row.get("raw_hits") or 0) if result_row else 0
            kept_hits_for_atomic = int(result_row.get("kept_hits") or 0) if result_row else 0
            ledger["atomic_page_consumption_debug"].append(
                _build_atomic_page_consumption_debug_row(
                    row,
                    plan_row,
                    result_row,
                    parent_diag,
                    parent_summary,
                    "refuted",
                    raw_hits_for_atomic,
                    kept_hits_for_atomic,
                    converted_point,
                )
            )
            ledger["atomic_refuted_points"].append(
                {
                    "atomic_claim_id": atomic_id,
                    "parent_claim_id": parent_claim_id,
                    "risk_type": str(row.get("risk_type") or ""),
                    "atomic_label": atomic_label,
                    "centrality_hint": str(row.get("centrality_hint") or ""),
                    "state": "refuted",
                    "atomic_gate_result": str(parent_diag.get("atomic_gate_result") or ""),
                    "atomic_stop_reason": str(parent_diag.get("atomic_stop_reason") or ""),
                    "raw_hits": raw_hits_for_atomic,
                    "kept_hits": kept_hits_for_atomic,
                    "query": str(result_row.get("query") or plan_row.get("query") or converted_point.get("atomic_query") or ""),
                    "claim": compact_claim_text(str(row.get("text") or ""), 120),
                    "point": compact_claim_text(point_text(converted_point), 180),
                    "title": compact_claim_text(str(converted_point.get("title") or ""), 90),
                    "url": str(converted_point.get("url") or ""),
                    "conflict_slot": str(converted_point.get("conflict_slot") or ""),
                    "conflict_type": str(converted_point.get("conflict_type") or ""),
                    "conflict_strength": str(converted_point.get("conflict_strength") or ""),
                    "claim_value": converted_point.get("claim_value"),
                    "evidence_value": converted_point.get("evidence_value"),
                    "same_slot_conflict_ready": bool(converted_point.get("same_slot_conflict_ready")),
                }
            )
            ledger["atomic_label_pressure"].append(
                {
                    "atomic_claim_id": atomic_id,
                    "parent_claim_id": parent_claim_id,
                    "risk_type": str(row.get("risk_type") or ""),
                    "label": atomic_label,
                    "pressure": 2 if atomic_label == LABEL_0 else 1,
                    "state": "strong_refutation",
                    "reason": str(converted_point.get("atomic_refutation_reason") or ""),
                    "atomic_gate_result": str(parent_diag.get("atomic_gate_result") or ""),
                    "atomic_stop_reason": str(parent_diag.get("atomic_stop_reason") or ""),
                }
            )
            continue
        raw_hits = int(result_row.get("raw_hits") or 0) if result_row else 0
        kept_hits = int(result_row.get("kept_hits") or 0) if result_row else 0
        if kept_hits > 0:
            state = "retrieved_waiting_gate"
        elif raw_hits > 0:
            state = "retrieval_raw_only_no_gate"
        elif plan_row and str(plan_row.get("execution_state") or "") == "ready":
            state = "retrieval_no_result"
        elif plan_row:
            state = str(plan_row.get("execution_state") or plan_row.get("state") or "planned_not_executed")
        else:
            state = "extracted_only_no_retrieval"
        ledger["atomic_page_consumption_debug"].append(
            _build_atomic_page_consumption_debug_row(
                row,
                plan_row,
                result_row,
                parent_diag,
                parent_summary,
                state,
                raw_hits,
                kept_hits,
            )
        )
        if state in {"retrieved_waiting_gate", "retrieval_raw_only_no_gate"}:
            ledger["atomic_gate_blocked_points"].append(
                {
                    "atomic_claim_id": atomic_id,
                    "parent_claim_id": row.get("parent_claim_id"),
                    "risk_type": str(row.get("risk_type") or ""),
                    "state": state,
                    "atomic_gate_result": str(parent_diag.get("atomic_gate_result") or ""),
                    "atomic_stop_reason": str(parent_diag.get("atomic_stop_reason") or ""),
                    "raw_hits": raw_hits,
                    "kept_hits": kept_hits,
                    "query": str(result_row.get("query") or plan_row.get("query") or ""),
                }
            )
        ledger["atomic_unresolved_points"].append(
            {
                "atomic_claim_id": atomic_id,
                "parent_claim_id": row.get("parent_claim_id"),
                "text": compact_claim_text(str(row.get("text") or ""), 120),
                "risk_type": str(row.get("risk_type") or ""),
                "slot_contract": row.get("slot_contract") if isinstance(row.get("slot_contract"), dict) else {},
                "refutation_target": row.get("refutation_target") if isinstance(row.get("refutation_target"), dict) else {},
                "state": state,
                "atomic_query": str(result_row.get("query") or plan_row.get("query") or ""),
                "raw_hits": raw_hits,
                "kept_hits": kept_hits,
                "atomic_gate_result": str(parent_diag.get("atomic_gate_result") or ""),
                "atomic_stop_reason": str(parent_diag.get("atomic_stop_reason") or ""),
                "do_not_decide_without_gate": True,
            }
        )
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "")
        claim_text = normalize_text(str(claim.get("claim") or ""))
        summary = summaries.get(claim_id) if isinstance(summaries.get(claim_id), dict) else {}
        direct_refuting = claim_direct_refuting_points(summary)
        direct_supporting = claim_direct_supporting_points(summary)
        strong_refuting = [
            point for point in direct_refuting
            if point_is_strong_refutation(point, need_type, claim, summary)
        ]
        if strong_refuting:
            row = _ledger_point_row(claim_id, claim_text, strong_refuting[0], "refuted")
            ledger["refuted_points"].append(row)
            claim_state = "refuted"
        elif direct_supporting:
            row = _ledger_point_row(claim_id, claim_text, direct_supporting[0], "confirmed")
            ledger["confirmed_points"].append(row)
            claim_state = "confirmed"
        else:
            point_conversion = summary.get("point_conversion") if isinstance(summary.get("point_conversion"), dict) else {}
            pipeline_row = pipeline_items.get(claim_id, {})
            slot_missing = point_conversion.get("slot_missing") if isinstance(point_conversion.get("slot_missing"), list) else []
            slot_mismatch = point_conversion.get("slot_mismatch") if isinstance(point_conversion.get("slot_mismatch"), list) else []
            if not slot_missing:
                slot_missing = pipeline_row.get("missing_required_slots") if isinstance(pipeline_row.get("missing_required_slots"), list) else []
            unresolved = {
                "claim_id": claim_id,
                "claim": compact_claim_text(claim_text, 90),
                "state": "unresolved",
                "pipeline_stage": str(pipeline_row.get("pipeline_stage") or ""),
                "point_conversion_block_reason": str(point_conversion.get("block_reason") or pipeline_row.get("point_conversion_block_reason") or ""),
                "slot_contract_state": str(point_conversion.get("slot_contract_state") or ""),
                "slot_missing": [str(slot) for slot in slot_missing if str(slot)][:5],
                "slot_mismatch": [str(slot) for slot in slot_mismatch if str(slot)][:5],
                "slot_conflict": point_conversion.get("slot_conflict") if isinstance(point_conversion.get("slot_conflict"), list) else [],
                "candidate_conflict_profile": (
                    point_conversion.get("candidate_conflict_profile")
                    if isinstance(point_conversion.get("candidate_conflict_profile"), dict)
                    else {}
                ),
                "conflict_type": str(point_conversion.get("conflict_type") or ""),
                "conflict_strength": str(point_conversion.get("conflict_strength") or ""),
                "conflict_slot": str(point_conversion.get("conflict_slot") or ""),
                "claim_value": point_conversion.get("claim_value"),
                "evidence_value": point_conversion.get("evidence_value"),
                "same_slot_conflict_ready": bool(point_conversion.get("same_slot_conflict_ready")),
                "direct_evidence_gate_result": str(point_conversion.get("direct_evidence_gate_result") or ""),
            }
            ledger["unresolved_points"].append(unresolved)
            claim_state = "unresolved"
        candidates = summary.get("evidence_sentence_candidates") if isinstance(summary.get("evidence_sentence_candidates"), list) else []
        for candidate in candidates[:4]:
            if not isinstance(candidate, dict):
                continue
            gate = str(candidate.get("direct_evidence_gate_result") or "")
            if gate.startswith("blocked_"):
                ledger["gate_blocked_pages"].append(
                    {
                        "claim_id": claim_id,
                        "title": compact_claim_text(str(candidate.get("title") or ""), 90),
                        "page_role": str(candidate.get("page_role") or ""),
                        "direct_evidence_gate_result": gate,
                    }
                )
            slot_missing = candidate.get("slot_missing") if isinstance(candidate.get("slot_missing"), list) else []
            slot_mismatch = candidate.get("slot_mismatch") if isinstance(candidate.get("slot_mismatch"), list) else []
            if slot_missing or slot_mismatch:
                ledger["slot_blocked_candidates"].append(
                    {
                        "claim_id": claim_id,
                        "title": compact_claim_text(str(candidate.get("title") or ""), 90),
                        "slot_contract_state": str(candidate.get("slot_contract_state") or ""),
                        "slot_missing": slot_missing[:5],
                        "slot_mismatch": slot_mismatch[:5],
                    }
                )
            conflict_profile = (
                candidate.get("candidate_conflict_profile")
                if isinstance(candidate.get("candidate_conflict_profile"), dict)
                else {}
            )
            conflict_state = str(conflict_profile.get("state") or "")
            conflict_type = str(candidate.get("conflict_type") or conflict_profile.get("conflict_type") or "")
            conflict_strength = str(candidate.get("conflict_strength") or conflict_profile.get("conflict_strength") or "")
            if conflict_profile or conflict_type:
                conflict_row = {
                    "claim_id": claim_id,
                    "claim": compact_claim_text(claim_text, 90),
                    "sentence": compact_claim_text(
                        str(candidate.get("sentence") or candidate.get("text") or candidate.get("snippet") or ""),
                        180,
                    ),
                    "title": compact_claim_text(str(candidate.get("title") or ""), 90),
                    "url": str(candidate.get("url") or ""),
                    "conflict_state": conflict_state,
                    "conflict_type": conflict_type,
                    "conflict_strength": conflict_strength,
                    "conflict_slot": str(candidate.get("conflict_slot") or conflict_profile.get("conflict_slot") or ""),
                    "claim_value": candidate.get("claim_value", conflict_profile.get("claim_value")),
                    "evidence_value": candidate.get("evidence_value", conflict_profile.get("evidence_value")),
                    "same_slot_conflict_ready": bool(candidate.get("same_slot_conflict_ready") or conflict_profile.get("same_slot_conflict_ready")),
                    "direct_evidence_gate_result": str(candidate.get("direct_evidence_gate_result") or ""),
                    "page_role": str(candidate.get("page_role") or ""),
                    "block_reason": str(
                        conflict_profile.get("block_reason")
                        or candidate.get("generic_page_not_consumed_reason")
                        or candidate.get("entry_page_not_consumed_reason")
                        or candidate.get("direct_evidence_gate_result")
                        or ""
                    ),
                }
                if conflict_strength in {"strong", "medium"} or conflict_state in {"conflict_ready", "conflict_diagnostic"}:
                    ledger["candidate_conflict_points"].append(conflict_row)
                elif not conflict_row["same_slot_conflict_ready"]:
                    ledger["contrastive_unresolved_points"].append(conflict_row)
        ledger["claim_rows"].append(
            {
                "claim_id": claim_id,
                "claim": compact_claim_text(claim_text, 90),
                "centrality": str(claim.get("centrality") or ""),
                "state": claim_state,
            }
        )
    for key in (
        "confirmed_points",
        "refuted_points",
        "unresolved_points",
        "gate_blocked_pages",
        "slot_blocked_candidates",
        "candidate_conflict_points",
        "contrastive_unresolved_points",
        "atomic_claims",
        "high_risk_atomic_claims",
        "atomic_query_plan",
        "atomic_search_results",
        "atomic_refuted_points",
        "atomic_unresolved_points",
        "atomic_gate_blocked_points",
        "atomic_page_consumption_debug",
        "reader_rescue_debug",
        "reader_sentence_candidates",
        "slot_sentence_judge_debug",
        "atomic_label_pressure",
        "atomic_claim_route_debug",
    ):
        ledger[key] = ledger[key][:8]
    return ledger


def evidence_ledger_reason(label: str, evidence_summary: Optional[Dict[str, Any]]) -> str:
    ledger = (
        evidence_summary.get("_evidence_ledger")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("_evidence_ledger"), dict)
        else {}
    )
    if not ledger:
        return ""
    refuted = ledger.get("refuted_points") if isinstance(ledger.get("refuted_points"), list) else []
    confirmed = ledger.get("confirmed_points") if isinstance(ledger.get("confirmed_points"), list) else []
    unresolved = ledger.get("unresolved_points") if isinstance(ledger.get("unresolved_points"), list) else []
    conflict_points = ledger.get("candidate_conflict_points") if isinstance(ledger.get("candidate_conflict_points"), list) else []
    contrastive_unresolved = ledger.get("contrastive_unresolved_points") if isinstance(ledger.get("contrastive_unresolved_points"), list) else []
    atomic_refuted = ledger.get("atomic_refuted_points") if isinstance(ledger.get("atomic_refuted_points"), list) else []
    atomic_unresolved = ledger.get("atomic_unresolved_points") if isinstance(ledger.get("atomic_unresolved_points"), list) else []
    atomic_page_debug = ledger.get("atomic_page_consumption_debug") if isinstance(ledger.get("atomic_page_consumption_debug"), list) else []
    if refuted:
        first = refuted[0]
        claim_text = str(first.get("claim") or "")
        point = str(first.get("point") or "")
        scope = "主需" if label == LABEL_0 else "次需"
        return f"证据账本显示存在同槽反证：{claim_text}；{point}。因此判为{scope}事实错误。"
    if atomic_refuted:
        first = atomic_refuted[0]
        scope = "主需" if label == LABEL_0 else "次需"
        risk = str(first.get("risk_type") or "high_risk_atomic_claim")
        claim_text = str(first.get("claim") or "")
        point = str(first.get("point") or "")
        return f"原子证据账本形成同槽反证：{risk}「{claim_text}」；{point}。因此判为{scope}事实错误。"
    parts: List[str] = []
    if atomic_page_debug:
        first_debug = atomic_page_debug[0]
        state = str(first_debug.get("page_consumption_state") or first_debug.get("state") or "")
        blocked_layer = str(first_debug.get("blocked_layer") or "")
        risk = str(first_debug.get("risk_type") or "高风险原子事实")
        text = str(first_debug.get("text") or first_debug.get("atomic_claim_id") or "")
        hint = str(first_debug.get("block_reason") or "")
        if state:
            parts.append(f"原子页面消费停在 {state}：{risk}#{text}；{blocked_layer}{('，' + hint) if hint else ''}")
    if confirmed:
        first = confirmed[0]
        parts.append(f"已确认：{first.get('claim')}；{first.get('point')}")
    if conflict_points:
        first = conflict_points[0]
        slot = str(first.get("conflict_slot") or "冲突槽位")
        strength = str(first.get("conflict_strength") or "diagnostic")
        if first.get("same_slot_conflict_ready"):
            parts.append(
                f"候选冲突已成型但仍未进入直接反证点：{first.get('claim')} 的 {slot} 与材料值不一致"
            )
        else:
            block = str(first.get("block_reason") or first.get("direct_evidence_gate_result") or "gate 未通过")
            parts.append(
                f"发现候选冲突诊断：{first.get('claim')} 的 {slot} 出现 {strength} 冲突信号，但卡在 {block}"
            )
    if atomic_unresolved:
        first_atomic = atomic_unresolved[0]
        state = str(first_atomic.get("state") or "")
        risk = str(first_atomic.get("risk_type") or "高风险原子事实")
        text = str(first_atomic.get("text") or "")
        if state in {"retrieved_waiting_gate", "retrieval_raw_only_no_gate"}:
            block = str(first_atomic.get("atomic_gate_result") or first_atomic.get("atomic_stop_reason") or "gate 未闭合")
            parts.append(f"原子错点已进入检索但尚未可裁决：{risk}「{text}」卡在 {block}")
        elif state not in {"extracted_only_no_retrieval", ""}:
            block = str(first_atomic.get("atomic_stop_reason") or state)
            parts.append(f"高风险原子 claim 已定位：{risk}「{text}」，当前停在 {block}")
    if unresolved:
        first = unresolved[0]
        gaps = ",".join(str(slot) for slot in (first.get("slot_missing") or first.get("slot_mismatch") or []) if str(slot))
        block = str(first.get("point_conversion_block_reason") or first.get("pipeline_stage") or "证据未闭合")
        gap_text = f"，缺口在 {gaps}" if gaps else ""
        parts.append(f"未闭合：{first.get('claim')} 仍停在 {block}{gap_text}")
    if not conflict_points and contrastive_unresolved:
        first = contrastive_unresolved[0]
        block = str(first.get("block_reason") or "主体/时间/指标仍未同槽")
        parts.append(f"对照式反证仍未成型：{first.get('claim')} 卡在 {block}")
    if parts:
        tail = "。证据账本没有同槽反证，fallback 只做保守兜底，因此当前不判定为事实错误。" if label == LABEL_2 else "。当前仍未形成足以翻转标签的同槽反证，因此先按现有证据保守裁决。"
        return "；".join(parts[:2]) + tail
    return ""


def decision_state_reason_candidate(label: str, evidence_summary: Optional[Dict[str, Any]]) -> str:
    if not isinstance(evidence_summary, dict):
        return ""
    debug = evidence_summary.get("decision_state_debug") if isinstance(evidence_summary.get("decision_state_debug"), dict) else {}
    policy_debug = evidence_summary.get("decision_policy_debug") if isinstance(evidence_summary.get("decision_policy_debug"), dict) else {}
    try:
        from reason_builder import build_decision_state_reason

        natural_reason = build_decision_state_reason(label, debug, policy_debug)
        if natural_reason:
            return natural_reason
    except Exception:
        pass
    rows = debug.get("claim_state_rows") if isinstance(debug.get("claim_state_rows"), list) else []
    if not rows:
        return ""
    ranked_rows = sorted(
        [row for row in rows if isinstance(row, dict)],
        key=lambda row: (
            0 if str(row.get("scope") or "") == "core" else 1,
            0 if str(row.get("label_candidate") or "") == label else 1,
        ),
    )
    for row in ranked_rows:
        permission = str(row.get("decision_permission") or "")
        candidate = str(row.get("label_candidate") or "")
        basis = normalize_text(str(row.get("reason_basis") or ""))
        scope = str(row.get("scope") or "")
        evidence_state = str(row.get("evidence_state") or "")
        slot_state = str(row.get("slot_state") or "")
        if not basis:
            continue
        if label == LABEL_2 and permission.startswith("insufficient"):
            return f"裁决状态显示当前 {scope} claim 停在 {evidence_state}/{slot_state}，原因是：{basis}。因此不把未闭合证据包装成事实错误。"
        if label in {LABEL_0, LABEL_1} and candidate == label and permission in {"risk_calibrate", "rubric_fallback"}:
            return f"裁决状态显示当前 {scope} claim 不能由直接证据闭合，但存在可授权补判的风险形态：{basis}。"
    return ""


def choose_final_reason(
    verify_obj: Dict[str, Any],
    label: str,
    decision_basis: str,
    fallback_reason: str,
    evidence_summary: Optional[Dict[str, Any]],
    extracted: Dict[str, Any],
) -> Tuple[str, str]:
    policy = str(
        verify_obj.get("_decision_policy")
        or verify_obj.get("_calibration_override")
        or verify_obj.get("_evidence_override")
        or verify_obj.get("_semantic_audit")
        or ""
    )
    candidates = [
        ("aggregation", verify_obj.get("_aggregation_analyse")),
        ("semantic_audit", verify_obj.get("_semantic_audit_analyse")),
        ("llm_verify", verify_obj.get("_llm_analyse")),
        ("review", verify_obj.get("_review_analyse")),
    ]
    allow_evidence_reason = (
        label in {LABEL_0, LABEL_1}
        and (has_direct_refuting_evidence(evidence_summary) or has_atomic_refuting_evidence(evidence_summary))
    ) or (
        label == LABEL_2
        and decision_basis == "evidence_support"
        and has_direct_supporting_evidence(evidence_summary)
    )
    if policy == "attached_detail_pollution":
        allow_evidence_reason = allow_evidence_reason and attached_detail_refuting_reason_allowed(extracted, evidence_summary)
    if allow_evidence_reason:
        evidence_based = evidence_reason(
            label,
            policy or "direct_evidence_refutation",
            extracted,
            evidence_summary,
            verify_obj.get("_claim_pipeline_diagnostics"),
            verify_obj.get("_evidence_non_decidable_state"),
        )
        candidates.insert(0, ("evidence_reason", evidence_based))
    ledger_based = evidence_ledger_reason(label, evidence_summary)
    if ledger_based and (label == LABEL_2 or has_direct_refuting_evidence(evidence_summary) or has_atomic_refuting_evidence(evidence_summary)):
        candidates.insert(0, ("evidence_ledger_reason", ledger_based))
    consistency_based = cross_claim_consistency_reason(label, evidence_summary)
    if consistency_based:
        candidates.insert(0, ("cross_claim_consistency_reason", consistency_based))
    state_based = decision_state_reason_candidate(label, evidence_summary)
    if state_based and not allow_evidence_reason:
        candidates.insert(0, ("decision_state_reason", state_based))
    for source, value in candidates:
        reason = normalize_reason_by_decision_basis(str(value or ""), label, decision_basis)
        if llm_reason_is_safe(reason, label, decision_basis, evidence_summary):
            return reason, source
    if llm_reason_is_safe(fallback_reason, label, decision_basis, evidence_summary):
        return fallback_reason, "llm_verify_fallback"
    if label == LABEL_0:
        return "最终判为主需事实错误；当前 LLM 裁决给出了错误类标签，但未生成足够清晰的可用 reason，需要复核决定性 claim 与证据链。", "emergency_fallback"
    if label == LABEL_1:
        return "最终判为次需事实错误；当前 LLM 裁决给出了次要错误类标签，但未生成足够清晰的可用 reason，需要复核附带 claim 与证据链。", "emergency_fallback"
    return "未发现足以直接反驳关键 claim 的证据，因此不判定为事实错误。", "emergency_fallback"


def consistent_conflict_fallback_reason(label: str, decision_basis: str, verify_obj: Dict[str, Any], evidence_summary: Optional[Dict[str, Any]]) -> str:
    audit_reason = normalize_text(str(verify_obj.get("_semantic_audit_analyse") or ""))
    aggregation_reason = normalize_text(str(verify_obj.get("_aggregation_analyse") or ""))
    policy = str(verify_obj.get("_decision_policy") or verify_obj.get("_calibration_override") or verify_obj.get("_semantic_audit") or "")
    if label == LABEL_2:
        if decision_basis == "evidence_support" and has_direct_supporting_evidence(evidence_summary):
            return "最终标签来自直接支持证据：关键 claim 已得到可直接核对的支持，因此当前不判定为事实错误。"
        return "没有形成可直接裁决的支持或反驳证据，因此不判定为事实错误。"
    if decision_basis == "evidence_refutation" and (has_direct_refuting_evidence(evidence_summary) or has_atomic_refuting_evidence(evidence_summary)):
        return "最终标签来自直接证据反驳：关键 claim 与可用证据存在冲突，因此判为事实错误风险。"
    if decision_basis == "evidence_support" and has_direct_supporting_evidence(evidence_summary):
        detail = aggregation_reason or audit_reason or "关键 claim 与可核对证据一致"
        return f"最终标签来自直接支持证据：{detail}。这是证据直裁，不是因为缺少反证而保守放过。"
    if decision_basis in {"rubric_fallback", "rubric_fallback_with_partial_evidence"}:
        detail = aggregation_reason or audit_reason or "当前没有形成可直接裁决的强证据结论，因此由判标先验兜底裁决"
        return f"最终标签来自判标先验兜底：{detail}。这不是直接证据反驳，而是基于回答确定性、主次作用域和当前证据状态作出的补判。"
    detail = aggregation_reason or audit_reason or "回答存在高风险事实表达边界"
    return f"最终标签为错误类，但不是因为证据不足本身；决定性依据是：{detail}。"


def policy_reason(label: str, policy: str) -> str:
    reason_by_policy = {
        "sports_result_has_multiple_unsupported_core_result_claims": "多条核心赛果缺少可直接验证的比赛上下文证据，影响用户询问的比赛结果主需。",
        "sports_result_has_unsupported_core_result_claim": "核心赛果缺少可直接验证的比赛上下文证据，影响用户询问的比赛结果主需。",
        "market_movement_has_multiple_unsupported_core_claims": "价格/涨跌类回答中多个核心时间或数值结论缺少直接证据支撑，影响用户主需判断。",
        "market_movement_has_weak_core_refutation": "价格/涨跌类回答存在与核心结论冲突的较强证据，影响用户主需判断。",
        "market_movement_resolved_forecast_overclaim": "市场价格/涨跌预测被写成确定结论，影响用户主需判断。",
        "distance_position_core_numeric_distance_lacks_support": "距离/位置类回答中的核心距离数值缺少直接证据支撑，影响用户主需判断。",
        "fictional_scenario_contaminates_current_need": "当前状态题中混入虚构剧本、假设推演或非真实新闻内容，直接污染用户主需。",
        "schedule_time_core_date_lacks_direct_evidence": "日程/发布时间题给出了具体核心日期，但缺少可直接验证的来源支撑，影响用户主需判断。",
        "geopolitical_negative_route_core_lacks_support": "地缘军事回答的核心结论依赖“无需经过/绕开某路线”的关键前提，但该前提缺少直接证据支撑。",
        "geopolitical_core_high_assertion_lacks_support": "地缘政治回答的核心强断言缺少直接证据支撑，已经影响主需判断。",
        "geopolitical_core_policy_intent_lacks_support": "地缘政治回答中的核心政策意图或军事施压说法缺少直接证据，按次需风险处理。",
        "geopolitical_absolute_route_premise_lacks_support": "回答把“无需经过/完全绕开某领空”这类绝对路线前提当成主结论支点，但该前提没有直接证据支撑，已经影响用户主需判断。",
        "high_risk_current_need_has_multiple_unsupported_core_claims": "时间敏感主需中的核心事实缺少直接证据支撑，不能作为可靠结论。",
        "market_movement_has_unsupported_core_or_details": "核心市场判断或多个关键细节证据不足，属于次要事实风险。",
        "market_movement_has_unsupported_time_detail": "市场解释中包含交易日、休市或节假日等关键时间细节风险，属于次要事实错误风险。",
        "geopolitical_claims_have_insufficient_direct_support": "地缘政治回答中的核心说法缺少足够直接证据，属于次要事实风险。",
        "geopolitical_supporting_absolute_detail_lacks_support": "地缘政治回答的附带解释中包含“唯一/必经/完全”等强事实断言，属于次要事实风险。",
        "current_geopolitical_status_has_unsupported_core_claim": "当前战争、袭击、封锁等高风险状态题中，核心现实状态缺少直接证据支撑。",
        "current_geopolitical_status_has_multiple_unsupported_details": "当前地缘状态回答中多个关键细节缺少直接证据支撑，会误导主需判断。",
        "multiple_unsupported_secondary_details": "多个次要事实或背景细节缺少直接证据支撑，但暂未形成主结论错误。",
        "financial_quote_without_strong_same_metric_refutation": "金融报价题缺少同指标强反证；不同报价口径的数字差异不能直接判为事实错误。",
        "open_route_summary_without_absolute_boundary": "开放式路线说明没有出现强绝对化或排他性表达，证据薄不能单独升级成事实错误。",
        "only_weak_core_refutation_or_secondary_errors": "现有证据只形成弱反证或次要细节错误，未达到主需事实错误门槛。",
        "evidence_first_core_direct_refutation": "核心 claim 已有直接反证，最终标签直接由证据层裁决，不再交给语义兜底或风险校准层改写。",
        "atomic_core_direct_refutation": "核心高风险原子 claim 已被同槽证据反驳，最终标签直接由原子证据账本裁决。",
        "atomic_secondary_direct_refutation": "附带高风险原子 claim 已被同槽证据反驳，按次需事实错误处理。",
        "evidence_first_core_direct_support": "核心 claim 已有可直接核对的支持证据，最终标签直接由证据层裁决，不再交给 fallback 补判。",
        "secondary_detail_direct_refutation": "主需结论未被推翻，但附带数字、日期、身份或金额等细节存在直接反证。",
        "unsupported_claims_are_not_fact_errors": "只有证据不足或弱相关材料，没有直接反证；证据不足不能等同于事实错误。",
        "rubric_core_error": "当前没有形成可直接裁决的强反证，但回答采用高确定性核心断言表达，按主需风险兜底处理。",
        "rubric_detail_error": "当前没有形成可直接裁决的强反证，但回答中的细节断言风险更高，按次需风险兜底处理。",
        "rubric_no_error": "当前没有形成可直接裁决的强反证，且回答更像弱确定或开放式表述，因此不判定为明确事实错误。",
    }
    detail = reason_by_policy.get(policy, policy)
    if label == LABEL_0:
        return f"证据聚合判断为“{label}”：{detail}"
    if label == LABEL_1:
        return f"证据聚合判断为“{label}”：{detail}"
    return f"证据聚合判断为“{label}”：{detail}"


def aggregate_by_confidence(
    result: Dict[str, Any],
    extracted: Dict[str, Any],
    evidence_bundle: Dict[str, Any],
    evidence_summary: Optional[Dict[str, Any]] = None,
    item: Optional[Dict[str, Any]] = None,
    claim_pipeline_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    original_label = pick_label(result.get("final_label")) or LABEL_2
    final_label = original_label
    result["_pre_aggregation_analyse"] = str(result.get("analyse") or "")
    result["_evidence_first_audit"] = evidence_first_audit(extracted, evidence_summary)
    if isinstance(evidence_summary, dict):
        if isinstance(evidence_summary.get("decision_state_debug"), dict):
            result["_decision_state_debug"] = evidence_summary.get("decision_state_debug")
        try:
            from decision_policy import build_decision_policy_debug

            result["_decision_policy_debug"] = build_decision_policy_debug(result.get("_decision_state_debug"))
            evidence_summary["decision_policy_debug"] = result["_decision_policy_debug"]
        except Exception as exc:
            result["_decision_policy_debug"] = {
                "policy_route": "insufficient",
                "allow_rubric_fallback": False,
                "error": f"decision_policy_debug_failed:{type(exc).__name__}",
            }
            evidence_summary["decision_policy_debug"] = result["_decision_policy_debug"]
        if isinstance(evidence_summary.get("_core_assertion_audit"), dict):
            result["_core_assertion_audit"] = evidence_summary.get("_core_assertion_audit")
        if isinstance(evidence_summary.get("_cross_claim_consistency"), dict):
            result["_cross_claim_consistency"] = evidence_summary.get("_cross_claim_consistency")
    if isinstance(claim_pipeline_diagnostics, dict):
        result["_claim_pipeline_diagnostics"] = claim_pipeline_diagnostics
    verdicts = result.get("claim_verdicts") or []
    summary_by_id = (
        evidence_summary.get("claim_summaries")
        if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("claim_summaries"), dict)
        else {}
    )
    major_refuted = False
    minor_refuted = False
    low_confidence_refuted = False
    borderline_major_refuted = 0
    max_conf = 0.0
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            continue
        v = str(verdict.get("verdict") or "")
        sev = str(verdict.get("severity_if_wrong") or "")
        claim_id = str(verdict.get("claim_id") or "")
        summary = summary_by_id.get(claim_id) if isinstance(summary_by_id.get(claim_id), dict) else {}
        mode = str(summary.get("evidence_mode") or "")
        if v == "refuted" and mode == "route_fact":
            route_refuting = [
                point for point in summary.get("refuting_points") or []
                if isinstance(point, dict) and point.get("direct_answer") == "direct"
            ]
            if not route_refuting:
                continue
        conf = verdict.get("confidence") or {}
        if isinstance(conf, dict):
            score = float(conf.get("verdict", 0.0) or 0.0)
            severity_score = float(conf.get("severity", 0.0) or 0.0)
        else:
            score = 0.0
            severity_score = 0.0
        max_conf = max(max_conf, score)
        if v == "refuted":
            if sev == "major" and score >= 0.75 and severity_score >= 0.7:
                major_refuted = True
            elif sev == "major" and score >= 0.65 and severity_score >= 0.85:
                borderline_major_refuted += 1
            elif sev == "minor" and score >= 0.65:
                minor_refuted = True
            elif score < 0.65:
                low_confidence_refuted = True
    if borderline_major_refuted >= 2:
        major_refuted = True
    if major_refuted:
        final_label = LABEL_0
    elif minor_refuted:
        final_label = LABEL_1
    elif low_confidence_refuted:
        final_label = LABEL_2
    else:
        final_label = LABEL_2
    evidence_signal = evidence_first_decision_signal(extracted, evidence_summary)
    atomic_signal = atomic_refutation_decision_signal(extracted, evidence_summary)
    if evidence_signal:
        final_label = evidence_signal.get("label") or final_label
        result["_evidence_first_signal"] = evidence_signal.get("policy") or ""
        result["_evidence_first_locked"] = True
        result["_evidence_non_decidable_state"] = {
            "state": "direct_decidable",
            "reason": str(evidence_signal.get("policy") or "evidence_first_locked"),
        }
        result["_decision_basis"] = evidence_signal.get("decision_basis") or classify_decision_basis(final_label, "", evidence_summary, extracted)
        result["_decision_policy"] = evidence_signal.get("policy") or ""
        result["_decision_policy_explanation"] = policy_reason(final_label, str(result.get("_decision_policy") or ""))
        result["_aggregation_analyse"] = evidence_reason(
            final_label,
            str(result.get("_decision_policy") or ""),
            extracted,
            evidence_summary,
            claim_pipeline_diagnostics,
            result.get("_evidence_non_decidable_state"),
        )
        result["analyse"] = result["_aggregation_analyse"]
    elif atomic_signal:
        final_label = atomic_signal.get("label") or final_label
        result["_evidence_first_signal"] = atomic_signal
        result["_evidence_first_locked"] = True
        result["_evidence_non_decidable_state"] = {
            "state": "direct_decidable",
            "reason": str(atomic_signal.get("policy") or "atomic_refutation_available"),
        }
        result["_decision_basis"] = atomic_signal.get("decision_basis") or classify_decision_basis(final_label, "", evidence_summary, extracted)
        result["_decision_policy"] = atomic_signal.get("policy") or ""
        result["_decision_policy_explanation"] = policy_reason(final_label, str(result.get("_decision_policy") or ""))
        result["_aggregation_analyse"] = evidence_reason(
            final_label,
            str(result.get("_decision_policy") or ""),
            extracted,
            evidence_summary,
            claim_pipeline_diagnostics,
            result.get("_evidence_non_decidable_state"),
        )
        result["analyse"] = result["_aggregation_analyse"]
    else:
        result["_evidence_first_locked"] = False
        evidence_non_decidable_state = build_evidence_non_decidable_state(item or {}, extracted, evidence_summary)
        result["_evidence_non_decidable_state"] = evidence_non_decidable_state
        fallback_risk_features = build_fallback_risk_features(item or {}, extracted, evidence_summary)
        result["_fallback_risk_features"] = fallback_risk_features
        legacy_preview = legacy_fallback_preview(final_label, extracted, evidence_summary, item)
        result["_legacy_fallback_preview"] = legacy_preview
        decision_policy_debug = result.get("_decision_policy_debug") if isinstance(result.get("_decision_policy_debug"), dict) else {}
        allow_policy_fallback = normalize_bool(decision_policy_debug.get("allow_rubric_fallback"), False)
        result["_decision_policy_route"] = str(decision_policy_debug.get("policy_route") or "")
        result["_decision_permission_gate"] = "fallback_allowed" if allow_policy_fallback else "fallback_blocked"
        if legacy_preview_is_actionable_calibration(legacy_preview) and allow_policy_fallback:
            final_label = apply_risk_calibration_result(result, legacy_preview, evidence_summary)
            result["_rubric_prior_attempted"] = False
        else:
            if not allow_policy_fallback:
                rubric_decision = {
                    "attempted": False,
                    "valid": False,
                    "skip_reason": "decision_policy_no_fallback_permission",
                    "trigger_gate": {
                        "allow": False,
                        "reason": "decision_policy_no_fallback_permission",
                        "policy_route": str(decision_policy_debug.get("policy_route") or ""),
                    },
                }
            else:
                rubric_decision = rubric_fallback_decide(
                    item or {},
                    extracted,
                    evidence_summary,
                    fallback_risk_features,
                    evidence_non_decidable_state,
                    legacy_preview,
                    claim_pipeline_diagnostics,
                ) if item else {
                    "attempted": False,
                    "valid": False,
                    "skip_reason": "missing_item_context",
                    "trigger_gate": {"allow": False, "reason": "missing_item_context"},
                }
            result["_rubric_prior_attempted"] = bool(rubric_decision.get("attempted")) if isinstance(rubric_decision, dict) else False
            if isinstance(rubric_decision, dict):
                result["_rubric_skip_reason"] = str(rubric_decision.get("skip_reason") or "")
                result["_rubric_trigger_gate"] = rubric_decision.get("trigger_gate") or {}
                trigger_gate = result["_rubric_trigger_gate"] if isinstance(result.get("_rubric_trigger_gate"), dict) else {}
                result["decision_gate_consumed_diagnostics"] = normalize_bool(trigger_gate.get("decision_gate_consumed_diagnostics"), False)
                result["decision_gate_primary_block"] = str(trigger_gate.get("decision_gate_primary_block") or "")
                result["reason_source_layer"] = str(trigger_gate.get("reason_source_layer") or "")
                if rubric_decision.get("elapsed_ms") is not None:
                    result["_rubric_elapsed_ms"] = float(rubric_decision.get("elapsed_ms") or 0.0)
                result["_rubric_prior_raw"] = rubric_decision.get("raw") or ""
                if rubric_decision.get("valid"):
                    final_label = rubric_decision.get("label") or final_label
                    result["_rubric_prior"] = rubric_decision.get("prior") or {}
                    result["_rubric_fallback_policy"] = rubric_decision.get("policy") or ""
                    result["_replaced_legacy_policy"] = rubric_decision.get("replaced_legacy_policy") or ""
                    result["_replaced_legacy_basis"] = rubric_decision.get("replaced_legacy_basis") or ""
                    result["_replaced_legacy_source"] = rubric_decision.get("replaced_legacy_source") or ""
                    result["_decision_basis"] = rubric_decision.get("decision_basis") or "rubric_fallback"
                    result["_decision_policy"] = rubric_decision.get("policy") or ""
                    result["_decision_policy_explanation"] = policy_reason(final_label, str(result.get("_decision_policy") or ""))
                    result["_aggregation_analyse"] = str(rubric_decision.get("reason") or "")
                    result["analyse"] = result["_aggregation_analyse"]
                else:
                    final_label = LABEL_2
                    result["_decision_basis"] = "insufficient_evidence"
                    result["_decision_policy"] = "unsupported_claims_are_not_fact_errors"
                    result["_decision_policy_explanation"] = policy_reason(final_label, "unsupported_claims_are_not_fact_errors")
                    result["_aggregation_analyse"] = evidence_reason(
                        final_label,
                        "unsupported_claims_are_not_fact_errors",
                        extracted,
                        evidence_summary,
                        claim_pipeline_diagnostics,
                        evidence_non_decidable_state,
                    )
                    result["analyse"] = result["_aggregation_analyse"]
    if not result.get("decision_gate_consumed_diagnostics"):
        result["decision_gate_consumed_diagnostics"] = False
    if not result.get("decision_gate_primary_block"):
        result["decision_gate_primary_block"] = ""
    if not result.get("reason_source_layer"):
        if result.get("_evidence_first_locked"):
            result["reason_source_layer"] = "evidence_first"
        elif result.get("_rubric_fallback_policy"):
            result["reason_source_layer"] = "rubric_fallback"
        else:
            result["reason_source_layer"] = "insufficient_reason"
    result["final_label"] = final_label
    if (
        final_label == LABEL_2
        and original_label != final_label
        and not result.get("_evidence_first_signal")
        and not result.get("_evidence_override")
        and not result.get("_calibration_override")
        and not result.get("_rubric_fallback_policy")
    ):
        result["_aggregation_analyse"] = evidence_reason(
            final_label,
            "unsupported_claims_are_not_fact_errors",
            extracted,
            evidence_summary,
            claim_pipeline_diagnostics,
            result.get("_evidence_non_decidable_state"),
        )
    if not result.get("analyse"):
        result["analyse"] = result.get("_aggregation_analyse") or "未发现明确事实错误"
    if not result.get("_decision_basis"):
        result["_decision_basis"] = classify_decision_basis(final_label, "", evidence_summary, extracted)
    channel_protocol = aggregate_decision_channel_protocol(
        extracted,
        evidence_summary,
        claim_pipeline_diagnostics,
        result.get("_evidence_non_decidable_state"),
    )
    evidence_signal = result.get("_evidence_first_signal") if isinstance(result.get("_evidence_first_signal"), dict) else {}
    result["_decision_channel"] = channel_protocol.get("decision_channel") or ""
    result["_channel_decision_candidate"] = channel_protocol.get("channel_decision_candidate") or ""
    result["_channel_decision_confidence"] = float(channel_protocol.get("channel_decision_confidence") or 0.0)
    result["_channel_label_candidate"] = channel_protocol.get("channel_label_candidate") or LABEL_2
    result["_channel_scope"] = channel_protocol.get("channel_scope") or ""
    result["label_source_channel"] = infer_label_source_channel(final_label, evidence_signal, channel_protocol)
    result["_label_source_channel"] = result.get("label_source_channel") or ""
    result["analyse"] = normalize_reason_by_decision_basis(
        str(result.get("analyse") or ""),
        final_label,
        str(result.get("_decision_basis") or ""),
    )
    consistency_reason = cross_claim_consistency_reason(final_label, evidence_summary)
    if consistency_reason and str(result.get("_decision_basis") or "") == "insufficient_evidence":
        result["analyse"] = consistency_reason
        result["_aggregation_analyse"] = consistency_reason
        result["_decision_policy"] = result.get("_decision_policy") or "surface_fact_confirmed_but_core_unresolved"
    result["_max_verdict_confidence"] = max_conf
    return result


# 19. 单条样本主流程：extract -> retrieve -> rewrite -> summarize -> verify -> review。
def run_one(item: Dict[str, Any]) -> Dict[str, Any]:
    started_at = time.perf_counter()
    last_mark = started_at

    def mark_timing(name: str) -> None:
        nonlocal last_mark
        now = time.perf_counter()
        timing = debug.setdefault("timing", {})
        timing[name] = round(now - last_mark, 3)
        timing["total_so_far"] = round(now - started_at, 3)
        last_mark = now

    debug: Dict[str, Any] = {
        "id": item.get("id"),
        "question": item.get("question", ""),
        "time": item.get("time", ""),
        "stage": "start",
        "runtime_check": ensure_llm_runtime_check(),
    }
    extracted, raw1, extract_meta = extract_with_fallback(item)
    debug["extract_meta"] = extract_meta
    if extracted is None:
        debug.update({"stage": "extract_failed", "error": raw1})
        return {
            "result": {"id": item.get("id"), "label": LABEL_2, "reason": f"抽取失败：{raw1}"},
            "debug": debug,
        }
    extracted = maybe_attach_detail_supplement(item, extracted, extract_meta)
    extracted = normalize_extracted_plan(extracted)
    mark_timing("extract")
    debug["extract_meta"]["claim_count"] = len(extracted.get("claims") or [])
    debug["extracted"] = extracted
    verification_plan, verification_plan_raw = build_debug_verification_plan(item, extracted)
    mark_timing("verification_plan")
    debug["verification_plan"] = verification_plan
    if verification_plan_raw:
        debug["verification_plan_raw"] = verification_plan_raw
    extracted = attach_verification_plan_hints_to_claims(extracted, verification_plan)
    extracted = maybe_apply_program_repair(item, extracted, extract_meta)
    debug["extracted"] = extracted

    claims = extracted.get("claims") if isinstance(extracted.get("claims"), list) else []
    retrieval_claims, retrieval_scope_reason, retrieval_scope_trace = claims_for_initial_retrieval(item, extracted)
    retrieval_budget = retrieval_budget_for_initial(item, extracted, retrieval_claims, retrieval_scope_reason)
    retrieval_claims, retrieval_budget = attach_atomic_claims_for_retrieval(extracted, retrieval_claims, retrieval_budget)
    annotate_claim_budget_metadata(claims, retrieval_budget)
    debug["retrieval_scope_reason"] = retrieval_scope_reason
    debug["initial_retrieval_scope_trace"] = retrieval_scope_trace
    debug["retrieval_claim_ids"] = [str(claim.get("claim_id") or claim.get("id") or "") for claim in retrieval_claims]
    debug["retrieval_budget"] = retrieval_budget
    debug["atomic_claim_attach_trace"] = retrieval_budget.get("atomic_claim_attach_trace", [])
    evidence_bundle = retrieve_evidence(
        question=str(item.get("question", "")),
        answer=str(item.get("answer", "")),
        history=item.get("history_question", []) or [],
        claims=retrieval_claims,
        time_value=str(item.get("time", "")),
        max_results_per_query=MAX_RESULTS_PER_QUERY,
        fetch_details=FETCH_DETAILS,
        timeout_sec=RETRIEVAL_TIMEOUT,
        query_limits=retrieval_budget.get("query_limits", {}),
        source_limits=retrieval_budget.get("source_limits", {}),
    )
    mark_timing("retrieve")
    debug["evidence_bundle"] = evidence_bundle
    debug["retrieval_effect_review"] = build_retrieval_effect_review(
        evidence_bundle if isinstance(evidence_bundle, dict) else {},
        debug.get("timing") if isinstance(debug.get("timing"), dict) else {},
    )
    evidence_summary = summarize_claim_evidence(claims, evidence_bundle.get("evidence_by_claim", {}) if isinstance(evidence_bundle, dict) else {})
    apply_page_role_consumption_gate(evidence_bundle if isinstance(evidence_bundle, dict) else {}, evidence_summary, debug)
    apply_decision_useful_candidate_rerank(claims, evidence_bundle if isinstance(evidence_bundle, dict) else {}, evidence_summary, debug)
    attach_comparability_profiles(extracted, evidence_summary)
    refine_route_claim_points_with_llm(claims, evidence_bundle if isinstance(evidence_bundle, dict) else {}, evidence_summary, debug)
    apply_llm_evidence_refiners(claims, evidence_summary, debug)
    apply_blocked_page_reader_rescue(extracted, claims, evidence_bundle, evidence_summary, debug)
    apply_page_role_consumption_gate(evidence_bundle if isinstance(evidence_bundle, dict) else {}, evidence_summary, debug)
    apply_decision_useful_candidate_rerank(claims, evidence_bundle if isinstance(evidence_bundle, dict) else {}, evidence_summary, debug)
    apply_decision_useful_consumption_state(claims, evidence_summary)
    evidence_summary["_qa_evidence"] = build_qa_evidence(claims, evidence_summary)
    mark_timing("initial_summary")
    debug["initial_evidence_summary"] = evidence_summary
    verification_gap_alignment = build_verification_gap_alignment(
        verification_plan if isinstance(verification_plan, dict) else {},
        evidence_bundle if isinstance(evidence_bundle, dict) else {},
        evidence_summary,
    )
    debug["verification_gap_alignment"] = verification_gap_alignment
    if ENABLE_REWRITE:
        skip_rewrite = rewrite_skip_reason(item, extracted, evidence_summary, verification_gap_alignment)
        route_probe_override = skip_rewrite == "skip_rewrite_open_route_summary_first"
        verification_alignment_override = skip_rewrite == "skip_rewrite_semantic_boundary_first" and verification_alignment_supports_retry(verification_gap_alignment)
        retry_claims, retry_claim_candidates, retry_budget_summary = claims_needing_rewrite(
            claims,
            evidence_bundle,
            evidence_summary,
            extracted.get("need_type", ""),
            allow_route_supporting_probe=route_probe_override or verification_alignment_override,
            verification_gap_alignment=verification_gap_alignment,
        ) if (not skip_rewrite or route_probe_override or verification_alignment_override) else ([], [], {})
        if route_probe_override and retry_claims:
            debug["rewrite_skip_override"] = "open_route_summary_route_probe_retry"
            skip_rewrite = ""
        elif verification_alignment_override and retry_claims:
            debug["rewrite_skip_override"] = "verification_gap_alignment_retry"
            skip_rewrite = ""
        debug["rewrite_skipped_reason"] = skip_rewrite
        debug["retry_claim_ids"] = [str(claim.get("claim_id") or claim.get("id") or "") for claim in retry_claims]
        debug["retry_claim_candidates"] = retry_claim_candidates
        debug["retry_budget_summary"] = retry_budget_summary.get("debug_summary", retry_budget_summary) if isinstance(retry_budget_summary, dict) else {}
        if retry_claims:
            rewrite_obj, raw_rewrite = llm_chat(
                SYSTEM_REWRITE,
                build_rewrite_prompt(
                    item,
                    extracted,
                    evidence_bundle,
                    retry_claims,
                    evidence_summary,
                    verification_gap_alignment,
                ),
            )
            mark_timing("rewrite")
            debug["rewrite_raw"] = raw_rewrite
            rewrite_plan = normalize_rewrite_plan(rewrite_obj)
            debug["rewrite_plan"] = rewrite_plan
            rewrite_frames = normalize_rewrite_frames(rewrite_obj, retry_claims)
            debug["rewrite_route_frames"] = rewrite_frames
            rewritten_claims = build_retry_claims(claims, rewrite_plan, rewrite_frames, retry_claims, verification_gap_alignment)
            if rewritten_claims:
                retry_bundle = retrieve_evidence(
                    question=str(item.get("question", "")),
                    answer=str(item.get("answer", "")),
                    history=item.get("history_question", []) or [],
                    claims=rewritten_claims,
                    time_value=str(item.get("time", "")),
                    max_results_per_query=MAX_RESULTS_PER_QUERY,
                    fetch_details=FETCH_DETAILS,
                    timeout_sec=RETRIEVAL_TIMEOUT,
                )
                mark_timing("retry_retrieve")
                debug["retry_evidence_bundle"] = retry_bundle
                evidence_bundle = merge_evidence_bundles(evidence_bundle, retry_bundle)
                debug["evidence_bundle"] = evidence_bundle
    evidence_summary = summarize_claim_evidence(claims, evidence_bundle.get("evidence_by_claim", {}) if isinstance(evidence_bundle, dict) else {})
    apply_decision_useful_candidate_rerank(claims, evidence_bundle if isinstance(evidence_bundle, dict) else {}, evidence_summary, debug)
    attach_comparability_profiles(extracted, evidence_summary)
    refine_route_claim_points_with_llm(claims, evidence_bundle if isinstance(evidence_bundle, dict) else {}, evidence_summary, debug)
    apply_llm_evidence_refiners(claims, evidence_summary, debug)
    apply_blocked_page_reader_rescue(extracted, claims, evidence_bundle, evidence_summary, debug)
    apply_page_role_consumption_gate(evidence_bundle if isinstance(evidence_bundle, dict) else {}, evidence_summary, debug)
    apply_decision_useful_candidate_rerank(claims, evidence_bundle if isinstance(evidence_bundle, dict) else {}, evidence_summary, debug)
    apply_decision_useful_consumption_state(claims, evidence_summary)
    evidence_summary["_qa_evidence"] = build_qa_evidence(claims, evidence_summary)
    mark_timing("final_summary")
    debug["evidence_summary"] = evidence_summary
    debug["qa_evidence"] = evidence_summary.get("_qa_evidence")
    claim_pipeline_diagnostics = build_claim_pipeline_diagnostics(extracted, evidence_bundle, evidence_summary)
    debug["claim_pipeline_diagnostics"] = claim_pipeline_diagnostics
    evidence_ledger = build_evidence_ledger(extracted, evidence_summary, claim_pipeline_diagnostics)
    evidence_summary["_evidence_ledger"] = evidence_ledger
    debug["evidence_ledger"] = evidence_ledger
    core_assertion_audit = build_core_assertion_audit(
        extracted,
        evidence_summary,
        claim_pipeline_diagnostics,
        evidence_ledger,
    )
    evidence_summary["_core_assertion_audit"] = core_assertion_audit
    debug["core_assertion_audit"] = core_assertion_audit
    cross_claim_consistency = build_cross_claim_consistency(
        extracted,
        evidence_summary,
        claim_pipeline_diagnostics,
        evidence_ledger,
        core_assertion_audit,
    )
    evidence_summary["_cross_claim_consistency"] = cross_claim_consistency
    debug["cross_claim_consistency"] = cross_claim_consistency
    debug["evidence_first_audit"] = evidence_first_audit(extracted, evidence_summary)
    verify_obj, raw2 = llm_chat(SYSTEM_VERIFY, build_verify_prompt(item, extracted, evidence_bundle, evidence_summary))
    mark_timing("verify")
    if verify_obj is None:
        debug.update({"stage": "verify_failed", "error": raw2})
        return {
            "result": {"id": item.get("id"), "label": LABEL_2, "reason": f"裁决失败：{raw2}"},
            "debug": debug,
        }

    verify_obj["_llm_analyse"] = str(verify_obj.get("analyse") or "")
    verify_obj["_llm_final_label"] = pick_label(verify_obj.get("final_label")) or ""
    verify_obj = aggregate_by_confidence(
        verify_obj,
        extracted,
        evidence_bundle,
        evidence_summary,
        item,
        claim_pipeline_diagnostics,
    )
    if verify_obj.get("_rubric_elapsed_ms") is not None:
        debug.setdefault("timing", {})["rubric"] = round(float(verify_obj.get("_rubric_elapsed_ms") or 0.0) / 1000.0, 3)
    debug["verify"] = verify_obj

    if should_run_semantic_audit(item, extracted, verify_obj, evidence_summary):
        audit_obj, raw_audit = llm_chat(
            SYSTEM_SEMANTIC_AUDIT,
            build_semantic_audit_prompt(item, extracted, evidence_bundle, evidence_summary, verify_obj),
        )
        mark_timing("semantic_audit")
        debug["semantic_audit_raw"] = raw_audit
        debug["semantic_audit_triggers"] = semantic_audit_triggers(item, extracted, verify_obj)
        if audit_obj and pick_label(audit_obj.get("final_label")):
            audit_label = pick_label(audit_obj.get("final_label"))
            audit_type = str(audit_obj.get("audit_type") or "")
            audit_reason = normalize_text(str(audit_obj.get("analyse") or ""))
            audit_confidence = float(audit_obj.get("confidence", 0.0) or 0.0)
            need_type = normalize_need_type(extracted.get("need_type"))
            answer_text = normalize_text(str(item.get("answer") or ""))
            if (
                audit_label == LABEL_0
                and need_type == "market_movement"
                and not any(term in answer_text for term in ["无悬念", "年内最大", "即将迎来", "确定落地"])
            ):
                audit_label = LABEL_1
            if (
                audit_label == LABEL_0
                and need_type == "geopolitical_claim"
                and audit_type == "absolute_route_or_causal"
                and not any(term in answer_text for term in ["根本不需要", "没有实质性影响", "完全绕开", "不需要经过"])
            ):
                audit_label = LABEL_1
            if semantic_audit_upgrade_allowed(audit_label, audit_type, audit_confidence, item, extracted, evidence_summary):
                verify_obj["final_label"] = audit_label
                verify_obj["analyse"] = audit_reason or verify_obj.get("analyse") or ""
                verify_obj["_semantic_audit_analyse"] = audit_reason
                verify_obj["_semantic_audit"] = audit_type
                verify_obj["_semantic_audit_confidence"] = audit_confidence
                verify_obj["_decision_basis"] = classify_decision_basis(audit_label, audit_type, evidence_summary, extracted)
                verify_obj["_decision_policy"] = audit_type
                debug["semantic_audit"] = audit_obj
                if audit_label in {LABEL_0, LABEL_1} and has_direct_refuting_evidence(evidence_summary) and audit_type != "attached_detail_pollution":
                    verify_obj["analyse"] = evidence_reason(audit_label, "direct_evidence_refutation", extracted, evidence_summary)
                    verify_obj["_reason_source"] = "evidence_refutation_after_audit"
                    verify_obj["_decision_basis"] = "evidence_refutation"
            else:
                debug["semantic_audit_rejected"] = {
                    "audit_label": audit_label,
                    "audit_type": audit_type,
                    "confidence": audit_confidence,
                    "reason": "audit_not_allowed_to_override_without_direct_refutation_or_explicit_boundary",
                }

    if (
        verify_obj.get("final_label") == LABEL_0
        and not verify_obj.get("_rubric_fallback_policy")
        and not verify_obj.get("_calibration_override")
        and not verify_obj.get("_semantic_audit")
        and str(verify_obj.get("_decision_policy") or "") not in {"atomic_core_direct_refutation", "atomic_secondary_direct_refutation"}
        and not has_new_scheme_core_refuting_evidence(extracted, evidence_summary)
        and float(verify_obj.get("_max_verdict_confidence", 0.0) or 0.0) < 0.85
    ):
        review_obj, raw3 = llm_chat(SYSTEM_REVIEW, build_review_prompt(item, extracted, evidence_bundle, evidence_summary, verify_obj))
        mark_timing("review")
        debug["review_raw"] = raw3
        if review_obj and pick_label(review_obj.get("final_label")):
            verify_obj["final_label"] = pick_label(review_obj.get("final_label"))
            verify_obj["analyse"] = str(review_obj.get("analyse") or verify_obj.get("analyse") or "").strip()
            verify_obj["_review_analyse"] = str(review_obj.get("analyse") or "")
            verify_obj["_decision_basis"] = verify_obj.get("_decision_basis") or classify_decision_basis(
                pick_label(verify_obj.get("final_label")) or LABEL_2,
                str(verify_obj.get("_decision_policy") or verify_obj.get("_semantic_audit") or ""),
                evidence_summary,
                extracted,
            )
            debug["review"] = review_obj

    label = pick_label(verify_obj.get("final_label")) or LABEL_2
    decision_basis = str(verify_obj.get("_decision_basis") or classify_decision_basis(
        label,
        str(verify_obj.get("_decision_policy") or verify_obj.get("_calibration_override") or verify_obj.get("_semantic_audit") or ""),
        evidence_summary,
        extracted,
    ))
    verify_obj["_decision_basis"] = decision_basis
    fallback_reason = normalize_reason_by_decision_basis(str(verify_obj.get("analyse") or ""), label, decision_basis)
    reason, reason_source = choose_final_reason(verify_obj, label, decision_basis, fallback_reason, evidence_summary, extracted)
    verify_obj["_final_reason_source"] = reason_source
    verify_obj["_evidence_summary_for_reason"] = evidence_summary
    conflict_issues = final_reason_conflict_issues(reason, label, decision_basis, evidence_summary)
    if conflict_issues:
        verify_obj["_final_reason_conflict_issues"] = conflict_issues
    if should_refine_final_reason(verify_obj, reason, extracted):
        refined_obj, raw_final_reason = llm_chat(
            SYSTEM_FINAL_REASON,
            build_final_reason_prompt(item, extracted, evidence_bundle, evidence_summary, verify_obj, reason),
            retries=0,
        )
        mark_timing("final_reason")
        debug["final_reason_raw"] = raw_final_reason
        if isinstance(refined_obj, dict):
            refined_reason = normalize_reason_by_decision_basis(
                str(refined_obj.get("analyse") or ""),
                label,
                decision_basis,
            )
            if (
                refined_reason
                and len(refined_reason) >= 12
                and llm_reason_is_safe(refined_reason, label, decision_basis, evidence_summary)
            ):
                reason = refined_reason
                verify_obj["_reason_refined_by_llm"] = True
                verify_obj["_final_reason_source"] = "llm_final_reason_refine"
            else:
                verify_obj["_reason_refine_rejected"] = True
                verify_obj["_reason_refine_reject_issues"] = final_reason_conflict_issues(refined_reason, label, decision_basis, evidence_summary)
    final_conflict_issues = final_reason_conflict_issues(reason, label, decision_basis, evidence_summary)
    if final_conflict_issues:
        reason = consistent_conflict_fallback_reason(label, decision_basis, verify_obj, evidence_summary)
        verify_obj["_final_reason_source"] = "code_consistency_guard"
        verify_obj["_final_reason_conflict_guard"] = final_conflict_issues
    if not reason:
        reason = "未发现明确事实错误"
    if isinstance(evidence_summary, dict) and isinstance(evidence_summary.get("_evidence_ledger"), dict):
        evidence_summary["_evidence_ledger"]["final_label_reason"] = reason
        policy_debug = verify_obj.get("_decision_policy_debug") if isinstance(verify_obj.get("_decision_policy_debug"), dict) else {}
        if policy_debug:
            evidence_summary["_evidence_ledger"]["decision_policy_debug"] = policy_debug
        evidence_summary["_evidence_ledger"]["decision_policy_route"] = str(
            verify_obj.get("_decision_policy_route") or policy_debug.get("policy_route") or ""
        )
        evidence_summary["_evidence_ledger"]["decision_permission_gate"] = str(verify_obj.get("_decision_permission_gate") or "")
        debug["evidence_ledger"] = evidence_summary["_evidence_ledger"]
    result = {"id": item.get("id"), "label": label, "reason": reason}
    debug_final_result = dict(result)
    debug_final_result.update(
        {
            "_decision_channel": verify_obj.get("_decision_channel") or "",
            "_channel_decision_candidate": verify_obj.get("_channel_decision_candidate") or "",
            "_channel_decision_confidence": float(verify_obj.get("_channel_decision_confidence") or 0.0),
            "_channel_label_candidate": verify_obj.get("_channel_label_candidate") or LABEL_2,
            "_channel_scope": verify_obj.get("_channel_scope") or "",
            "label_source_channel": verify_obj.get("label_source_channel") or "",
            "_label_source_channel": verify_obj.get("_label_source_channel") or "",
            "_decision_basis": verify_obj.get("_decision_basis") or "",
            "_decision_policy": verify_obj.get("_decision_policy") or "",
            "decision_gate_consumed_diagnostics": bool(verify_obj.get("decision_gate_consumed_diagnostics")),
            "decision_gate_primary_block": verify_obj.get("decision_gate_primary_block") or "",
            "reason_source_layer": verify_obj.get("reason_source_layer") or "",
        }
    )
    debug.update({"stage": "done", "final_result": debug_final_result})
    return {"result": result, "debug": debug}


# 18. 输入输出：加载数据、保存结果和 debug。
def load_items(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("input json must be a list")
    return data


def save_output(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    temp_path.replace(path)


def save_debug(path: Optional[Path], rows: List[Dict[str, Any]]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    temp_path.replace(path)


def load_resume_results(path: Path, input_ids: set[str]) -> Dict[str, Dict[str, Any]]:
    if not RESUME_OUTPUT or not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(rows, list):
        return {}
    resumed: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id") or "")
        if row_id in input_ids and row.get("label") in VALID_LABELS:
            resumed[row_id] = row
    return resumed


# 19. 命令行入口：批量并发处理样本，并写出 output/debug 文件。
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data.json")
    parser.add_argument("--output", default=os.path.join("output", "results.json"))
    parser.add_argument("--debug-output", default="")
    parser.add_argument("--perf-output", default="")
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    items = load_items(input_path)

    results: List[Optional[Dict[str, Any]]] = [None] * len(items)
    debug_rows: List[Optional[Dict[str, Any]]] = [None] * len(items)
    input_ids = {str(item.get("id") or "") for item in items}
    resumed = {} if args.no_resume else load_resume_results(output_path, input_ids)
    pending: List[Tuple[int, Dict[str, Any]]] = []
    for index, item in enumerate(items):
        item_id = str(item.get("id") or "")
        if item_id in resumed:
            results[index] = resumed[item_id]
            debug_rows[index] = {"id": item_id, "stage": "resumed"}
        else:
            pending.append((index, item))

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        future_map = {executor.submit(run_one, item): index for index, item in pending}
        for future in as_completed(future_map):
            index = future_map[future]
            item = items[index]
            try:
                payload = future.result()
                if isinstance(payload, dict) and "result" in payload:
                    results[index] = payload["result"]
                    debug_rows[index] = payload.get("debug")
                else:
                    results[index] = payload
                    debug_rows[index] = {"id": item.get("id"), "stage": "legacy_result", "final_result": payload}
            except Exception as exc:
                results[index] = {"id": item.get("id"), "label": LABEL_2, "reason": f"运行异常：{exc}"}
                debug_rows[index] = {"id": item.get("id"), "stage": "exception", "error": str(exc)}
            save_output(output_path, [row for row in results if row is not None])
            if args.debug_output:
                save_debug(Path(args.debug_output), [row for row in debug_rows if row is not None])

    final_results = [row for row in results if row is not None]
    save_output(output_path, final_results)
    if args.debug_output:
        save_debug(Path(args.debug_output), [row for row in debug_rows if row is not None])
    if args.perf_output:
        timings = [
            row.get("timing", {})
            for row in debug_rows
            if isinstance(row, dict) and isinstance(row.get("timing"), dict)
        ]
        summary: Dict[str, Any] = {"count": len(final_results), "timed_count": len(timings)}
        if timings:
            keys = sorted({key for timing in timings for key in timing if key != "total_so_far"})
            summary["total_seconds"] = round(sum(float(timing.get("total_so_far") or 0.0) for timing in timings), 3)
            summary["avg_seconds"] = round(summary["total_seconds"] / max(1, len(timings)), 3)
            summary["stage_avg_seconds"] = {
                key: round(sum(float(timing.get(key) or 0.0) for timing in timings) / max(1, len(timings)), 3)
                for key in keys
            }
        save_output(Path(args.perf_output), [summary])


if __name__ == "__main__":
    main()
    os._exit(0)
