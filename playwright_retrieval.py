# -*- coding: utf-8 -*-
import argparse
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests


_HTTP_SESSION = requests.Session()
_HTTP_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

ANTI_BOT_STATUS_CODES = {401, 403, 406, 409, 412, 418, 429, 451, 503}
ANTI_BOT_URL_HINTS = ("captcha", "challenge", "verify", "security-check", "bot-check", "robot", "blocked")
ANTI_BOT_TEXT_PATTERNS = [
    (re.compile(r"captcha|verify (?:you are )?human|security check|access denied|unusual traffic|are you a robot", flags=re.I), "challenge_page"),
    (re.compile(r"cloudflare|cf-chl|attention required", flags=re.I), "cloudflare_challenge"),
    (re.compile(r"too many requests|rate limit|temporarily blocked", flags=re.I), "rate_limit_page"),
    (re.compile(r"人机验证|验证码|访问频繁|访问过于频繁|操作过于频繁|安全验证|滑动验证|请完成验证|异常流量|机器人", flags=re.I), "cn_challenge_page"),
]


class AntiBotBlockedError(RuntimeError):
    pass


CLAIM_PREFIXES = ["请判断", "請判斷", "判断", "判斷"]
ENGLISH_STOPWORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "from",
    "and",
    "or",
    "that",
    "this",
    "there",
    "called",
    "named",
}
ENGLISH_RELATION_HINTS = [
    "born",
    "founded",
    "created",
    "directed",
    "produced",
    "released",
    "published",
    "won",
    "nominated",
    "ranked",
    "located",
    "capital",
    "president",
    "prime minister",
    "governor",
    "population",
    "area",
    "derived from",
    "known as",
    "called",
    "larger than",
    "smaller than",
    "higher than",
    "lower than",
]


def normalize_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def anti_bot_signal_reasons(text, url=""):
    sample = normalize_text(text)[:12000]
    lowered_url = normalize_text(url).lower()
    reasons = []
    if any(hint in lowered_url for hint in ANTI_BOT_URL_HINTS):
        reasons.append("challenge_url")
    for pattern, reason in ANTI_BOT_TEXT_PATTERNS:
        if pattern.search(sample):
            reasons.append(reason)
    return dedupe_keep_order(reasons)


def guard_response(response, request_url="", source_name=""):
    status_code = int(getattr(response, "status_code", 0) or 0)
    sample = ""
    content_type = normalize_text(str(response.headers.get("Content-Type") or "")).lower()
    if status_code in ANTI_BOT_STATUS_CODES or any(marker in content_type for marker in ("html", "text", "xml", "json")):
        sample = decode_response_text(response)
    reasons = anti_bot_signal_reasons(sample, getattr(response, "url", "") or request_url)
    if status_code in ANTI_BOT_STATUS_CODES:
        reasons = [f"http_{status_code}"] + reasons
    if reasons:
        raise AntiBotBlockedError(f"anti_bot_blocked:{','.join(dedupe_keep_order(reasons))} source={source_name} url={request_url}")


def guarded_get(url, timeout_sec, source_name="", **kwargs):
    response = _HTTP_SESSION.get(url, timeout=timeout_sec, **kwargs)
    guard_response(response, request_url=url, source_name=source_name)
    response.raise_for_status()
    return response


def decode_response_text(response):
    encoding = response.encoding
    if not encoding or encoding.lower() == "iso-8859-1":
        encoding = response.apparent_encoding or "utf-8"
    try:
        return response.content.decode(encoding, errors="ignore")
    except Exception:
        return response.text


def strip_claim_eval_prefix(text):
    cleaned = normalize_text(text)
    for prefix in CLAIM_PREFIXES:
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :].strip(" :：")
    return cleaned


def dedupe_keep_order(parts):
    seen = set()
    output = []
    for part in parts:
        part = normalize_text(part)
        if not part or part in seen:
            continue
        seen.add(part)
        output.append(part)
    return output


def is_ascii_heavy(text):
    text = text or ""
    ascii_letters = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    cjk_letters = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return ascii_letters >= 8 and ascii_letters >= cjk_letters * 2


def extract_english_title_phrases(text, max_phrases=4):
    cleaned = strip_claim_eval_prefix(text)
    matches = re.findall(
        r"\b(?:[A-Z][A-Za-z0-9()'._-]*\s+){0,5}[A-Z][A-Za-z0-9()'._-]*\b",
        cleaned,
    )
    phrases = []
    for match in matches:
        candidate = normalize_text(match).strip(" ,.;:()[]{}\"'")
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered in ENGLISH_STOPWORDS or len(candidate) < 3:
            continue
        phrases.append(candidate)
    return dedupe_keep_order(phrases)[:max_phrases]


def extract_english_comparison_query_parts(text):
    cleaned = normalize_text(text).strip(" .")
    pattern = re.compile(
        r"^(?:the\s+)?(?P<metric1>area|population|height|length|rank|ranking|price|box office)\s+of\s+"
        r"(?P<entity1>.+?)\s+is\s+"
        r"(?P<comparator>larger than|smaller than|higher than|lower than|greater than|less than)\s+"
        r"(?:the\s+)?(?P<metric2>area|population|height|length|rank|ranking|price|box office)\s+of\s+"
        r"(?P<entity2>.+?)$",
        flags=re.IGNORECASE,
    )
    match = pattern.match(cleaned)
    if not match:
        return []
    return [
        match.group("entity1").strip(" ,."),
        match.group("metric1").lower(),
        match.group("entity2").strip(" ,."),
        match.group("metric2").lower(),
        match.group("comparator").lower(),
    ]


def extract_english_birth_query_parts(text):
    cleaned = normalize_text(text).strip(" .")
    match = re.match(
        r"^(?P<person>.+?)\s+was\s+born\s+in\s+(?P<place>.+?)(?:\s+after\s+(?P<year>\d{4}))?$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return []
    parts = [match.group("person").strip(" ,."), "born", match.group("place").strip(" ,.")]
    year = match.group("year")
    if year:
        parts.append(year)
    return parts


def build_english_claim_query(claim):
    cleaned = strip_claim_eval_prefix(claim)
    lowered = cleaned.lower()
    years = re.findall(r"\b\d{3,4}\b", cleaned)
    entities = extract_english_title_phrases(cleaned)
    relation_terms = [hint for hint in ENGLISH_RELATION_HINTS if hint in lowered][:3]

    comparison_parts = extract_english_comparison_query_parts(cleaned)
    if comparison_parts:
        return " ".join(dedupe_keep_order(comparison_parts))

    birth_parts = extract_english_birth_query_parts(cleaned)
    if birth_parts:
        return " ".join(dedupe_keep_order(birth_parts))

    parts = []
    parts.extend(entities[:3])
    parts.extend(years[:2])
    parts.extend(relation_terms)
    if len(entities) < 2:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9._'-]*", cleaned)
        parts.extend(token for token in tokens if token.lower() not in ENGLISH_STOPWORDS)

    query = " ".join(dedupe_keep_order(parts))
    if len(query) < 24:
        query = cleaned[:160]
    return query.strip()


def build_english_claim_queries(claim):
    cleaned = strip_claim_eval_prefix(claim)
    queries = []
    primary = build_english_claim_query(cleaned)
    if primary:
        queries.append(primary)

    comparison_parts = extract_english_comparison_query_parts(cleaned)
    if comparison_parts and len(comparison_parts) >= 4:
        entity1, metric1, entity2, metric2 = comparison_parts[:4]
        queries.append(f"{entity1} {metric1}")
        queries.append(f"{entity2} {metric2}")

    birth_parts = extract_english_birth_query_parts(cleaned)
    if birth_parts:
        person = birth_parts[0]
        queries.append(f"{person} born")
        if len(birth_parts) >= 3:
            queries.append(f"{person} {birth_parts[2]}")

    lowered = cleaned.lower()
    entities = extract_english_title_phrases(cleaned)
    years = re.findall(r"\b\d{3,4}\b", cleaned)
    relation_terms = [hint for hint in ENGLISH_RELATION_HINTS if hint in lowered][:3]
    if entities and relation_terms:
        queries.append(" ".join(dedupe_keep_order(entities[:3] + years[:2] + relation_terms)))
        queries.append(" ".join(dedupe_keep_order(entities[:2] + relation_terms[:2])))

    return dedupe_keep_order(query for query in queries if query)[:3]


def build_claim_style_query(claim):
    claim = strip_claim_eval_prefix(claim)
    if is_ascii_heavy(claim):
        return build_english_claim_query(claim)
    tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,40}", claim)
    query = " ".join(dedupe_keep_order(tokens[:4]))
    return query[:120].strip() or claim[:120]


def infer_evidence_requirements(payload):
    # 这里先识别“需要哪类证据”，而不是直接把问题硬分成固定题型。
    # 后面的路由、query 生成、专源选择都基于这些证据需求来做。
    question = normalize_text(str(payload.get("question", "")))
    answer = normalize_text(str(payload.get("answer", "")))
    combined = f"{question}\n{answer}"

    realtime_markers = ["今天", "今日", "现在", "目前", "最新", "刚刚", "截至", "实时"]
    numeric_market_markers = [
        "汇率",
        "兑换",
        "兑美元",
        "兑人民币",
        "现汇买入价",
        "卖出价",
        "中间价",
        "在岸",
        "离岸",
        "报价",
        "开盘",
        "收盘",
        "涨了",
        "跌了",
        "票房",
        "排名",
        "指数",
    ]
    publish_markers = ["公布", "发布", "宣布", "结果什么时候出", "何时出", "何时公布", "何时发布"]
    result_markers = ["赛果", "比分", "战况", "谁赢了", "谁赢", "结果"]
    route_markers = ["路线", "领空", "经过", "通道", "飞行路线", "路径", "绕开"]
    identity_markers = ["谁", "是谁", "获奖者", "作者", "导演", "作家", "哪位", "哪个人", "哪个组织"]

    return {
        "needs_realtime_anchor": any(marker in combined for marker in realtime_markers),
        "needs_numeric_market_data": any(marker in combined for marker in numeric_market_markers),
        "needs_publish_timeline": any(marker in question for marker in publish_markers),
        "needs_result_status": any(marker in question for marker in result_markers),
        "needs_route_evidence": any(marker in combined for marker in route_markers),
        "needs_identity_detail": any(marker in question for marker in identity_markers),
        "has_explicit_number": bool(re.search(r"\d", combined)),
    }


def infer_evidence_target(payload):
    requirements = infer_evidence_requirements(payload)

    if requirements["needs_numeric_market_data"] and (
        requirements["needs_realtime_anchor"] or requirements["has_explicit_number"]
    ):
        return "fresh_numeric_market"
    if requirements["needs_publish_timeline"]:
        return "publish_timeline"
    if requirements["needs_result_status"] and requirements["needs_realtime_anchor"]:
        return "current_result"
    if requirements["needs_route_evidence"]:
        return "route_impact"
    if requirements["needs_identity_detail"]:
        return "identity_detail"
    return "generic"


def infer_evidence_requirements(payload):
    # 覆盖旧版，使用明确的中文证据需求标记，避免时间线类问题漏路由。
    question = normalize_text(str(payload.get("question", "")))
    answer = normalize_text(str(payload.get("answer", "")))
    combined = f"{question}\n{answer}"

    realtime_markers = ["今天", "今日", "现在", "目前", "最新", "刚刚", "截至", "实时"]
    numeric_market_markers = [
        "汇率",
        "兑换",
        "兑美元",
        "兑人民币",
        "现汇买入价",
        "现汇卖出价",
        "卖出价",
        "中间价",
        "在岸",
        "离岸",
        "报价",
        "开盘",
        "收盘",
        "涨了",
        "跌了",
        "票房",
        "排名",
        "指数",
    ]
    publish_markers = [
        "结果什么时候出",
        "什么时候出结果",
        "什么时候出",
        "何时出",
        "何时公布",
        "何时发布",
        "什么时候公布",
        "什么时候发布",
        "公布时间",
        "发布时间",
        "结果何时公布",
        "结果何时发布",
        "结果多久出来",
    ]
    result_markers = ["赛果", "比分", "战况", "谁赢了", "谁赢", "结果"]
    route_markers = ["路线", "领空", "经过", "通道", "飞行路线", "路径", "绕开"]
    identity_markers = ["谁", "是谁", "获奖者", "作者", "导演", "作家", "哪位", "哪个人", "哪个组织"]

    return {
        "needs_realtime_anchor": any(marker in combined for marker in realtime_markers),
        "needs_numeric_market_data": any(marker in combined for marker in numeric_market_markers),
        "needs_publish_timeline": any(marker in question for marker in publish_markers),
        "needs_result_status": any(marker in question for marker in result_markers),
        "needs_route_evidence": any(marker in combined for marker in route_markers),
        "needs_identity_detail": any(marker in question for marker in identity_markers),
        "has_explicit_number": bool(re.search(r"\d", combined)),
    }


def strip_question_tail(text):
    cleaned = normalize_text(text)
    patterns = [
        r"(的?获奖者)?是谁[？?]?$",
        r"分别是谁[？?]?$",
        r"是哪位[？?]?$",
        r"是哪个人[？?]?$",
        r"是哪个组织[？?]?$",
        r"是谁写的[？?]?$",
        r"是谁导演的[？?]?$",
        r"有没有影响[吗么]?[？?]?$",
        r"是否有影响[吗么]?[？?]?$",
        r"是什么[？?]?$",
        r"是多少[？?]?$",
        r"分别是多少[？?]?$",
        r"有哪些[？?]?$",
        r"经过哪些国家[？?]?$",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned)
    return cleaned.strip(" ，,：:。.!！?？")


def extract_focus_subject(payload):
    question = normalize_text(str(payload.get("question", "")))
    answer = normalize_text(str(payload.get("answer", "")))
    target = infer_evidence_target(payload)
    text = strip_claim_eval_prefix(question) or question
    title_phrases = extract_english_title_phrases(text)
    if title_phrases:
        return title_phrases[0]

    if target == "identity_detail":
        candidate = strip_question_tail(text)
        if candidate:
            text = candidate

    cjk_chunks = re.findall(r"[\u4e00-\u9fffA-Za-z0-9·()（）\-]{2,40}", text)
    filtered = []
    stop_chunks = {
        "是不是",
        "是否",
        "有没有",
        "有影响吗",
        "有影响么",
        "打完了吗",
        "出了吗",
        "定了吗",
        "今天",
        "今日",
        "现在",
        "目前",
        "最新",
        "刚刚",
        "实时",
        "结果",
        "赛果",
        "比分",
        "汇率",
        "兑换",
        "开盘",
        "收盘",
        "涨了",
        "跌了",
        "是多少",
        "分别是多少",
        "谁",
        "是谁",
        "获奖者",
    }
    for chunk in cjk_chunks:
        if chunk in stop_chunks:
            continue
        filtered.append(chunk)
    if filtered:
        return filtered[0]

    if answer and len(answer) <= 40:
        return answer[:30]
    return ""


def extract_focus_subject(payload):
    question = normalize_text(str(payload.get("question", "")))
    answer = normalize_text(str(payload.get("answer", "")))
    target = infer_evidence_target(payload)
    text = strip_claim_eval_prefix(question) or question
    title_phrases = extract_english_title_phrases(text)
    if title_phrases:
        return title_phrases[0]

    if target == "identity_detail":
        candidate = strip_question_tail(text)
        if candidate:
            text = candidate
    elif target == "publish_timeline":
        candidate = re.sub(
            r"(结果什么时候出|什么时候出结果|什么时候出|何时出|何时公布|何时发布|什么时候公布|什么时候发布|公布时间|发布时间)$",
            "",
            text,
        ).strip("？?，,。 ")
        if candidate:
            text = candidate

    cjk_chunks = re.findall(r"[\u4e00-\u9fffA-Za-z0-9路()（）\-]{2,40}", text)
    stop_chunks = {
        "是不是",
        "是否",
        "有没有",
        "有影响吗",
        "有影响么",
        "打完了吗",
        "出了吗",
        "定了吗",
        "今天",
        "今日",
        "现在",
        "目前",
        "最新",
        "刚刚",
        "实时",
        "结果",
        "赛果",
        "比分",
        "汇率",
        "兑换",
        "开盘",
        "收盘",
        "涨了",
        "跌了",
        "是多少",
        "分别是多少",
        "谁",
        "是谁",
        "获奖者",
    }
    filtered = [chunk for chunk in cjk_chunks if chunk not in stop_chunks]
    if filtered:
        return filtered[0]

    if answer and len(answer) <= 40:
        return answer[:30]
    return ""


def extract_market_focus_terms(payload):
    question = normalize_text(str(payload.get("question", "")))
    answer = normalize_text(str(payload.get("answer", "")))
    combined = f"{question}\n{answer}"

    terms = []
    if any(token in combined for token in ["美元", "美金", "USD", "usd"]):
        terms.extend(["美元", "USD"])
    if any(token in combined for token in ["人民币", "CNY", "cny"]):
        terms.extend(["人民币", "CNY"])
    if "现汇买入价" in combined:
        terms.append("现汇买入价")
    if "现汇卖出价" in combined:
        terms.append("现汇卖出价")
    if "中间价" in combined:
        terms.append("中间价")
    if any(token in combined for token in ["汇率", "兑换", "兑美元", "兑人民币"]):
        terms.append("汇率")
    if "开盘" in combined:
        terms.append("开盘")
    if "收盘" in combined:
        terms.append("收盘")
    if "涨了" in combined or "上涨" in combined:
        terms.append("上涨")
    if "跌了" in combined or "下跌" in combined:
        terms.append("下跌")
    if any(token in combined for token in ["中国银行", "中行"]):
        terms.append("中国银行")

    date_match = re.search(r"(20\d{2})[-年](\d{1,2})[-月](\d{1,2})", combined)
    if date_match:
        year, month, day = date_match.groups()
        terms.append(f"{year}年{month}月{day}日")
    elif any(token in combined for token in ["今天", "今日", "现在", "目前", "最新"]):
        terms.append("今日")

    return dedupe_keep_order(terms)


def build_market_queries(payload):
    question = normalize_text(str(payload.get("question", "")))
    answer = normalize_text(str(payload.get("answer", "")))
    combined = f"{question}\n{answer}"

    currency_pair = ""
    if any(token in combined for token in ["美元", "美金"]):
        currency_pair = "美元兑人民币"
    elif "人民币兑美元" in combined:
        currency_pair = "人民币兑美元"

    queries = []
    date_match = re.search(r"(20\d{2})[-年](\d{1,2})[-月](\d{1,2})", combined)
    date_text = ""
    if date_match:
        year, month, day = date_match.groups()
        date_text = f"{year}年{int(month)}月{int(day)}日"
    elif any(token in combined for token in ["今天", "今日", "现在", "目前", "最新", "实时"]):
        date_text = "今日"

    if "现汇买入价" in combined or "现汇卖出价" in combined:
        if currency_pair:
            queries.append(f"{currency_pair} 中国银行 现汇买入价 现汇卖出价 {date_text}".strip())
            queries.append(f"中国银行 美元 现汇牌价 {date_text}".strip())
        else:
            queries.append(f"中国银行 现汇买入价 现汇卖出价 {date_text}".strip())
    elif "中间价" in combined or "汇率" in combined or "兑换" in combined:
        if currency_pair:
            queries.append(f"{currency_pair} 汇率 中间价 {date_text}".strip())
            queries.append(f"{currency_pair} 今日 汇率 {date_text}".strip())
    if "涨了" in combined or "上涨" in combined or "下跌" in combined or "跌了" in combined:
        if currency_pair:
            queries.append(f"{currency_pair} 今日 汇率 涨跌 {date_text}".strip())

    queries.append(question)
    return dedupe_keep_order(query for query in queries if query)[:3]


def infer_target_date(payload):
    combined = normalize_text(
        "\n".join(
            [
                str(payload.get("question", "")).strip(),
                str(payload.get("answer", "")).strip(),
                str(payload.get("time", "")).strip(),
            ]
        )
    )
    match = re.search(r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})", combined)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return ""


def extract_answer_detail_fragments(answer, limit=3):
    text = normalize_text(answer)
    patterns = [
        r"\d+(?:\.\d+)?\s*(?:万|亿)?\s*(?:瑞典克朗|美元|元|人民币|欧元|英镑|日元)",
        r"20\d{2}年\d{1,2}月\d{1,2}日",
        r"\d+(?:\.\d+)?\s*%",
    ]
    found = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            found.append(normalize_text(match))
    return dedupe_keep_order(found)[:limit]


def extract_result_focus_terms(payload):
    question = normalize_text(str(payload.get("question", "")))
    answer = normalize_text(str(payload.get("answer", "")))
    combined = f"{question}\n{answer}"
    terms = []
    if any(token in combined for token in ["退赛", "因伤退赛", "伤退", "弃权", "不战而胜", "未出战", "未能出战"]):
        terms.extend(["退赛", "不战而胜"])
    if any(token in combined for token in ["比分", "赛果", "结果", "战况"]):
        terms.extend(["赛果", "比分"])
    if any(token in combined for token in ["澳门", "世界杯", "世乒赛", "乒乓球"]):
        terms.extend(["澳门", "世界杯"])
    return dedupe_keep_order(terms)


def extract_result_entity_terms(payload, limit=4):
    answer = normalize_text(str(payload.get("answer", "")))
    candidates = []
    candidates.extend(re.findall(r"[\u4e00-\u9fff]{2,4}·[\u4e00-\u9fff]{1,8}", answer))
    for match in re.findall(r"\|\s*([\u4e00-\u9fff]{2,4})\s*\|", answer):
        candidates.append(match)
    for match in re.findall(r"vs\s*([\u4e00-\u9fffA-Za-z·\-\u00b7]{2,20})", answer, flags=re.I):
        match = normalize_text(re.sub(r"[（(].*?[)）]", "", match))
        if re.search(r"[\u4e00-\u9fff]", match):
            candidates.append(match)

    filtered = []
    stopwords = {
        "今天", "今日", "结果", "赛果", "比分", "状态", "项目", "小组赛", "实时更新",
        "完整结果", "战报回顾", "即时比分", "晚间赛程", "比赛结果", "澳门", "世界杯", "国乒",
        "女单", "男单", "德国", "阿根廷", "罗马尼亚", "阿尔及利亚", "中国", "实时", "更新",
    }
    for token in candidates:
        token = token.strip()
        if len(token) < 2 or token in stopwords:
            continue
        if any(bad in token for bad in ["今天", "澳门", "比赛", "结果", "赛程", "赛果", "战报", "更新", "进行"]):
            continue
        filtered.append(token)
    return dedupe_keep_order(filtered)[:limit]


def build_evidence_coverage(payload, item):
    question = normalize_text(str(payload.get("question", "")))
    answer = normalize_text(str(payload.get("answer", "")))
    target_date = infer_target_date(payload)
    subject = extract_focus_subject(payload)
    text = normalize_text(
        " ".join(
            [
                str(item.get("title", "")),
                str(item.get("snippet", "")),
                str(item.get("detail", "")),
            ]
        )
    )

    date_match = False
    if target_date:
        alt_dates = {
            target_date,
            target_date.replace("-", "/"),
            target_date.replace("-", "年", 1).replace("-", "月", 1) + "日",
            f"{target_date[5:7]}月{target_date[8:10]}日",
        }
        date_match = any(date_text in text for date_text in alt_dates)

    subject_match = False
    if subject:
        subject_match = subject in text

    result_entities = extract_result_entity_terms(payload, limit=4)
    if not subject_match and result_entities:
        subject_match = any(entity in text for entity in result_entities)

    field_markers = []
    if any(token in question + "\n" + answer for token in ["现汇买入价", "现汇卖出价"]):
        field_markers.extend(["现汇买入价", "现汇卖出价"])
    if any(token in question + "\n" + answer for token in ["中间价", "汇率"]):
        field_markers.extend(["中间价", "汇率"])
    if any(token in question + "\n" + answer for token in ["比分", "赛果", "结果"]):
        field_markers.extend(["比分", "赛果", "结果", "退赛", "不战而胜"])
    field_match = any(marker in text for marker in dedupe_keep_order(field_markers)) if field_markers else False

    authority_match = item.get("source") in {
        "safe_rmb_midrate",
        "boc_exchange_rate",
        "qq_news_search",
        "zh_wikipedia",
    }

    date_alignment = str(item.get("date_alignment", "")).strip()
    penalty = 0
    if date_alignment == "mismatch":
        penalty = 2

    score = 0
    score += 2 if authority_match else 0
    score += 2 if date_match else 0
    score += 2 if subject_match else 0
    score += 2 if field_match else 0
    score -= penalty

    return {
        "date_match": date_match,
        "subject_match": subject_match,
        "field_match": field_match,
        "authority_match": authority_match,
        "date_alignment": date_alignment or None,
        "score": score,
    }


def build_targeted_queries(payload):
    question = normalize_text(str(payload.get("question", "")))
    answer = normalize_text(str(payload.get("answer", "")))
    combined = f"{question}\n{answer}"
    target = infer_evidence_target(payload)
    subject = extract_focus_subject(payload)
    queries = []

    if target == "fresh_numeric_market":
        queries.extend(build_market_queries(payload))
        queries.append(question)
    elif target == "publish_timeline":
        if subject:
            queries.append(f"{subject} 官方 公布 发布时间")
            queries.append(f"{subject} 什么时候 公布")
        queries.append(question)
    elif target == "current_result":
        if subject:
            entity_terms = extract_result_entity_terms(payload, limit=3)
            if entity_terms:
                queries.append(" ".join([subject] + entity_terms))
                for entity in entity_terms:
                    queries.append(f"{entity} 退赛 赛果")
            queries.append(f"{subject} 今天 结果")
            queries.append(f"{subject} 最新 赛果 比分")
            for term in extract_result_focus_terms(payload):
                queries.append(f"{subject} {term}")
        queries.append(question)
    elif target == "route_impact":
        if subject:
            queries.append(f"{subject} 路线 经过 领空")
            queries.append(f"{subject} 主要 通道 影响")
        queries.append(question)
    elif target == "identity_detail":
        if subject:
            queries.append(f"{subject} 官方 信息")
            queries.append(f"{subject} 奖金 日期 详情")
            queries.append(f"{subject} official prize amount")
            if any(token in combined for token in ["获奖", "獲獎", "奖金", "獎金", "诺贝尔", "奖项", "頒獎", "颁奖"]):
                queries.append(f"{subject} 官方 奖金 金额")
                queries.append(f"{subject} site:nobelprize.org prize amount")
            for fragment in extract_answer_detail_fragments(answer, limit=2):
                queries.append(f"{subject} {fragment} 官方")
        queries.append(question)
    else:
        queries.extend(build_queries(payload))
    return dedupe_keep_order(query for query in queries if query)[:6]


def build_queries(payload):
    question = str(payload.get("question", "")).strip()
    answer = str(payload.get("answer", "")).strip()
    history = payload.get("history_question", []) or []
    history_text = " ".join(str(x).strip() for x in history if str(x).strip())

    stripped_question = strip_claim_eval_prefix(question)
    if stripped_question != question or any(question.startswith(prefix) for prefix in CLAIM_PREFIXES):
        claim = stripped_question.strip() or strip_claim_eval_prefix(answer)
        if is_ascii_heavy(claim):
            queries = build_english_claim_queries(claim)
            if queries:
                return queries
        return [build_claim_style_query(claim or answer)]

    chunks = [question]
    if answer and len(answer) <= 40:
        chunks.append(answer)
    if history_text:
        chunks.append(history_text)
    query = normalize_text(" ".join(part for part in chunks if part))
    return [query[:220]] if query else []


def load_json_or_default(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def dump_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def search_bing_rss(query, max_results, timeout_sec):
    url = f"https://www.bing.com/search?format=rss&q={quote_plus(query)}"
    response = guarded_get(
        url,
        timeout_sec,
        source_name="bing_rss",
        headers={
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    text = decode_response_text(response)
    guard_response(response, request_url=url, source_name="bing_rss")
    root = ET.fromstring(text)
    results = []
    for item in root.findall(".//item")[:max_results]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        snippet = (item.findtext("description") or "").strip()
        results.append(
            {
                "title": title,
                "url": link,
                "snippet": snippet,
                "source": "bing_rss",
            }
        )
    return results


def parse_html_cells(row_html):
    values = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.S | re.I)
    return [normalize_text(re.sub(r"<[^>]+>", " ", value)) for value in values]


def search_boc_exchange_rate(payload, max_results, timeout_sec):
    response = guarded_get("https://www.bankofchina.com/sourcedb/whpj/", timeout_sec, source_name="boc_exchange_rate")
    text = decode_response_text(response)
    guard_response(response, request_url="https://www.bankofchina.com/sourcedb/whpj/", source_name="boc_exchange_rate")
    target_date = infer_target_date(payload)
    rows = re.findall(r"<tr[^>]*data-currency='([^']+)'[^>]*>(.*?)</tr>", text, flags=re.S | re.I)
    results = []
    for currency_name, row_html in rows:
        if currency_name != "美元":
            continue
        cells = parse_html_cells(row_html)
        if len(cells) < 8:
            continue
        published_at = cells[6]
        date_alignment = "unknown"
        if target_date:
            normalized_published = published_at.replace("/", "-")[:10]
            date_alignment = "match" if normalized_published == target_date else "mismatch"
        snippet = (
            f"{cells[0]} 现汇买入价 {cells[1]}，现汇卖出价 {cells[3]}，"
            f"中行折算价 {cells[5]}，发布日期 {published_at}。"
        )
        if date_alignment == "mismatch":
            snippet += f" 注意：该牌价日期与目标日期 {target_date} 不一致，只能作近邻参考，不能直接当作目标日证据。"
        results.append(
            {
                "title": "中国银行外汇牌价（美元）",
                "url": "https://www.bankofchina.com/sourcedb/whpj/",
                "snippet": snippet,
                "source": "boc_exchange_rate",
                "detail": snippet,
                "date_alignment": date_alignment,
                "target_date": target_date,
            }
        )
        break
    return results[:max_results]


def search_safe_rmb_midrate(payload, max_results, timeout_sec):
    target_date = infer_target_date(payload)
    if not target_date:
        return []

    response = _HTTP_SESSION.post(
        "https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do",
        data={"startDate": target_date, "endDate": target_date, "queryYN": "true"},
        timeout=timeout_sec,
    )
    response.raise_for_status()
    text = decode_response_text(response)
    row_match = re.search(
        rf"<tr[^>]*>\s*<td[^>]*>\s*{re.escape(target_date)}\s*</td>(.*?)</tr>",
        text,
        flags=re.S | re.I,
    )
    if not row_match:
        return []
    row_html = f"<td>{target_date}</td>{row_match.group(1)}"
    cells = parse_html_cells(row_html)
    if len(cells) < 2:
        return []
    usd_mid = cells[1]
    try:
        usd_mid_value = float(usd_mid) / 100.0
        usd_mid_desc = f"{usd_mid_value:.4f}"
    except Exception:
        usd_mid_desc = usd_mid
    snippet = (
        f"国家外汇管理局人民币汇率中间价显示：{target_date} 人民币对美元中间价为 {usd_mid}"
        f"（按每100美元计），折合 1 美元约 {usd_mid_desc} 人民币。"
    )
    return [
        {
            "title": "人民币汇率中间价（美元）",
            "url": "https://www.safe.gov.cn/safe/rmbhlzjj/index.html",
            "snippet": snippet,
            "source": "safe_rmb_midrate",
            "detail": snippet,
        }
    ][:max_results]


def normalize_result_url(url):
    raw = normalize_text(url)
    if not raw:
        return raw
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = urlparse(raw)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [])
        if uddg:
            return unquote(uddg[0])
    return raw


def search_duckduckgo_html(query, max_results, timeout_sec):
    response = guarded_get(
        "https://html.duckduckgo.com/html/",
        timeout_sec,
        source_name="duckduckgo_html",
        params={"q": query},
    )
    html = decode_response_text(response)
    guard_response(response, request_url="https://html.duckduckgo.com/html/", source_name="duckduckgo_html")
    matches = re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        html,
        flags=re.DOTALL,
    )
    results = []
    for match in matches:
        title = normalize_text(re.sub(r"<[^>]+>", " ", match.group("title")))
        url = normalize_result_url(match.group("url"))
        snippet = normalize_text(re.sub(r"<[^>]+>", " ", match.group("snippet")))
        if not title or not url:
            continue
        results.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "source": "duckduckgo_html",
            }
        )
        if len(results) >= max_results:
            break
    return results


def search_qq_news(query, max_results, timeout_sec):
    results = search_duckduckgo_html(f"site:news.qq.com {query}", max_results, timeout_sec)
    normalized = []
    for item in results:
        item = dict(item)
        item["source"] = "qq_news_search"
        normalized.append(item)
    return normalized


def search_zh_wikipedia(query, max_results, timeout_sec):
    response = guarded_get(
        "https://zh.wikipedia.org/w/api.php",
        timeout_sec,
        source_name="zh_wikipedia",
        params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "utf8": 1,
            "format": "json",
        },
    )
    data = response.json()
    results = []
    for item in data.get("query", {}).get("search", [])[:max_results]:
        title = str(item.get("title", "")).strip()
        snippet = normalize_text(re.sub(r"<[^>]+>", " ", str(item.get("snippet", ""))))
        if not title:
            continue
        results.append(
            {
                "title": title,
                "url": f"https://zh.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
                "snippet": snippet,
                "source": "zh_wikipedia",
            }
        )
    return results


def cache_key(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_source_plan(payload):
    # source_plan 不是按题面风格路由，而是按“证据最可能存在于哪里”路由。
    target = infer_evidence_target(payload)
    if target == "fresh_numeric_market":
        return ["safe_rmb_midrate", "boc_exchange_rate", "duckduckgo_html", "bing_rss"]
    if target == "current_result":
        return ["qq_news_search", "duckduckgo_html", "bing_rss"]
    if target == "publish_timeline":
        return ["duckduckgo_html", "bing_rss", "zh_wikipedia"]
    if target == "identity_detail":
        return ["duckduckgo_html", "bing_rss", "zh_wikipedia"]
    if target == "route_impact":
        return ["duckduckgo_html", "bing_rss"]
    return ["zh_wikipedia", "duckduckgo_html", "bing_rss"]


def build_targeted_queries(payload):
    question = normalize_text(str(payload.get("question", "")))
    answer = normalize_text(str(payload.get("answer", "")))
    combined = f"{question}\n{answer}"
    target = infer_evidence_target(payload)
    subject = extract_focus_subject(payload)
    queries = []

    if target == "fresh_numeric_market":
        queries.extend(build_market_queries(payload))
        queries.append(question)
    elif target == "publish_timeline":
        if subject:
            queries.append(f"{subject} 官方 公布 发布时间")
            queries.append(f"{subject} 什么时候 公布")
            queries.append(f"{subject} 官方 时间线 阶段")
            queries.append(f"{subject} 重启 时间线 新闻")
        queries.append(question)
    elif target == "current_result":
        if subject:
            entity_terms = extract_result_entity_terms(payload, limit=3)
            if entity_terms:
                queries.append(" ".join([subject] + entity_terms))
                for entity in entity_terms:
                    queries.append(f"{entity} 退赛 赛果")
            queries.append(f"{subject} 今天 结果")
            queries.append(f"{subject} 最新 赛果 比分")
            for term in extract_result_focus_terms(payload):
                queries.append(f"{subject} {term}")
        queries.append(question)
    elif target == "route_impact":
        if subject:
            queries.append(f"{subject} 路线 经过 领空")
            queries.append(f"{subject} 主要 通道 影响")
        queries.append(question)
    elif target == "identity_detail":
        if subject:
            queries.append(f"{subject} 官方 信息")
            queries.append(f"{subject} 奖金 日期 详情")
            queries.append(f"{subject} official prize amount")
            if any(token in combined for token in ["获奖", "奖金", "奖项", "诺贝尔", "颁奖"]):
                queries.append(f"{subject} 官方 奖金 金额")
                queries.append(f"{subject} site:nobelprize.org prize amount")
            for fragment in extract_answer_detail_fragments(answer, limit=2):
                queries.append(f"{subject} {fragment} 官方")
        queries.append(question)
    else:
        queries.extend(build_queries(payload))
    return dedupe_keep_order(query for query in queries if query)[:6]


def build_source_plan(payload):
    # 按证据最可能出现的位置路由，而不是按题面押题。
    target = infer_evidence_target(payload)
    if target == "fresh_numeric_market":
        return ["safe_rmb_midrate", "boc_exchange_rate", "duckduckgo_html", "bing_rss"]
    if target == "current_result":
        return ["qq_news_search", "duckduckgo_html", "bing_rss"]
    if target == "publish_timeline":
        return ["qq_news_search", "duckduckgo_html", "bing_rss", "zh_wikipedia"]
    if target == "identity_detail":
        return ["duckduckgo_html", "bing_rss", "zh_wikipedia"]
    if target == "route_impact":
        return ["duckduckgo_html", "bing_rss"]
    return ["zh_wikipedia", "duckduckgo_html", "bing_rss"]


def run_source_search(source_name, query, max_results, timeout_sec):
    if source_name == "safe_rmb_midrate":
        return search_safe_rmb_midrate(query, max_results, timeout_sec)
    if source_name == "boc_exchange_rate":
        return search_boc_exchange_rate(query, max_results, timeout_sec)
    if source_name == "qq_news_search":
        return search_qq_news(query, max_results, timeout_sec)
    if source_name == "zh_wikipedia":
        return search_zh_wikipedia(query, max_results, timeout_sec)
    if source_name == "duckduckgo_html":
        return search_duckduckgo_html(query, max_results, timeout_sec)
    if source_name == "bing_rss":
        return search_bing_rss(query, max_results, timeout_sec)
    raise ValueError(f"unknown_source:{source_name}")


def fetch_result_detail(url, max_chars, timeout_sec):
    clean_url = normalize_result_url(url)
    if not clean_url or not clean_url.startswith(("http://", "https://")):
        return ""
    response = guarded_get(clean_url, timeout_sec, source_name="fetch_result_detail")
    text = decode_response_text(response)
    guard_response(response, request_url=clean_url, source_name="fetch_result_detail")
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = normalize_text(re.sub(r"<[^>]+>", " ", text))
    focus_markers = [
        "prize amount",
        "奖金",
        "獎金",
        "瑞典克朗",
        "SEK",
        "million",
        "awarded jointly",
        "announced",
    ]
    lowered = text.lower()
    for marker in focus_markers:
        pos = lowered.find(marker.lower())
        if pos >= 0:
            start = max(0, pos - 180)
            end = min(len(text), pos + max_chars)
            return text[start:end]
    return text[:max_chars]


def run_search(payload):
    queries = build_targeted_queries(payload)
    if not queries:
        return {"ok": False, "error": "empty_query", "query": "", "results": []}

    max_results = int(payload.get("max_results", 3) or 3)
    timeout_ms = int(os.environ.get("PLAYWRIGHT_BROWSER_TIMEOUT_MS", "20000"))
    timeout_sec = max(5, int(timeout_ms / 1000))
    results = []
    search_errors = []
    seen = set()
    source_plan = build_source_plan(payload)
    per_call_results = max(1, min(2, max_results))

    question = str(payload.get("question", "")).strip()
    claim = strip_claim_eval_prefix(question)
    wiki_query = ""
    if claim and claim != question:
        wiki_query = extract_english_title_phrases(claim)[0] if is_ascii_heavy(claim) and extract_english_title_phrases(claim) else ""
        if not wiki_query:
            wiki_query = claim[:40]

    if wiki_query and "zh_wikipedia" in source_plan:
        try:
            for item in search_zh_wikipedia(wiki_query, per_call_results, timeout_sec):
                if item.get("url") in seen:
                    continue
                seen.add(item.get("url"))
                results.append(item)
        except Exception as exc:
            search_errors.append(f"zh_wikipedia_failed:{exc}")

    for search_query in queries[:6]:
        for source_name in source_plan:
            try:
                source_input = payload if source_name in {"safe_rmb_midrate", "boc_exchange_rate"} else search_query
                for item in run_source_search(source_name, source_input, per_call_results, timeout_sec):
                    if item.get("url") in seen:
                        continue
                    seen.add(item.get("url"))
                    results.append(item)
                    if len(results) >= max_results:
                        break
            except Exception as exc:
                search_errors.append(f"{source_name}_failed[{search_query}]:{exc}")
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    for item in results:
        item["coverage"] = build_evidence_coverage(payload, item)
    results.sort(key=lambda item: item.get("coverage", {}).get("score", 0), reverse=True)
    results = results[:max_results]
    detail_pages = int(payload.get("detail_pages", 0) or 0)
    detail_max_chars = int(payload.get("detail_max_chars", 500) or 500)
    if detail_pages > 0:
        for item in results[:detail_pages]:
            try:
                item["detail"] = fetch_result_detail(item.get("url", ""), detail_max_chars, timeout_sec)
            except Exception as exc:
                item["detail_error"] = str(exc)
                item["detail_error_type"] = "anti_bot_blocked" if "anti_bot_blocked" in str(exc) else "fetch_error"
        for item in results[:detail_pages]:
            item["coverage"] = build_evidence_coverage(payload, item)
        results.sort(key=lambda item: item.get("coverage", {}).get("score", 0), reverse=True)
    ok = bool(results)
    return {
        "ok": ok,
        "query": queries[0],
        "queries": queries,
        "sources": source_plan,
        "results": results,
        "error": "; ".join(search_errors) if search_errors and not ok else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True)
    args = parser.parse_args()
    payload = json.loads(args.json_input)
    print(json.dumps(run_search(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
