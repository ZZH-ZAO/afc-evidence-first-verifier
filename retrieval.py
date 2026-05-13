# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import hashlib
import os
import re
import time
from html import unescape
from io import BytesIO
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, unquote, urlparse, urljoin

import requests
from afc_route_markers import (
    ROUTE_DIRECTIONAL_MARKERS,
    ROUTE_ENTITY_QUERY_STOPWORDS,
    ROUTE_MEDIUM_HINTS,
    ROUTE_OBJECT_MARKERS,
    ROUTE_STRICT_OBJECT_MARKERS,
    ROUTE_QUERY_STOPWORDS,
    ROUTE_RELATION_MARKERS,
)
from evidence_contract import (
    infer_missing_required_slots as shared_infer_missing_required_slots,
    required_slot_profile_for_mode as shared_required_slot_profile_for_mode,
    slot_bucket_aliases,
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

try:
    from search_providers import search_with_provider
except Exception:
    search_with_provider = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        PdfReader = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

_HTTP = requests.Session()
_HTTP.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
_SITEMAP_CACHE: Dict[str, List[str]] = {}
_MEM_CACHE: Dict[str, Any] = {}
if load_dotenv:
    load_dotenv()
CACHE_DIR = os.environ.get("V2_CACHE_DIR") or os.path.join(os.path.dirname(__file__), ".cache_v2")
USE_CACHE = os.environ.get("V2_DISABLE_CACHE", "0").lower() not in {"1", "true", "yes"}
FETCH_DETAILS_PER_CLAIM = int(os.environ.get("V2_FETCH_DETAILS_PER_CLAIM", "2"))
MAX_QUERIES_PER_CLAIM = int(os.environ.get("V2_MAX_QUERIES_PER_CLAIM", "3"))
ENABLE_CONTRASTIVE_RETRIEVAL = os.environ.get("V2_ENABLE_CONTRASTIVE_RETRIEVAL", "0").lower() in {"1", "true", "yes"}
ENABLE_ATOMIC_CLAIM_RETRIEVAL = os.environ.get("V2_ENABLE_ATOMIC_CLAIM_RETRIEVAL", "1").lower() in {"1", "true", "yes"}
ATOMIC_CLAIM_QUERY_LIMIT = int(os.environ.get("V2_ATOMIC_CLAIM_QUERY_LIMIT", "1"))
ENABLE_BING_HTML = os.environ.get("V2_ENABLE_BING_HTML", "0").lower() in {"1", "true", "yes"}
ENABLE_DUCKDUCKGO = os.environ.get("V2_ENABLE_DUCKDUCKGO", "0").lower() in {"1", "true", "yes"}
ENABLE_PLAYWRIGHT = os.environ.get("V2_ENABLE_PLAYWRIGHT", "1").lower() in {"1", "true", "yes"}
PLAYWRIGHT_MAX_QUERIES_PER_CLAIM = int(os.environ.get("V2_PLAYWRIGHT_MAX_QUERIES_PER_CLAIM", "1"))
SOGOU_TIMEOUT_CAP_SEC = int(os.environ.get("V2_SOGOU_TIMEOUT_CAP_SEC", "4"))
PLAYWRIGHT_TIMEOUT_CAP_SEC = int(os.environ.get("V2_PLAYWRIGHT_TIMEOUT_CAP_SEC", "6"))
ENABLE_QA_QUERIES = os.environ.get("V2_ENABLE_QA_QUERIES", "1").lower() in {"1", "true", "yes"}
QA_QUERY_LIMIT = int(os.environ.get("V2_QA_QUERY_LIMIT", "2"))
ENABLE_QA_ENHANCED_SOURCES = os.environ.get("V2_ENABLE_QA_ENHANCED_SOURCES", "1").lower() in {"1", "true", "yes"}
ENABLE_QA_BING_HTML = os.environ.get("V2_ENABLE_QA_BING_HTML", "1").lower() in {"1", "true", "yes"}
PLAYWRIGHT_AFTER_SEARCH = os.environ.get("V2_PLAYWRIGHT_AFTER_SEARCH", "1").lower() in {"1", "true", "yes"}
ENABLE_ADAPTIVE_SOURCE_FALLBACK = os.environ.get("V2_ENABLE_ADAPTIVE_SOURCE_FALLBACK", "0").lower() in {"1", "true", "yes"}
ADAPTIVE_SOURCE_FALLBACK_LIMIT = int(os.environ.get("V2_ADAPTIVE_SOURCE_FALLBACK_LIMIT", "1"))
ENABLE_SOURCE_TOP1_PRECHECK = os.environ.get("V2_ENABLE_SOURCE_TOP1_PRECHECK", "0").lower() in {"1", "true", "yes"}
ENABLE_SOURCE_HEALTH_REORDER = os.environ.get("V2_ENABLE_SOURCE_HEALTH_REORDER", "1").lower() in {"1", "true", "yes"}
ENABLE_TRUSTED_FILTER_DEEPEN = os.environ.get("V2_ENABLE_TRUSTED_FILTER_DEEPEN", "0").lower() in {"1", "true", "yes"}
ENABLE_PAGE_UTILITY_LLM_RERANK = os.environ.get("V2_ENABLE_PAGE_UTILITY_LLM_RERANK", "1").lower() in {"1", "true", "yes"}
PAGE_UTILITY_LLM_MAX_ITEMS_PER_CLAIM = int(os.environ.get("V2_PAGE_UTILITY_LLM_MAX_ITEMS_PER_CLAIM", "3"))
PAGE_UTILITY_LLM_MIN_RETENTION_SCORE = int(os.environ.get("V2_PAGE_UTILITY_LLM_MIN_RETENTION_SCORE", "35"))
OFFICIAL_INNER_LINK_MAX_PER_CLAIM = int(os.environ.get("V2_OFFICIAL_INNER_LINK_MAX_PER_CLAIM", "2"))
PAGE_UTILITY_LLM_MIN_SOURCE_QUALITY = int(os.environ.get("V2_PAGE_UTILITY_LLM_MIN_SOURCE_QUALITY", "25"))
PAGE_UTILITY_LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4.1")
PAGE_UTILITY_LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0"))
PAGE_UTILITY_LLM_MAX_TOKENS = int(os.environ.get("V2_PAGE_UTILITY_LLM_MAX_TOKENS", "500"))
PAGE_UTILITY_LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "45"))
PAGE_UTILITY_LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
PAGE_UTILITY_LLM_BASE_URL = os.environ.get("API_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
ENABLE_PAGE_SHAPE_LLM_BRIDGE = os.environ.get("V2_ENABLE_PAGE_SHAPE_LLM_BRIDGE", "1").lower() in {"1", "true", "yes"}

_PAGE_UTILITY_LLM_CLIENT = None

SOURCE_TYPES = {
    "official": {".gov", "gov.cn", ".edu", "who.int", "nih.gov", "wto.org", "imf.org", "worldbank.org", "sec.gov", "fda.gov", "ec.europa.eu", "europa.eu"},
    "encyclopedia": {"wikipedia.org", "baike.baidu.com"},
    "news": {"news.", "reuters.com", "apnews.com", "bbc.com", "cnn.com", "nytimes.com", "washingtonpost.com", "theguardian.com", "ap.org", "pbs.org", "yahoo.com", "msn.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com"},
    "forum": {"reddit.com", "zhihu.com", "tieba.baidu.com", "x.com"},
}

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


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


ANTI_BOT_STATUS_CODES = {401, 403, 406, 409, 412, 418, 429, 451, 503}
ANTI_BOT_URL_HINTS = (
    "captcha",
    "challenge",
    "verify",
    "security-check",
    "security_check",
    "bot-check",
    "robot",
    "blocked",
)
ANTI_BOT_TEXT_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"captcha|verify (?:you are )?human|security check|access denied|unusual traffic|are you a robot", flags=re.I), "challenge_page"),
    (re.compile(r"cloudflare|cf-chl|attention required", flags=re.I), "cloudflare_challenge"),
    (re.compile(r"too many requests|rate limit|temporarily blocked|request rate", flags=re.I), "rate_limit_page"),
    (re.compile(r"人机验证|验证码|访问频繁|访问过于频繁|操作过于频繁|安全验证|滑动验证|请完成验证|异常流量|机器人", flags=re.I), "cn_challenge_page"),
]


class AntiBotBlockedError(RuntimeError):
    def __init__(
        self,
        url: str = "",
        source_name: str = "",
        status_code: int = 0,
        reasons: Optional[List[str]] = None,
    ) -> None:
        self.url = normalize_text(url)
        self.source_name = normalize_text(source_name)
        self.status_code = int(status_code or 0)
        self.reasons = [str(item) for item in (reasons or []) if str(item)]
        detail = ",".join(self.reasons) if self.reasons else "anti_bot_blocked"
        parts = [f"anti_bot_blocked:{detail}"]
        if self.source_name:
            parts.append(f"source={self.source_name}")
        if self.status_code:
            parts.append(f"status={self.status_code}")
        if self.url:
            parts.append(f"url={self.url}")
        super().__init__(" ".join(parts))


def anti_bot_signal_reasons(text: str, url: str = "") -> List[str]:
    sample = normalize_text(text)[:12000]
    lowered_url = normalize_text(url).lower()
    reasons: List[str] = []
    if any(hint in lowered_url for hint in ANTI_BOT_URL_HINTS):
        reasons.append("challenge_url")
    for pattern, reason in ANTI_BOT_TEXT_PATTERNS:
        if pattern.search(sample):
            reasons.append(reason)
    return dedupe_keep_order(reasons)


def exception_looks_like_anti_bot(exc: Exception) -> bool:
    message = normalize_text(str(exc)).lower()
    if not message:
        return False
    anti_bot_terms = [
        "anti_bot_blocked",
        "captcha",
        "challenge",
        "cloudflare",
        "verify human",
        "access denied",
        "too many requests",
        "rate limit",
        "人机验证",
        "验证码",
        "访问频繁",
        "安全验证",
        "异常流量",
        "403",
        "429",
    ]
    return any(term in message for term in anti_bot_terms)


def response_text_for_guard(response: requests.Response) -> str:
    content_type = normalize_text(str(response.headers.get("Content-Type") or "")).lower()
    if not content_type or any(marker in content_type for marker in ("html", "text", "xml", "json")):
        return decode_response_text(response)
    if response.status_code in ANTI_BOT_STATUS_CODES:
        return decode_response_text(response)
    return ""


def ensure_response_not_blocked(
    response: requests.Response,
    request_url: str = "",
    source_name: str = "",
    decoded_text: str = "",
) -> None:
    url = normalize_text(str(response.url or request_url or ""))
    reasons: List[str] = []
    if int(response.status_code or 0) in ANTI_BOT_STATUS_CODES:
        reasons.append(f"http_{int(response.status_code)}")
    sample = decoded_text or response_text_for_guard(response)
    reasons.extend(anti_bot_signal_reasons(sample, url))
    reasons = dedupe_keep_order(reasons)
    if reasons:
        raise AntiBotBlockedError(url=url, source_name=source_name, status_code=int(response.status_code or 0), reasons=reasons)


def guarded_http_get(
    url: str,
    timeout_sec: int = 10,
    headers: Optional[Dict[str, str]] = None,
    source_name: str = "",
) -> requests.Response:
    response = _HTTP.get(url, timeout=timeout_sec, headers=headers)
    ensure_response_not_blocked(response, request_url=url, source_name=source_name)
    response.raise_for_status()
    return response


def fetch_with_playwright(url: str, timeout_sec: int = 10, return_html: bool = False) -> str:
    if not ENABLE_PLAYWRIGHT or sync_playwright is None or not url:
        return ""
    with sync_playwright() as playwright:
        launch_kwargs: Dict[str, Any] = {"headless": True}
        chrome_path = os.environ.get("V2_PLAYWRIGHT_CHROME") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if os.path.exists(chrome_path):
            launch_kwargs["executable_path"] = chrome_path
        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            locale="zh-CN",
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=max(3000, timeout_sec * 1000))
            try:
                page.wait_for_load_state("networkidle", timeout=max(1500, timeout_sec * 400))
            except Exception:
                pass
            body_text = normalize_text(page.locator("body").inner_text(timeout=max(1000, timeout_sec * 120))) if page.locator("body").count() else ""
            block_reasons = anti_bot_signal_reasons(body_text, page.url or url)
            if block_reasons:
                raise AntiBotBlockedError(url=page.url or url, source_name="playwright_fetch", reasons=block_reasons)
            if return_html:
                return page.content() or ""
            return body_text
        finally:
            context.close()
            browser.close()


def merge_fetch_trace(trace: Optional[Dict[str, Any]], **kwargs: Any) -> None:
    if not isinstance(trace, dict):
        return
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, bool):
            trace[key] = bool(trace.get(key)) or value
        elif isinstance(value, int):
            trace[key] = int(trace.get(key, 0) or 0) + value
        elif isinstance(value, list):
            existing = trace.setdefault(key, [])
            if isinstance(existing, list):
                existing.extend(value)
            else:
                trace[key] = list(value)
        else:
            trace[key] = value


def increment_named_counter(bucket: Dict[str, Any], field: str, key: str) -> None:
    if not key:
        return
    counters = bucket.setdefault(field, {})
    counters[key] = int(counters.get(key, 0) or 0) + 1


def apply_detail_fetch_trace(
    stats: Dict[str, Any],
    item: Dict[str, Any],
    trace: Optional[Dict[str, Any]],
    source_name: str = "",
) -> None:
    if not isinstance(trace, dict) or not trace:
        return
    bucket = source_pollution_bucket(stats, source_name) if source_name else {}
    if trace.get("playwright_used"):
        stats["playwright_used"] = int(stats.get("playwright_used", 0) or 0) + 1
        if bucket:
            bucket["playwright_used"] = int(bucket.get("playwright_used", 0) or 0) + 1
    if trace.get("playwright_rescued"):
        stats["playwright_rescued"] = int(stats.get("playwright_rescued", 0) or 0) + 1
        item["playwright_rescued"] = True
        if bucket:
            bucket["playwright_rescued"] = int(bucket.get("playwright_rescued", 0) or 0) + 1
    if trace.get("playwright_rescue_role"):
        role = str(trace.get("playwright_rescue_role") or "")
        if role:
            stats.setdefault("playwright_roles", []).append(role)
            item["playwright_rescue_role"] = role
    if trace.get("playwright_rescue_trigger"):
        trigger = str(trace.get("playwright_rescue_trigger") or "")
        if trigger:
            stats.setdefault("playwright_reasons", []).append(trigger)
            item["playwright_rescue_trigger"] = trigger
    if trace.get("playwright_rescue_skipped_by_policy"):
        stats.setdefault("playwright_skipped_reasons", []).append(str(trace.get("rescue_skip_reason") or "detail_rescue_budget_exhausted"))
        item["playwright_rescue_skipped_by_policy"] = True
        item["rescue_skip_reason"] = str(trace.get("rescue_skip_reason") or "detail_rescue_budget_exhausted")
    if trace.get("environment_block_reason"):
        item["environment_block_reason"] = str(trace.get("environment_block_reason") or "")
        increment_named_counter(stats, "environment_block_reasons", str(trace.get("environment_block_reason") or ""))
        if bucket:
            increment_named_counter(bucket, "environment_block_reasons", str(trace.get("environment_block_reason") or ""))
    if trace.get("detail_fetch_path"):
        detail_fetch_path = str(trace.get("detail_fetch_path") or "")
        item["detail_fetch_path"] = detail_fetch_path
        increment_named_counter(stats, "detail_fetch_paths", detail_fetch_path)
        if bucket:
            increment_named_counter(bucket, "detail_fetch_paths", detail_fetch_path)
            if "playwright_failed" in detail_fetch_path:
                bucket["playwright_failed"] = int(bucket.get("playwright_failed", 0) or 0) + 1
    if trace.get("playwright_block_reasons"):
        item["playwright_block_reasons"] = [str(value) for value in trace.get("playwright_block_reasons", []) if str(value)][:6]
    if trace.get("request_block_reasons"):
        item["request_block_reasons"] = [str(value) for value in trace.get("request_block_reasons", []) if str(value)][:6]
    if trace.get("playwright_used"):
        item["playwright_used"] = True


def record_detail_fetch_failure(
    stats: Dict[str, Any],
    item: Dict[str, Any],
    exc: Exception,
    source_name: str = "",
) -> None:
    stats["detail_errors"] = int(stats.get("detail_errors", 0) or 0) + 1
    stats["detail_read_failed"] = int(stats.get("detail_read_failed", 0) or 0) + 1
    item["detail_error"] = str(exc)
    item["detail_read_failed"] = True
    if source_name:
        bucket = source_pollution_bucket(stats, source_name)
        bucket["detail_read_failed"] = int(bucket.get("detail_read_failed", 0) or 0) + 1
    if exception_looks_like_anti_bot(exc):
        item["detail_error_type"] = "anti_bot_blocked"
        current_reason = str(item.get("environment_block_reason") or "")
        if not current_reason:
            item["environment_block_reason"] = "requests_blocked_playwright_failed"
        stats["detail_anti_bot_errors"] = int(stats.get("detail_anti_bot_errors", 0) or 0) + 1
    else:
        item["detail_error_type"] = "fetch_error"


def looks_like_mojibake(text: str) -> bool:
    sample = text or ""
    if not sample:
        return False
    latin1_like = len(re.findall(r"[\u00c0-\u00ff]", sample))
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", sample))
    if latin1_like >= 8 and (cjk_count == 0 or latin1_like >= cjk_count * 2):
        return True
    mojibake_markers = ["Ã", "Â", "æ", "å", "ä", "ç", "é", "ê", "ë"]
    marker_hits = sum(sample.count(marker) for marker in mojibake_markers)
    return marker_hits >= 6 and cjk_count == 0


def repair_mojibake_text(text: str) -> str:
    sample = text or ""
    if not looks_like_mojibake(sample):
        return sample
    for source_encoding, target_encoding in [("latin-1", "utf-8"), ("cp1252", "utf-8")]:
        try:
            repaired = sample.encode(source_encoding, errors="ignore").decode(target_encoding, errors="ignore")
        except Exception:
            continue
        repaired = repaired or ""
        if not repaired:
            continue
        if not looks_like_mojibake(repaired):
            return repaired
        repaired_cjk = len(re.findall(r"[\u4e00-\u9fff]", repaired))
        original_cjk = len(re.findall(r"[\u4e00-\u9fff]", sample))
        if repaired_cjk > original_cjk:
            return repaired
    return sample


def decode_response_text(response: requests.Response) -> str:
    encoding = response.encoding
    if not encoding or encoding.lower() in {"iso-8859-1", "latin-1"}:
        encoding = response.apparent_encoding or "utf-8"
    try:
        return repair_mojibake_text(response.content.decode(encoding, errors="ignore"))
    except Exception:
        return repair_mojibake_text(response.text)


def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        item = normalize_text(item)
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def top_count_items(data: Any, limit: int = 3) -> Dict[str, int]:
    if not isinstance(data, dict):
        return {}
    items = sorted(
        [(str(key), int(value or 0)) for key, value in data.items() if normalize_text(str(key))],
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )
    return {key: value for key, value in items[:limit]}


def source_family_name(source_name: str) -> str:
    text = normalize_text(str(source_name)).lower()
    if not text:
        return "other"
    if "news" in text and "rss" in text:
        return "news_rss"
    if text.endswith("_html") or "_html" in text:
        return "html"
    if text.endswith("_rss") or "_rss" in text:
        return "rss"
    if "sitemap" in text:
        return "sitemap"
    return "other"


def source_is_authority_or_news(source_name: str) -> bool:
    text = normalize_text(str(source_name)).lower()
    return text in {"domain_sitemap", "bing_rss", "bing_news_zh_rss", "bing_news_rss"} or source_family_name(text) in {"news_rss", "rss", "sitemap"}


def source_is_non_sogou_html(source_name: str) -> bool:
    text = normalize_text(str(source_name)).lower()
    return text in {"bing_html", "duckduckgo_html"}


def query_needs_authority_pair(
    query_goal: str,
    query_family_role: str,
    source_intent: Optional[Dict[str, Any]] = None,
) -> bool:
    evidence_mode = effective_evidence_mode(source_intent or {}, str((source_intent or {}).get("evidence_mode") or ""))
    return query_family_role in {"closure", "distinguish", "refute"} or (
        query_goal == "verification_question"
        and evidence_mode in {"numeric_fact", "date_fact", "schedule_fact", "route_fact", "event_result"}
    )


def source_order_trace_entry(stage: str, sources: List[str], previous_sources: Optional[List[str]] = None, reason: str = "") -> Dict[str, Any]:
    prev = [str(item) for item in (previous_sources or []) if str(item)]
    curr = [str(item) for item in (sources or []) if str(item)]
    return {
        "stage": stage,
        "sources": curr[:10],
        "changed": curr != prev if prev else False,
        "reason": reason,
    }


def note_source_order_stage(
    query_item: Optional[Dict[str, Any]],
    stage: str,
    sources: List[str],
    previous_sources: Optional[List[str]] = None,
    reason: str = "",
) -> None:
    if not isinstance(query_item, dict):
        return
    trace = query_item.setdefault("_source_order_trace", [])
    if not isinstance(trace, list):
        trace = []
        query_item["_source_order_trace"] = trace
    trace.append(source_order_trace_entry(stage, sources, previous_sources, reason))


def preserved_authority_pair(selected_sources: List[str]) -> bool:
    has_authority_or_news = any(source_is_authority_or_news(source_name) for source_name in selected_sources)
    has_non_sogou_html = any(source_is_non_sogou_html(source_name) for source_name in selected_sources)
    return has_authority_or_news and has_non_sogou_html


def summarize_source_recall_diagnosis(
    stats: Dict[str, Any],
    raw_results: int,
    filtered_results: int,
    web_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    source_pollution = stats.get("source_pollution_stats") if isinstance(stats.get("source_pollution_stats"), dict) else {}
    family_rollup: Dict[str, Dict[str, int]] = {}
    raw_sources: List[str] = []
    error_sources: List[str] = []
    anti_bot_sources: List[str] = []
    for source_name, bucket in source_pollution.items():
        if not isinstance(bucket, dict):
            continue
        family = source_family_name(source_name)
        target = family_rollup.setdefault(
            family,
            {"calls": 0, "raw": 0, "kept": 0, "filtered": 0, "errors": 0, "anti_bot_blocks": 0},
        )
        for key in ["calls", "raw", "kept", "filtered", "errors", "anti_bot_blocks"]:
            target[key] += int(bucket.get(key, 0) or 0)
        if int(bucket.get("raw", 0) or 0) > 0:
            raw_sources.append(str(source_name))
        if int(bucket.get("errors", 0) or 0) > 0:
            error_sources.append(str(source_name))
        if int(bucket.get("anti_bot_blocks", 0) or 0) > 0:
            anti_bot_sources.append(str(source_name))

    html_raw = int((family_rollup.get("html") or {}).get("raw", 0) or 0)
    html_calls = int((family_rollup.get("html") or {}).get("calls", 0) or 0)
    html_errors = int((family_rollup.get("html") or {}).get("errors", 0) or 0)
    news_raw = int((family_rollup.get("news_rss") or {}).get("raw", 0) or 0)
    news_calls = int((family_rollup.get("news_rss") or {}).get("calls", 0) or 0)
    news_errors = int((family_rollup.get("news_rss") or {}).get("errors", 0) or 0)
    rss_raw = int((family_rollup.get("rss") or {}).get("raw", 0) or 0)

    high_priority_empty = (html_calls > 0 or news_calls > 0) and (html_raw + news_raw) <= 0
    provider_error_present = (html_errors + news_errors) > 0 or bool(error_sources) or bool(anti_bot_sources)
    fallback_only_raw = raw_results > 0 and (html_raw + news_raw) <= 0 and rss_raw > 0
    all_filtered = raw_results > 0 and filtered_results >= raw_results and not web_items

    if raw_results <= 0 and anti_bot_sources:
        barrier_stage = "provider_error_or_block"
        barrier_reason = "高优先检索源疑似被反爬或安全校验拦截，导致原始结果没有稳定返回"
    elif raw_results <= 0 and provider_error_present:
        barrier_stage = "provider_error_or_block"
        barrier_reason = "高优先检索源存在错误或阻塞，且没有召回任何原始结果"
    elif raw_results <= 0 and high_priority_empty:
        barrier_stage = "high_priority_sources_no_raw"
        barrier_reason = "高优先 HTML/News 检索源已执行，但没有返回原始结果"
    elif fallback_only_raw and all_filtered:
        barrier_stage = "fallback_only_raw_then_filtered"
        barrier_reason = "只有 fallback 弱源返回结果，且这些结果全部在页面保留阶段被过滤"
    elif fallback_only_raw:
        barrier_stage = "fallback_only_raw"
        barrier_reason = "只有 fallback 弱源返回结果，高优先检索源没有有效召回"
    elif all_filtered:
        barrier_stage = "raw_but_all_filtered"
        barrier_reason = "已有原始结果返回，但全部死在页面保留或质量过滤"
    elif raw_results <= 0:
        barrier_stage = "no_source_return"
        barrier_reason = "所有已执行检索源都没有返回原始结果"
    else:
        barrier_stage = "mixed_or_ready"
        barrier_reason = "当前不是单一 source recall 阻塞"

    return {
        "barrier_stage": barrier_stage,
        "barrier_reason": barrier_reason,
        "high_priority_empty": high_priority_empty,
        "provider_error_present": provider_error_present,
        "anti_bot_present": bool(anti_bot_sources),
        "fallback_only_raw": fallback_only_raw,
        "family_rollup": family_rollup,
        "raw_sources": dedupe_keep_order(raw_sources)[:8],
        "error_sources": dedupe_keep_order(error_sources)[:8],
        "anti_bot_sources": dedupe_keep_order(anti_bot_sources)[:8],
    }


def source_family_recall_state(source_recall_diagnosis: Dict[str, Any], family: str) -> str:
    family_rollup = (
        source_recall_diagnosis.get("family_rollup")
        if isinstance(source_recall_diagnosis.get("family_rollup"), dict)
        else {}
    )
    bucket = family_rollup.get(family) if isinstance(family_rollup.get(family), dict) else {}
    calls = int(bucket.get("calls", 0) or 0)
    raw = int(bucket.get("raw", 0) or 0)
    kept = int(bucket.get("kept", 0) or 0)
    errors = int(bucket.get("errors", 0) or 0)
    anti_bot_blocks = int(bucket.get("anti_bot_blocks", 0) or 0)
    if calls <= 0:
        return "not_used"
    if anti_bot_blocks > 0 and raw <= 0:
        return "blocked"
    if errors > 0 and raw <= 0:
        return "provider_error"
    if raw <= 0:
        return "no_raw"
    if kept <= 0:
        return "raw_but_filtered"
    return "raw_and_kept"


def retrieval_responsibility_boundary(
    raw_results: int,
    web_items: List[Dict[str, Any]],
    strong_items: List[Dict[str, Any]],
    direct_items: List[Dict[str, Any]],
    source_recall_diagnosis: Dict[str, Any],
    readiness_promotion_used: int = 0,
    answer_candidate_total: int = 0,
) -> Dict[str, Any]:
    barrier_stage = str(source_recall_diagnosis.get("barrier_stage") or "")
    barrier_reason = str(source_recall_diagnosis.get("barrier_reason") or "")
    high_priority_empty = bool(source_recall_diagnosis.get("high_priority_empty"))
    fallback_only_raw = bool(source_recall_diagnosis.get("fallback_only_raw"))
    family_states = {
        family: source_family_recall_state(source_recall_diagnosis, family)
        for family in ("html", "news_rss", "rss")
    }
    if raw_results <= 0:
        responsibility_layer = "provider_recall"
        stop_stage = barrier_stage or "provider_empty_recall"
        reason = barrier_reason or "检索源没有召回原始结果"
    elif not web_items:
        responsibility_layer = "retrieval_filter"
        stop_stage = "all_results_filtered"
        reason = "已有原始结果，但页面保留阶段没有留下可用网页"
    elif readiness_promotion_used > 0:
        responsibility_layer = "retrieval_readiness"
        stop_stage = "candidate_promoted_from_filter" if answer_candidate_total > 0 else "page_promoted_but_sentence_weak"
        reason = "已经从差一点被过滤掉的页面里保住了相关材料，但句层仍未形成稳定可直裁的证据"
    elif answer_candidate_total > 0 and (not strong_items or not direct_items):
        responsibility_layer = "retrieval_readiness"
        stop_stage = "weak_source_candidate_only" if not strong_items else "candidate_not_direct"
        reason = "页面里已经抽到候选句，但这些句子还不够稳定或不够直接，尚未形成可直裁证据"
    elif not strong_items:
        responsibility_layer = "retrieval_filter"
        if high_priority_empty and fallback_only_raw:
            stop_stage = "fallback_only_raw"
            reason = "已有原始结果，但只有 fallback 弱源留下可用网页，高优先检索源没有有效召回"
        elif high_priority_empty:
            stop_stage = "high_priority_sources_no_raw"
            reason = "已有原始结果，但高优先 HTML/News 检索源没有留下有效网页"
        else:
            stop_stage = "weak_sources_only"
            reason = "保留下来的网页存在，但强源不足，检索质量仍不够"
    elif not direct_items:
        responsibility_layer = "retrieval_readiness"
        stop_stage = "no_direct_evidence"
        reason = "网页材料已保留，但还没有整理出可直接比对的句子/段落"
    else:
        responsibility_layer = "retrieval_ready"
        stop_stage = "retrieval_ready"
        reason = "检索层已拿到可继续转点的网页材料"
    return {
        "responsibility_layer": responsibility_layer,
        "stop_stage": stop_stage,
        "reason": reason,
        "source_recall_barrier_stage": barrier_stage,
        "source_recall_barrier_reason": barrier_reason,
        "family_states": family_states,
        "html_family_state": family_states.get("html", "not_used"),
        "news_family_state": family_states.get("news_rss", "not_used"),
        "rss_family_state": family_states.get("rss", "not_used"),
    }


def budgeted_source_jobs(
    source_jobs: List[tuple[str, str]],
    limit: int,
    query_goal: str,
    source_intent: Dict[str, Any],
    query_item: Optional[Dict[str, Any]] = None,
) -> tuple[List[tuple[str, str]], Dict[str, Any]]:
    query_item = query_item if isinstance(query_item, dict) else {}
    planned_source_order = [str(item) for item in (query_item.get("_planned_source_order") or []) if str(item)]
    post_role_priority_order = [str(item) for item in (query_item.get("_post_role_priority_order") or []) if str(item)]
    query_family_role = normalize_text(str(query_item.get("query_family_role") or ""))
    high_value_query = (
        query_goal in {"verification_question", "find_page_intent_page", "find_route_page", "find_metric_source_page", "find_atomic_refutation"}
        or query_family_role in {"closure", "distinguish", "refute"}
    )
    authority_pair_needed = query_needs_authority_pair(query_goal, query_family_role, source_intent)

    def build_result(
        selected_jobs: List[tuple[str, str]],
        omitted_jobs: List[tuple[str, str]],
        *,
        applied: bool,
        preserved_family_diversity: bool,
        priority_drop_stage: str = "",
        selection_reason: str = "",
    ) -> Dict[str, Any]:
        selected_sources = [str(source) for source, _ in selected_jobs]
        omitted_sources = [str(source) for source, _ in omitted_jobs]
        top_priority_omitted = [
            name for name in post_role_priority_order[:limit + 2]
            if name not in selected_sources
        ]
        return {
            "applied": applied,
            "limit": limit,
            "original_count": len(source_jobs),
            "selected_count": len(selected_jobs),
            "selected_sources": selected_sources,
            "omitted_sources": omitted_sources[:6],
            "omitted_families": dedupe_keep_order(source_family_name(str(source)) for source, _ in omitted_jobs)[:4],
            "different_family_omitted": bool({source_family_name(str(source)) for source, _ in omitted_jobs} - {source_family_name(str(source)) for source, _ in selected_jobs}),
            "higher_priority_omitted": bool(top_priority_omitted),
            "preserved_family_diversity": preserved_family_diversity,
            "high_value_query": high_value_query,
            "planned_source_order": planned_source_order[:10],
            "post_role_priority_order": post_role_priority_order[:10],
            "post_budget_selected_order": selected_sources[:10],
            "priority_source_dropped_stage": priority_drop_stage or ("budget" if top_priority_omitted else ""),
            "final_source_selection_reason": selection_reason,
            "authority_pair_preserved": preserved_authority_pair(selected_sources) if authority_pair_needed else False,
        }

    if limit <= 0 or len(source_jobs) <= limit:
        return source_jobs, build_result(
            source_jobs,
            [],
            applied=False,
            preserved_family_diversity=False,
            selection_reason="within_budget",
        )
    if limit == 1:
        selected = source_jobs[:1]
        omitted = source_jobs[1:]
        return selected, build_result(
            selected,
            omitted,
            applied=True,
            preserved_family_diversity=False,
            priority_drop_stage="budget" if omitted else "",
            selection_reason="single_slot_budget",
        )
    page_intent = normalize_page_intent(source_intent)
    needed_page_type = str(page_intent.get("needed_page_type") or "")
    preserve_family_diversity = query_goal in {"find_route_page", "find_page_intent_page"} or (
        query_goal == "verification_question" and needed_page_type not in {"", "general_page"}
    )
    preserve_family_diversity = preserve_family_diversity or high_value_query
    if not preserve_family_diversity:
        selected = source_jobs[:limit]
        omitted = source_jobs[limit:]
        return selected, build_result(
            selected,
            omitted,
            applied=True,
            preserved_family_diversity=False,
            priority_drop_stage="budget" if omitted else "",
            selection_reason="head_preserved_without_diversity",
        )

    selected: List[tuple[str, str]] = []
    used_names = set()

    def pick_family(family_name: str, source_names: Optional[List[str]] = None) -> None:
        if source_names:
            for preferred_name in source_names:
                for job in source_jobs:
                    source_name = str(job[0])
                    if source_name in used_names or source_name != preferred_name:
                        continue
                    selected.append(job)
                    used_names.add(source_name)
                    return
        for job in source_jobs:
            source_name = str(job[0])
            if source_name in used_names:
                continue
            if source_names and source_name not in source_names:
                continue
            if not source_names and source_family_name(source_name) != family_name:
                continue
            selected.append(job)
            used_names.add(source_name)
            return

    if authority_pair_needed and limit >= 2:
        pick_family("authority_or_news", ["domain_sitemap", "bing_rss", "bing_news_zh_rss", "bing_news_rss"])
        if len(selected) < limit:
            pick_family("html", ["bing_html", "duckduckgo_html"])
        if len(selected) < limit and not any(source_is_authority_or_news(str(source_name)) for source_name, _ in selected):
            pick_family("news_rss", ["bing_news_zh_rss", "bing_news_rss"])
        if len(selected) < limit and not any(source_is_non_sogou_html(str(source_name)) for source_name, _ in selected):
            pick_family("html", ["bing_html", "duckduckgo_html"])
    elif high_value_query and limit >= 2:
        if query_family_role in {"closure", "distinguish"}:
            pick_family("authority_or_news", ["domain_sitemap", "bing_rss"])
            if len(selected) < limit:
                pick_family("html", ["bing_html", "duckduckgo_html", "sogou_html"])
            if len(selected) < limit:
                pick_family("news_rss", ["bing_news_zh_rss", "bing_news_rss"])
        elif query_family_role == "refute":
            pick_family("html", ["bing_html", "duckduckgo_html", "sogou_html"])
            if len(selected) < limit:
                pick_family("news_rss", ["bing_news_zh_rss", "bing_news_rss"])
            if len(selected) < limit:
                pick_family("authority_or_news", ["domain_sitemap", "bing_rss"])
        else:
            pick_family("html", ["bing_html", "duckduckgo_html", "sogou_html"])
            if len(selected) < limit:
                pick_family("authority_or_news", ["domain_sitemap", "bing_rss", "bing_news_zh_rss", "bing_news_rss"])
        if len(selected) < limit:
            pick_family("html", ["bing_html", "duckduckgo_html", "sogou_html"])

    for family_name in ["html", "news_rss", "rss", "other"]:
        if len(selected) >= limit:
            break
        pick_family(family_name)

    for job in source_jobs:
        source_name = str(job[0])
        if source_name in used_names:
            continue
        selected.append(job)
        used_names.add(source_name)
        if len(selected) >= limit:
            break
    selected = selected[:limit]
    selected_names = {str(source) for source, _ in selected}
    omitted = [job for job in source_jobs if str(job[0]) not in selected_names]
    selection_reason = "family_diversity_budget"
    if authority_pair_needed:
        selection_reason = "authority_pair_guarded"
    elif query_family_role in {"closure", "distinguish", "refute"}:
        selection_reason = f"{query_family_role}_priority_budget"
    return selected, build_result(
        selected,
        omitted,
        applied=True,
        preserved_family_diversity=preserve_family_diversity,
        priority_drop_stage="budget" if omitted else "",
        selection_reason=selection_reason,
    )


def clamp_int(value: Any, lower: int, upper: int) -> int:
    try:
        return max(lower, min(upper, int(value)))
    except Exception:
        return lower


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except Exception:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def load_page_utility_llm_client() -> Optional[Any]:
    global _PAGE_UTILITY_LLM_CLIENT
    if _PAGE_UTILITY_LLM_CLIENT is not None:
        return _PAGE_UTILITY_LLM_CLIENT
    if not PAGE_UTILITY_LLM_API_KEY or OpenAI is None:
        _PAGE_UTILITY_LLM_CLIENT = False
        return None
    try:
        _PAGE_UTILITY_LLM_CLIENT = OpenAI(
            api_key=PAGE_UTILITY_LLM_API_KEY,
            base_url=PAGE_UTILITY_LLM_BASE_URL,
            timeout=PAGE_UTILITY_LLM_TIMEOUT,
        )
        return _PAGE_UTILITY_LLM_CLIENT
    except Exception:
        _PAGE_UTILITY_LLM_CLIENT = False
        return None


def page_utility_llm_candidate(
    item: Dict[str, Any],
    source_intent: Dict[str, Any],
    base_retention_score: int,
) -> bool:
    if not ENABLE_PAGE_UTILITY_LLM_RERANK:
        return False
    if str(source_intent.get("evidence_mode") or "") != "route_fact":
        return False
    if PAGE_UTILITY_LLM_MAX_ITEMS_PER_CLAIM <= 0:
        return False
    if base_retention_score < PAGE_UTILITY_LLM_MIN_RETENTION_SCORE:
        return False
    if int(item.get("source_quality_score") or 0) < PAGE_UTILITY_LLM_MIN_SOURCE_QUALITY:
        return False
    if str(item.get("source_type") or "") in {"forum"}:
        return False
    if not normalize_text(str(item.get("detail") or "")) and not normalize_text(str(item.get("snippet") or "")):
        return False
    route_sentence = item.get("route_sentence") if isinstance(item.get("route_sentence"), dict) else {}
    if route_sentence or normalize_text(str(item.get("detail") or "")):
        return True
    return False


def build_page_utility_llm_messages(
    query: str,
    claim_text: str,
    source_intent: Dict[str, Any],
    item: Dict[str, Any],
) -> Tuple[str, str]:
    page_intent = normalize_page_intent(source_intent)
    preview = normalize_text(
        "\n".join(
            [
                f"title: {str(item.get('title') or '')[:220]}",
                f"url: {str(item.get('url') or '')[:220]}",
                f"snippet: {str(item.get('snippet') or '')[:600]}",
                f"detail: {str(item.get('detail') or '')[:1400]}",
            ]
        )
    )
    system_prompt = (
        "你是 AFC 检索阶段的页面证据效用评估器。"
        "目标不是判断 claim 真伪，而是判断当前网页是否有机会产出可裁决证据句。"
        "必须输出 JSON 对象，不要输出解释性前后缀。"
    )
    user_prompt = f"""请按“页面证据效用”评估下面这个候选网页。

评估对象：
- claim: {claim_text[:260]}
- query: {query[:260]}
- evidence_mode: {str(source_intent.get("evidence_mode") or "")}
- evidence_target: {str(source_intent.get("evidence_target") or "")}
- needed_page_type: {str(page_intent.get("needed_page_type") or "")}

请重点判断：
1. 这页是否像“路径分析页 / 轨迹说明页 / 过境段落页”，而不只是战况背景页
2. 是否有机会抽出“对象 + 路径/方向/过境关系 + 地区”同句证据
3. 是否只是提到实体相关，但无法回答是否经过某区域

网页预览：
{preview}

返回 JSON，字段必须齐全：
{{
  "decision": "keep|borderline|drop",
  "page_type": "route_analysis|event_background|result_page|landing_page|mixed|other",
  "answerability": 0-3,
  "relation_evidence": 0-3,
  "entity_grounding": 0-3,
  "structural_extractability": 0-3,
  "specificity": 0-3,
  "noise_penalty": 0-3,
  "positive_signals": ["..."],
  "risks": ["..."],
  "reason": "不超过60字"
}}
"""
    return system_prompt, user_prompt


def call_page_utility_llm(
    query: str,
    claim_text: str,
    source_intent: Dict[str, Any],
    item: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    system_prompt, user_prompt = build_page_utility_llm_messages(query, claim_text, source_intent, item)
    cache_hit = cache_get("page_utility_llm_rerank", PAGE_UTILITY_LLM_MODEL, system_prompt, user_prompt)
    if isinstance(cache_hit, dict):
        return cache_hit
    client = load_page_utility_llm_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=PAGE_UTILITY_LLM_MODEL,
            temperature=PAGE_UTILITY_LLM_TEMPERATURE,
            max_tokens=PAGE_UTILITY_LLM_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = response.choices[0].message.content or ""
        data = extract_json_object(text)
        if isinstance(data, dict):
            cache_set("page_utility_llm_rerank", data, PAGE_UTILITY_LLM_MODEL, system_prompt, user_prompt)
            return data
    except Exception:
        return None
    return None


def normalize_page_utility_llm_result(result: Dict[str, Any]) -> Dict[str, Any]:
    decision = str(result.get("decision") or "borderline").strip().lower()
    if decision not in {"keep", "borderline", "drop"}:
        decision = "borderline"
    positive = [str(item).strip() for item in (result.get("positive_signals") or []) if str(item).strip()]
    risks = [str(item).strip() for item in (result.get("risks") or []) if str(item).strip()]
    components = {
        "answerability": clamp_int(result.get("answerability"), 0, 3),
        "relation_evidence": clamp_int(result.get("relation_evidence"), 0, 3),
        "entity_grounding": clamp_int(result.get("entity_grounding"), 0, 3),
        "structural_extractability": clamp_int(result.get("structural_extractability"), 0, 3),
        "specificity": clamp_int(result.get("specificity"), 0, 3),
        "noise_penalty": clamp_int(result.get("noise_penalty"), 0, 3),
    }
    llm_score = max(
        0,
        min(
            100,
            18
            + components["answerability"] * 14
            + components["relation_evidence"] * 12
            + components["entity_grounding"] * 8
            + components["structural_extractability"] * 7
            + components["specificity"] * 9
            - components["noise_penalty"] * 12,
        ),
    )
    score_adjust = {"keep": 8, "borderline": 0, "drop": -10}.get(decision, 0)
    return {
        "page_utility_llm_score": llm_score,
        "page_utility_llm_decision": decision,
        "page_utility_llm_page_type": str(result.get("page_type") or "other")[:40],
        "page_utility_llm_components": components,
        "page_utility_llm_positive_signals": dedupe_keep_order(positive)[:8],
        "page_utility_llm_risks": dedupe_keep_order(risks)[:8],
        "page_utility_llm_reason": str(result.get("reason") or "")[:80],
        "page_utility_llm_retention_adjustment": score_adjust,
    }


def cache_key(prefix: str, *parts: Any) -> str:
    raw = json.dumps([prefix, *parts], ensure_ascii=False, sort_keys=True)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()}.json"


def cache_get(prefix: str, *parts: Any) -> Any:
    if not USE_CACHE:
        return None
    key = cache_key(prefix, *parts)
    if key in _MEM_CACHE:
        return _MEM_CACHE[key]
    path = os.path.join(CACHE_DIR, key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f)
        _MEM_CACHE[key] = value
        return value
    except Exception:
        return None


def cache_set(prefix: str, value: Any, *parts: Any) -> None:
    if not USE_CACHE:
        return
    key = cache_key(prefix, *parts)
    _MEM_CACHE[key] = value
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(os.path.join(CACHE_DIR, key), "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
    except Exception:
        pass


def passage_focus_terms(query: str, title: str = "") -> List[str]:
    text = f"{query} {title}".lower()
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", text)
    stop = {
        "site", "http", "https", "www", "com", "org", "the", "and", "for", "with",
        "who", "what", "when", "where", "which", "query", "official",
    }
    terms = [token for token in tokens if token not in stop]
    if any(token in text for token in ["amount", "money", "奖金"]):
        terms.extend(["amount", "money", "million", "sek", "kronor", "奖金", "瑞典克朗"])
    if any(token in text for token in ["announcement", "announce", "公布", "宣布"]):
        terms.extend(["announcement", "announced", "october", "公布", "宣布"])
    if any(token in text for token in ["withdraw", "retired", "walkover", "退赛", "弃权", "不战而胜"]):
        terms.extend(["withdraw", "withdrew", "retired", "walkover", "退赛", "弃权", "不战而胜"])
    if any(token in text for token in ["trading day", "market holiday", "休市", "交易日", "节假日"]):
        terms.extend(["trading day", "market holiday", "closed", "休市", "交易日", "节假日"])
    if any(token in text for token in ["census", "phase", "阶段"]):
        terms.extend(["census", "phase", "enumeration", "results", "阶段", "结果", "公布"])
    if any(token in text for token in ["location", "distance", "位置", "距离"]):
        terms.extend(["location", "position", "distance", "位置", "距离", "公里"])
    return dedupe_keep_order(terms)[:16]


def extract_relevant_passage(text: str, focus_terms: List[str], max_chars: int = 1200) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return ""
    if not focus_terms:
        return normalized[:max_chars]
    lower = normalized.lower()
    best_start = 0
    best_score = -1
    window = min(max(900, max_chars), 1800)
    for term in focus_terms:
        idx = lower.find(term.lower())
        if idx < 0:
            continue
        start = max(0, idx - window // 3)
        end = min(len(normalized), start + window)
        snippet = normalized[start:end].lower()
        score = sum(2 if len(token) >= 4 else 1 for token in focus_terms if token.lower() in snippet)
        if re.search(r"\d", snippet):
            score += 2
        if score > best_score:
            best_score = score
            best_start = start
    if best_score < 0:
        return normalized[:max_chars]
    passage = normalized[best_start: best_start + window]
    return passage[:max_chars]


def classify_source_type(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    for source_type, markers in SOURCE_TYPES.items():
        for marker in markers:
            if marker.startswith("."):
                if host.endswith(marker):
                    return source_type
            elif marker.startswith("news."):
                if host.startswith("news."):
                    return source_type
            elif marker in host:
                return source_type
    if host:
        return "unknown"
    return "unknown"


def build_duckduckgo_url(query: str) -> str:
    return f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"


def build_bing_rss_url(query: str) -> str:
    return f"https://www.bing.com/search?format=rss&q={quote_plus(query)}"


def build_bing_html_url(query: str) -> str:
    return f"https://www.bing.com/search?q={quote_plus(query)}"


def build_bing_news_rss_url(query: str) -> str:
    return f"https://www.bing.com/news/search?format=rss&q={quote_plus(query)}&mkt=en-US&setlang=en-US"


def build_bing_news_zh_rss_url(query: str) -> str:
    return f"https://www.bing.com/news/search?format=rss&q={quote_plus(query)}&mkt=zh-CN&setlang=zh-CN"


def build_sogou_url(query: str) -> str:
    return f"https://www.sogou.com/web?query={quote_plus(query)}"


def unwrap_bing_url(url: str) -> str:
    url = unescape(url or "")
    parsed = urlparse(url or "")
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/news/apiclick"):
        target = re.search(r"[?&]url=([^&]+)", parsed.query, flags=re.I)
        if target:
            return unquote(normalize_text(target.group(1)).replace("&amp;", "&"))
    return url


def unwrap_duckduckgo_url(url: str) -> str:
    url = unescape(url or "")
    if url.startswith("//"):
        url = "https:" + url
    target = re.search(r"[?&]uddg=([^&]+)", url, flags=re.I)
    if target:
        return unquote(normalize_text(target.group(1)).replace("&amp;", "&"))
    parsed = urlparse(url or "")
    if "duckduckgo.com" in parsed.netloc:
        target = re.search(r"[?&]uddg=([^&]+)", parsed.query, flags=re.I)
        if target:
            return unquote(normalize_text(target.group(1)).replace("&amp;", "&"))
    return url


def search_duckduckgo_html(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[Dict[str, Any]]:
    url = build_duckduckgo_url(query)
    response = guarded_http_get(url, timeout_sec=timeout_sec, source_name="duckduckgo_html")
    html = decode_response_text(response)
    ensure_response_not_blocked(response, request_url=url, source_name="duckduckgo_html", decoded_text=html)
    items: List[Dict[str, Any]] = []
    blocks = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)"[^>]*>(.*?)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>', html, flags=re.S)
    for href, title_html, snippet_html in blocks[:max_results]:
        link = unwrap_duckduckgo_url(href)
        title = re.sub(r"<.*?>", "", title_html)
        snippet = re.sub(r"<.*?>", "", snippet_html)
        items.append(
            {
                "title": normalize_text(title),
                "url": link,
                "snippet": normalize_text(snippet),
                "source_type": classify_source_type(link),
                "source": "duckduckgo_html",
            }
        )
    return items


def search_bing_rss(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[Dict[str, Any]]:
    url = build_bing_rss_url(query)
    response = guarded_http_get(url, timeout_sec=timeout_sec, source_name="bing_rss")
    text = decode_response_text(response)
    ensure_response_not_blocked(response, request_url=url, source_name="bing_rss", decoded_text=text)
    items: List[Dict[str, Any]] = []
    for match in re.finditer(r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<description>(.*?)</description>.*?</item>", text, flags=re.S):
        title = unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", match.group(1)))
        link = unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", match.group(2)))
        description = unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", match.group(3)))
        items.append(
            {
                "title": normalize_text(re.sub(r"<.*?>", "", title)),
                "url": normalize_text(link),
                "snippet": normalize_text(re.sub(r"<.*?>", "", description)),
                "source_type": classify_source_type(link),
                "source": "bing_rss",
            }
        )
        if len(items) >= max_results:
            break
    return items


def search_bing_html(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[Dict[str, Any]]:
    url = build_bing_html_url(query)
    response = guarded_http_get(url, timeout_sec=timeout_sec, source_name="bing_html")
    html = decode_response_text(response)
    ensure_response_not_blocked(response, request_url=url, source_name="bing_html", decoded_text=html)
    items: List[Dict[str, Any]] = []
    blocks = re.findall(r'<li class="b_algo".*?</li>', html, flags=re.S)
    for block in blocks:
        link_match = re.search(r'<h2[^>]*>.*?<a[^>]+href="(.*?)"[^>]*>(.*?)</a>.*?</h2>', block, flags=re.S)
        if not link_match:
            continue
        link = unescape(link_match.group(1))
        title = normalize_text(re.sub(r"<.*?>", "", link_match.group(2)))
        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.S)
        snippet = normalize_text(re.sub(r"<.*?>", "", snippet_match.group(1))) if snippet_match else ""
        items.append(
            {
                "title": title,
                "url": normalize_text(link),
                "snippet": snippet,
                "source_type": classify_source_type(link),
                "source": "bing_html",
            }
        )
        if len(items) >= max_results:
            break
    return items


def search_sogou_html(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[Dict[str, Any]]:
    url = build_sogou_url(query)
    response = guarded_http_get(url, timeout_sec=timeout_sec, source_name="sogou_html")
    html = decode_response_text(response)
    ensure_response_not_blocked(response, request_url=url, source_name="sogou_html", decoded_text=html)
    items: List[Dict[str, Any]] = []
    blocks = re.findall(r"<h3[^>]*>(.*?)</h3>.*?<p[^>]*class=\"(?:str_info|txt-info)\"[^>]*>(.*?)</p>", html, flags=re.S)
    if not blocks:
        blocks = [(match, "") for match in re.findall(r"<h3[^>]*>(.*?)</h3>", html, flags=re.S)]
    for title_html, snippet_html in blocks[: max_results * 2]:
        href_match = re.search(r"href=\"([^\"]+)\"", title_html)
        if not href_match:
            continue
        title = normalize_text(re.sub(r"<.*?>", " ", title_html))
        snippet = normalize_text(re.sub(r"<.*?>", " ", snippet_html))
        link = unescape(href_match.group(1))
        if not title or not link.startswith("http"):
            continue
        items.append(
            {
                "title": title,
                "url": link,
                "snippet": snippet,
                "source_type": classify_source_type(link),
                "source": "sogou_html",
            }
        )
        if len(items) >= max_results:
            break
    return items


def search_playwright_duckduckgo(query: str, max_results: int = 3, timeout_sec: int = 10) -> List[Dict[str, Any]]:
    if sync_playwright is None:
        return []
    cached = cache_get("playwright_search", query, max_results)
    if isinstance(cached, list):
        return [dict(item) for item in cached if isinstance(item, dict)]
    items: List[Dict[str, Any]] = []
    with sync_playwright() as playwright:
        launch_kwargs: Dict[str, Any] = {"headless": True}
        chrome_path = os.environ.get("V2_PLAYWRIGHT_CHROME") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if os.path.exists(chrome_path):
            launch_kwargs["executable_path"] = chrome_path
        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            locale="zh-CN",
        )
        page = context.new_page()
        page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "media", "font", "stylesheet"}
            else route.continue_(),
        )
        page.goto(build_duckduckgo_url(query), wait_until="domcontentloaded", timeout=max(3000, timeout_sec * 1000))
        try:
            body_text = normalize_text(page.locator("body").inner_text(timeout=max(1000, timeout_sec * 120)))
        except Exception:
            body_text = ""
        block_reasons = anti_bot_signal_reasons(body_text, page.url or "")
        if block_reasons:
            context.close()
            browser.close()
            raise AntiBotBlockedError(url=page.url or build_duckduckgo_url(query), source_name="playwright_duckduckgo", reasons=block_reasons)
        try:
            page.wait_for_selector("a.result__a", timeout=max(2000, timeout_sec * 500))
        except Exception:
            pass
        rows = page.locator("div.result").all()[: max_results * 2]
        for row in rows:
            try:
                link_node = row.locator("a.result__a").first
                title = normalize_text(link_node.inner_text(timeout=1000))
                href = unwrap_duckduckgo_url(link_node.get_attribute("href") or "")
                snippet = normalize_text(row.locator(".result__snippet").first.inner_text(timeout=1000))
            except Exception:
                continue
            if not title or not href.startswith("http"):
                continue
            items.append(
                {
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                    "source_type": classify_source_type(href),
                    "source": "playwright_duckduckgo",
                }
            )
            if len(items) >= max_results:
                break
        context.close()
        browser.close()
    cache_set("playwright_search", items, query, max_results)
    return items


def sitemap_candidates(domain: str, timeout_sec: int = 10, max_sitemaps: int = 40, max_urls: int = 8000) -> List[str]:
    domain = normalize_domain(domain)
    if not domain:
        return []
    cached = cache_get("sitemap", domain)
    if isinstance(cached, list):
        _SITEMAP_CACHE[domain] = [str(x) for x in cached]
        return _SITEMAP_CACHE[domain]
    if domain in _SITEMAP_CACHE:
        return _SITEMAP_CACHE[domain]
    sitemap_urls = [f"https://{domain}/sitemap.xml", f"https://www.{domain}/sitemap.xml"]
    try:
        robots = _HTTP.get(f"https://{domain}/robots.txt", timeout=timeout_sec)
        if robots.ok:
            sitemap_urls.extend(re.findall(r"(?im)^sitemap:\s*(\S+)", robots.text))
    except Exception:
        pass
    seen_sitemaps = set()
    seen_urls = []
    queue = dedupe_keep_order(sitemap_urls)
    while queue and len(seen_sitemaps) < max_sitemaps and len(seen_urls) < max_urls:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            response = _HTTP.get(sitemap_url, timeout=timeout_sec)
            if not response.ok:
                continue
        except Exception:
            continue
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", response.text, flags=re.I | re.S)
        for loc in locs:
            loc = normalize_text(unescape(loc))
            if not loc:
                continue
            if loc.lower().endswith(".xml") and len(seen_sitemaps) + len(queue) < max_sitemaps:
                queue.append(loc)
            elif url_matches_domain(loc, domain):
                seen_urls.append(loc)
                if len(seen_urls) >= max_urls:
                    break
    result = dedupe_keep_order(seen_urls)
    _SITEMAP_CACHE[domain] = result
    cache_set("sitemap", result, domain)
    return result


def sitemap_url_score(query: str, url: str) -> int:
    url_lower = url.lower()
    query_lower = query.lower()
    score = 0
    distinctive_hits = 0
    query_years = re.findall(r"\b(?:19|20)\d{2}\b", query_lower)
    url_years = re.findall(r"\b(?:19|20)\d{2}\b", url_lower)
    query_year_set = set(query_years)
    url_year_set = set(url_years)
    is_amount_query = any(marker in query_lower for marker in ["amount", "money", "sek", "kronor", "瑞典克朗", "奖金"])
    if is_amount_query and any(marker in url_lower for marker in ["money", "amount", "prize-money", "prize_money"]):
        score += 10
        distinctive_hits += 1
        if "/prizes/about/" in url_lower:
            score += 8
    if query_year_set and url_year_set:
        shared_years = query_year_set & url_year_set
        if shared_years:
            score += 5
            distinctive_hits += 1
        elif "/prizes/" in url_lower:
            score -= 6
    for token in query_core_tokens(query):
        token_lower = token.lower()
        if re.fullmatch(r"\d{4}", token_lower):
            if token_lower in url_lower:
                score += 3
            continue
        if token_lower in {"nobel", "official", "swedish", "kronor", "sek", "amount", "money"}:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(token_lower)}(?![a-z0-9])", url_lower):
            score += 2
            distinctive_hits += 1
        elif len(token_lower) >= 6 and token_lower in url_lower:
            score += 1
            distinctive_hits += 1
    if distinctive_hits == 0:
        return 0
    if "prize" in query_lower and "/prizes/" in url_lower:
        score += 2
    if "official" in query_lower and any(marker in url_lower for marker in ["/press-release", "/summary", "/facts"]):
        score += 1
    if is_amount_query:
        if any(marker in url_lower for marker in ["/summary", "/press-release", "/facts"]):
            score += 1
        if any(marker in url_lower for marker in ["ceremony", "speech", "swedish"]):
            score -= 5
    score -= min(3, len(urlparse(url).path.strip("/").split("/")) // 5)
    return score


def title_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return urlparse(url).netloc
    slug = path.split("/")[-1] or path
    return normalize_text(unquote(slug).replace("-", " ").replace("_", " "))


def official_inner_link_bridge_terms(source_intent: Dict[str, Any]) -> List[str]:
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    binding_terms = source_strategy_binding_terms(source_intent, evidence_mode)
    metric_slots = metric_slots_from_intent(source_intent)
    authority_scope = normalize_text(str(metric_slots.get("source_authority") or binding_terms.get("authority_scope") or "")).lower()
    terms: List[str] = []
    for key in ("subject_entity", "relation_or_metric", "time_scope", "unit"):
        value = str(binding_terms.get(key) or "")
        for term in binding_slot_search_values(key, value, source_intent, evidence_mode)[:2]:
            append_query_term_unique(terms, term)
    authority_terms = {
        "bank_rate_table": ["外汇牌价", "牌价表", "汇率", "历史查询"],
        "central_bank": ["中间价", "公告", "数据"],
        "exchange": ["行情", "报价", "历史数据"],
        "official_notice": ["公告", "通知"],
        "market_data_page": ["数据", "历史数据", "查询"],
    }
    for term in authority_terms.get(authority_scope, []):
        append_query_term_unique(terms, term)
    return terms[:10]


def official_homepage_like(item: Dict[str, Any]) -> bool:
    url = str(item.get("url") or "")
    path = urlparse(url).path.lower().strip("/")
    text = normalize_text(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')}").lower()
    return (
        path in {"", "/", "home", "index", "news", "en", "cn", "zh"}
        or any(marker in text for marker in ["首页", "门户", "global web site", "homepage", "home page"])
    )


def official_inner_link_allowed_domains(homepage_domain: str, preferred_domains: Optional[List[str]] = None) -> List[str]:
    allowed: List[str] = []
    if homepage_domain:
        allowed.append(homepage_domain)
    for domain in preferred_domains or []:
        normalized = normalize_domain(domain)
        if normalized:
            allowed.append(normalized)
    return dedupe_keep_order(allowed)[:4]


def official_inner_link_score(
    anchor_text: str,
    href: str,
    source_intent: Dict[str, Any],
    allowed_domains: Optional[List[str]] = None,
) -> int:
    anchor_normalized = normalize_text(anchor_text).lower()
    combined = normalize_text(f"{anchor_text} {href}").lower()
    if not combined:
        return 0
    normalized_allowed = [normalize_domain(domain) for domain in (allowed_domains or []) if normalize_domain(domain)]
    if normalized_allowed and not any(url_matches_domain(href, domain) for domain in normalized_allowed):
        return 0
    metric_slots = metric_slots_from_intent(source_intent)
    authority_scope = normalize_text(str(metric_slots.get("source_authority") or "")).lower()
    value_type = normalize_text(str(metric_slots.get("value_type") or "")).lower()
    score = 0
    for term in official_inner_link_bridge_terms(source_intent):
        normalized = normalize_text(term).lower()
        if normalized and normalized in combined:
            score += 4 if len(normalized) >= 4 else 2
    path = urlparse(href).path.lower()
    if any(marker in path for marker in ["sourcedb", "whpj", "exchange", "forex", "rate", "quote", "history", "data", "query"]):
        score += 8
    if any(marker in combined for marker in ["外汇牌价", "牌价", "汇率", "历史查询", "quote", "rate", "forex", "exchange"]):
        score += 6
    if authority_scope == "bank_rate_table":
        if "外汇牌价" in anchor_normalized and not any(
            marker in anchor_normalized for marker in ["远期", "forward", "ffx", "境外机构", "overseas", "基金", "净值", "理财", "债券", "指数"]
        ):
            score += 10
        if any(marker in combined for marker in ["远期", "forward", "ffx"]) and value_type in {"spot_buying_price", "cash_buying_price", "selling_price", "real_time_rate", "spot_price"}:
            score -= 14
        if any(marker in combined for marker in ["境外机构", "overseas", "branch"]):
            score -= 8
        if any(marker in combined for marker in ["基金", "净值", "理财", "债券", "指数", "贵金属", "cfets", "srfd"]):
            score -= 10
    if any(marker in path for marker in ["index", "home"]) and score < 12:
        score -= 6
    return max(0, score)


def official_inner_link_candidates(
    homepage_url: str,
    source_intent: Dict[str, Any],
    preferred_domains: Optional[List[str]] = None,
    timeout_sec: int = 10,
    max_candidates: int = 4,
) -> List[Dict[str, Any]]:
    if not homepage_url or BeautifulSoup is None:
        return []
    homepage_domain = normalize_domain(urlparse(homepage_url).netloc)
    if not homepage_domain:
        return []
    allowed_domains = official_inner_link_allowed_domains(homepage_domain, preferred_domains)
    try:
        response = _HTTP.get(homepage_url, timeout=timeout_sec)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
    except Exception:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    scored: List[Tuple[int, Dict[str, Any]]] = []
    seen_urls = set()
    for anchor in soup.find_all("a", href=True):
        raw_href = str(anchor.get("href") or "").strip()
        if not raw_href or raw_href.lower().startswith("javascript:"):
            continue
        href = urljoin(homepage_url, raw_href)
        href = normalize_text(href)
        if not href.startswith("http") or href in seen_urls:
            continue
        seen_urls.add(href)
        text = normalize_text(anchor.get_text(" ", strip=True) or "")
        score = official_inner_link_score(text, href, source_intent, allowed_domains)
        if score <= 0:
            continue
        scored.append(
            (
                score,
                {
                    "title": text or title_from_url(href),
                    "url": href,
                    "snippet": f"official inner link candidate score={score}",
                    "source_type": "official",
                    "source": "official_inner_link",
                },
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored[:max_candidates]]


def search_domain_sitemap(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[Dict[str, Any]]:
    domain = extract_site_constraint(query)
    if not domain:
        return []
    urls = sitemap_candidates(domain, timeout_sec=timeout_sec)
    scored = [(sitemap_url_score(query, url), url) for url in urls]
    scored = [(score, url) for score, url in scored if score > 0]
    scored.sort(key=lambda item: item[0], reverse=True)
    items: List[Dict[str, Any]] = []
    for score, url in scored[:max_results]:
        items.append(
            {
                "title": title_from_url(url),
                "url": url,
                "snippet": f"sitemap match score={score}",
                "source_type": classify_source_type(url),
                "source": "domain_sitemap",
            }
        )
    return items


def search_source(source_name: str, query: str, max_results: int, timeout_sec: int) -> List[Dict[str, Any]]:
    cached = cache_get("search", source_name, query, max_results)
    if isinstance(cached, list):
        return [dict(item) for item in cached if isinstance(item, dict)]
    effective_timeout_sec = timeout_sec
    if source_name == "sogou_html" and SOGOU_TIMEOUT_CAP_SEC > 0:
        effective_timeout_sec = min(timeout_sec, SOGOU_TIMEOUT_CAP_SEC)
    elif source_name == "playwright_duckduckgo" and PLAYWRIGHT_TIMEOUT_CAP_SEC > 0:
        effective_timeout_sec = min(timeout_sec, PLAYWRIGHT_TIMEOUT_CAP_SEC)

    items: Optional[List[Dict[str, Any]]] = None
    if search_with_provider is not None:
        try:
            provider_items = search_with_provider(source_name, query, max_results, effective_timeout_sec)
            if isinstance(provider_items, list):
                items = [dict(item) for item in provider_items if isinstance(item, dict)]
                if not items:
                    items = None
        except Exception:
            items = None

    try:
        if items is not None:
            pass
        elif source_name == "duckduckgo_html":
            items = search_duckduckgo_html(query, max_results=max_results, timeout_sec=effective_timeout_sec)
        elif source_name == "domain_sitemap":
            items = search_domain_sitemap(query, max_results=max_results, timeout_sec=effective_timeout_sec)
        elif source_name == "bing_html":
            items = search_bing_html(query, max_results=max_results, timeout_sec=effective_timeout_sec)
        elif source_name == "bing_news_rss":
            items = search_bing_news_rss(query, max_results=max_results, timeout_sec=effective_timeout_sec)
        elif source_name == "bing_news_zh_rss":
            items = search_bing_news_zh_rss(query, max_results=max_results, timeout_sec=effective_timeout_sec)
        elif source_name == "bing_rss":
            items = search_bing_rss(query, max_results=max_results, timeout_sec=effective_timeout_sec)
        elif source_name == "sogou_html":
            items = search_sogou_html(query, max_results=max_results, timeout_sec=effective_timeout_sec)
        elif source_name == "playwright_duckduckgo":
            items = search_playwright_duckduckgo(query, max_results=max_results, timeout_sec=effective_timeout_sec)
        else:
            items = search_wikipedia(query, max_results=max_results, timeout_sec=effective_timeout_sec)
    except AntiBotBlockedError:
        if ENABLE_PLAYWRIGHT and source_name in {"duckduckgo_html", "bing_html", "sogou_html"}:
            items = search_playwright_duckduckgo(query, max_results=max_results, timeout_sec=min(effective_timeout_sec, PLAYWRIGHT_TIMEOUT_CAP_SEC) if PLAYWRIGHT_TIMEOUT_CAP_SEC > 0 else effective_timeout_sec)
            for item in items:
                if isinstance(item, dict):
                    item["search_fallback_from_anti_bot"] = source_name
            cache_set("search", items, source_name, query, max_results)
            return items
        raise
    cache_set("search", items, source_name, query, max_results)
    return items


def parse_bing_news_rss(text: str, source_name: str, max_results: int = 5) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for match in re.finditer(r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<description>(.*?)</description>.*?</item>", text, flags=re.S):
        title = unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", match.group(1)))
        link = unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", match.group(2)))
        description = unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", match.group(3)))
        link = unwrap_bing_url(normalize_text(link))
        items.append(
            {
                "title": normalize_text(re.sub(r"<.*?>", "", title)),
                "url": link,
                "snippet": normalize_text(re.sub(r"<.*?>", "", description)),
                "source_type": classify_source_type(link),
                "source": source_name,
            }
        )
        if len(items) >= max_results:
            break
    return items


def search_bing_news_rss(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[Dict[str, Any]]:
    url = build_bing_news_rss_url(query)
    response = guarded_http_get(
        url,
        timeout_sec=timeout_sec,
        headers={"Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"},
        source_name="bing_news_rss",
    )
    text = decode_response_text(response)
    ensure_response_not_blocked(response, request_url=url, source_name="bing_news_rss", decoded_text=text)
    return parse_bing_news_rss(text, "bing_news_rss", max_results=max_results)


def search_bing_news_zh_rss(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[Dict[str, Any]]:
    url = build_bing_news_zh_rss_url(query)
    response = guarded_http_get(
        url,
        timeout_sec=timeout_sec,
        headers={"Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"},
        source_name="bing_news_zh_rss",
    )
    text = decode_response_text(response)
    ensure_response_not_blocked(response, request_url=url, source_name="bing_news_zh_rss", decoded_text=text)
    return parse_bing_news_rss(text, "bing_news_zh_rss", max_results=max_results)


def search_wikipedia(query: str, max_results: int = 3, timeout_sec: int = 10) -> List[Dict[str, Any]]:
    url = f"https://zh.wikipedia.org/w/api.php?action=opensearch&search={quote_plus(query)}&limit={max_results}&namespace=0&format=json"
    response = guarded_http_get(url, timeout_sec=timeout_sec, source_name="wikipedia")
    data = response.json()
    results: List[Dict[str, Any]] = []
    titles = data[1] if len(data) > 1 else []
    snippets = data[2] if len(data) > 2 else []
    links = data[3] if len(data) > 3 else []
    for title, snippet, link in zip(titles, snippets, links):
        results.append(
            {
                "title": normalize_text(title),
                "url": normalize_text(link),
                "snippet": normalize_text(snippet),
                "source_type": "encyclopedia",
                "source": "wikipedia",
            }
        )
    return results[:max_results]


def extract_year_tokens(text: str) -> List[str]:
    return dedupe_keep_order(re.findall(r"(?:19|20)\d{2}", text or ""))


def prefer_news_first_for_intent(source_intent: Dict[str, Any]) -> bool:
    if not isinstance(source_intent, dict):
        return False
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    shape = str(source_intent.get("evidence_shape") or source_intent.get("evidence_page_shape") or "")
    return (
        mode in {"date_fact", "schedule_fact", "event_result"}
        or target in {"match_result", "withdrawal_status", "market_calendar", "census_phase", "current_status"}
        or shape == "current_status_update"
    )


def metric_time_scope_has_explicit_year(source_intent: Dict[str, Any]) -> bool:
    metric_slots = metric_slots_from_intent(source_intent)
    binding = core_binding_from_intent(source_intent)
    combined = normalize_text(
        " ".join(
            [
                str(binding.get("time_scope") or ""),
                str(metric_slots.get("time_scope") or ""),
            ]
        )
    )
    return bool(extract_year_tokens(combined))


def metric_time_scope_matches_context(
    source_intent: Dict[str, Any],
    publish_time: str = "",
    title: str = "",
    url: str = "",
    detail: str = "",
) -> bool:
    metric_slots = metric_slots_from_intent(source_intent)
    binding = core_binding_from_intent(source_intent)
    time_scope = normalize_text(
        str(binding.get("time_scope") or metric_slots.get("time_scope") or "")
    )
    if not time_scope:
        return False
    normalized_publish_time = normalize_text(publish_time).replace("/", "-")
    if normalized_publish_time and time_scope in normalized_publish_time:
        return True
    scope_years = extract_year_tokens(time_scope)
    if not scope_years:
        return False
    combined = normalize_text(" ".join([publish_time, title, url, detail]))
    visible_years = extract_year_tokens(combined)
    if not visible_years:
        return False
    return any(year in visible_years for year in scope_years)


def detect_claim_features(question: str, claim: str) -> Dict[str, bool]:
    combined = f"{question} {claim}".lower()
    return {
        "has_number": bool(re.search(r"\d", combined)),
        "has_date": bool(re.search(r"\d{4}[-年]\d{1,2}|\d{1,2}月\d{1,2}日|今天|今日|目前|现在|最新", combined)),
        "has_amount": bool(re.search(r"金额|奖金|价格|票价|汇率|涨|跌|million|sek|dollar|usd|元|克朗", combined)),
        "has_time_event": bool(re.search(r"公布|宣布|发布|结果|截止|结束|阶段|颁奖|announcement|result|publish", combined)),
        "has_route": bool(re.search(r"距离|经过|领空|路线|通道|海峡|航运|通航|过境|边境|route|airspace|distance", combined)),
        "has_score": bool(re.search(r"比分|赛果|战绩|box score|result|match|game", combined)),
    }


def route_medium_from_text(text: str) -> str:
    combined = normalize_text(text).lower()
    scores: Dict[str, int] = {}
    for medium, config in ROUTE_MEDIUM_HINTS.items():
        if medium == "generic":
            continue
        terms = config.get("terms") if isinstance(config.get("terms"), list) else []
        score = 0
        for term in terms:
            term_text = normalize_text(str(term)).lower()
            if term_text and term_text in combined:
                score += 2 if " " in term_text else 1
        scores[medium] = score
    if not scores:
        return "generic"
    best_medium = max(scores.items(), key=lambda item: (item[1], item[0] == "maritime", item[0] == "land"))[0]
    if scores.get(best_medium, 0) <= 0:
        return "generic"
    return best_medium


def route_medium_context(question: str, claim: str, source_intent: Dict[str, Any], existing_queries: Optional[List[Dict[str, str]]] = None) -> Dict[str, str]:
    route_meta = source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}
    route_bits = " ".join(
        normalize_text(str(route_meta.get(key) or ""))
        for key in ("origin", "destination", "route_area")
    )
    query_bits = " ".join(
        normalize_text(str(item.get("q") or ""))
        for item in (existing_queries or [])
        if isinstance(item, dict)
    )
    medium = route_medium_from_text(" ".join([question, claim, route_bits, query_bits]))
    config = ROUTE_MEDIUM_HINTS.get(medium) if isinstance(ROUTE_MEDIUM_HINTS.get(medium), dict) else ROUTE_MEDIUM_HINTS.get("generic", {})
    generic_config = ROUTE_MEDIUM_HINTS.get("generic", {})
    return {
        "route_medium": medium,
        "suffix_zh": str(config.get("suffix_zh") or generic_config.get("suffix_zh") or ""),
        "suffix_en": str(config.get("suffix_en") or generic_config.get("suffix_en") or ""),
    }


def append_query_term_unique(terms: List[str], candidate: str) -> None:
    value = normalize_text(candidate)
    if not value:
        return
    lowered = value.lower()
    kept: List[str] = []
    for existing in terms:
        existing_lower = existing.lower()
        if lowered == existing_lower or lowered in existing_lower:
            return
        if existing_lower in lowered:
            continue
        kept.append(existing)
    kept.append(value)
    terms[:] = kept


def route_query_object_terms(texts: List[str], english_only: bool = False, limit: int = 2) -> List[str]:
    markers = [
        str(marker)
        for marker in ROUTE_STRICT_OBJECT_MARKERS
        if str(marker)
        and (not english_only or re.search(r"[A-Za-z]", str(marker)))
    ]
    terms: List[str] = []
    for text in texts:
        normalized = normalize_text(text)
        if not normalized:
            continue
        for marker in markers:
            if route_marker_present(normalized, marker):
                append_query_term_unique(terms, marker)
        if len(terms) >= limit:
            break
    return terms[:limit]


GENERIC_QUERY_NOISE_TOKENS = {
    "article", "articles", "breaking", "detail", "details", "latest", "live", "news",
    "report", "reports", "update", "updates",
    "信息", "详情", "报道", "新闻", "最新", "消息", "资讯", "快讯",
}

ROUTE_FRAME_GENERIC_SKIP = GENERIC_QUERY_NOISE_TOKENS | {
    "analysis", "analyze", "background", "conflict", "corridor",
    "flight", "map", "overflight", "overfly", "passage", "path", "route", "routing",
    "track", "trajectory", "war",
    "分析", "战况", "背景", "地图", "示意图", "通道", "路径", "路线", "航线", "航迹", "轨迹", "过境", "公里", "分钟", "全程",
}

# Spatial modifiers are weak geographic qualifiers, not stable retrieval anchors.
LOCATION_SPATIAL_MODIFIER_TOKENS = {
    "北部", "南部", "东部", "西部", "中部",
    "北线", "南线", "东线", "西线", "中线",
}

LOCATION_SPATIAL_MODIFIER_SUFFIXES = (
    "北部", "南部", "东部", "西部", "中部",
    "北线", "南线", "东线", "西线", "中线",
)

def route_retry_query_frame(
    question: str,
    claim: str,
    source_intent: Dict[str, Any],
    existing_queries: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    route_meta = source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}
    retry_route_frame = source_intent.get("_retry_route_search_frame") if isinstance(source_intent.get("_retry_route_search_frame"), dict) else {}
    llm_contract_focus = source_intent.get("_retry_contract_focus_llm") if isinstance(source_intent.get("_retry_contract_focus_llm"), dict) else {}
    route_context = route_medium_context(question, claim, source_intent, existing_queries)
    page_intent = normalize_page_intent(source_intent)
    needed_page_type = str(page_intent.get("needed_page_type") or "route_analysis_page")
    object_terms = route_query_object_terms(
        [
            question,
            claim,
            " ".join(
                normalize_text(str(retry_route_frame.get(key) or ""))
                for key in ("object_or_area", "relation_need", "subject", "action_or_event")
            ),
            " ".join(
                normalize_text(str(llm_contract_focus.get(key) or ""))
                for key in ("page_brief", "target_sentence", "avoid", "reject_shape")
            ),
            " ".join(
                normalize_text(str(item.get("q") or ""))
                for item in (existing_queries or [])
                if isinstance(item, dict)
            ),
        ],
        limit=2,
    )
    object_terms_en = route_query_object_terms(
        [
            question,
            claim,
            " ".join(
                normalize_text(str(retry_route_frame.get(key) or ""))
                for key in ("object_or_area", "relation_need", "subject", "action_or_event")
            ),
            " ".join(
                normalize_text(str(llm_contract_focus.get(key) or ""))
                for key in ("page_brief", "target_sentence", "avoid", "reject_shape")
            ),
            " ".join(
                normalize_text(str(item.get("q") or ""))
                for item in (existing_queries or [])
                if isinstance(item, dict)
            ),
        ],
        english_only=True,
        limit=2,
    )
    stop_terms = (
        {marker.lower() for marker in ROUTE_QUERY_STOPWORDS}
        | {marker.lower() for marker in ROUTE_ENTITY_QUERY_STOPWORDS}
        | {normalize_text(str(marker)).lower() for marker in ROUTE_OBJECT_MARKERS if normalize_text(str(marker))}
        | ROUTE_FRAME_GENERIC_SKIP
    )
    anchor_texts: List[tuple[str, str]] = []
    for value in [route_meta.get("origin"), route_meta.get("destination")]:
        normalized_value = normalize_text(str(value or ""))
        if normalized_value:
            anchor_texts.append((normalized_value, "route_meta"))
    for key in ("subject", "action_or_event", "relation_need", "object_or_area", "time_or_event_window"):
        normalized_value = normalize_text(str(retry_route_frame.get(key) or ""))
        if normalized_value:
            anchor_texts.append((normalized_value, "route_frame"))
    route_area = normalize_text(str(route_meta.get("route_area") or ""))
    if route_area:
        for segment in re.split(r"[、,，/\-|—]|或|或者|以及|及|和|至", route_area):
            normalized_segment = normalize_text(segment)
            if normalized_segment:
                anchor_texts.append((normalized_segment, "route_meta"))
    anchor_texts.extend(
        (normalize_text(str(item.get("q") or "")), "query")
        for item in (existing_queries or [])
        if isinstance(item, dict) and normalize_text(str(item.get("q") or ""))
    )
    if not any(kind == "query" for _text, kind in anchor_texts):
        anchor_texts.extend([(claim, "fallback"), (question, "fallback")])
    zh_anchor_terms: List[str] = []
    en_anchor_terms: List[str] = []
    for text, source_kind in anchor_texts:
        normalized = normalize_text(text)
        if not normalized:
            continue
        tokens = []
        if source_kind == "route_meta":
            tokens.append(normalized)
        elif source_kind == "query" and " " in normalized:
            tokens.extend(part for part in normalized.split() if normalize_text(part))
        elif any("\u4e00" <= ch <= "\u9fff" for ch in normalized):
            tokens.extend(compact_query_seed_tokens(normalized, 12))
            tokens.extend(query_core_tokens(normalized))
        else:
            tokens.extend(query_core_tokens(normalized))
        for token in tokens:
            anchor_token = normalize_location_anchor_token(token)
            if not location_anchor_token_allowed(anchor_token, stop_terms):
                continue
            if any("\u4e00" <= ch <= "\u9fff" for ch in anchor_token):
                append_query_term_unique(zh_anchor_terms, anchor_token)
            elif re.search(r"[A-Za-z]", anchor_token):
                append_query_term_unique(en_anchor_terms, anchor_token)
        if len(zh_anchor_terms) >= 5 and len(en_anchor_terms) >= 5:
            break
    zh_anchor_terms = zh_anchor_terms[:5]
    en_anchor_terms = en_anchor_terms[:5]
    page_phrases = {
        "zh": page_intent_query_phrases(needed_page_type, "zh"),
        "en": page_intent_query_phrases(needed_page_type, "en"),
    }
    return {
        "needed_page_type": needed_page_type,
        "route_medium": route_context.get("route_medium") or "generic",
        "object_terms": object_terms,
        "object_terms_en": object_terms_en,
        "zh_anchor_terms": zh_anchor_terms,
        "en_anchor_terms": en_anchor_terms,
        "page_phrases": page_phrases,
        "llm_route_frame_object": normalize_text(str(retry_route_frame.get("object_or_area") or "")),
        "llm_route_frame_subject": normalize_text(str(retry_route_frame.get("subject") or "")),
        "zh_anchor_ready": len(zh_anchor_terms) >= 2,
        "en_anchor_ready": len(en_anchor_terms) >= 2,
    }


def normalize_location_anchor_token(token: str) -> str:
    normalized = normalize_text(token)
    if normalized in LOCATION_SPATIAL_MODIFIER_TOKENS:
        return ""
    for suffix in LOCATION_SPATIAL_MODIFIER_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def location_anchor_token_allowed(token: str, stop_terms: set[str]) -> bool:
    lowered = normalize_text(token).lower()
    if not lowered or lowered in stop_terms or re.fullmatch(r"\d{4}", token):
        return False
    if token in LOCATION_SPATIAL_MODIFIER_TOKENS:
        return False
    if token in ROUTE_FRAME_GENERIC_SKIP:
        return False
    return True


def route_frame_probe_query(
    frame: Dict[str, Any],
    language: str,
    extra_terms: Optional[List[str]] = None,
    total_limit: int = 8,
) -> str:
    language = normalize_text(language).lower()
    anchor_terms = frame.get("en_anchor_terms") if language == "en" else frame.get("zh_anchor_terms")
    if not isinstance(anchor_terms, list) or len(anchor_terms) < 2:
        return ""
    object_terms = frame.get("object_terms_en") if language == "en" else frame.get("object_terms")
    page_phrases = frame.get("page_phrases") if isinstance(frame.get("page_phrases"), dict) else {}
    phrase_list = page_phrases.get(language) if isinstance(page_phrases.get(language), list) else []
    terms: List[str] = []
    for token in anchor_terms[:4]:
        append_query_term_unique(terms, str(token))
    for token in (object_terms or [])[:1]:
        append_query_term_unique(terms, str(token))
    if phrase_list:
        append_query_term_unique(terms, str(phrase_list[0]))
    for token in extra_terms or []:
        append_query_term_unique(terms, str(token))
    query = " ".join(term for term in terms if normalize_text(term))
    query = compact_text_for_query(query, 96)
    split_terms = query.split()
    if language == "en":
        if len(split_terms) < 3:
            return ""
        return " ".join(split_terms[:total_limit])
    if len(split_terms) < 3:
        return ""
    return compact_text_for_query(" ".join(split_terms[: min(total_limit, 6)]), 96)


def should_use_gap_driven_page_brief(source_intent: Dict[str, Any]) -> bool:
    if not ENABLE_PAGE_SHAPE_LLM_BRIDGE:
        return False
    if not isinstance(source_intent, dict) or not source_intent.get("_is_retry"):
        return False
    if str(source_intent.get("evidence_mode") or "") != "route_fact":
        return False
    actions = source_intent.get("_retry_recommended_actions") if isinstance(source_intent.get("_retry_recommended_actions"), list) else []
    if not any(action in {"add_gap_query", "re_retrieve_with_page_intent", "change_source_plan"} for action in actions):
        return False
    stage = str(source_intent.get("_retry_retrieval_quality_stage") or "")
    return stage in {"search_recall", "page_retention", "sentence_readiness"}


def fallback_gap_driven_page_brief(
    question: str,
    claim: str,
    source_intent: Dict[str, Any],
    existing_queries: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, str]:
    page_intent = normalize_page_intent(source_intent)
    gap_flags = source_intent.get("_retry_gap_flags") if isinstance(source_intent.get("_retry_gap_flags"), list) else []
    stage = str(source_intent.get("_retry_retrieval_quality_stage") or "")
    route_context = route_medium_context(question, claim, source_intent, existing_queries)
    route_meta = source_intent.get("route_meta") if isinstance(source_intent.get("route_meta"), dict) else {}
    anchor_terms = dedupe_keep_order(
        [
            normalize_text(str(route_meta.get("origin") or "")),
            normalize_text(str(route_meta.get("destination") or "")),
            normalize_text(str(route_meta.get("route_area") or "")),
        ]
    )
    object_terms = route_query_object_terms(
        [
            question,
            claim,
            " ".join(normalize_text(str(item.get("q") or "")) for item in (existing_queries or []) if isinstance(item, dict)),
        ],
        limit=2,
    )
    page_focus: List[str] = []
    sentence_focus: List[str] = []
    avoid_focus: List[str] = []

    if stage == "search_recall" or "no_search_result" in gap_flags:
        page_focus.append("body-rich route explainer page")
    if stage == "page_retention" or any(flag in gap_flags for flag in {"background_dominant", "poor_page_type", "all_filtered"}):
        page_focus.append("analysis/detail page rather than live updates or summary roundup")
    if "utility_judge_conflict" in gap_flags:
        page_focus.append("route explainer page whose body focuses on the path, not event reporting with incidental route sentences")
    if stage == "sentence_readiness" or any(flag in gap_flags for flag in {"no_direct_sentence", "thin_direct_evidence"}):
        page_focus.append("page with readable body paragraphs and direct route sentences")

    if "missing_relation" in gap_flags:
        sentence_focus.append("one neutral sentence where object, area and route relation appear together")
    if "missing_object" in gap_flags:
        sentence_focus.append("one sentence explicitly naming the route object and the passage area")
    if not sentence_focus:
        sentence_focus.append("one direct sentence explaining whether the route passed through the area")

    if any(flag in gap_flags for flag in {"background_dominant", "poor_page_type"}):
        avoid_focus.append("live updates, landing pages, timeline summaries")
    if "utility_judge_conflict" in gap_flags:
        avoid_focus.append("event reports where route words appear only as background or incidental fragments")
    if "weak_source_only" in gap_flags or "low_source_quality" in gap_flags:
        avoid_focus.append("forums, generic aggregators, entity-only pages")
    if not avoid_focus:
        avoid_focus.append("pages with only event outcome and no route explanation")

    needed_page_type = str(page_intent.get("needed_page_type") or "route_analysis_page")
    answer_target = "verify_route_relation"
    required_sentence_shape = "subject + route/transit relation + intermediate place/object in an extractable sentence"
    reject_shape = "only strike/result/interception/background reporting, with route mentioned incidentally"
    medium_suffix = normalize_text(str(route_context.get("suffix_en") or route_context.get("suffix_zh") or ""))
    page_brief = compact_text_for_query(
        " ; ".join(
            part
            for part in [
                f"target page type: {needed_page_type}",
                f"page focus: {' ; '.join(page_focus[:2])}" if page_focus else "",
                f"route medium: {route_context.get('route_medium')}" if route_context.get("route_medium") else "",
                f"anchors: {', '.join(anchor_terms[:3])}" if anchor_terms else "",
                f"medium hint: {medium_suffix}" if medium_suffix else "",
            ]
            if normalize_text(part)
        ),
        220,
    )
    target_sentence = compact_text_for_query(" ; ".join(sentence_focus[:2]), 180)
    avoid = compact_text_for_query(" ; ".join(avoid_focus[:2]), 160)
    query_hint_parts = dedupe_keep_order(anchor_terms[:3] + object_terms[:1] + [medium_suffix])
    query_hint = compact_text_for_query(" ".join(part for part in query_hint_parts if normalize_text(part)), 96)
    return {
        "page_brief": page_brief,
        "target_sentence": target_sentence,
        "avoid": avoid,
        "query_hint": query_hint,
        "answer_target": answer_target,
        "required_sentence_shape": required_sentence_shape,
        "reject_shape": reject_shape,
    }


def gap_driven_page_brief(
    question: str,
    claim: str,
    source_intent: Dict[str, Any],
    existing_queries: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, str]:
    if not isinstance(source_intent, dict) or str(source_intent.get("evidence_mode") or "") != "route_fact":
        return {}
    fallback = fallback_gap_driven_page_brief(question, claim, source_intent, existing_queries)
    if not should_use_gap_driven_page_brief(source_intent):
        return fallback
    strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
    languages = [str(item).lower() for item in strategy.get("languages") or []]
    llm_contract_focus = source_intent.get("_retry_contract_focus_llm") if isinstance(source_intent.get("_retry_contract_focus_llm"), dict) else {}
    gap_flags = source_intent.get("_retry_gap_flags") if isinstance(source_intent.get("_retry_gap_flags"), list) else []
    stage = str(source_intent.get("_retry_retrieval_quality_stage") or "")
    page_intent = normalize_page_intent(source_intent)
    existing_query_texts = [
        normalize_text(str(item.get("q") or ""))
        for item in (existing_queries or [])
        if isinstance(item, dict) and normalize_text(str(item.get("q") or ""))
    ]
    client = load_page_utility_llm_client()
    if client is None:
        return fallback
    system_prompt = (
        "你是 AFC 检索阶段的 gap-driven page brief planner。"
        "目标是根据当前检索失败画像，生成很短的目标页面说明。"
        "只输出 JSON 对象，不要输出解释。"
    )
    user_prompt = f"""请根据下面信息，生成一份很短的页面检索 brief。

要求：
1. 只输出 JSON：{{"page_brief":"...","target_sentence":"...","avoid":"...","query_hint":"...","answer_target":"...","required_sentence_shape":"...","reject_shape":"..."}}。
2. page_brief 只描述“想找什么页面”，不要复述整条 claim。
3. target_sentence 只描述“网页里理想的可裁决句应该长什么样”。
4. avoid 只写应该避开的噪声页面类型。
5. query_hint 只写一个短的搜索短语，不要写成长句。
6. answer_target / required_sentence_shape / reject_shape 必须沿用 fallback_brief 的合同口径，不要改成支持原 claim 的单边句式。
7. 不要输出 site:，不要判断真假。

[retrieval_stage]
{stage}

[gap_flags]
{", ".join(gap_flags[:6])}

[languages]
{", ".join(languages[:2])}

[page_intent]
{json.dumps(page_intent, ensure_ascii=False)}

[question]
{question}

[claim]
{claim}

[existing_queries]
{json.dumps(existing_query_texts[:4], ensure_ascii=False)}

[llm_contract_focus]
{json.dumps(llm_contract_focus, ensure_ascii=False)}

[fallback_brief]
{json.dumps(fallback, ensure_ascii=False)}
"""
    cache_hit = cache_get("gap_page_brief", PAGE_UTILITY_LLM_MODEL, system_prompt, user_prompt)

    def sanitize_gap_brief(data: Dict[str, Any]) -> Dict[str, str]:
        if not isinstance(data, dict):
            return fallback
        contract_fallback = llm_contract_focus if llm_contract_focus else fallback
        out = {
            "page_brief": compact_text_for_query(normalize_text(str(data.get("page_brief") or contract_fallback.get("page_brief") or "")), 220),
            "target_sentence": compact_text_for_query(normalize_text(str(data.get("target_sentence") or contract_fallback.get("target_sentence") or "")), 180),
            "avoid": compact_text_for_query(normalize_text(str(data.get("avoid") or contract_fallback.get("avoid") or "")), 160),
            "query_hint": compact_text_for_query(normalize_text(str(data.get("query_hint") or fallback.get("query_hint") or "")), 96),
            "answer_target": compact_text_for_query(normalize_text(str(data.get("answer_target") or contract_fallback.get("answer_target") or "")), 80),
            "required_sentence_shape": compact_text_for_query(normalize_text(str(data.get("required_sentence_shape") or contract_fallback.get("required_sentence_shape") or "")), 160),
            "reject_shape": compact_text_for_query(normalize_text(str(data.get("reject_shape") or contract_fallback.get("reject_shape") or "")), 160),
        }
        if not out["page_brief"]:
            out["page_brief"] = contract_fallback.get("page_brief", "")
        if not out["target_sentence"]:
            out["target_sentence"] = contract_fallback.get("target_sentence", "")
        if not out["avoid"]:
            out["avoid"] = contract_fallback.get("avoid", "")
        if not out["query_hint"]:
            out["query_hint"] = fallback.get("query_hint", "")
        if not out["answer_target"]:
            out["answer_target"] = contract_fallback.get("answer_target", "")
        if not out["required_sentence_shape"]:
            out["required_sentence_shape"] = contract_fallback.get("required_sentence_shape", "")
        if not out["reject_shape"]:
            out["reject_shape"] = contract_fallback.get("reject_shape", "")
        return out

    if isinstance(cache_hit, dict):
        return sanitize_gap_brief(cache_hit)
    try:
        response = client.chat.completions.create(
            model=PAGE_UTILITY_LLM_MODEL,
            temperature=0,
            max_tokens=220,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        data = extract_json_object(raw)
    except Exception:
        return fallback
    if not isinstance(data, dict):
        return fallback
    cache_set("gap_page_brief", data, PAGE_UTILITY_LLM_MODEL, system_prompt, user_prompt)
    return sanitize_gap_brief(data)


def page_shape_llm_bridge_candidate(
    question: str,
    claim: str,
    source_intent: Dict[str, Any],
    existing_queries: Optional[List[Dict[str, str]]] = None,
    goal: str = "find_page_intent_page",
    suffix_text: str = "",
    gap_brief: Optional[Dict[str, str]] = None,
) -> str:
    if not ENABLE_PAGE_SHAPE_LLM_BRIDGE:
        return ""
    page_intent = normalize_page_intent(source_intent)
    needed_page_type = str(page_intent.get("needed_page_type") or "")
    if not needed_page_type or needed_page_type == "general_page":
        return ""
    strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
    languages = [str(item).lower() for item in strategy.get("languages") or []]
    existing_query_texts = [
        normalize_text(str(item.get("q") or ""))
        for item in (existing_queries or [])
        if isinstance(item, dict) and normalize_text(str(item.get("q") or ""))
    ]
    target_language = "en" if "en" in languages or any(re.search(r"[A-Za-z]{3,}", text) for text in existing_query_texts) else "zh"
    if target_language == "en":
        seed_query = next((text for text in existing_query_texts if re.search(r"[A-Za-z]{3,}", text)), "")
    else:
        seed_query = next((text for text in existing_query_texts if any("\u4e00" <= ch <= "\u9fff" for ch in text)), "")
    gap_brief = gap_brief if isinstance(gap_brief, dict) else {}
    gap_page_brief = normalize_text(str(gap_brief.get("page_brief") or ""))
    gap_target_sentence = normalize_text(str(gap_brief.get("target_sentence") or ""))
    gap_avoid = normalize_text(str(gap_brief.get("avoid") or ""))
    gap_query_hint = normalize_text(str(gap_brief.get("query_hint") or ""))
    gap_answer_target = normalize_text(str(gap_brief.get("answer_target") or ""))
    gap_required_sentence_shape = normalize_text(str(gap_brief.get("required_sentence_shape") or ""))
    gap_reject_shape = normalize_text(str(gap_brief.get("reject_shape") or ""))
    if not seed_query and gap_query_hint:
        seed_query = gap_query_hint
    if not seed_query:
        seed_query = compact_text_for_query(strip_numeric_values(claim) or claim, 72)
    if not seed_query:
        return ""
    page_markers = page_intent_markers(needed_page_type)
    page_phrases = page_intent_query_phrases(needed_page_type, target_language)
    must_contain = [normalize_text(str(item)) for item in page_intent.get("must_contain") or [] if normalize_text(str(item))]
    evidence_shape = str(page_intent.get("evidence_shape") or normalize_evidence_shape(source_intent))
    system_prompt = (
        "你是 AFC 检索阶段的 page-shape query bridge。"
        "目标是生成一条短搜索查询，让搜索更容易命中指定页面类型。"
        "只输出 JSON 对象，不要输出解释。"
    )
    user_prompt = f"""请根据下面信息生成 1 条页面检索查询。

要求：
1. 只输出 JSON：{{"search_query": "...", "why": "..."}}。
2. 查询应更像用户会搜的页面短语，不要堆很多同义词。
3. 重点保留：主体、关键对象、页面类型线索。
4. 如果 target_language 为 en，请输出英文短查询；如果为 zh，请输出中文短查询。
5. 不要输出 site: 限制，不要输出解释句。

[goal]
{goal}

[target_language]
{target_language}

[needed_page_type]
{needed_page_type}

[evidence_shape]
{evidence_shape}

[question]
{question}

[claim]
{claim}

[seed_query]
{seed_query}

[page_markers]
{", ".join(page_markers[:4])}

[page_phrases]
{", ".join(page_phrases[:3])}

[page_suffix]
{suffix_text}

[must_contain]
{", ".join(must_contain[:2])}

[gap_page_brief]
{gap_page_brief}

[gap_target_sentence]
{gap_target_sentence}

[gap_avoid]
{gap_avoid}

[gap_query_hint]
{gap_query_hint}

[gap_answer_target]
{gap_answer_target}

[gap_required_sentence_shape]
{gap_required_sentence_shape}

[gap_reject_shape]
{gap_reject_shape}
"""
    cache_hit = cache_get("page_shape_query_bridge", PAGE_UTILITY_LLM_MODEL, system_prompt, user_prompt)

    def sanitize_page_shape_bridge_query(query: str) -> str:
        query = compact_text_for_query(normalize_text(query), 96)
        if not query:
            return ""
        if target_language == "en":
            tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]*|\d{4}", query)
            cleaned_terms: List[str] = []
            for token in tokens:
                append_query_term_unique(cleaned_terms, token)
            query = " ".join(cleaned_terms[:10])
            if len(cleaned_terms) < 3:
                return ""
            return query
        if not any("\u4e00" <= ch <= "\u9fff" for ch in query):
            return ""
        if len(query) < 4:
            return ""
        return query

    if isinstance(cache_hit, dict):
        return sanitize_page_shape_bridge_query(str(cache_hit.get("search_query") or ""))
    client = load_page_utility_llm_client()
    if client is None:
        return ""
    try:
        response = client.chat.completions.create(
            model=PAGE_UTILITY_LLM_MODEL,
            temperature=0,
            max_tokens=160,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        data = extract_json_object(raw)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    cache_set("page_shape_query_bridge", data, PAGE_UTILITY_LLM_MODEL, system_prompt, user_prompt)
    return sanitize_page_shape_bridge_query(str(data.get("search_query") or ""))


QUERY_ORIGIN_BASE_PRIORITY = {
    "planner": 100,
    "fact_slot_query": 98,
    "preferred_domain_probe": 92,
    "semantic_task_probe": 91,
    "structured_point_retry": 90,
    "metric_source_probe": 88,
    "gap_pseudo_page_probe": 86,
    "page_intent_retry": 84,
    "route_frame_probe": 83,
    "page_shape_probe": 82,
    "numeric_discovery": 74,
    "specialized_lexical": 70,
    "lexical_fallback": 66,
    "qa": 58,
}


def with_query_origin(items: List[Dict[str, Any]], origin: str) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        current = dict(item)
        if not normalize_text(str(current.get("origin") or "")):
            current["origin"] = origin
        enriched.append(current)
    return enriched


def retry_operator_priority_bonus(item: Dict[str, Any], source_intent: Optional[Dict[str, Any]] = None) -> int:
    if not isinstance(source_intent, dict):
        return 0
    origin = normalize_text(str(item.get("origin") or ""))
    variant = normalize_text(str(item.get("variant") or ""))
    primary_origin = normalize_text(str(source_intent.get("_retry_operator_origin") or ""))
    variant_hint = normalize_text(str(source_intent.get("_retry_operator_variant_hint") or ""))
    supporting_raw = source_intent.get("_retry_operator_supporting_origins") if isinstance(source_intent.get("_retry_operator_supporting_origins"), list) else []
    supporting_origins = {
        normalize_text(str(value))
        for value in supporting_raw
        if normalize_text(str(value))
    }
    bonus = 0
    if primary_origin and origin == primary_origin:
        bonus += 10
        if variant_hint and variant == variant_hint:
            bonus += 4
    elif origin and origin in supporting_origins:
        bonus += 5
    return bonus


def query_priority_score(item: Dict[str, Any], evidence_mode: str = "", source_intent: Optional[Dict[str, Any]] = None) -> int:
    mode = policy_mode_label(evidence_mode)
    origin = normalize_text(str(item.get("origin") or "")) or "planner"
    goal = normalize_text(str(item.get("goal") or "general_verify")) or "general_verify"
    query = normalize_text(str(item.get("q") or ""))
    variant = normalize_text(str(item.get("variant") or ""))
    source_preference = item.get("source_preference") if isinstance(item.get("source_preference"), list) else []
    score = int(QUERY_ORIGIN_BASE_PRIORITY.get(origin, 60))
    if goal == "find_preferred_domain" or origin == "preferred_domain_probe":
        score += 14
    if source_preference:
        score += 4
    if goal in {"discover_truth", "find_news", "verify_original", "find_context"}:
        score += 3
    if goal == "find_metric_source_page" or origin == "metric_source_probe":
        score += 8 if is_structured_fact_mode(mode) else 4
    if goal == "find_atomic_refutation" or origin == "atomic_claim_query":
        score += 9
    if is_route_like_mode(mode) and goal in {"find_route_page", "find_route"}:
        score += 4
    if is_route_like_mode(mode) and origin in {"route_frame_probe", "gap_pseudo_page_probe", "page_shape_probe", "page_intent_retry"}:
        score += 2
    if goal == "verification_question":
        score -= 2
    if origin == "structured_point_retry" and variant == "dated_record":
        score += 3
    elif origin == "structured_point_retry" and variant == "history":
        score += 2
    score += retry_operator_priority_bonus(item, source_intent)
    site_constraint = extract_site_constraint(query)
    preferred_domains = preferred_domains_from_intent(source_intent or {})
    if site_constraint and goal != "find_preferred_domain" and origin != "preferred_domain_probe":
        if preferred_domains and any(normalize_domain(site_constraint) == normalize_domain(domain) for domain in preferred_domains):
            score += 4
        else:
            score -= 6
    return score


def normalize_query_items(raw_queries: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for raw_query in raw_queries or []:
        if isinstance(raw_query, str):
            query_text = normalize_text(raw_query)
            if query_text:
                normalized.append({"q": query_text, "goal": "general_verify", "origin": "planner"})
        elif isinstance(raw_query, dict):
            query_text = normalize_text(str(raw_query.get("q") or raw_query.get("query") or ""))
            if query_text:
                query_item: Dict[str, Any] = {
                    "q": query_text,
                    "goal": normalize_text(str(raw_query.get("goal") or "general_verify")) or "general_verify",
                    "origin": normalize_text(str(raw_query.get("origin") or "")) or "planner",
                }
                raw_preference = raw_query.get("source_preference") if isinstance(raw_query.get("source_preference"), list) else []
                source_preference = [normalize_text(str(item)) for item in raw_preference if normalize_text(str(item))][:3]
                if source_preference:
                    query_item["source_preference"] = source_preference
                for extra_key in ("operator", "variant", "gap_flag", "query_variant_origin", "atomic_claim_id", "atomic_risk_type", "atomic_claim_text"):
                    extra_value = normalize_text(str(raw_query.get(extra_key) or ""))
                    if extra_value:
                        query_item[extra_key] = extra_value
                if raw_query.get("atomic_query"):
                    query_item["atomic_query"] = True
                normalized.append(query_item)
    deduped: List[Dict[str, str]] = []
    seen = set()
    for item in normalized:
        key = (item["q"], item["goal"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[: max(1, MAX_QUERIES_PER_CLAIM)]


EVIDENCE_SHAPE_TYPES = {
    "authoritative_notice",
    "structured_historical_data",
    "event_detail_page",
    "current_status_update",
    "open_news_analysis",
    "general_evidence_page",
}

RETRIEVAL_PROFILE_CONFIGS = {
    "default": {
        "required_goals": [],
        "prefer_lexical_anchor": False,
        "query_frames": [],
        "goal_sources": {},
    },
    "structured_fact": {
        "required_goals": [],
        "prefer_lexical_anchor": False,
        "query_frames": [
            {
                "goal": "find_page_intent_page",
                "suffix_zh": "历史 数据 表 详情",
                "suffix_en": "historical data table details",
            }
        ],
        "goal_sources": {
            "verification_question": {
                "prepend_preferred_domain": True,
                "default": ["bing_html", "sogou_html", "bing_rss", "bing_news_zh_rss", "bing_news_rss", "duckduckgo_html"],
            },
        },
    },
    "authoritative_notice": {
        "required_goals": [],
        "prefer_lexical_anchor": False,
        "query_frames": [
            {
                "goal": "find_page_intent_page",
                "suffix_zh": "官方 公告 通知 声明",
                "suffix_en": "official announcement notice statement",
            }
        ],
        "goal_sources": {
            "verification_question": {
                "prepend_preferred_domain": True,
                "default": ["bing_html", "sogou_html", "bing_rss", "bing_news_zh_rss", "bing_news_rss", "duckduckgo_html"],
            },
        },
    },
    "event_detail": {
        "required_goals": [],
        "prefer_lexical_anchor": False,
        "query_frames": [
            {
                "goal": "find_page_intent_page",
                "suffix_zh": "详情 战报 结果 页面",
                "suffix_en": "event detail recap result page",
            }
        ],
        "goal_sources": {
            "verification_question": {
                "default": ["bing_html", "bing_news_zh_rss", "bing_rss", "sogou_html", "bing_news_rss", "duckduckgo_html"],
                "english": ["bing_html", "bing_news_rss", "bing_rss", "bing_news_zh_rss", "sogou_html", "duckduckgo_html"],
            },
        },
    },
    "current_status": {
        "required_goals": [],
        "prefer_lexical_anchor": False,
        "query_frames": [
            {
                "goal": "find_page_intent_page",
                "suffix_zh": "当前 状态 位置 跟踪",
                "suffix_en": "current status position tracking",
            }
        ],
        "goal_sources": {
            "verification_question": {
                "default": ["bing_news_zh_rss", "bing_rss", "bing_html", "sogou_html", "bing_news_rss", "duckduckgo_html"],
                "english": ["bing_news_rss", "bing_rss", "bing_html", "bing_news_zh_rss", "sogou_html", "duckduckgo_html"],
            },
        },
    },
    "open_analysis": {
        "required_goals": [],
        "prefer_lexical_anchor": False,
        "query_frames": [
            {
                "goal": "find_page_intent_page",
                "suffix_zh": "分析 解读 详情 页面",
                "suffix_en": "analysis explainer detail page",
            }
        ],
        "goal_sources": {
            "verification_question": {
                "default": ["bing_news_zh_rss", "bing_news_rss", "bing_html", "bing_rss", "duckduckgo_html", "sogou_html"],
                "english": ["bing_news_rss", "bing_news_zh_rss", "bing_html", "bing_rss", "duckduckgo_html", "sogou_html"],
            },
        },
    },
    "route_relation": {
        "required_goals": ["find_route_page"],
        "prefer_lexical_anchor": True,
        "query_frames": [],
        "goal_sources": {
            "find_route_page": {
                "default": ["bing_html", "duckduckgo_html", "bing_news_zh_rss", "bing_news_rss", "bing_rss", "sogou_html"],
                "english": ["bing_news_rss", "bing_rss", "bing_html", "bing_news_zh_rss", "duckduckgo_html", "sogou_html"],
            },
            "verification_question": {
                "default": ["bing_news_zh_rss", "bing_news_rss", "bing_rss", "bing_html", "duckduckgo_html", "sogou_html"],
                "english": ["bing_news_rss", "bing_news_zh_rss", "bing_rss", "bing_html", "duckduckgo_html", "sogou_html"],
            },
        },
    },
}


def normalize_evidence_shape(source_intent: Dict[str, Any]) -> str:
    shape = str(
        source_intent.get("evidence_shape")
        or source_intent.get("evidence_page_shape")
        or ""
    ).strip()
    mechanism_type = mechanism_type_from_intent(source_intent)
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    if shape == "general_evidence_page" and (mode == "route_fact" or target == "route_relation" or mechanism_type == "relation_sentence"):
        return "open_news_analysis"
    if shape in EVIDENCE_SHAPE_TYPES and shape != "general_evidence_page":
        return shape
    page_intent = source_intent.get("page_intent") if isinstance(source_intent.get("page_intent"), dict) else {}
    page_type = str(page_intent.get("needed_page_type") or "").strip()
    if page_type in {"official_notice", "award_detail", "calendar_page"}:
        return "authoritative_notice"
    if page_type in {"historical_table", "quote_page"}:
        return "structured_historical_data"
    if page_type in {"event_detail", "result_page"}:
        return "event_detail_page"
    if page_type == "current_status_page":
        return "current_status_update"
    if target in {"market_price", "prize_amount"} or mode in {"numeric_fact", "date_fact", "schedule_fact"}:
        return "structured_historical_data"
    if target in {"market_calendar", "census_phase"}:
        return "authoritative_notice"
    if target in {"match_result", "withdrawal_status"} or mode == "event_result":
        return "event_detail_page"
    if target in {"position_distance", "current_status"}:
        return "current_status_update"
    if mode in {"route_fact", "policy_fact"} or target == "route_relation" or mechanism_type == "relation_sentence":
        return "open_news_analysis"
    return "general_evidence_page"


def prefers_body_rich_sources(source_intent: Dict[str, Any]) -> bool:
    mechanism_type = mechanism_type_from_intent(source_intent)
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    if mode == "route_fact" or target == "route_relation" or mechanism_type == "relation_sentence":
        return True
    page_intent = source_intent.get("page_intent") if isinstance(source_intent.get("page_intent"), dict) else {}
    needed_page_type = str(page_intent.get("needed_page_type") or "").strip()
    return needed_page_type in {"route_analysis_page", "route_passage_page", "event_detail_page", "result_page"}


def retrieval_profile_name(source_intent: Dict[str, Any]) -> str:
    mechanism_type = mechanism_type_from_intent(source_intent)
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    if mechanism_type == "relation_sentence" or (mode == "route_fact" and target == "route_relation"):
        return "route_relation"
    if mechanism_type == "structured_numeric_authority":
        return "structured_fact"
    if mechanism_type == "date_authority":
        return "authoritative_notice"
    if mechanism_type == "event_result_page":
        return "event_detail"
    if mechanism_type == "current_status_update":
        return "current_status"
    shape = normalize_evidence_shape(source_intent)
    shape_map = {
        "structured_historical_data": "structured_fact",
        "authoritative_notice": "authoritative_notice",
        "event_detail_page": "event_detail",
        "current_status_update": "current_status",
        "open_news_analysis": "open_analysis",
    }
    return shape_map.get(shape, "default")


def retrieval_profile(source_intent: Dict[str, Any]) -> Dict[str, Any]:
    name = retrieval_profile_name(source_intent)
    raw = RETRIEVAL_PROFILE_CONFIGS.get(name, RETRIEVAL_PROFILE_CONFIGS["default"])
    goal_sources: Dict[str, Dict[str, Any]] = {}
    for goal, config in (raw.get("goal_sources") or {}).items():
        if not isinstance(config, dict):
            continue
        goal_sources[goal] = {
            key: (list(value) if isinstance(value, list) else value)
            for key, value in config.items()
        }
    return {
        "name": name,
        "required_goals": list(raw.get("required_goals") or []),
        "prefer_lexical_anchor": bool(raw.get("prefer_lexical_anchor")),
        "query_frames": [dict(item) for item in raw.get("query_frames") or [] if isinstance(item, dict)],
        "goal_sources": goal_sources,
    }


def mechanism_type_from_intent(source_intent: Dict[str, Any]) -> str:
    if not isinstance(source_intent, dict):
        return "general_web_evidence"
    mechanism_type = normalize_text(str(source_intent.get("mechanism_type") or ""))
    if mechanism_type in VERIFICATION_MECHANISM_TYPES:
        return mechanism_type
    metric_slots = metric_slots_from_intent(source_intent)
    value_type = normalize_text(str((metric_slots or {}).get("value_type") or ""))
    if value_type and value_type != "not_metric":
        return "structured_numeric_authority"
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    shape = str(source_intent.get("evidence_shape") or "")
    if mode in {"date_fact", "schedule_fact"}:
        return "date_authority"
    if mode == "event_result" or target in {"match_result", "withdrawal_status"}:
        return "event_result_page"
    if mode == "route_fact" or target == "route_relation":
        return "relation_sentence"
    if target == "current_status" or shape == "current_status_update":
        return "current_status_update"
    if mode in {"numeric_fact"}:
        return "structured_numeric_authority"
    return "general_web_evidence"


def relation_sentence_intent(source_intent: Dict[str, Any]) -> bool:
    mechanism_type = mechanism_type_from_intent(source_intent)
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    return mechanism_type == "relation_sentence" or mode == "route_fact" or target == "route_relation"


def structured_numeric_intent(source_intent: Dict[str, Any]) -> bool:
    mechanism_type = mechanism_type_from_intent(source_intent)
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    metric_slots = metric_slots_from_intent(source_intent)
    return mechanism_type == "structured_numeric_authority" or bool(metric_slots) or mode in {"numeric_fact", "date_fact", "schedule_fact"} or target in {"market_price", "market_calendar", "prize_amount", "position_distance"}


def source_enabled_for_query(source_name: str) -> bool:
    if source_name == "bing_html":
        return ENABLE_BING_HTML or ENABLE_QA_BING_HTML
    if source_name == "duckduckgo_html":
        return ENABLE_DUCKDUCKGO
    if source_name == "playwright_duckduckgo":
        return ENABLE_PLAYWRIGHT
    return True


def html_search_available() -> bool:
    return source_enabled_for_query("bing_html")


def profile_sources_for_goal(profile: Dict[str, Any], goal: str, query: str, source_intent: Dict[str, Any]) -> List[str]:
    goal_sources = profile.get("goal_sources") if isinstance(profile.get("goal_sources"), dict) else {}
    config = goal_sources.get(goal) if isinstance(goal_sources.get(goal), dict) else {}
    if not config:
        return []
    language_key = "english" if is_english_query(query) else "default"
    sources = list(config.get(language_key) or config.get("default") or [])
    if config.get("prepend_preferred_domain") and preferred_domains_from_intent(source_intent):
        sources = ["domain_sitemap"] + sources
    return dedupe_keep_order([source for source in sources if source_enabled_for_query(source)])


def evidence_shape_source_order(shape: str, has_preferred_domains: bool, source_intent: Optional[Dict[str, Any]] = None) -> List[str]:
    site_first = ["domain_sitemap"] if has_preferred_domains else []
    body_rich_first = prefers_body_rich_sources(source_intent or {})
    news_first = prefer_news_first_for_intent(source_intent or {})
    if shape == "structured_historical_data":
        if news_first:
            return dedupe_keep_order(site_first + ["bing_news_zh_rss", "bing_news_rss", "bing_html", "sogou_html", "bing_rss", "duckduckgo_html"])
        return dedupe_keep_order(site_first + ["bing_html", "sogou_html", "bing_rss", "duckduckgo_html", "bing_news_rss", "bing_news_zh_rss"])
    if shape == "authoritative_notice":
        if news_first:
            return dedupe_keep_order(site_first + ["bing_news_zh_rss", "bing_news_rss", "bing_html", "sogou_html", "bing_rss", "duckduckgo_html"])
        return dedupe_keep_order(site_first + ["bing_html", "sogou_html", "bing_rss", "bing_news_zh_rss", "bing_news_rss", "duckduckgo_html"])
    if shape == "event_detail_page":
        return dedupe_keep_order(["bing_html", "bing_news_rss", "bing_news_zh_rss", "sogou_html", "bing_rss", "duckduckgo_html"])
    if shape == "current_status_update":
        return dedupe_keep_order(["bing_news_rss", "bing_news_zh_rss", "bing_html", "sogou_html", "bing_rss", "duckduckgo_html"])
    if shape == "open_news_analysis":
        if body_rich_first:
            return dedupe_keep_order(site_first + ["bing_html", "sogou_html", "duckduckgo_html", "bing_news_rss", "bing_news_zh_rss", "bing_rss"])
        return dedupe_keep_order(["bing_news_rss", "bing_news_zh_rss", "bing_html", "sogou_html", "bing_rss", "duckduckgo_html"])
    return dedupe_keep_order(site_first + ["bing_rss", "bing_html", "sogou_html", "bing_news_rss", "bing_news_zh_rss", "duckduckgo_html"])


def reorder_sources_by_evidence_shape(sources: List[str], source_intent: Dict[str, Any]) -> List[str]:
    if not sources:
        return sources
    has_preferred_domains = bool(preferred_domains_from_intent(source_intent))
    order = evidence_shape_source_order(normalize_evidence_shape(source_intent), has_preferred_domains, source_intent)
    order_index = {source: index for index, source in enumerate(order)}
    return dedupe_keep_order(
        sorted(
            sources,
            key=lambda source: order_index.get(source, len(order_index) + sources.index(source)),
        )
    )


def reorder_sources_by_priority_order(sources: List[str], priority_order: List[str]) -> List[str]:
    if not sources:
        return sources
    order_index = {source: index for index, source in enumerate(priority_order)}
    return dedupe_keep_order(
        sorted(
            sources,
            key=lambda source: order_index.get(source, len(order_index) + sources.index(source)),
        )
    )


def retry_source_plan_policy(source_intent: Dict[str, Any]) -> str:
    if not isinstance(source_intent, dict) or not source_intent.get("_is_retry"):
        return ""
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    actions = source_intent.get("_retry_recommended_actions") if isinstance(source_intent.get("_retry_recommended_actions"), list) else []
    gap_flags = source_intent.get("_retry_gap_flags") if isinstance(source_intent.get("_retry_gap_flags"), list) else []
    stage = str(source_intent.get("_retry_retrieval_quality_stage") or "")
    if "change_source_plan" not in actions:
        return ""
    if stage == "page_retention" or any(flag in gap_flags for flag in {"background_dominant", "poor_page_type"}):
        return "route_page_intent_html_first" if evidence_mode == "route_fact" else "page_intent_html_first"
    if stage == "search_recall" or "no_search_result" in gap_flags:
        return "route_broaden_recall" if evidence_mode == "route_fact" else "broaden_recall"
    if "low_source_quality" in gap_flags:
        return "route_trusted_news_html" if evidence_mode == "route_fact" else "trusted_news_html"
    return "retry_source_reorder"


def apply_retry_source_plan_policy(sources: List[str], policy: str, source_intent: Dict[str, Any]) -> List[str]:
    if not sources or not policy:
        return sources
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    if policy in {"route_page_intent_html_first", "page_intent_html_first"}:
        priority = ["bing_html", "sogou_html"]
        if ENABLE_DUCKDUCKGO:
            priority.append("duckduckgo_html")
        if ENABLE_PLAYWRIGHT:
            priority.append("playwright_duckduckgo")
        priority.extend(["bing_news_rss", "bing_news_zh_rss", "bing_rss"])
        return reorder_sources_by_priority_order(dedupe_keep_order(sources + priority), priority)
    if policy in {"route_broaden_recall", "broaden_recall"}:
        priority = ["bing_news_rss", "bing_news_zh_rss", "bing_html", "sogou_html"]
        if ENABLE_DUCKDUCKGO:
            priority.append("duckduckgo_html")
        priority.append("bing_rss")
        return reorder_sources_by_priority_order(dedupe_keep_order(sources + priority), priority)
    if policy in {"route_trusted_news_html", "trusted_news_html"}:
        priority = ["bing_news_rss", "bing_news_zh_rss", "bing_html", "sogou_html"]
        if evidence_mode == "route_fact" and ENABLE_PLAYWRIGHT:
            priority.append("playwright_duckduckgo")
        return reorder_sources_by_priority_order(dedupe_keep_order(sources + priority), priority)
    return sources


def route_rss_fallback_allowed(source_intent: Dict[str, Any], query_goal: str = "") -> bool:
    if effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or "")) != "route_fact":
        return True
    source_strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
    strategy_channels = source_strategy.get("search_channels") if isinstance(source_strategy.get("search_channels"), list) else []
    if "general_search" in {str(item) for item in strategy_channels}:
        return True
    if not source_intent.get("_is_retry"):
        return False
    actions = source_intent.get("_retry_recommended_actions") if isinstance(source_intent.get("_retry_recommended_actions"), list) else []
    gap_flags = source_intent.get("_retry_gap_flags") if isinstance(source_intent.get("_retry_gap_flags"), list) else []
    stage = str(source_intent.get("_retry_retrieval_quality_stage") or "")
    if stage == "search_recall" or "no_search_result" in gap_flags:
        return True
    if "add_gap_query" in actions and query_goal in {"find_route_page", "find_route"}:
        return True
    return False


def finalize_route_source_plan(sources: List[str], source_intent: Dict[str, Any], query_goal: str = "") -> List[str]:
    if not sources:
        return sources
    cleaned = dedupe_keep_order(sources)
    goal = normalize_text(str(query_goal or "")) or "general_verify"
    if effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or "")) == "route_fact" and goal in {"find_route_page", "verification_question"}:
        return [source for source in cleaned if source != "bing_rss"]
    if route_rss_fallback_allowed(source_intent, query_goal):
        if "bing_rss" in cleaned:
            cleaned = [source for source in cleaned if source != "bing_rss"] + ["bing_rss"]
        return cleaned
    return [source for source in cleaned if source != "bing_rss"]


def source_plan_from_intent(question: str, claim: str, source_intent: Dict[str, Any]) -> List[str]:
    preferred = source_intent.get("preferred_source_types") if isinstance(source_intent, dict) else []
    if not isinstance(preferred, list):
        preferred = []
    evidence_mode = str(source_intent.get("evidence_mode") or "") if isinstance(source_intent, dict) else ""
    evidence_target = str(source_intent.get("evidence_target") or "") if isinstance(source_intent, dict) else ""
    is_retry = bool(source_intent.get("_is_retry")) if isinstance(source_intent, dict) else False
    source_strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
    strategy_channels = source_strategy.get("search_channels") if isinstance(source_strategy.get("search_channels"), list) else []
    strategy_source_types = source_strategy.get("source_types") if isinstance(source_strategy.get("source_types"), list) else []
    strategy_languages = source_strategy.get("languages") if isinstance(source_strategy.get("languages"), list) else []
    sources: List[str] = []
    if strategy_channels:
        has_preferred_domains = bool(preferred_domains_from_intent(source_intent))
        if "site_search" in strategy_channels and has_preferred_domains:
            sources.append("domain_sitemap")
        if "news_search" in strategy_channels:
            if "zh" in strategy_languages:
                sources.append("bing_news_zh_rss")
            sources.append("bing_news_rss")
        if "web_search" in strategy_channels:
            if html_search_available():
                sources.append("bing_html")
            sources.append("sogou_html")
            if ENABLE_DUCKDUCKGO:
                sources.append("duckduckgo_html")
        if "playwright_detail" in strategy_channels and ENABLE_PLAYWRIGHT:
            sources.append("playwright_duckduckgo")
        if "general_search" in strategy_channels:
            sources.append("bing_rss")
        if "encyclopedia" in strategy_source_types:
            sources.append("wikipedia")
        if "forum" not in strategy_source_types and evidence_mode in {"route_fact", "event_result", "policy_fact"}:
            sources = [source for source in sources if source != "bing_rss"] + (["bing_rss"] if "general_search" in strategy_channels else [])
    if evidence_mode == "route_fact" and is_retry:
        sources.extend(["bing_news_rss", "bing_news_zh_rss", "bing_html", "sogou_html"])
        if ENABLE_DUCKDUCKGO:
            sources.append("duckduckgo_html")
        sources.append("bing_rss")
    elif not sources and evidence_target in {"match_result", "withdrawal_status", "market_calendar", "census_phase", "position_distance", "current_status"}:
        sources.extend(["bing_news_zh_rss", "bing_news_rss", "bing_html", "sogou_html", "bing_rss"])
    elif not sources and html_search_available() and evidence_mode in {"route_fact", "event_result", "policy_fact"}:
        sources.extend(["bing_html", "sogou_html", "bing_news_rss"])
    elif not sources and ("official" in preferred or "news" in preferred):
        sources.extend(["bing_news_rss", "bing_rss", "sogou_html"])
    elif not sources and "encyclopedia" in preferred:
        sources.extend(["wikipedia", "bing_news_rss", "bing_rss", "sogou_html"])
    elif not sources and "forum" in preferred:
        sources.extend(["bing_news_rss", "bing_rss"])
    if prefer_news_first_for_intent(source_intent):
        news_priority = ["bing_news_zh_rss", "bing_news_rss", "bing_html", "sogou_html"]
        if ENABLE_DUCKDUCKGO:
            news_priority.append("duckduckgo_html")
        news_priority.append("bing_rss")
        sources = reorder_sources_by_priority_order(dedupe_keep_order(sources + news_priority), news_priority)
    if not sources:
        sources = choose_sources(claim, question, "")
    sources = reorder_sources_by_evidence_shape(dedupe_keep_order(sources), source_intent)
    sources = apply_retry_source_plan_policy(sources, retry_source_plan_policy(source_intent), source_intent)
    return finalize_route_source_plan(sources, source_intent)


def score_source_strategy(source_intent: Dict[str, Any], claim: str, question: str) -> Dict[str, Any]:
    strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
    if not strategy:
        return {
            "source_strategy_score": 0,
            "source_strategy_label": "bad",
            "source_strategy_issues": ["missing_source_strategy"],
            "source_strategy_components": {},
        }
    source_types = [str(item) for item in strategy.get("source_types") or []]
    channels = [str(item) for item in strategy.get("search_channels") or []]
    languages = [str(item) for item in strategy.get("languages") or []]
    must_have = [str(item) for item in strategy.get("must_have") or []]
    avoid_sources = [str(item) for item in strategy.get("avoid_sources") or []]
    why = normalize_text(str(strategy.get("why") or ""))
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    preferred_domains = preferred_domains_from_intent(source_intent)
    text = f"{question} {claim}".lower()
    issues: List[str] = []

    source_score = 0
    if source_types:
        source_score += 8
    if any(item in source_types for item in ["official", "news"]):
        source_score += 8
    if "forum" not in source_types:
        source_score += 4
    else:
        issues.append("source_strategy_uses_forum")

    channel_score = 0
    if channels:
        channel_score += 6
    if "news_search" in channels and evidence_mode in {"route_fact", "event_result", "policy_fact", "date_fact"}:
        channel_score += 5
    if any(item in channels for item in ["web_search", "playwright_detail"]):
        channel_score += 5
    if "site_search" not in channels or preferred_domains:
        channel_score += 4
    else:
        issues.append("site_search_without_domain")

    language_score = 0
    if languages:
        language_score += 4
    has_latin_or_foreign = bool(re.search(r"[A-Za-z]{3,}", text)) or evidence_mode in {"route_fact", "policy_fact"}
    if has_latin_or_foreign and "en" in languages:
        language_score += 4
    if "zh" in languages:
        language_score += 2

    route_context = route_medium_context(question, claim, source_intent) if evidence_mode == "route_fact" else {}
    route_mode_terms = dedupe_keep_order(
        re.split(
            r"\s+",
            " ".join(
                [
                    str(route_context.get("suffix_zh") or ""),
                    str(route_context.get("suffix_en") or ""),
                    "路线 route",
                ]
            ),
        )
    )
    binding_terms = source_strategy_binding_terms(source_intent, evidence_mode)
    must_score = 0
    if must_have:
        must_score += 8
    must_text = " ".join(must_have).lower()
    if any(token.lower() in must_text for token in query_core_tokens(claim)[:4]):
        must_score += 6
    mode_terms = {
        "route_fact": route_mode_terms or ["路线", "经过", "route", "passage"],
        "numeric_fact": ["数值", "金额", "价格", "比分", "涨幅", "rate", "amount", "score"],
        "date_fact": ["日期", "时间", "公布", "date", "time"],
        "event_result": ["结果", "发生", "胜负", "result"],
        "schedule_fact": ["日程", "赛程", "休市", "schedule"],
    }.get(evidence_mode, [])
    if any(term in must_text for term in mode_terms):
        must_score += 7
    binding_hits: List[str] = []
    for key, value in binding_terms.items():
        if binding_slot_present(must_text, key, value, source_intent, evidence_mode):
            binding_hits.append(key)
    if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result", "policy_fact", "entity_fact"}:
        weights = {
            "subject_entity": 5,
            "relation_or_metric": 5,
            "time_scope": 4,
            "authority_scope": 3,
            "expected_evidence_shape": 2,
            "unit": 2,
            "time_window": 2,
        }
        must_score += sum(weights.get(key, 1) for key in binding_hits)
        if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}:
            required_binding_keys = ["subject_entity", "relation_or_metric", "time_scope"]
            missing_binding = [key for key in required_binding_keys if binding_terms.get(key) and key not in binding_hits]
            if missing_binding:
                issues.append("structured_binding_slots_missing_in_must_have")
                must_score -= min(8, 2 * len(missing_binding))
        elif evidence_mode == "event_result":
            required_binding_keys = ["subject_entity", "time_scope"]
            missing_binding = [key for key in required_binding_keys if binding_terms.get(key) and key not in binding_hits]
            if missing_binding:
                issues.append("event_binding_slots_missing_in_must_have")
                must_score -= min(6, 2 * len(missing_binding))
    if must_have and not any(item in {"相关信息", "新闻报道", "资料", "information", "news"} for item in must_have):
        must_score += 4
    else:
        issues.append("must_have_too_generic")

    avoid_score = 0
    avoid_text = " ".join(avoid_sources).lower()
    if avoid_sources:
        avoid_score += 5
    if any(term in avoid_text for term in ["forum", "qa", "问答", "论坛"]):
        avoid_score += 4
    if any(term in avoid_text for term in ["generic", "encyclopedia", "single", "old", "百科", "单实体", "旧"]):
        avoid_score += 4
    if not any(term in source_types for term in ["forum"]):
        avoid_score += 2

    why_score = 0
    if why:
        why_score += 4
    if why and any(term in why for term in [evidence_mode, "直接", "证据", "官方", "新闻", "source", "evidence"]):
        why_score += 4
    if why and not any(term in why for term in ["可能有", "我觉得", "maybe", "probably"]):
        why_score += 2

    components = {
        "source_types": min(20, source_score),
        "channels": min(20, channel_score),
        "languages": min(10, language_score),
        "must_have": min(25, must_score),
        "avoid": min(15, avoid_score),
        "why": min(10, why_score),
    }
    score = sum(components.values())
    if "site_search_without_domain" in issues:
        score -= 15
    if evidence_mode == "route_fact" and not any(term.lower() in must_text for term in mode_terms):
        issues.append("route_strategy_missing_route_must_have")
        score -= 15
    if evidence_mode in {"numeric_fact", "date_fact"} and not any(term in must_text for term in mode_terms) and not any(
        key in binding_hits for key in {"relation_or_metric", "unit", "time_scope"}
    ):
        issues.append("structured_strategy_missing_key_must_have")
        score -= 10
    score = max(0, min(100, score))
    if score >= 80:
        label = "good"
    elif score >= 60:
        label = "usable"
    elif score >= 40:
        label = "weak"
    else:
        label = "bad"
    return {
        "source_strategy_score": score,
        "source_strategy_label": label,
        "source_strategy_issues": dedupe_keep_order(issues),
        "source_strategy_components": components,
    }


def default_source_strategy(source_intent: Dict[str, Any], claim: str, question: str) -> Dict[str, Any]:
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    preferred_types = [str(item) for item in source_intent.get("preferred_source_types") or []]
    preferred_domains = preferred_domains_from_intent(source_intent)
    source_types = preferred_types or ["official", "news"]
    if evidence_mode == "route_fact":
        source_types = ["news"]
    channels = ["news_search", "web_search"]
    if preferred_domains:
        channels.append("site_search")
    languages = ["zh"]
    if re.search(r"[A-Za-z]{3,}", f"{question} {claim}") or evidence_mode in {"route_fact", "policy_fact"}:
        languages.append("en")
    route_context = route_medium_context(question, claim, source_intent) if evidence_mode == "route_fact" else {}
    route_mode_terms = dedupe_keep_order(
        re.split(
            r"\s+",
            " ".join(
                [
                    str(route_context.get("suffix_zh") or ""),
                    str(route_context.get("suffix_en") or ""),
                    "route passage",
                ]
            ),
        )
    )
    mode_terms = {
        "route_fact": route_mode_terms or ["路线", "route", "passage"],
        "numeric_fact": ["数值", "金额", "价格", "amount"],
        "date_fact": ["日期", "时间", "date"],
        "event_result": ["结果", "result"],
        "schedule_fact": ["日程", "schedule"],
        "policy_fact": ["政策", "规则", "official"],
    }.get(evidence_mode, ["直接证据"])
    binding_terms = source_strategy_binding_terms(source_intent, evidence_mode)
    binding_seed: List[str] = []
    for key in ("subject_entity", "relation_or_metric", "time_scope", "authority_scope", "unit", "time_window"):
        value = str(binding_terms.get(key) or "")
        best_term = best_binding_slot_term(key, value, source_intent, evidence_mode)
        if best_term:
            binding_seed.append(best_term)
    must_have = dedupe_keep_order(binding_seed + query_core_tokens(claim)[:3] + mode_terms)[:6]
    return {
        "source_types": dedupe_keep_order(source_types)[:3],
        "search_channels": dedupe_keep_order(channels)[:3],
        "languages": dedupe_keep_order(languages)[:2],
        "must_have": must_have,
        "avoid_sources": ["forum", "qa", "generic_encyclopedia"],
        "why": f"按{evidence_mode or 'general'}查找可直接核验 claim 的证据",
    }


def sanitize_source_intent(source_intent: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(source_intent, dict):
        return {"source_intent": {}, "changed": False, "actions": [], "before": {}, "after": {}}
    sanitized = dict(source_intent)
    strategy = dict(source_intent.get("source_strategy")) if isinstance(source_intent.get("source_strategy"), dict) else {}
    before = json.loads(json.dumps(strategy, ensure_ascii=False)) if strategy else {}
    actions: List[str] = []
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    preferred_domains = preferred_domains_from_intent(source_intent)

    source_types = [str(item) for item in strategy.get("source_types") or []]
    channels = [str(item) for item in strategy.get("search_channels") or []]
    languages = [str(item) for item in strategy.get("languages") or []]
    must_have = [str(item) for item in strategy.get("must_have") or []]
    avoid_sources = [str(item) for item in strategy.get("avoid_sources") or []]

    if "site_search" in channels and not preferred_domains:
        channels = [channel for channel in channels if channel != "site_search"]
        actions.append("removed_site_search_without_domain")

    if evidence_mode == "route_fact":
        if "official" in source_types:
            source_types = [source_type for source_type in source_types if source_type != "official"]
            actions.append("removed_route_official_source_type")
        if "site_search" in channels:
            channels = [channel for channel in channels if channel != "site_search"]
            actions.append("removed_route_site_search")
        if "news_search" not in channels:
            channels.insert(0, "news_search")
            actions.append("added_route_news_search")
        if "web_search" not in channels:
            channels.append("web_search")
            actions.append("added_route_web_search")
        if "en" not in languages:
            languages.append("en")
            actions.append("added_route_english_language")

    if not channels and strategy:
        if evidence_mode in {"route_fact", "event_result", "policy_fact"}:
            channels = ["news_search", "web_search"]
            actions.append("fallback_news_web_channels")
        else:
            channels = ["web_search", "general_search"]
            actions.append("fallback_web_general_channels")

    generic_must = {"相关信息", "新闻报道", "资料", "information", "news", "details"}
    if must_have and all(item.strip().lower() in generic_must for item in must_have):
        must_have = []
        actions.append("removed_generic_must_have")
    filtered_must_have: List[str] = []
    removed_schema_term = False
    for item in must_have:
        normalized_item = normalize_text(item)
        if looks_like_internal_schema_token(normalized_item):
            removed_schema_term = True
            continue
        filtered_must_have.append(item)
    if removed_schema_term:
        must_have = filtered_must_have
        actions.append("removed_internal_schema_must_have")

    binding_terms = source_strategy_binding_terms(source_intent, evidence_mode)
    if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result"} and binding_terms:
        must_text = " ".join(must_have)
        enrich_keys = {
            "numeric_fact": ("subject_entity", "relation_or_metric", "time_scope", "unit"),
            "date_fact": ("subject_entity", "relation_or_metric", "time_scope", "time_window"),
            "schedule_fact": ("subject_entity", "relation_or_metric", "time_scope", "time_window"),
            "event_result": ("subject_entity", "time_scope"),
        }.get(evidence_mode, ())
        added_binding = False
        for key in enrich_keys:
            value = str(binding_terms.get(key) or "")
            if not value:
                continue
            if binding_slot_present(must_text, key, value, source_intent, evidence_mode):
                continue
            best_term = best_binding_slot_term(key, value, source_intent, evidence_mode)
            if not best_term:
                continue
            must_have.append(best_term)
            must_text = f"{must_text} {best_term}".strip()
            added_binding = True
        if added_binding:
            actions.append("enriched_must_have_with_binding_terms")

    if "forum" in source_types:
        source_types = [source_type for source_type in source_types if source_type != "forum"]
        actions.append("removed_forum_source_type")
    if "forum" not in " ".join(avoid_sources).lower():
        avoid_sources.append("forum")
        actions.append("added_forum_avoid")
    if "qa" not in " ".join(avoid_sources).lower():
        avoid_sources.append("qa")
        actions.append("added_qa_avoid")

    if strategy:
        strategy["source_types"] = dedupe_keep_order(source_types)
        strategy["search_channels"] = dedupe_keep_order(channels)
        strategy["languages"] = dedupe_keep_order(languages)
        strategy["must_have"] = dedupe_keep_order(must_have)
        strategy["avoid_sources"] = dedupe_keep_order(avoid_sources)
        sanitized["source_strategy"] = strategy

    after = json.loads(json.dumps(strategy, ensure_ascii=False)) if strategy else {}
    return {
        "source_intent": sanitized,
        "changed": bool(actions),
        "actions": dedupe_keep_order(actions),
        "before": before,
        "after": after,
    }


def needs_official_source_discovery(source_intent: Dict[str, Any]) -> bool:
    if not isinstance(source_intent, dict) or preferred_domains_from_intent(source_intent):
        return False
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    evidence_shape = normalize_evidence_shape(source_intent)
    strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
    source_types = [str(item).lower() for item in strategy.get("source_types") or []]
    preferred = [str(item).lower() for item in source_intent.get("preferred_source_types") or []]
    channels = [str(item).lower() for item in strategy.get("search_channels") or []]
    official_requested = "official" in source_types or "official" in preferred
    official_friendly_modes = {"entity_fact", "numeric_fact", "date_fact", "schedule_fact", "policy_fact", "event_result"}
    weak_official_priority = (
        evidence_mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result"}
        and evidence_shape in {"authoritative_notice", "structured_historical_data", "event_detail_page"}
    )
    if "site_search" in channels and official_requested and evidence_mode in official_friendly_modes:
        return True
    if official_requested and evidence_mode in official_friendly_modes:
        return True
    return weak_official_priority


def official_shape_query_terms(source_intent: Dict[str, Any]) -> List[str]:
    shape = normalize_evidence_shape(source_intent)
    needed_page_type = str(normalize_page_intent(source_intent).get("needed_page_type") or "")
    if shape == "structured_historical_data":
        return ["历史数据", "数据表", "quote", "rate", "结果页", "牌价", "汇率", "报价"]
    if shape == "authoritative_notice":
        return ["公告", "通知", "发布", "official notice", "announcement"]
    if shape == "event_detail_page":
        return page_intent_markers(needed_page_type or "event_detail")[:8]
    return page_intent_markers(needed_page_type)[:6]


def registered_domain(host: str) -> str:
    host = (host or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = [part for part in host.split(".") if part]
    if len(parts) <= 2:
        return host
    two_part_suffixes = {"com.cn", "org.cn", "gov.cn", "edu.cn", "co.uk", "ac.uk", "com.au"}
    suffix = ".".join(parts[-2:])
    if suffix in two_part_suffixes and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def official_discovery_queries(question: str, claim: str, source_intent: Dict[str, Any]) -> List[str]:
    metric_slots = metric_slots_from_intent(source_intent)
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    binding_terms = source_strategy_binding_terms(source_intent, evidence_mode)
    seeds: List[str] = []
    entity_hint = extract_authority_entity_hint(source_intent)

    def build_seed(keys: List[str], extra_terms: Optional[List[str]] = None) -> str:
        terms: List[str] = []
        for key in keys:
            value = str(binding_terms.get(key) or "")
            for term in binding_slot_search_values(key, value, source_intent, evidence_mode)[:2]:
                append_query_term_unique(terms, term)
        for term in extra_terms or []:
            append_query_term_unique(terms, term)
        return compact_text_for_query(" ".join(terms[:8]), 96)

    direct_need = source_intent.get("evidence_need_program", {}).get("direct_evidence_need", {}) if isinstance(source_intent.get("evidence_need_program"), dict) else {}
    source_strategy = source_intent.get("source_strategy", {}) if isinstance(source_intent.get("source_strategy"), dict) else {}
    page_intent = source_intent.get("page_intent", {}) if isinstance(source_intent.get("page_intent"), dict) else {}
    high_specific_terms: List[str] = []
    for key in ("subject_entity", "time_scope", "object_entity", "status_or_result", "relation_or_metric"):
        value = str(binding_terms.get(key) or "")
        for term in binding_slot_search_values(key, value, source_intent, evidence_mode)[:2]:
            append_query_term_unique(high_specific_terms, term)
    for collection in (
        source_strategy.get("must_have") if isinstance(source_strategy.get("must_have"), list) else [],
        page_intent.get("must_contain") if isinstance(page_intent.get("must_contain"), list) else [],
        direct_need.get("must_include") if isinstance(direct_need.get("must_include"), list) else [],
    ):
        for term in collection:
            append_query_term_unique(high_specific_terms, normalize_text(str(term)).replace("数值", ""))
    high_specific_seed = compact_text_for_query(" ".join(high_specific_terms[:10]), 112)
    if high_specific_seed:
        seeds.append(high_specific_seed)

    authority = str(metric_slots.get("source_authority") or "").lower()
    authority_extras = []
    if authority == "bank_rate_table":
        authority_extras = ["外汇牌价", "牌价表"]
    if entity_hint:
        seeds.append(entity_hint)
        if authority_extras:
            seeds.append(compact_text_for_query(" ".join([entity_hint] + authority_extras[:2]), 96) or "")
    primary_seed = build_seed(["subject_entity", "relation_or_metric", "time_scope"], authority_extras)
    secondary_seed = build_seed(["subject_entity", "time_scope", "authority_scope"], authority_extras)
    metric_seed = compact_text_for_query(" ".join(_metric_slot_search_terms(metric_slots, claim)[:6]), 96) if metric_slots else ""
    for seed in (primary_seed, secondary_seed, metric_seed):
        if seed:
            seeds.append(seed)
    queries: List[str] = []
    shape_terms = official_shape_query_terms(source_intent)
    weak_official_priority = not preferred_domains_from_intent(source_intent) and needs_official_source_discovery(source_intent)
    token_seed = compact_text_for_query(" ".join(query_core_tokens(f"{question} {claim}")[:6]), 96)
    for seed in dedupe_keep_order(seeds):
        query_terms = normalize_text(seed)
        if not query_terms:
            continue
        queries.append(query_terms if "官网" in query_terms else f"{query_terms} 官网")
        queries.append(query_terms if "official site" in query_terms.lower() else f"{query_terms} official site")
        if weak_official_priority:
            queries.append(query_terms)
            if shape_terms:
                queries.append(compact_text_for_query(" ".join([query_terms] + shape_terms[:3]), 96))
    if token_seed:
        queries.append(token_seed if not shape_terms else compact_text_for_query(" ".join([token_seed] + shape_terms[:3]), 96))
        queries.append(f"{token_seed} 官网")
    if not queries:
        fallback_seed = compact_text_for_query(claim or question, 96)
        if fallback_seed:
            queries.append(fallback_seed if not shape_terms else compact_text_for_query(" ".join([fallback_seed] + shape_terms[:3]), 96))
            queries.append(f"{fallback_seed} 官网")
    return dedupe_keep_order(queries)[:3]


def score_official_domain_candidate(
    item: Dict[str, Any],
    question: str,
    claim: str,
    source_intent: Dict[str, Any],
) -> Dict[str, Any]:
    url = str(item.get("url") or "")
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    domain = registered_domain(host)
    title = normalize_text(str(item.get("title") or ""))
    snippet = normalize_text(str(item.get("snippet") or ""))
    surface_text = f"{title} {snippet}".lower()
    combined = f"{title} {snippet} {parsed.path}".lower()
    path = parsed.path.lower()
    reasons: List[str] = []
    score = 0

    if not domain or "." not in domain:
        return {"domain": "", "score": 0, "reasons": ["missing_domain"]}

    blocked = [
        "wikipedia.org",
        "baidu.com",
        "zhihu.com",
        "reddit.com",
        "facebook.com",
        "x.com",
        "twitter.com",
        "youtube.com",
        "bing.com",
        "google.com",
        "sogou.com",
        "duckduckgo.com",
    ]
    if any(domain.endswith(blocked_domain) for blocked_domain in blocked):
        return {"domain": domain, "score": 0, "reasons": ["blocked_weak_or_search_domain"]}

    if host.startswith("www."):
        score += 2
    if domain.endswith(".gov") or domain.endswith(".gov.cn") or ".gov." in domain:
        score += 28
        reasons.append("government_domain")
    if domain.endswith(".edu") or domain.endswith(".edu.cn") or domain.endswith(".ac.uk"):
        score += 14
        reasons.append("education_domain")
    if domain.endswith(".org") or domain.endswith(".org.cn") or domain.endswith(".int"):
        score += 8
        reasons.append("organization_domain")

    official_markers = ["official", "官网", "官方网站", "官方", "press release", "announcement", "notice", "公告", "发布"]
    marker_hits = [marker for marker in official_markers if marker in combined]
    if marker_hits:
        score += min(20, 6 + 4 * len(marker_hits))
        reasons.append("official_marker")

    homepage_markers = ["首页", "门户", "网站", "global web site", "home page", "homepage"]
    homepage_hits = [marker for marker in homepage_markers if marker in combined]
    if homepage_hits:
        score += min(14, 4 + 3 * len(homepage_hits))
        reasons.append("homepage_marker")

    domain_stem = re.sub(r"\.(com|org|net|gov|edu|int|cn|uk|au)$", "", domain)
    domain_stem = domain_stem.replace("-", "").replace("_", "")
    compact_surface = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", surface_text)
    if len(domain_stem) >= 5 and domain_stem in compact_surface:
        score += 12
        reasons.append("domain_brand_in_result")

    metric_slots = metric_slots_from_intent(source_intent)
    authority_scope = normalize_text(str(metric_slots.get("source_authority") or "")).lower()
    evidence_shape = normalize_evidence_shape(source_intent)
    needed_page_type = str(normalize_page_intent(source_intent).get("needed_page_type") or "")
    authority_shape_match = False
    if authority_scope == "bank_rate_table":
        if any(marker in path for marker in ["/whpj", "/search/whpj", "sourcedb", "/forex", "/exchange", "/rate"]):
            authority_shape_match = True
        if any(marker in combined for marker in ["外汇牌价", "牌价表", "买入价", "卖出价", "汇率"]):
            authority_shape_match = True
    elif authority_scope == "central_bank":
        if any(marker in combined for marker in ["中间价", "reference rate", "central parity", "公告", "公布"]):
            authority_shape_match = True
    elif authority_scope == "exchange":
        if any(marker in combined for marker in ["行情", "报价", "历史数据", "market data", "quote"]):
            authority_shape_match = True
    elif authority_scope == "official_notice":
        if any(marker in combined for marker in ["公告", "通知", "notice", "announcement"]):
            authority_shape_match = True
    elif authority_scope == "market_data_page":
        if any(marker in combined for marker in ["数据", "历史数据", "query", "search", "报价"]):
            authority_shape_match = True
    if not authority_shape_match and evidence_shape == "structured_historical_data":
        markers = page_intent_markers(needed_page_type or "historical_table")
        authority_shape_match = any(marker.lower() in combined or marker.lower() in path for marker in markers[:10])
    elif not authority_shape_match and evidence_shape == "authoritative_notice":
        markers = page_intent_markers(needed_page_type or "official_notice")
        authority_shape_match = any(marker.lower() in combined or marker.lower() in path for marker in markers[:10])
    elif not authority_shape_match and evidence_shape == "event_detail_page":
        markers = page_intent_markers(needed_page_type or "event_detail")
        authority_shape_match = any(marker.lower() in combined or marker.lower() in path for marker in markers[:10])
    if authority_shape_match:
        score += 18
        reasons.append("authority_shape_match")

    core_tokens = [token.lower() for token in query_core_tokens(f"{question} {claim}")[:8]]
    token_hits = [token for token in core_tokens if len(token) >= 3 and token in combined]
    if token_hits:
        score += min(24, len(token_hits) * 4)
        reasons.append("entity_or_topic_match")
    else:
        score -= 4 if marker_hits or "domain_brand_in_result" in reasons else 12
        reasons.append("no_entity_match")

    source_type = dynamic_source_type(url, f"{question} {claim}", None, source_intent)
    if source_type == "official":
        score += 12
        reasons.append("known_official_source_type")
    if source_type in {"forum", "encyclopedia"}:
        score -= 25
        reasons.append(f"weak_source_type_{source_type}")
    if (
        authority_shape_match
        and source_type != "official"
        and not (
            evidence_shape in {"structured_historical_data", "authoritative_notice", "event_detail_page"}
            and source_type == "unknown"
            and "entity_or_topic_match" in reasons
        )
        and not any(reason in reasons for reason in ["government_domain", "organization_domain", "education_domain", "domain_brand_in_result"])
    ):
        score -= 24
        reasons.append("authority_shape_without_official_domain")

    if any(part in path for part in ["/official", "/press", "/news", "/notice", "/announcement", "/release"]):
        score += 6
        reasons.append("official_like_path")
    if evidence_shape == "structured_historical_data" and any(part in path for part in ["/quote", "/quotes", "/rate", "/rates", "/forex", "/exchange", "/history", "/historical", "/table"]):
        score += 8
        reasons.append("structured_page_path_match")
    if evidence_shape == "authoritative_notice" and any(part in path for part in ["/notice", "/announcement", "/release", "/press", "/bulletin"]):
        score += 8
        reasons.append("notice_page_path_match")
    if evidence_shape == "event_detail_page" and any(part in path for part in ["/game", "/games", "/match", "/matches", "/result", "/results", "/boxscore", "/score"]):
        score += 8
        reasons.append("event_detail_page_path_match")
    if path in {"", "/", "/en/", "/english/"}:
        score += 5
        reasons.append("root_homepage_path")
    if len(path.strip("/").split("/")) > 6:
        score -= 4
        reasons.append("deep_path_penalty")
    if "entity_or_topic_match" in reasons and ("homepage_marker" in reasons or "root_homepage_path" in reasons):
        score += 12
        reasons.append("entity_homepage_candidate")

    return {
        "domain": domain,
        "score": max(0, min(100, score)),
        "reasons": dedupe_keep_order(reasons),
        "title": title,
        "url": url,
        "source": item.get("source", ""),
    }


def discover_official_domains(
    question: str,
    claim: str,
    source_intent: Dict[str, Any],
    timeout_sec: int = 8,
) -> Dict[str, Any]:
    if not needs_official_source_discovery(source_intent):
        return {
            "official_discovery_attempted": False,
            "official_domain_candidates": [],
            "discovered_domains": [],
            "official_discovery_score": 0,
            "official_discovery_used": False,
            "official_discovery_block_reason": "",
            "official_discovery_reason": "not_required_or_already_has_preferred_domains",
        }

    queries = official_discovery_queries(question, claim, source_intent)
    candidates_by_domain: Dict[str, Dict[str, Any]] = {}
    logs: List[Dict[str, Any]] = []
    discovery_sources: List[str] = []
    for source_name in ["bing_rss", "bing_news_zh_rss", "bing_news_rss", "bing_html", "duckduckgo_html", "sogou_html"]:
        if source_enabled_for_query(source_name):
            discovery_sources.append(source_name)
    for query in queries[:2]:
        for source_name in discovery_sources:
            try:
                items = search_source(source_name, query, max_results=5, timeout_sec=timeout_sec)
            except Exception as exc:
                logs.append({"query": query, "source": source_name, "error": str(exc)})
                continue
            for item in items:
                scored = score_official_domain_candidate(item, question, claim, source_intent)
                domain = scored.get("domain", "")
                if not domain:
                    continue
                previous = candidates_by_domain.get(domain)
                if not previous or int(scored.get("score") or 0) > int(previous.get("score") or 0):
                    candidates_by_domain[domain] = scored

    candidates = sorted(candidates_by_domain.values(), key=lambda item: int(item.get("score") or 0), reverse=True)
    discovered: List[str] = []
    for item in candidates:
        reasons = set(item.get("reasons") or [])
        score = int(item.get("score") or 0)
        has_official_signal = any(
            reason in reasons
            for reason in [
                "official_marker",
                "domain_brand_in_result",
                "official_like_path",
                "known_official_source_type",
                "government_domain",
                "organization_domain",
                "homepage_marker",
                "entity_homepage_candidate",
                "authority_shape_match",
            ]
        )
        strong_match = any(reason in reasons for reason in ["entity_or_topic_match", "domain_brand_in_result", "authority_shape_match"])
        homepage_candidate = (
            "homepage_marker" in reasons
            and ("root_homepage_path" in reasons or "entity_homepage_candidate" in reasons)
        )
        if (
            score >= 35
            and has_official_signal
            and ("entity_or_topic_match" in reasons or homepage_candidate)
        ) or (
            score >= 28
            and homepage_candidate
            and any(reason in reasons for reason in ["official_marker", "domain_brand_in_result", "organization_domain", "government_domain"])
        ) or (
            score >= 24
            and "authority_shape_match" in reasons
            and "entity_or_topic_match" in reasons
            and any(reason in reasons for reason in ["known_official_source_type", "domain_brand_in_result", "official_like_path", "official_marker"])
        ) or (
            score >= 26
            and "authority_shape_match" in reasons
            and "entity_or_topic_match" in reasons
            and any(reason in reasons for reason in ["government_domain", "organization_domain", "education_domain", "domain_brand_in_result"])
        ) or (
            score >= 22
            and "authority_shape_match" in reasons
            and "entity_or_topic_match" in reasons
            and any(reason in reasons for reason in ["structured_page_path_match", "notice_page_path_match", "event_detail_page_path_match", "known_official_source_type", "official_marker"])
        ):
            discovered.append(str(item.get("domain")))
        if len(discovered) >= 2:
            break
    best_discovered_score = 0
    for item in candidates:
        if item.get("domain") in discovered:
            best_discovered_score = max(best_discovered_score, int(item.get("score") or 0))
    return {
        "official_discovery_attempted": True,
        "official_discovery_queries": queries,
        "official_domain_candidates": candidates[:5],
        "discovered_domains": discovered,
        "official_discovery_score": best_discovered_score,
        "official_discovery_used": bool(discovered),
        "official_discovery_block_reason": infer_official_discovery_block_reason(logs, discovered),
        "official_discovery_logs": logs[:5],
    }


def infer_official_discovery_block_reason(logs: List[Dict[str, Any]], discovered: List[str]) -> str:
    if discovered:
        return ""
    if any(exception_looks_like_anti_bot(RuntimeError(str(item.get("error") or ""))) for item in logs if isinstance(item, dict)):
        return "anti_bot_blocked"
    if any(normalize_text(str(item.get("error") or "")) for item in logs if isinstance(item, dict)):
        return "provider_error"
    return "no_authority_domain_found"


def query_texts_from_plan(question: str, claim: str, time_value: str, claim_item: Dict[str, Any]) -> List[Dict[str, Any]]:
    source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
    profile = retrieval_profile(source_intent)
    task_card = claim_item.get("evidence_task_card") if isinstance(claim_item.get("evidence_task_card"), dict) else {}
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    normalized_queries = normalize_query_items(claim_item.get("queries") or [])
    planner_query_keys = {
        normalize_text(str(item.get("q") or ""))
        for item in normalized_queries
        if isinstance(item, dict)
        and (
            normalize_text(str(item.get("goal") or "")) in {"discover_truth", "find_news", "verify_original", "find_context"}
            or bool(item.get("source_preference"))
        )
    }
    verification_questions = verification_query_items(claim_item, claim, source_intent)
    page_intent_retry_queries = retry_page_intent_queries(question, claim, source_intent, normalized_queries)
    queries: List[Dict[str, Any]] = []
    preferred_domains = preferred_domains_from_intent(source_intent)
    compact = retrieval_query_seed_text(question, claim, normalized_queries, 6)
    task_semantics = task_card.get("task_semantics") if isinstance(task_card.get("task_semantics"), dict) else {}
    core_binding = core_binding_from_intent(source_intent)
    semantic_terms = dedupe_keep_order(
        [
            normalize_text(str(core_binding.get("subject_entity") or "")),
            normalize_text(str(core_binding.get("relation_or_metric") or "")),
            normalize_text(str(core_binding.get("object_entity") or "")),
            normalize_text(str(core_binding.get("time_scope") or "")),
        ]
    )
    if sum(1 for term in semantic_terms if term) >= 2:
        semantic_query = compact_text_for_query(" ".join(term for term in semantic_terms if term), 96)
        if semantic_query:
            queries.append({"q": semantic_query, "goal": "discover_truth", "origin": "semantic_task_probe"})
        confusion_terms = task_semantics.get("must_not_confuse") if isinstance(task_semantics.get("must_not_confuse"), list) else []
        confusion_term = normalize_text(str(confusion_terms[0] or "")) if confusion_terms else ""
        if confusion_term and confusion_term not in semantic_query:
            refined_semantic_query = compact_text_for_query(f"{semantic_query} {confusion_term}", 96)
            if refined_semantic_query and refined_semantic_query != semantic_query:
                queries.append({"q": refined_semantic_query, "goal": "verify_original", "origin": "semantic_task_probe"})
    for domain in preferred_domains:
        for item in normalized_queries[:2]:
            query_text = sanitize_preferred_domain_query_text(item.get("q") or "", source_intent)
            if query_text and not extract_site_constraint(query_text):
                queries.append({"q": f"site:{domain} {query_text}", "goal": "find_preferred_domain", "origin": "preferred_domain_probe"})
        if compact:
            compact_query = sanitize_preferred_domain_query_text(compact, source_intent)
            if compact_query:
                queries.append({"q": f"site:{domain} {compact_query}", "goal": "find_preferred_domain", "origin": "preferred_domain_probe"})
    planner_front_count = 2 if relation_sentence_intent(source_intent) else 1
    if normalized_queries:
        queries.extend(normalized_queries[:planner_front_count])
    queries.extend(with_query_origin(metric_source_authority_queries(question, claim, source_intent, normalized_queries), "metric_source_probe"))
    queries.extend(with_query_origin(structured_point_retry_queries(question, claim, source_intent, normalized_queries), "structured_point_retry"))
    queries.extend(with_query_origin(page_shape_probe_queries(question, claim, source_intent, normalized_queries), "page_shape_probe"))
    queries.extend(with_query_origin(page_intent_retry_queries, "page_intent_retry"))
    queries.extend(refutation_target_query_items(claim_item, claim, evidence_mode))
    queries.extend(contrastive_query_items(claim_item, claim, evidence_mode))
    queries.extend(normalized_queries[planner_front_count:])
    queries.extend(with_query_origin(numeric_value_discovery_queries(claim, source_intent), "numeric_discovery"))
    for query in build_specialized_queries(question, claim, time_value):
        queries.append({"q": query, "goal": "general_verify", "origin": "specialized_lexical"})
    queries.extend(with_query_origin(verification_questions, "qa"))
    lexical_mode = evidence_mode or "entity_fact"
    for query in build_queries_for_claim(question, claim, time_value, lexical_mode):
        queries.append({"q": query, "goal": "general_verify", "origin": "lexical_fallback"})
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in queries:
        query_text = normalize_text(item.get("q") or "")
        if not query_text:
            continue
        key = query_text
        if key in seen:
            continue
        seen.add(key)
        query_item: Dict[str, Any] = {
            "q": query_text,
            "goal": normalize_text(item.get("goal") or "general_verify") or "general_verify",
            "origin": normalize_text(str(item.get("origin") or "")) or "planner",
        }
        raw_preference = item.get("source_preference") if isinstance(item.get("source_preference"), list) else []
        source_preference = [normalize_text(str(value)) for value in raw_preference if normalize_text(str(value))][:3]
        if source_preference:
            query_item["source_preference"] = source_preference
        for extra_key in ("operator", "variant", "gap_flag", "query_variant_origin", "atomic_claim_id", "atomic_risk_type", "atomic_claim_text"):
            extra_value = normalize_text(str(item.get(extra_key) or ""))
            if extra_value:
                query_item[extra_key] = extra_value
        if item.get("atomic_query"):
            query_item["atomic_query"] = True
        deduped.append(query_item)
    limit = max(1, MAX_QUERIES_PER_CLAIM)
    return apply_query_plan_policy(deduped, limit, source_intent, task_card, evidence_mode)


CORE_FACT_QUERY_MODES = {"numeric_fact", "date_fact", "schedule_fact", "event_result"}


def query_variant_origin_value(item: Dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return ""
    return (
        normalize_text(str(item.get("query_variant_origin") or ""))
        or normalize_text(str(item.get("origin") or ""))
        or "planner"
    )


def query_variant_origin_rows(query_plan: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in query_plan or []:
        if not isinstance(item, dict):
            continue
        query_text = normalize_text(str(item.get("q") or ""))
        if not query_text:
            continue
        rows.append(
            {
                "q": query_text,
                "origin": normalize_text(str(item.get("origin") or "")) or "planner",
                "query_variant_origin": query_variant_origin_value(item),
            }
        )
    return rows[:8]


def core_fact_claim_for_recall_probe(claim_item: Dict[str, Any], evidence_mode: str) -> bool:
    if not isinstance(claim_item, dict):
        return False
    if str(claim_item.get("centrality") or "") != "core":
        return False
    source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
    if str(source_intent.get("claim_shape") or "") == "exclusive_premise":
        return False
    return evidence_mode in CORE_FACT_QUERY_MODES


def recall_probe_goal_for_mode(evidence_mode: str) -> str:
    if evidence_mode == "numeric_fact":
        return "verify_numeric_detail"
    if evidence_mode in {"date_fact", "schedule_fact"}:
        return "verify_date_detail"
    if evidence_mode == "event_result":
        return "find_result"
    return "general_verify"


def build_fact_slot_probe_query_text(claim_item: Dict[str, Any], claim: str, evidence_mode: str) -> str:
    program = claim_program_from_claim_item(claim_item)
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    subject = normalize_text(str(decision_slots.get("subject") or ""))
    time_scope = normalize_text(str(decision_slots.get("time_scope") or ""))
    metric = normalize_text(str(decision_slots.get("metric_or_relation") or ""))
    status_or_result = normalize_text(str(decision_slots.get("status_or_result") or ""))
    must_include = [
        normalize_text(str(term))
        for term in (direct_need.get("must_include") or [])[:4]
        if normalize_text(str(term))
    ]
    opening_required = bool(
        re.search(
            r"(开盘|开市|opening|opened)",
            " ".join([claim, subject, metric, status_or_result, str(direct_need.get("must_answer") or "")]),
            flags=re.I,
        )
    )
    terms = dedupe_keep_order(
        [
            time_scope,
            subject,
            "开盘" if opening_required else "",
            "开市" if opening_required else "",
            "opening" if opening_required else "",
            "opened" if opening_required else "",
            metric,
            status_or_result,
        ] + must_include[:2]
    )
    query_text = compact_text_for_query(" ".join(term for term in terms if term), 96)
    if query_text:
        return query_text
    return compact_text_for_query(
        normalize_text(str(program.get("normalized_assertion") or claim)),
        96,
    )


REFUTATION_QUERY_MODES = {"numeric_fact", "date_fact", "schedule_fact", "event_result", "route_fact", "entity_fact"}
CONTRASTIVE_QUERY_MODES = {"numeric_fact", "date_fact", "schedule_fact", "event_result", "route_fact", "entity_fact"}


def build_refutation_target(claim_item: Dict[str, Any], claim: str, evidence_mode: str) -> Dict[str, Any]:
    source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
    program = claim_program_from_claim_item(claim_item)
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    required_slots = (
        [str(slot) for slot in (program.get("required_slot_profile") or []) if str(slot)]
        if isinstance(program.get("required_slot_profile"), list)
        else shared_required_slot_profile_for_mode(
            evidence_mode,
            claim_text=claim,
            source_intent=source_intent,
            decision_slots=decision_slots,
        )
    )
    slots = {
        key: normalize_text(str(decision_slots.get(key) or ""))
        for key in ("subject", "time_scope", "object", "metric_or_relation", "status_or_result")
    }
    missing_slots = [slot for slot in required_slots if not slots.get(slot)]
    must_include = [
        normalize_text(str(term))
        for term in (direct_need.get("must_include") or [])
        if normalize_text(str(term))
    ] if isinstance(direct_need.get("must_include"), list) else []
    target_terms = dedupe_keep_order(
        [
            slots.get("subject", ""),
            slots.get("time_scope", ""),
            slots.get("metric_or_relation", ""),
            slots.get("object", ""),
            slots.get("status_or_result", ""),
        ] + must_include[:3]
    )
    if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}:
        conflict_terms = ["实际", "官方", "历史", "公告", "公布"]
    elif evidence_mode == "event_result":
        conflict_terms = ["结果", "比分", "赛果", "官方"]
    elif evidence_mode == "route_fact":
        conflict_terms = ["实际", "路线", "是否经过", "官方"]
    else:
        conflict_terms = ["实际", "官方", "结果"]
    query_text = compact_text_for_query(" ".join([term for term in target_terms + conflict_terms[:2] if term]), 96)
    return {
        "state": "ready" if len([term for term in target_terms if term]) >= 2 else "insufficient_slots",
        "slots": slots,
        "required_slots": required_slots,
        "missing_slots": missing_slots,
        "target_terms": [term for term in target_terms if term][:8],
        "conflict_terms": conflict_terms[:4],
        "query": query_text,
    }


def refutation_target_query_items(claim_item: Dict[str, Any], claim: str, evidence_mode: str) -> List[Dict[str, Any]]:
    if evidence_mode not in REFUTATION_QUERY_MODES:
        return []
    if str(claim_item.get("centrality") or "") not in {"core", "supporting"}:
        return []
    target = build_refutation_target(claim_item, claim, evidence_mode)
    claim_item["_refutation_target"] = target
    query_text = normalize_text(str(target.get("query") or ""))
    if target.get("state") != "ready" or not query_text:
        return []
    return [
        {
            "q": query_text,
            "goal": "find_refutation_target",
            "origin": "refutation_target",
            "query_variant_origin": "refutation_target",
            "source_preference": ["official", "news", "html"],
        }
    ]


def build_contrastive_query_plan(claim_item: Dict[str, Any], claim: str, evidence_mode: str) -> Dict[str, Any]:
    source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
    program = claim_program_from_claim_item(claim_item)
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    slots = {
        key: normalize_text(str(decision_slots.get(key) or ""))
        for key in (
            "subject",
            "time_scope",
            "object",
            "metric_or_relation",
            "status_or_result",
            "comparison_baseline",
            "source_scope",
        )
    }
    required_slots = shared_required_slot_profile_for_mode(
        evidence_mode,
        claim_text=claim,
        source_intent=source_intent,
        decision_slots=decision_slots,
    )
    slot_gap = [slot for slot in required_slots if not slots.get(slot)]
    must_include = [
        normalize_text(str(term))
        for term in (direct_need.get("must_include") or [])
        if normalize_text(str(term))
    ] if isinstance(direct_need.get("must_include"), list) else []
    if evidence_mode in {"date_fact", "schedule_fact"}:
        contrast_terms = ["官方", "公告", "安排", "日程", "休市", "开市"]
        terms = [slots["subject"], slots["time_scope"], slots["status_or_result"]] + contrast_terms[:4]
    elif evidence_mode == "numeric_fact":
        contrast_terms = ["历史数据", "表格", "牌价", "中间价", "发布日期"]
        terms = [slots["subject"], slots["metric_or_relation"], slots["time_scope"], slots["object"]] + contrast_terms[:4]
    elif evidence_mode == "event_result":
        contrast_terms = ["result", "final score", "赛果", "战报", "官方"]
        terms = [slots["subject"], slots["object"], slots["time_scope"], slots["status_or_result"]] + contrast_terms[:4]
    elif evidence_mode == "route_fact":
        contrast_terms = ["实际", "是否", "路线", "经过", "官方", "说明"]
        terms = [slots["subject"], slots["object"], slots["time_scope"], slots["metric_or_relation"]] + contrast_terms[:4]
    else:
        explanation_hint = bool(
            re.search(r"(因为|导致|归因|抢筹|倒挂|资金|flow|inflow|outflow)", claim, flags=re.I)
            or normalize_text(str(source_intent.get("claim_shape") or "")) in {"causal_explanation", "interpretation"}
        )
        contrast_terms = (
            ["资金流", "南向资金", "外资", "机构", "成交额", "持仓"]
            if explanation_hint
            else ["实际", "官方", "结果", "说明"]
        )
        terms = [slots["subject"], slots["time_scope"], slots["metric_or_relation"], slots["object"]] + contrast_terms[:4]
    query_text = compact_text_for_query(" ".join(term for term in dedupe_keep_order(terms + must_include[:2]) if term), 96)
    filled = [value for value in (slots.get("subject"), slots.get("time_scope"), slots.get("metric_or_relation"), slots.get("object")) if value]
    trigger = "slot_contrastive_gap" if len(filled) >= 2 else ""
    return {
        "state": "ready" if query_text and trigger else "insufficient_slots",
        "trigger": trigger,
        "slots": slots,
        "slot_gap": slot_gap[:6],
        "contrast_terms": contrast_terms[:6],
        "query": query_text,
    }


def contrastive_query_items(claim_item: Dict[str, Any], claim: str, evidence_mode: str) -> List[Dict[str, Any]]:
    if evidence_mode not in CONTRASTIVE_QUERY_MODES:
        return []
    if str(claim_item.get("centrality") or "") not in {"core", "supporting"}:
        return []
    plan = build_contrastive_query_plan(claim_item, claim, evidence_mode)
    claim_item["_contrastive_query_plan"] = plan
    query_text = normalize_text(str(plan.get("query") or ""))
    if not ENABLE_CONTRASTIVE_RETRIEVAL:
        return []
    if plan.get("state") != "ready" or not query_text:
        return []
    return [
        {
            "q": query_text,
            "goal": "find_contrastive_evidence",
            "origin": "contrastive_query",
            "query_variant_origin": "contrastive_query",
            "source_preference": ["official", "news", "html"],
        }
    ]


def atomic_query_primary_score(value: str) -> str:
    match = re.search(r"\b\d{1,3}\s*[-:：]\s*\d{1,3}\b", normalize_text(str(value or "")))
    return normalize_text(match.group(0)) if match else normalize_text(str(value or ""))


def atomic_query_event_entity(value: str) -> str:
    text = normalize_text(str(value or ""))
    text = re.sub(r"[\(（][^)）]{1,20}[\)）]", " ", text)
    text = re.sub(r"[✅✔️❌✖️]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_atomic_claim_query_plan(atomic_claim: Dict[str, Any]) -> Dict[str, Any]:
    """Planned-only query hook for CI atomic claims; callers decide whether to execute it."""
    if not isinstance(atomic_claim, dict):
        return {"state": "invalid_atomic_claim", "query": ""}
    slots = atomic_claim.get("slot_contract") if isinstance(atomic_claim.get("slot_contract"), dict) else {}
    risk_type = normalize_text(str(atomic_claim.get("risk_type") or ""))
    target = atomic_claim.get("refutation_target") if isinstance(atomic_claim.get("refutation_target"), dict) else {}
    target_terms = target.get("target_terms") if isinstance(target.get("target_terms"), list) else []
    if risk_type == "market_calendar_status":
        terms = dedupe_keep_order(
            [
                normalize_text(str(slots.get("subject") or "")),
                normalize_text(str(slots.get("time_scope") or "")),
                "交易日历",
                "是否开市",
                "正常交易",
                "交易安排",
                "官方",
                "公告",
            ]
        )
    elif risk_type == "event_result_status":
        status_text = normalize_text(str(slots.get("status_or_result") or ""))
        score_text = atomic_query_primary_score(str(slots.get("metric_or_relation") or ""))
        terms = dedupe_keep_order(
            [
                atomic_query_event_entity(str(slots.get("subject") or "")),
                atomic_query_event_entity(str(slots.get("object") or "")),
                normalize_text(str(slots.get("time_scope") or "")),
                score_text if not str(slots.get("subject") or "").strip() and not str(slots.get("object") or "").strip() else "",
            ]
        )
    elif risk_type == "phase_boundary_time":
        time_role = normalize_text(str(slots.get("time_role") or ""))
        time_scope = normalize_text(str(slots.get("time_scope") or ""))
        stripped_time_scope = normalize_text(re.sub(r"(之后|以前|之前|后|前)$", "", time_scope))
        claim_text = normalize_text(str(atomic_claim.get("text") or ""))
        if not time_role:
            if re.search(r"(结果|数据|公布|发布|出炉|release|published|complete|完成|结束)", claim_text, flags=re.I):
                time_role = "result_release"
            elif re.search(r"(结束|完成|完结|截止)", claim_text, flags=re.I):
                time_role = "whole_event_end"
            elif re.search(r"(第一阶段|第二阶段|第三阶段|阶段)", claim_text) and re.search(r"(开始|开启|启动|开展|进行|start|begin|commence)", claim_text, flags=re.I):
                time_role = "phase_start"
        subject_text = normalize_text(str(slots.get("subject") or ""))
        time_surface = " ".join([time_scope, stripped_time_scope]).strip() or claim_text
        month_terms = dedupe_keep_order(
            re.findall(r"20\d{2}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?", time_surface)
            + re.findall(
                r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+20\d{2}\b",
                time_surface,
                flags=re.I,
            )
            + re.findall(r"\b20\d{2}[-/]\d{1,2}(?:[-/]\d{1,2})?\b", time_surface)
        )
        if not month_terms:
            month_terms = dedupe_keep_order(
                re.findall(r"20\d{2}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?", claim_text)
                + re.findall(
                    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+20\d{2}\b",
                    claim_text,
                    flags=re.I,
                )
                + re.findall(r"\b20\d{2}[-/]\d{1,2}(?:[-/]\d{1,2})?\b", claim_text)
            )
        if time_role in {"result_release", "whole_event_end", "phase_end"}:
            role_terms = [
                "阶段",
                "下一阶段",
                "第二阶段",
                "后续阶段",
                "开始",
                "启动",
                "start",
                "schedule",
                "dates",
                "结果",
                "公布",
                "release",
            ]
        elif time_role == "phase_start":
            role_terms = ["阶段", "开始", "启动", "schedule", "dates", "官方"]
        else:
            role_terms = ["阶段", "日程", "开始", "结束", "公布", "官方"]
        terms = dedupe_keep_order(
            [
                subject_text,
                normalize_text(str(slots.get("object") or "")),
                stripped_time_scope or time_scope,
            ]
            + month_terms
            + role_terms
            + [normalize_text(str(term)) for term in target_terms[:2]]
        )
    else:
        terms = dedupe_keep_order(
            [
                normalize_text(str(slots.get("subject") or "")),
                normalize_text(str(slots.get("time_scope") or "")),
                normalize_text(str(slots.get("metric_or_relation") or "")),
                normalize_text(str(slots.get("object") or "")),
                normalize_text(str(slots.get("status_or_result") or "")),
            ]
            + [normalize_text(str(term)) for term in target_terms[:4]]
        )
    query_text = compact_text_for_query(" ".join(term for term in terms if term), 96)
    priority = int(atomic_claim.get("search_priority") or 0)
    atomic_source_preference = (
        ["news", "html"]
        if risk_type in {"exclusive_or_only_path", "event_result_status", "phase_boundary_time", "reality_vs_fiction_status"}
        else ["official", "news", "html"]
    )
    return {
        "state": "planned_only" if query_text else "insufficient_slots",
        "risk_type": risk_type,
        "priority": priority,
        "query": query_text,
        "source_preference": atomic_source_preference,
        "do_not_execute_without_budget": True,
    }


def atomic_claim_query_plan_rows(claim_item: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_claims = (
        claim_item.get("_atomic_claims_for_retrieval")
        if isinstance(claim_item.get("_atomic_claims_for_retrieval"), list)
        else []
    )
    atomic_claims = [row for row in raw_claims if isinstance(row, dict)]
    if not atomic_claims:
        return []
    limit = max(0, int(ATOMIC_CLAIM_QUERY_LIMIT or 0))
    if limit <= 0:
        return []
    ordered = sorted(
        atomic_claims,
        key=lambda row: int(row.get("search_priority") or 0),
        reverse=True,
    )[:limit]
    rows: List[Dict[str, Any]] = []
    for atomic_claim in ordered:
        plan = build_atomic_claim_query_plan(atomic_claim)
        query_text = normalize_text(str(plan.get("query") or ""))
        state = str(plan.get("state") or "")
        execution_state = "ready" if ENABLE_ATOMIC_CLAIM_RETRIEVAL and state == "planned_only" and query_text else state
        if not ENABLE_ATOMIC_CLAIM_RETRIEVAL and state == "planned_only" and query_text:
            execution_state = "disabled_by_latency_guard"
        row = {
            "atomic_claim_id": str(atomic_claim.get("atomic_claim_id") or ""),
            "parent_claim_id": str(atomic_claim.get("parent_claim_id") or claim_item.get("claim_id") or claim_item.get("id") or ""),
            "risk_type": normalize_text(str(atomic_claim.get("risk_type") or plan.get("risk_type") or "")),
            "text": compact_text_for_query(str(atomic_claim.get("text") or ""), 140),
            "query": query_text,
            "priority": int(plan.get("priority") or atomic_claim.get("search_priority") or 0),
            "source_preference": plan.get("source_preference") if isinstance(plan.get("source_preference"), list) else ["official", "news", "html"],
            "state": state,
            "execution_state": execution_state,
            "enabled": bool(ENABLE_ATOMIC_CLAIM_RETRIEVAL),
        }
        rows.append(row)
    return rows


def atomic_claim_query_items_from_plan(plan_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in plan_rows or []:
        if not isinstance(row, dict):
            continue
        query_text = normalize_text(str(row.get("query") or ""))
        if row.get("execution_state") != "ready" or not query_text:
            continue
        items.append(
            {
                "q": query_text,
                "goal": "find_atomic_refutation",
                "origin": "atomic_claim_query",
                "query_family_role": "refute",
                "query_variant_origin": "atomic_claim_query",
                "source_preference": row.get("source_preference") if isinstance(row.get("source_preference"), list) else ["official", "news", "html"],
                "atomic_claim_id": str(row.get("atomic_claim_id") or ""),
                "atomic_risk_type": str(row.get("risk_type") or ""),
                "atomic_claim_text": str(row.get("text") or ""),
                "atomic_query": True,
            }
        )
    return items


def first_query_site_constraint(query_plan: List[Dict[str, Any]]) -> str:
    for item in query_plan or []:
        if not isinstance(item, dict):
            continue
        site = normalize_domain(extract_site_constraint(str(item.get("q") or "")))
        if site:
            return site
    return ""


def build_recall_probe_query_item(
    claim_item: Dict[str, Any],
    claim: str,
    source_intent: Dict[str, Any],
    query_plan: List[Dict[str, Any]],
    evidence_mode: str,
) -> Optional[Dict[str, Any]]:
    if not core_fact_claim_for_recall_probe(claim_item, evidence_mode):
        return None
    fact_slot_item = next(
        (
            item for item in query_plan
            if isinstance(item, dict) and query_variant_origin_value(item).startswith("fact_slot_query")
        ),
        None,
    )
    probe_query = normalize_text(str((fact_slot_item or {}).get("q") or "")) or build_fact_slot_probe_query_text(claim_item, claim, evidence_mode)
    if not probe_query:
        return None
    site_constraint = (
        normalize_domain(extract_site_constraint(probe_query))
        or first_query_site_constraint(query_plan)
    )
    preferred_domains = preferred_domains_from_intent(source_intent)
    if not site_constraint and preferred_domains:
        site_constraint = normalize_domain(preferred_domains[0])
    if site_constraint and not extract_site_constraint(probe_query):
        probe_query = f"site:{site_constraint} {probe_query}"
    source_preference = ["news", "html"] if evidence_mode == "event_result" else ["html", "news"]
    return {
        "q": probe_query,
        "goal": normalize_text(str((fact_slot_item or {}).get("goal") or recall_probe_goal_for_mode(evidence_mode))) or "general_verify",
        "origin": "fact_slot_recall_probe",
        "query_variant_origin": "fact_slot_query_probe",
        "source_preference": source_preference,
        "probe_only_if_raw_zero": True,
    }


def restrict_recall_probe_source_jobs(source_jobs: List[Tuple[str, str]], evidence_mode: str) -> List[Tuple[str, str]]:
    if evidence_mode == "event_result":
        preferred_families = ["news_rss", "html"]
    else:
        preferred_families = ["html", "news_rss"]
    selected: List[Tuple[str, str]] = []
    seen = set()
    for family in preferred_families:
        for source_name, source_query in source_jobs:
            if source_name in seen:
                continue
            if source_family_name(source_name) != family:
                continue
            selected.append((source_name, source_query))
            seen.add(source_name)
            if len(selected) >= 3:
                return selected
    for source_name, source_query in source_jobs:
        if source_name in seen:
            continue
        if source_family_name(source_name) not in {"html", "news_rss"}:
            continue
        selected.append((source_name, source_query))
        seen.add(source_name)
        if len(selected) >= 3:
            break
    return selected or source_jobs[:2]


def verification_query_items(claim_item: Dict[str, Any], claim: str, source_intent: Dict[str, Any]) -> List[Dict[str, str]]:
    if not ENABLE_QA_QUERIES:
        return []
    raw_questions = claim_item.get("verification_questions") if isinstance(claim_item.get("verification_questions"), list) else []
    questions = [normalize_text(str(item or "")) for item in raw_questions]
    questions = [item for item in questions if item]
    if not questions:
        questions = fallback_verification_questions(claim, source_intent)
    items: List[Dict[str, str]] = []
    for question_text in questions[: max(0, QA_QUERY_LIMIT)]:
        query = compact_text_for_query(question_text, 96)
        if query:
            items.append({"q": query, "goal": "verification_question"})
    return items


def retry_page_intent_goal(source_intent: Dict[str, Any]) -> str:
    if relation_sentence_intent(source_intent):
        return "find_route_page"
    return "find_page_intent_page"


def should_retry_with_page_intent(source_intent: Dict[str, Any]) -> bool:
    if not isinstance(source_intent, dict) or not source_intent.get("_is_retry"):
        return False
    actions = source_intent.get("_retry_recommended_actions") if isinstance(source_intent.get("_retry_recommended_actions"), list) else []
    if "re_retrieve_with_page_intent" not in actions:
        return False
    page_intent = normalize_page_intent(source_intent)
    needed_page_type = str(page_intent.get("needed_page_type") or "")
    if not needed_page_type or needed_page_type == "general_page":
        return False
    return bool(page_intent_markers(needed_page_type) or page_intent.get("must_contain"))


def retry_page_intent_queries(
    question: str,
    claim: str,
    source_intent: Dict[str, Any],
    existing_queries: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    if not should_retry_with_page_intent(source_intent):
        return []
    if str(source_intent.get("evidence_mode") or "") == "route_fact":
        return []
    page_intent = normalize_page_intent(source_intent)
    needed_page_type = str(page_intent.get("needed_page_type") or "")
    markers = page_intent_markers(needed_page_type)
    must_contain = [normalize_text(str(item)) for item in page_intent.get("must_contain") or [] if normalize_text(str(item))]
    compact = (
        preferred_probe_seed_text(question, claim, source_intent, existing_queries, 8)
        or compact_text_for_query(strip_numeric_values(claim) or claim, 72)
    )
    if not compact:
        return []
    existing_text = " ".join(
        normalize_text(str(item.get("q") or ""))
        for item in existing_queries
        if isinstance(item, dict)
    ).lower()
    goal = retry_page_intent_goal(source_intent)
    queries: List[Dict[str, str]] = []

    def probe_source_preference() -> List[str]:
        preference: List[str] = ["html"]
        preferred_types = source_intent.get("preferred_source_types") if isinstance(source_intent.get("preferred_source_types"), list) else []
        normalized_types = {normalize_text(str(item)).lower() for item in preferred_types if normalize_text(str(item))}
        if "news" in normalized_types:
            preference.append("news")
        return preference

    def compose_probe_query(base_text: str, extra_terms: List[str], base_limit: int = 6, total_limit: int = 8) -> str:
        terms: List[str] = []
        for token in compact_query_seed_tokens(base_text, max(base_limit, total_limit)):
            append_query_term_unique(terms, token)
            if len(terms) >= base_limit:
                break
        remaining = max(0, total_limit - len(terms))
        for term in extra_terms:
            if remaining <= 0:
                break
            added_for_term = 0
            for token in compact_query_seed_tokens(term, min(4, remaining)):
                before = len(terms)
                append_query_term_unique(terms, token)
                if len(terms) > before:
                    added_for_term += 1
                    remaining = max(0, total_limit - len(terms))
                if added_for_term >= 2 or remaining <= 0:
                    break
        return " ".join(terms[:total_limit])

    def marker_bucket(language: str) -> List[str]:
        combined = must_contain + markers
        bucket: List[str] = []
        for marker in combined:
            if not marker:
                continue
            has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in marker)
            has_alpha = any("a" <= ch.lower() <= "z" for ch in marker)
            if language == "zh" and not has_cjk:
                continue
            if language == "en" and not has_alpha:
                continue
            if marker.lower() in existing_text:
                continue
            bucket.append(marker)
        return dedupe_keep_order(bucket)[:2]

    if any("\u4e00" <= ch <= "\u9fff" for ch in compact):
        zh_query = compose_probe_query(compact, marker_bucket("zh"))
        if zh_query and zh_query.lower() not in existing_text:
            queries.append({"q": zh_query, "goal": goal, "source_preference": probe_source_preference()})
    if any("a" <= ch.lower() <= "z" for ch in compact):
        en_query = compose_probe_query(compact, marker_bucket("en"))
        if en_query and en_query.lower() not in existing_text:
            queries.append({"q": en_query, "goal": goal, "source_preference": probe_source_preference()})
    if not queries:
        fallback_query = compose_probe_query(compact, must_contain[:1] or markers[:1])
        if fallback_query and fallback_query.lower() not in existing_text:
            queries.append({"q": fallback_query, "goal": goal, "source_preference": probe_source_preference()})
    return queries[:2]


def structured_point_retry_queries(
    question: str,
    claim: str,
    source_intent: Dict[str, Any],
    existing_queries: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    if not isinstance(source_intent, dict) or not source_intent.get("_is_retry"):
        return []
    actions = source_intent.get("_retry_recommended_actions") if isinstance(source_intent.get("_retry_recommended_actions"), list) else []
    gap_flags = source_intent.get("_retry_gap_flags") if isinstance(source_intent.get("_retry_gap_flags"), list) else []
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    mechanism_type = mechanism_type_from_intent(source_intent)
    if "add_gap_query" not in actions:
        return []
    if not any(flag.startswith("point_") for flag in gap_flags):
        return []
    if not (
        mechanism_type in {"structured_numeric_authority", "date_authority"}
        or evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}
    ):
        return []
    metric_slots = metric_slots_from_intent(source_intent)
    binding_terms = source_strategy_binding_terms(source_intent, evidence_mode)
    source_authority = normalize_text(str(metric_slots.get("source_authority") or binding_terms.get("authority_scope") or "")).lower()
    time_scope = normalize_text(str(binding_terms.get("time_scope") or metric_slots.get("time_scope") or ""))
    if not time_scope:
        return []
    existing_text = " ".join(
        normalize_text(str(item.get("q") or ""))
        for item in existing_queries
        if isinstance(item, dict)
    ).lower()
    base_terms: List[str] = []
    for key in ("subject_entity", "relation_or_metric", "time_scope"):
        value = str(binding_terms.get(key) or "")
        for term in binding_slot_search_values(key, value, source_intent, evidence_mode)[:2]:
            append_query_term_unique(base_terms, term)

    authority_retry_terms = {
        "bank_rate_table": {
            "history": ["历史查询", "历史牌价", "牌价表", "外汇牌价"],
            "dated_record": ["当日牌价", "日期", "牌价", "外汇牌价"],
            "archive": ["历史查询", "查询", "汇率", "牌价表"],
        },
        "central_bank": {
            "history": ["历史数据", "历史公布", "官方数据"],
            "dated_record": ["发布日期", "当日数据", "官方公布"],
            "archive": ["历史数据", "查询", "archive"],
        },
        "exchange": {
            "history": ["historical data", "archive", "quote"],
            "dated_record": ["date", "daily", "quote"],
            "archive": ["archive", "history", "table"],
        },
        "official_notice": {
            "history": ["历史公告", "过往公告", "官方发布"],
            "dated_record": ["发布日期", "当日公告", "官方发布"],
            "archive": ["历史公告", "查询", "archive"],
        },
        "market_data_page": {
            "history": ["historical data", "history", "table"],
            "dated_record": ["date", "daily", "data"],
            "archive": ["archive", "historical data", "table"],
        },
        "price_monitoring_report": {
            "history": ["历史报告", "历史数据", "监测数据"],
            "dated_record": ["发布日期", "当日数据", "监测数据"],
            "archive": ["历史报告", "查询", "archive"],
        },
    }
    authority_variants = authority_retry_terms.get(
        source_authority,
        {
            "history": ["历史数据", "history", "archive"],
            "dated_record": ["发布日期", "date", "daily"],
            "archive": ["archive", "history", "table"],
        },
    )

    def compose_operator_query(
        variant: str,
        extra_terms: List[str],
        total_limit: int = 10,
    ) -> Optional[Dict[str, str]]:
        terms: List[str] = []
        for term in base_terms:
            append_query_term_unique(terms, term)
        for extra in extra_terms:
            append_query_term_unique(terms, extra)
        compact = compact_text_for_query(" ".join(dedupe_keep_order(terms)[:total_limit]), 96)
        if not compact or compact.lower() in existing_text:
            return None
        item: Dict[str, str] = {
            "q": compact,
            "goal": "find_metric_source_page",
            "source_preference": ["official", "html"],
            "operator": "structured_point_retry",
            "variant": variant,
        }
        if gap_flags:
            item["gap_flag"] = normalize_text(str(gap_flags[0]))
        return item

    queries: List[Dict[str, str]] = []
    if "point_time_scope_mismatch" in gap_flags:
        for variant in ("history", "dated_record", "archive"):
            item = compose_operator_query(
                variant,
                authority_variants.get(variant, []),
            )
            if item:
                queries.append(item)
        return queries[:3]

    if "point_metric_field_missing" in gap_flags:
        item = compose_operator_query(
            "field_record",
            authority_variants.get("history", [])[:2] + ["字段", "详情", "table", "details"],
        )
        return [item] if item else []

    if "point_subject_currency_mismatch" in gap_flags:
        item = compose_operator_query(
            "subject_row",
            authority_variants.get("dated_record", [])[:2] + ["币种", "currency", "row"],
        )
        return [item] if item else []

    if "point_metric_value_missing" in gap_flags:
        item = compose_operator_query(
            "value_extractable_record",
            authority_variants.get("history", [])[:2] + ["数值", "value", "table"],
        )
        return [item] if item else []

    fallback = compose_operator_query("history", authority_variants.get("history", []))
    return [fallback] if fallback else []


def fallback_verification_questions(claim: str, source_intent: Dict[str, Any]) -> List[str]:
    mechanism_type = mechanism_type_from_intent(source_intent)
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    evidence_target = str(source_intent.get("evidence_target") or "")
    base = compact_text_for_query(strip_numeric_values(claim) or claim, 72)
    if mechanism_type == "structured_numeric_authority" or evidence_mode == "numeric_fact" or evidence_target in {"market_price", "prize_amount", "position_distance"}:
        return [f"{base} 实际数值 单位 官方", f"{base} actual value official"]
    if mechanism_type == "date_authority" or evidence_mode in {"date_fact", "schedule_fact"} or evidence_target in {"market_calendar", "census_phase"}:
        return [f"{base} 实际日期 时间 官方", f"{base} official date schedule"]
    if mechanism_type == "event_result_page" or evidence_mode == "event_result" or evidence_target in {"match_result", "withdrawal_status"}:
        return [f"{base} 实际结果 比赛 退赛", f"{base} result withdrawal match"]
    if relation_sentence_intent(source_intent):
        route_context = route_medium_context("", claim, source_intent)
        suffix_zh = route_context.get("suffix_zh") or "路线 轨迹 经过 通道"
        suffix_en = route_context.get("suffix_en") or "route trajectory passage"
        return [f"{base} {suffix_zh}", f"{base} {suffix_en}"]
    if mechanism_type == "current_status_update" or evidence_target == "current_status":
        return [f"{base} 当前状态 官方 实时", f"{base} current status official live"]
    return [f"{base} 事实 核查 证据"]


def page_shape_probe_queries(question: str, claim: str, source_intent: Dict[str, Any], existing_queries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    evidence_mode = str(source_intent.get("evidence_mode") or "")
    profile = retrieval_profile(source_intent)
    queries: List[Dict[str, str]] = []
    gap_brief = gap_driven_page_brief(question, claim, source_intent, existing_queries)
    if relation_sentence_intent(source_intent):
        route_frame = route_retry_query_frame(question, claim, source_intent, existing_queries)
        existing_text = " ".join(normalize_text(str(item.get("q") or "")) for item in existing_queries if isinstance(item, dict)).lower()
        preferred_types = source_intent.get("preferred_source_types") if isinstance(source_intent.get("preferred_source_types"), list) else []
        normalized_types = {normalize_text(str(item)).lower() for item in preferred_types if normalize_text(str(item))}

        def probe_source_preference() -> List[str]:
            preference: List[str] = ["html", "analysis"]
            if "news" in normalized_types:
                preference.append("news")
            return preference

        route_queries: List[Dict[str, str]] = []
        if route_frame.get("zh_anchor_ready"):
            zh_query = route_frame_probe_query(route_frame, "zh")
            if zh_query and zh_query.lower() not in existing_text:
                route_queries.append(
                    {
                        "q": zh_query,
                        "goal": "find_route_page",
                        "source_preference": probe_source_preference(),
                        "origin": "route_frame_probe",
                    }
                )
        if route_frame.get("en_anchor_ready"):
            en_query = route_frame_probe_query(route_frame, "en")
            if en_query and en_query.lower() not in existing_text:
                route_queries.append(
                    {
                        "q": en_query,
                        "goal": "find_route_page",
                        "source_preference": probe_source_preference(),
                        "origin": "route_frame_probe",
                    }
                )
        gap_flags = source_intent.get("_retry_gap_flags") if isinstance(source_intent.get("_retry_gap_flags"), list) else []
        actions = source_intent.get("_retry_recommended_actions") if isinstance(source_intent.get("_retry_recommended_actions"), list) else []
        add_gap_shape_probe = bool(
            gap_brief
            and source_intent.get("_is_retry")
            and (
                "add_gap_query" in actions
                or any(flag in {"utility_judge_conflict", "background_dominant", "poor_page_type", "thin_direct_evidence"} for flag in gap_flags)
            )
        )
        if (not route_queries or add_gap_shape_probe) and gap_brief:
            generic_bridge_query = page_shape_llm_bridge_candidate(
                question,
                claim,
                source_intent,
                existing_queries,
                "find_route_page",
                "",
                gap_brief,
            )
            if generic_bridge_query and generic_bridge_query.lower() not in existing_text:
                route_queries.append(
                    {
                        "q": generic_bridge_query,
                        "goal": "find_route_page",
                        "source_preference": probe_source_preference(),
                        "origin": "gap_pseudo_page_probe",
                    }
                )
        if add_gap_shape_probe:
            gap_queries = [item for item in route_queries if item.get("origin") == "gap_pseudo_page_probe"]
            frame_queries = [item for item in route_queries if item.get("origin") != "gap_pseudo_page_probe"]
            return (frame_queries[:1] + gap_queries[:1])[:2]
        return route_queries[:2]

    query_frames = profile.get("query_frames") if isinstance(profile.get("query_frames"), list) else []
    if not query_frames:
        return []
    compact = (
        retrieval_query_seed_text(question, claim, existing_queries, 6)
        or compact_text_for_query(strip_numeric_values(claim) or claim, 72)
    )
    if not compact:
        return []
    existing_text = " ".join(normalize_text(str(item.get("q") or "")) for item in existing_queries if isinstance(item, dict)).lower()
    page_intent = normalize_page_intent(source_intent)
    page_intent_terms = page_intent_markers(str(page_intent.get("needed_page_type") or ""))
    intent_phrases = {
        "zh": page_intent_query_phrases(str(page_intent.get("needed_page_type") or ""), "zh"),
        "en": page_intent_query_phrases(str(page_intent.get("needed_page_type") or ""), "en"),
    }
    preferred_types = source_intent.get("preferred_source_types") if isinstance(source_intent.get("preferred_source_types"), list) else []
    normalized_types = {normalize_text(str(item)).lower() for item in preferred_types if normalize_text(str(item))}

    def probe_source_preference() -> List[str]:
        preference: List[str] = ["html", "analysis"]
        if "news" in normalized_types:
            preference.append("news")
        return preference

    def probe_seed_text(language: str) -> str:
        candidates: List[str] = []
        for item in existing_queries:
            if not isinstance(item, dict):
                continue
            query_text = normalize_text(str(item.get("q") or ""))
            if not query_text:
                continue
            has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in query_text)
            has_alpha = any("a" <= ch.lower() <= "z" for ch in query_text)
            if language == "zh" and not has_cjk:
                continue
            if language == "en" and not has_alpha:
                continue
            candidates.append(query_text)
        candidates.extend(
            [
                compact_text_for_query(strip_numeric_values(claim) or claim, 72),
                compact_text_for_query(question, 72),
            ]
        )
        for text in candidates:
            normalized = normalize_text(text)
            if not normalized:
                continue
            has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in normalized)
            has_alpha = any("a" <= ch.lower() <= "z" for ch in normalized)
            if language == "zh" and not has_cjk:
                continue
            if language == "en" and not has_alpha:
                continue
            return normalized
        return compact

    def page_probe_terms(language: str) -> List[str]:
        bucket: List[str] = []
        for marker in page_intent_terms:
            marker_text = normalize_text(str(marker))
            if not marker_text or marker_text.lower() in existing_text:
                continue
            has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in marker_text)
            has_alpha = any("a" <= ch.lower() <= "z" for ch in marker_text)
            if language == "zh" and not has_cjk:
                continue
            if language == "en" and not has_alpha:
                continue
            bucket.append(marker_text)
        return dedupe_keep_order(bucket)[:2]

    def compose_shape_probe_query(base_text: str, suffix_text: str, probe_terms: List[str], language: str) -> str:
        phrase_base = probe_seed_text(language)
        base_token_set = {token.lower() for token in query_core_tokens(phrase_base)}

        def residual_phrase(text: str, limit: int = 4) -> str:
            tokens = [
                token
                for token in compact_query_seed_tokens(text, max(4, limit + 2))
                if token.lower() not in base_token_set
            ]
            return " ".join(tokens[:limit])

        phrase_parts: List[str] = []
        if phrase_base:
            phrase_parts.append(phrase_base)
        preferred_phrase = next(
            (
                phrase
                for phrase in intent_phrases.get(language, [])
                if normalize_text(phrase) and normalize_text(phrase).lower() not in " ".join(phrase_parts).lower()
            ),
            "",
        )
        if preferred_phrase:
            phrase_parts.append(preferred_phrase)
        normalized_suffix = residual_phrase(suffix_text)
        if normalized_suffix and normalized_suffix.lower() not in " ".join(phrase_parts).lower():
            phrase_parts.append(normalized_suffix)
        extra_phrase = residual_phrase(" ".join(probe_terms[:1]))
        if extra_phrase and extra_phrase.lower() not in " ".join(phrase_parts).lower():
            phrase_parts.append(extra_phrase)
        phrase_query = compact_text_for_query(" ".join(part for part in phrase_parts if part), 96)
        if len(query_core_tokens(phrase_query)) >= 4:
            return phrase_query
        terms: List[str] = []
        token_source = phrase_base if phrase_base else base_text
        for token in compact_query_seed_tokens(token_source, 8):
            append_query_term_unique(terms, token)
            if len(terms) >= 5:
                break
        if preferred_phrase:
            append_query_term_unique(terms, preferred_phrase)
        extra_added = 0
        for token in compact_query_seed_tokens(suffix_text, 4):
            before = len(terms)
            append_query_term_unique(terms, token)
            if len(terms) > before:
                extra_added += 1
            if extra_added >= 1 or len(terms) >= 8:
                break
        probe_added = 0
        for term in probe_terms:
            before = len(terms)
            append_query_term_unique(terms, term)
            if len(terms) > before:
                probe_added += 1
            if probe_added >= 2 or len(terms) >= 8:
                break
        return " ".join(terms[:8])

    for frame in query_frames:
        goal = normalize_text(str(frame.get("goal") or "general_verify")) or "general_verify"
        zh_suffix = normalize_text(str(frame.get("suffix_zh") or ""))
        en_suffix = normalize_text(str(frame.get("suffix_en") or ""))
        if zh_suffix and zh_suffix.lower() not in existing_text and any("\u4e00" <= ch <= "\u9fff" for ch in compact):
            zh_query = compose_shape_probe_query(compact, zh_suffix, page_probe_terms("zh"), "zh")
            if zh_query:
                queries.append({"q": zh_query, "goal": goal, "source_preference": probe_source_preference()})
        if en_suffix and en_suffix.lower() not in existing_text and any("a" <= ch.lower() <= "z" for ch in compact):
            en_query = compose_shape_probe_query(compact, en_suffix, page_probe_terms("en"), "en")
            if en_query:
                queries.append({"q": en_query, "goal": goal, "source_preference": probe_source_preference()})
    deduped_queries: List[Dict[str, str]] = []
    seen_queries = set()
    for item in queries:
        if not isinstance(item, dict):
            continue
        query_text = normalize_text(str(item.get("q") or ""))
        if not query_text:
            continue
        lowered = query_text.lower()
        if lowered in seen_queries:
            continue
        seen_queries.add(lowered)
        deduped_queries.append(item)
    return deduped_queries[:2]


def compact_text_for_query(text: str, limit: int = 80) -> str:
    text = normalize_text(re.sub(r"[\[\]()*_#`>]+", " ", text or ""))
    return text[:limit].strip()


def numeric_value_discovery_queries(claim: str, source_intent: Dict[str, Any]) -> List[Dict[str, str]]:
    if not structured_numeric_intent(source_intent):
        return []
    query = strip_numeric_values(claim)
    if not query or query == claim:
        return []
    return [
        {"q": f"{query} 实际 数值 官方 新闻", "goal": "verify_numeric_detail"},
        {"q": f"{query} actual value official news", "goal": "verify_numeric_detail"},
    ]


METRIC_VALUE_TYPE_QUERY_TERMS = {
    "central_parity": ["中间价", "官方", "公布", "central parity"],
    "spot_buying_price": ["现汇买入价", "牌价", "spot buying"],
    "cash_buying_price": ["现钞买入价", "牌价", "cash buying"],
    "selling_price": ["现汇卖出价", "卖出价", "牌价", "selling rate"],
    "real_time_rate": ["实时汇率", "行情", "quote"],
    "movement_direction": ["涨跌", "较前一日", "change"],
    "movement_amount": ["涨跌幅", "变动", "change"],
    "movement_percent": ["涨跌幅", "百分比", "percent change"],
    "open_price": ["开盘价", "行情", "open"],
    "close_price": ["收盘价", "行情", "close"],
    "intraday_price": ["盘中", "行情", "intraday"],
    "settlement_price": ["结算价", "settlement"],
    "retail_price": ["零售价", "价格表", "retail price"],
    "spot_price": ["现货价", "spot price"],
    "futures_price": ["期货价", "futures price"],
    "index_level": ["指数", "点位", "index"],
    "generic_value": ["数值", "价格", "行情"],
}

METRIC_SOURCE_AUTHORITY_QUERY_TERMS = {
    "central_bank": ["官网", "官方", "公告", "公布", "中间价"],
    "exchange": ["交易所", "公告", "行情"],
    "bank_rate_table": ["官网", "官方", "外汇牌价", "牌价表", "买入价", "卖出价"],
    "official_notice": ["官方", "公告", "通知"],
    "financial_quote_page": ["行情", "报价", "更新时间"],
    "market_data_page": ["行情", "历史数据", "报价"],
    "price_monitoring_report": ["价格监测", "报告", "官方"],
    "authoritative_news": ["权威", "报道", "数据"],
}


def _metric_slot_search_terms(metric_slots: Dict[str, Any], claim: str) -> List[str]:
    value_type = normalize_text(str(metric_slots.get("value_type") or ""))
    source_authority = normalize_text(str(metric_slots.get("source_authority") or ""))
    raw_parts = [
        str(metric_slots.get("subject_entity") or ""),
        str(metric_slots.get("metric_name") or ""),
        strip_numeric_values(claim),
    ]
    terms: List[str] = []
    for part in raw_parts[:2]:
        phrase = normalize_text(part)
        if not phrase or phrase.lower() in {"unknown", "none", "not_applicable"}:
            continue
        if len(phrase) <= 24:
            append_query_term_unique(terms, phrase)
    for part in raw_parts:
        for token in compact_query_seed_tokens(part, 5):
            append_query_term_unique(terms, token)
            if len(terms) >= 5:
                break
        if len(terms) >= 5:
            break
    time_scope = normalize_text(str(metric_slots.get("time_scope") or ""))
    if time_scope and time_scope.lower() not in {"unknown", "none", "not_applicable", "报价更新时点", "当前时点"}:
        append_query_term_unique(terms, time_scope)
    for token in METRIC_VALUE_TYPE_QUERY_TERMS.get(value_type, [])[:3]:
        append_query_term_unique(terms, token)
    for token in METRIC_SOURCE_AUTHORITY_QUERY_TERMS.get(source_authority, [])[:4]:
        append_query_term_unique(terms, token)
    comparison_baseline = normalize_text(str(metric_slots.get("comparison_baseline") or ""))
    if value_type in {"movement_direction", "movement_amount", "movement_percent"} and comparison_baseline:
        for token in compact_query_seed_tokens(comparison_baseline, 2):
            append_query_term_unique(terms, token)
    return terms[:10]


def metric_source_authority_queries(
    question: str,
    claim: str,
    source_intent: Dict[str, Any],
    existing_queries: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    metric_slots = metric_slots_from_intent(source_intent)
    if not metric_slots:
        return []
    value_type = normalize_text(str(metric_slots.get("value_type") or ""))
    if not value_type or value_type == "not_metric":
        return []
    effective_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    if not (
        mechanism_type_from_intent(source_intent) in {"structured_numeric_authority", "date_authority"}
        or effective_mode in {"numeric_fact", "date_fact", "schedule_fact"}
    ):
        return []
    binding_terms = source_strategy_binding_terms(source_intent, effective_mode)
    existing_text = " ".join(
        normalize_text(str(item.get("q") or ""))
        for item in existing_queries
        if isinstance(item, dict)
    ).lower()
    source_authority = normalize_text(str(metric_slots.get("source_authority") or ""))
    terms: List[str] = []
    for key in ("subject_entity", "relation_or_metric", "time_scope", "unit"):
        value = str(binding_terms.get(key) or "")
        for term in binding_slot_search_values(key, value, source_intent, effective_mode)[:2]:
            append_query_term_unique(terms, term)
    for token in METRIC_SOURCE_AUTHORITY_QUERY_TERMS.get(source_authority, [])[:4]:
        append_query_term_unique(terms, token)
    if source_authority == "bank_rate_table":
        for token in ["外汇牌价", "牌价表", "历史查询"]:
            append_query_term_unique(terms, token)
    if len(terms) < 4:
        terms = dedupe_keep_order(terms + _metric_slot_search_terms(metric_slots, claim))
    if len(terms) < 3:
        compact = retrieval_query_seed_text(question, claim, existing_queries, 5)
        terms = compact_query_seed_tokens(compact, 5) + terms
    query = compact_text_for_query(" ".join(dedupe_keep_order(terms)[:10]), 96)
    if not query or query.lower() in existing_text:
        return []
    preference = ["html"]
    if source_authority in {"central_bank", "exchange", "bank_rate_table", "official_notice", "price_monitoring_report"}:
        preference.insert(0, "official")
    return [{"q": query, "goal": "find_metric_source_page", "source_preference": preference}]


def extract_site_domains(text: str) -> List[str]:
    return dedupe_keep_order(re.findall(r"\bsite:([^\s]+)", text or "", flags=re.I))


def normalize_domain(domain: str) -> str:
    domain = normalize_text(domain).lower()
    domain = re.sub(r"^https?://", "", domain)
    domain = domain.split("/")[0].split("?")[0].strip().lstrip(".")
    if not domain or "." not in domain:
        return ""
    return domain


def preferred_domains_from_intent(source_intent: Dict[str, Any]) -> List[str]:
    raw_domains = source_intent.get("preferred_domains") if isinstance(source_intent, dict) else []
    if not isinstance(raw_domains, list):
        return []
    return dedupe_keep_order([domain for domain in (normalize_domain(str(item)) for item in raw_domains) if domain])[:3]


def query_items_site_domains(query_items: List[Dict[str, Any]]) -> List[str]:
    domains: List[str] = []
    for item in query_items or []:
        if not isinstance(item, dict):
            continue
        query_text = normalize_text(str(item.get("q") or ""))
        if not query_text:
            continue
        for domain in extract_site_domains(query_text):
            normalized = normalize_domain(domain)
            if normalized:
                domains.append(normalized)
    return dedupe_keep_order(domains)[:3]


def sanitize_preferred_domain_query_text(query_text: str, source_intent: Dict[str, Any]) -> str:
    cleaned = normalize_text(query_text)
    if not cleaned:
        return ""
    evidence_target = str(source_intent.get("evidence_target") or "")
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    mechanism_type = mechanism_type_from_intent(source_intent)
    binding_terms = source_strategy_binding_terms(source_intent, evidence_mode)
    if evidence_mode == "numeric_fact" or mechanism_type == "structured_numeric_authority":
        metric_slots = metric_slots_from_intent(source_intent)
        source_authority = normalize_text(str(metric_slots.get("source_authority") or ""))
        rebuilt_terms: List[str] = []
        for key in ("subject_entity", "relation_or_metric", "time_scope", "unit"):
            value = str(binding_terms.get(key) or "")
            for term in binding_slot_search_values(key, value, source_intent, evidence_mode)[:2]:
                append_query_term_unique(rebuilt_terms, term)
        for term in METRIC_SOURCE_AUTHORITY_QUERY_TERMS.get(source_authority, [])[:3]:
            append_query_term_unique(rebuilt_terms, term)
        if source_authority == "bank_rate_table":
            for term in ["外汇牌价", "牌价表"]:
                append_query_term_unique(rebuilt_terms, term)
        if rebuilt_terms:
            rebuilt = compact_text_for_query(" ".join(rebuilt_terms), 96)
            if rebuilt:
                return rebuilt
    if evidence_mode in {"date_fact", "schedule_fact"} or mechanism_type == "date_authority":
        rebuilt_terms = []
        for key in ("subject_entity", "relation_or_metric", "time_scope", "time_window"):
            value = normalize_text(str(binding_terms.get(key) or ""))
            if value:
                append_query_term_unique(rebuilt_terms, value)
        if rebuilt_terms:
            rebuilt = compact_text_for_query(" ".join(rebuilt_terms), 96)
            if rebuilt:
                return rebuilt
    if evidence_target == "prize_amount" or evidence_mode == "numeric_fact" or mechanism_type == "structured_numeric_authority":
        cleaned = strip_numeric_values(cleaned)
        cleaned = re.sub(r"\b(split\s+(?:into|between|across|two)\s+\w+|split\s+two\s+ways)\b", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"\b(divided?\s+(?:equally|between|among)\b.*)", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"(平分|两人平分|二人平分|两位获奖者平分)", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def dynamic_source_type(
    url: str,
    query: str = "",
    preferred_domains: Optional[List[str]] = None,
    source_intent: Optional[Dict[str, Any]] = None,
) -> str:
    if preferred_domains and any(url_matches_domain(url, domain) for domain in preferred_domains):
        return "official"
    site_domain = extract_site_constraint(query)
    if site_domain and url_matches_domain(url, site_domain):
        return "official"
    classified = classify_source_type(url)
    if classified != "unknown":
        return classified
    source_intent = source_intent if isinstance(source_intent, dict) else {}
    evidence_shape = normalize_evidence_shape(source_intent) if source_intent else ""
    if evidence_shape not in {"structured_historical_data", "authoritative_notice", "event_detail_page"}:
        return classified
    host = (urlparse(url).netloc or "").lower()
    domain = registered_domain(host)
    if not domain:
        return classified
    if any(domain.endswith(blocked) for blocked in ["wikipedia.org", "baidu.com", "zhihu.com", "reddit.com", "x.com", "twitter.com", "facebook.com", "youtube.com"]):
        return classified
    needed_page_type = str(normalize_page_intent(source_intent).get("needed_page_type") or "")
    markers = [marker.lower() for marker in page_intent_markers(needed_page_type or "general_page")[:10]]
    combined = f"{url} {query}".lower()
    institutional_domain = (
        domain.endswith(".gov")
        or domain.endswith(".gov.cn")
        or domain.endswith(".edu")
        or domain.endswith(".edu.cn")
        or domain.endswith(".org")
        or domain.endswith(".org.cn")
        or domain.endswith(".int")
    )
    if institutional_domain and any(marker in combined for marker in markers):
        return "official"
    return classified


def fetch_page_text(url: str, max_chars: int = 800, timeout_sec: int = 10, trace: Optional[Dict[str, Any]] = None) -> str:
    if not url:
        return ""
    allow_playwright_rescue = True if not isinstance(trace, dict) else bool(trace.get("allow_playwright_detail_rescue", True))
    cached = cache_get("page", url, max_chars)
    if isinstance(cached, str):
        repaired_cached = repair_mojibake_text(cached)
        if repaired_cached != cached:
            cache_set("page", repaired_cached, url, max_chars)
        return repaired_cached
    try:
        response = guarded_http_get(url, timeout_sec=timeout_sec, source_name="fetch_page_text")
    except Exception as exc:
        if exception_looks_like_anti_bot(exc):
            merge_fetch_trace(
                trace,
                anti_bot_blocked=True,
                playwright_rescue_role="detail_rescue",
                playwright_rescue_trigger="detail_read_blocked",
                environment_block_reason="detail_access_blocked",
                detail_fetch_path="requests_blocked_before_playwright",
                request_block_reasons=[str(exc)],
            )
            if not allow_playwright_rescue:
                merge_fetch_trace(
                    trace,
                    playwright_rescue_skipped_by_policy=True,
                    rescue_skip_reason=str((trace or {}).get("rescue_skip_reason") or "detail_rescue_budget_exhausted"),
                    environment_block_reason="requests_blocked_playwright_failed",
                )
                raise exc
            merge_fetch_trace(trace, playwright_used=True)
            try:
                fallback_text = fetch_with_playwright(url, timeout_sec=timeout_sec, return_html=False)
            except Exception as fallback_exc:
                merge_fetch_trace(
                    trace,
                    playwright_rescued=False,
                    playwright_rescue_role="detail_rescue",
                    playwright_rescue_trigger="detail_read_blocked",
                    environment_block_reason="requests_blocked_playwright_failed",
                    detail_fetch_path="requests_blocked_playwright_failed",
                    playwright_block_reasons=[str(fallback_exc)],
                )
                raise fallback_exc
            if fallback_text:
                result = fallback_text[:max_chars]
                cache_set("page", result, url, max_chars)
                merge_fetch_trace(
                    trace,
                    playwright_rescued=True,
                    playwright_rescue_role="detail_rescue",
                    playwright_rescue_trigger="detail_read_blocked",
                    environment_block_reason="requests_blocked_playwright_rescued",
                    detail_fetch_path="requests_blocked_playwright_rescued",
                )
                return result
        raise
    apparent_encoding = normalize_text(str(response.apparent_encoding or "")).lower()
    current_encoding = normalize_text(str(response.encoding or "")).lower()
    if apparent_encoding and (
        not current_encoding
        or current_encoding in {"iso-8859-1", "latin-1"}
        or (apparent_encoding == "utf-8" and current_encoding != "utf-8")
    ):
        response.encoding = apparent_encoding
    if url.lower().endswith(".pdf"):
        if PdfReader is None:
            return ""
        reader = PdfReader(BytesIO(response.content))
        chunks: List[str] = []
        for page in reader.pages[:8]:
            chunks.append(page.extract_text() or "")
            text = normalize_text(" ".join(chunks))
            if len(text) >= max_chars:
                result = text[:max_chars]
                cache_set("page", result, url, max_chars)
                return result
        result = normalize_text(" ".join(chunks))[:max_chars]
        cache_set("page", result, url, max_chars)
        return result
    text = decode_response_text(response)
    try:
        ensure_response_not_blocked(response, request_url=url, source_name="fetch_page_text", decoded_text=text)
    except Exception as exc:
        if exception_looks_like_anti_bot(exc):
            merge_fetch_trace(
                trace,
                anti_bot_blocked=True,
                playwright_rescue_role="detail_rescue",
                playwright_rescue_trigger="detail_read_blocked",
                environment_block_reason="detail_access_blocked",
                detail_fetch_path="requests_blocked_after_fetch",
                request_block_reasons=[str(exc)],
            )
            if not allow_playwright_rescue:
                merge_fetch_trace(
                    trace,
                    playwright_rescue_skipped_by_policy=True,
                    rescue_skip_reason=str((trace or {}).get("rescue_skip_reason") or "detail_rescue_budget_exhausted"),
                    environment_block_reason="requests_blocked_playwright_failed",
                )
                raise exc
            merge_fetch_trace(trace, playwright_used=True)
            try:
                fallback_text = fetch_with_playwright(url, timeout_sec=timeout_sec, return_html=False)
            except Exception as fallback_exc:
                merge_fetch_trace(
                    trace,
                    playwright_rescued=False,
                    playwright_rescue_role="detail_rescue",
                    playwright_rescue_trigger="detail_read_blocked",
                    environment_block_reason="requests_blocked_playwright_failed",
                    detail_fetch_path="requests_blocked_playwright_failed",
                    playwright_block_reasons=[str(fallback_exc)],
                )
                raise fallback_exc
            if fallback_text:
                result = fallback_text[:max_chars]
                cache_set("page", result, url, max_chars)
                merge_fetch_trace(
                    trace,
                    playwright_rescued=True,
                    playwright_rescue_role="detail_rescue",
                    playwright_rescue_trigger="detail_read_blocked",
                    environment_block_reason="requests_blocked_playwright_rescued",
                    detail_fetch_path="requests_blocked_playwright_rescued",
                )
                return result
        raise
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = normalize_text(text)
    result = text[:max_chars]
    cache_set("page", result, url, max_chars)
    merge_fetch_trace(trace, detail_fetch_path="requests_ok")
    return result


def fetch_page_html(url: str, timeout_sec: int = 10, trace: Optional[Dict[str, Any]] = None) -> str:
    if not url:
        return ""
    allow_playwright_rescue = True if not isinstance(trace, dict) else bool(trace.get("allow_playwright_detail_rescue", True))
    cached = cache_get("page_html", url, 0)
    if isinstance(cached, str):
        repaired_cached = repair_mojibake_text(cached)
        if repaired_cached != cached:
            cache_set("page_html", repaired_cached, url, 0)
        return repaired_cached
    try:
        response = guarded_http_get(url, timeout_sec=timeout_sec, source_name="fetch_page_html")
    except Exception as exc:
        if exception_looks_like_anti_bot(exc):
            merge_fetch_trace(
                trace,
                anti_bot_blocked=True,
                playwright_rescue_role="detail_rescue",
                playwright_rescue_trigger="detail_read_blocked",
                environment_block_reason="detail_access_blocked",
                detail_fetch_path="requests_html_blocked_before_playwright",
                request_block_reasons=[str(exc)],
            )
            if not allow_playwright_rescue:
                merge_fetch_trace(
                    trace,
                    playwright_rescue_skipped_by_policy=True,
                    rescue_skip_reason=str((trace or {}).get("rescue_skip_reason") or "detail_rescue_budget_exhausted"),
                    environment_block_reason="requests_blocked_playwright_failed",
                )
                raise exc
            merge_fetch_trace(trace, playwright_used=True)
            try:
                fallback_html = fetch_with_playwright(url, timeout_sec=timeout_sec, return_html=True)
            except Exception as fallback_exc:
                merge_fetch_trace(
                    trace,
                    playwright_rescued=False,
                    playwright_rescue_role="detail_rescue",
                    playwright_rescue_trigger="detail_read_blocked",
                    environment_block_reason="requests_blocked_playwright_failed",
                    detail_fetch_path="requests_html_blocked_playwright_failed",
                    playwright_block_reasons=[str(fallback_exc)],
                )
                raise fallback_exc
            if fallback_html:
                cache_set("page_html", fallback_html, url, 0)
                merge_fetch_trace(
                    trace,
                    playwright_rescued=True,
                    playwright_rescue_role="detail_rescue",
                    playwright_rescue_trigger="detail_read_blocked",
                    environment_block_reason="requests_blocked_playwright_rescued",
                    detail_fetch_path="requests_html_blocked_playwright_rescued",
                )
                return fallback_html
        raise
    apparent_encoding = normalize_text(str(response.apparent_encoding or "")).lower()
    current_encoding = normalize_text(str(response.encoding or "")).lower()
    if apparent_encoding and (
        not current_encoding
        or current_encoding in {"iso-8859-1", "latin-1"}
        or (apparent_encoding == "utf-8" and current_encoding != "utf-8")
    ):
        response.encoding = apparent_encoding
    html = decode_response_text(response) or ""
    try:
        ensure_response_not_blocked(response, request_url=url, source_name="fetch_page_html", decoded_text=html)
    except Exception as exc:
        if exception_looks_like_anti_bot(exc):
            merge_fetch_trace(
                trace,
                anti_bot_blocked=True,
                playwright_rescue_role="detail_rescue",
                playwright_rescue_trigger="detail_read_blocked",
                environment_block_reason="detail_access_blocked",
                detail_fetch_path="requests_html_blocked_after_fetch",
                request_block_reasons=[str(exc)],
            )
            if not allow_playwright_rescue:
                merge_fetch_trace(
                    trace,
                    playwright_rescue_skipped_by_policy=True,
                    rescue_skip_reason=str((trace or {}).get("rescue_skip_reason") or "detail_rescue_budget_exhausted"),
                    environment_block_reason="requests_blocked_playwright_failed",
                )
                raise exc
            merge_fetch_trace(trace, playwright_used=True)
            try:
                fallback_html = fetch_with_playwright(url, timeout_sec=timeout_sec, return_html=True)
            except Exception as fallback_exc:
                merge_fetch_trace(
                    trace,
                    playwright_rescued=False,
                    playwright_rescue_role="detail_rescue",
                    playwright_rescue_trigger="detail_read_blocked",
                    environment_block_reason="requests_blocked_playwright_failed",
                    detail_fetch_path="requests_html_blocked_playwright_failed",
                    playwright_block_reasons=[str(fallback_exc)],
                )
                raise fallback_exc
            if fallback_html:
                cache_set("page_html", fallback_html, url, 0)
                merge_fetch_trace(
                    trace,
                    playwright_rescued=True,
                    playwright_rescue_role="detail_rescue",
                    playwright_rescue_trigger="detail_read_blocked",
                    environment_block_reason="requests_blocked_playwright_rescued",
                    detail_fetch_path="requests_html_blocked_playwright_rescued",
                )
                return fallback_html
        raise
    cache_set("page_html", html, url, 0)
    merge_fetch_trace(trace, detail_fetch_path="requests_html_ok")
    return html


def external_access_rescue_smoke(
    url: str,
    fetch_kind: str = "text",
    timeout_sec: int = 10,
    max_chars: int = 1200,
) -> Dict[str, Any]:
    trace: Dict[str, Any] = {}
    preview = ""
    error = ""
    try:
        if fetch_kind == "html":
            content = fetch_page_html(url, timeout_sec=timeout_sec, trace=trace)
        else:
            content = fetch_page_text(url, max_chars=max_chars, timeout_sec=timeout_sec, trace=trace)
        preview = normalize_text(str(content or ""))[:180]
    except Exception as exc:
        error = str(exc)
    return {
        "url": url,
        "fetch_kind": fetch_kind,
        "ok": not error,
        "preview": preview,
        "error": error[:240],
        "playwright_rescued": bool(trace.get("playwright_rescued")),
        "playwright_used": bool(trace.get("playwright_used")),
        "environment_block_reason": str(trace.get("environment_block_reason") or ""),
        "detail_fetch_path": str(trace.get("detail_fetch_path") or ""),
        "request_block_reasons": [str(value) for value in (trace.get("request_block_reasons") or []) if str(value)][:6],
        "playwright_block_reasons": [str(value) for value in (trace.get("playwright_block_reasons") or []) if str(value)][:6],
    }


def batch_external_access_rescue_smoke(
    urls: List[str],
    fetch_kind: str = "text",
    timeout_sec: int = 10,
    max_chars: int = 1200,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for url in urls:
        normalized = normalize_text(str(url or ""))
        if not normalized:
            continue
        results.append(
            external_access_rescue_smoke(
                normalized,
                fetch_kind=fetch_kind,
                timeout_sec=timeout_sec,
                max_chars=max_chars,
            )
        )
    return results


def evaluate_external_access_rescue_expectations(
    smoke_input: Dict[str, Any],
    timeout_sec: int = 10,
    max_chars: int = 1200,
) -> Dict[str, Any]:
    success_urls = [normalize_text(str(url)) for url in (smoke_input.get("rescue_expected_success") or []) if normalize_text(str(url))]
    fail_urls = [normalize_text(str(url)) for url in (smoke_input.get("rescue_expected_fail") or []) if normalize_text(str(url))]
    success_results = batch_external_access_rescue_smoke(success_urls, fetch_kind="text", timeout_sec=timeout_sec, max_chars=max_chars)
    fail_results = batch_external_access_rescue_smoke(fail_urls, fetch_kind="text", timeout_sec=timeout_sec, max_chars=max_chars)
    success_pass = [
        item for item in success_results
        if item.get("playwright_rescued") and item.get("preview")
    ]
    fail_pass = [
        item for item in fail_results
        if (not item.get("playwright_rescued")) and str(item.get("environment_block_reason") or "") in {
            "requests_blocked_playwright_failed",
            "source_access_blocked_without_rescue",
            "detail_read_failed_after_fetch",
        }
    ]
    return {
        "rescue_expected_success": success_results,
        "rescue_expected_fail": fail_results,
        "success_pass_count": len(success_pass),
        "fail_pass_count": len(fail_pass),
        "success_total": len(success_results),
        "fail_total": len(fail_results),
        "all_passed": len(success_pass) == len(success_results) and len(fail_pass) == len(fail_results),
    }


def choose_sources(claim: str, question: str, time_value: str) -> List[str]:
    features = detect_claim_features(question, claim)
    sources = ["bing_news_rss", "bing_rss", "sogou_html"]
    if ENABLE_DUCKDUCKGO:
        sources.append("duckduckgo_html")
    if not (features["has_date"] or features["has_amount"] or features["has_score"] or features["has_route"]):
        sources.append("wikipedia")
    return dedupe_keep_order(sources)


def source_plan_for_query(source_plan: List[str], query: str) -> List[str]:
    if extract_site_constraint(query):
        site_sources = ["domain_sitemap", "bing_rss"]
        if html_search_available():
            site_sources.append("bing_html")
        return dedupe_keep_order(site_sources)
    if ENABLE_DUCKDUCKGO:
        return source_plan
    return [source for source in source_plan if source != "duckduckgo_html"]


def reorder_sources_by_query_preference(
    sources: List[str],
    goal: str,
    query: str,
    source_preference: List[str],
) -> List[str]:
    if not sources:
        return sources
    preference = {normalize_text(str(item)).lower() for item in source_preference if normalize_text(str(item))}
    priority: List[str] = []
    if goal in {"discover_truth", "find_news"}:
        priority.extend(["bing_news_rss", "bing_news_zh_rss", "bing_html", "sogou_html"])
        if ENABLE_DUCKDUCKGO:
            priority.append("duckduckgo_html")
        priority.append("bing_rss")
    elif goal == "verify_original":
        priority.extend(["bing_html", "bing_news_rss", "bing_news_zh_rss", "sogou_html"])
        if ENABLE_DUCKDUCKGO:
            priority.append("duckduckgo_html")
        priority.append("bing_rss")
    elif goal == "find_context":
        priority.extend(["bing_news_rss", "bing_html", "bing_news_zh_rss", "sogou_html", "bing_rss"])
    if "official" in preference:
        priority = ["domain_sitemap", "bing_html", "sogou_html"] + [item for item in priority if item not in {"domain_sitemap", "bing_html", "sogou_html"}]
    elif "news" in preference:
        priority = ["bing_news_rss", "bing_news_zh_rss", "bing_html", "sogou_html"] + [item for item in priority if item not in {"bing_news_rss", "bing_news_zh_rss", "bing_html", "sogou_html"}]
    if "forum" not in preference and goal in {"discover_truth", "find_news", "verify_original"}:
        priority = [item for item in priority if item != "bing_rss"] + (["bing_rss"] if "bing_rss" in sources else [])
    if "html" in preference or ("analysis" in preference and is_english_query(query)):
        priority = ["bing_html", "sogou_html"] + [item for item in priority if item not in {"bing_html", "sogou_html"}]
        if ENABLE_DUCKDUCKGO:
            priority = ["duckduckgo_html"] + [item for item in priority if item != "duckduckgo_html"]
    if not priority:
        return sources
    available_priority = [item for item in dedupe_keep_order(priority) if item in sources]
    if not available_priority:
        return dedupe_keep_order(sources)
    return reorder_sources_by_priority_order(dedupe_keep_order(sources), available_priority)


def source_plan_for_query_goal(
    source_plan: List[str],
    query_or_item: Any,
    goal: Optional[str],
    source_intent: Dict[str, Any],
) -> List[str]:
    query_item = query_or_item if isinstance(query_or_item, dict) else {}
    query = normalize_text(str(query_item.get("q") or query_or_item or ""))
    query_goal = normalize_text(str(query_item.get("goal") or goal or "general_verify")) or "general_verify"
    query_family_role = normalize_text(str(query_item.get("query_family_role") or ""))
    source_preference = query_item.get("source_preference") if isinstance(query_item.get("source_preference"), list) else []
    sources = source_plan_for_query(source_plan, query)
    initial_sources = list(sources)
    query_item["_source_order_trace"] = []
    query_item["_planned_source_order"] = initial_sources[:10]
    note_source_order_stage(query_item, "planned_source_order", initial_sources, reason="source_plan_for_query")
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    if query_goal == "find_metric_source_page":
        priority_sources = ["bing_html", "sogou_html", "bing_rss"]
        if ENABLE_DUCKDUCKGO:
            priority_sources.append("duckduckgo_html")
        priority_sources.extend(["bing_news_zh_rss", "bing_news_rss"])
        sources = reorder_sources_by_priority_order(dedupe_keep_order(priority_sources + sources), priority_sources)
        sources = reorder_sources_by_query_preference(sources, query_goal, query, [str(item) for item in source_preference])
        note_source_order_stage(query_item, "post_role_priority_order", sources, initial_sources, "metric_source_priority")
        sources = finalize_route_source_plan(sources, source_intent, query_goal)
        note_source_order_stage(query_item, "post_route_finalize_order", sources, query_item.get("_post_role_priority_order") or initial_sources, "route_finalize")
        query_item["_post_role_priority_order"] = [str(item) for item in sources][:10]
        return sources
    if query_goal == "find_page_intent_page":
        priority_sources = ["bing_html", "sogou_html"]
        if ENABLE_DUCKDUCKGO:
            priority_sources.append("duckduckgo_html")
        priority_sources.extend(["bing_news_rss", "bing_news_zh_rss", "bing_rss"])
        sources = reorder_sources_by_priority_order(dedupe_keep_order(priority_sources + sources), priority_sources)
        note_source_order_stage(query_item, "post_role_priority_order", sources, initial_sources, "page_intent_priority")
        query_item["_post_role_priority_order"] = [str(item) for item in sources][:10]
        return sources
    profile = retrieval_profile(source_intent)
    priority_sources = profile_sources_for_goal(profile, query_goal, query, source_intent)
    if priority_sources:
        before_priority = list(sources)
        sources = reorder_sources_by_priority_order(dedupe_keep_order(priority_sources + sources), priority_sources)
        note_source_order_stage(query_item, "profile_priority_order", sources, before_priority, "profile_sources_for_goal")
    role_priority: List[str] = []
    if query_family_role == "closure":
        role_priority = ["domain_sitemap", "bing_rss", "bing_news_zh_rss", "bing_news_rss", "bing_html"]
    elif query_family_role == "distinguish":
        role_priority = ["domain_sitemap", "bing_html", "bing_news_zh_rss", "bing_news_rss", "bing_rss"]
    elif query_family_role == "refute":
        role_priority = ["bing_news_zh_rss", "bing_news_rss", "bing_html", "bing_rss", "domain_sitemap"]
    elif query_goal == "verification_question" and evidence_mode in {"numeric_fact", "date_fact", "schedule_fact", "route_fact", "event_result"}:
        role_priority = ["domain_sitemap", "bing_news_zh_rss", "bing_news_rss", "bing_html", "bing_rss"]
    if ENABLE_DUCKDUCKGO and role_priority:
        insert_after = role_priority.index("bing_html") + 1 if "bing_html" in role_priority else len(role_priority)
        role_priority = role_priority[:insert_after] + ["duckduckgo_html"] + role_priority[insert_after:]
    if role_priority:
        before_role = list(sources)
        sources = reorder_sources_by_priority_order(dedupe_keep_order(role_priority + sources), role_priority)
        note_source_order_stage(query_item, "role_priority_order", sources, before_role, "query_family_role")
    before_shape = list(sources)
    sources = reorder_sources_by_evidence_shape(sources, source_intent)
    note_source_order_stage(query_item, "evidence_shape_order", sources, before_shape, "reorder_sources_by_evidence_shape")
    before_preference = list(sources)
    sources = reorder_sources_by_query_preference(sources, query_goal, query, [str(item) for item in source_preference])
    note_source_order_stage(query_item, "query_preference_order", sources, before_preference, "reorder_sources_by_query_preference")
    authority_first = query_needs_authority_pair(query_goal, query_family_role, source_intent)
    if authority_first and "sogou_html" in sources:
        before_sogou = list(sources)
        sources = [item for item in sources if item != "sogou_html"] + ["sogou_html"]
        note_source_order_stage(query_item, "authority_first_sogou_demoted", sources, before_sogou, "non_sogou_html_preferred")
    query_item["_post_role_priority_order"] = [str(item) for item in sources][:10]
    note_source_order_stage(query_item, "post_role_priority_order", sources, initial_sources, "pre_budget_contract")
    before_finalize = list(sources)
    sources = finalize_route_source_plan(sources, source_intent, query_goal)
    note_source_order_stage(query_item, "post_route_finalize_order", sources, before_finalize, "finalize_route_source_plan")
    query_item["_post_role_priority_order"] = [str(item) for item in sources][:10]
    if query_goal != "verification_question" or not ENABLE_QA_ENHANCED_SOURCES:
        return sources
    return sources


def adaptive_fallback_candidates(source_plan: List[str], source_jobs: List[tuple[str, str]], query: str) -> List[tuple[str, str]]:
    if extract_site_constraint(query):
        return []
    existing = {source_name for source_name, _ in source_jobs}
    candidates = []
    for source_name in source_plan_for_query(source_plan, query):
        if source_name not in existing:
            candidates.append((source_name, query))
    for source_name in ["bing_html", "sogou_html", "bing_rss"]:
        if source_name == "bing_html" and not (ENABLE_BING_HTML or ENABLE_QA_BING_HTML):
            continue
        if source_name not in existing:
            candidates.append((source_name, query))
    deduped: List[tuple[str, str]] = []
    seen = set()
    for item in candidates:
        if item[0] in seen:
            continue
        seen.add(item[0])
        deduped.append(item)
    return deduped


def route_retry_should_fetch_detail(
    source_name: str,
    item: Dict[str, Any],
    rough_relevance: int,
    rough_matches: int,
    source_intent: Dict[str, Any],
) -> bool:
    if str(source_intent.get("evidence_mode") or "") != "route_fact" or not source_intent.get("_is_retry"):
        return False
    if rough_matches < 1 or rough_relevance < 2:
        return False
    url_text = str(item.get("url") or "").lower()
    title_text = str(item.get("title") or "").lower()
    if any(token in url_text or token in title_text for token in ["zhihu.com", "baidu.com/question", "quora.com"]):
        return False
    if source_name in {"bing_news_rss", "bing_news_zh_rss", "bing_html", "duckduckgo_html", "playwright_duckduckgo"}:
        return True
    return False


def has_high_priority_source_attempt(stats: Dict[str, Any]) -> bool:
    pollution = stats.get("source_pollution_stats") if isinstance(stats.get("source_pollution_stats"), dict) else {}
    for source_name, bucket in pollution.items():
        if not isinstance(bucket, dict):
            continue
        if source_family_name(str(source_name)) in {"html", "news_rss"} and int(bucket.get("calls", 0) or 0) > 0:
            return True
    return False


def has_source_level_anti_bot(stats: Dict[str, Any]) -> bool:
    pollution = stats.get("source_pollution_stats") if isinstance(stats.get("source_pollution_stats"), dict) else {}
    for bucket in pollution.values():
        if isinstance(bucket, dict) and int(bucket.get("anti_bot_blocks", 0) or 0) > 0:
            return True
    return False


def infer_playwright_rescue_state(stats: Dict[str, Any]) -> str:
    playwright_rescued = int(stats.get("playwright_rescued", 0) or 0)
    playwright_queries = stats.get("playwright_queries") if isinstance(stats.get("playwright_queries"), list) else []
    skipped_reasons = stats.get("playwright_skipped_reasons") if isinstance(stats.get("playwright_skipped_reasons"), list) else []
    family_rescue_budget_used = stats.get("family_rescue_budget_used") if isinstance(stats.get("family_rescue_budget_used"), dict) else {}
    serp_count = int(family_rescue_budget_used.get("serp_count", 0) or 0)
    detail_count = int(family_rescue_budget_used.get("detail_count", 0) or 0)
    pollution = stats.get("source_pollution_stats") if isinstance(stats.get("source_pollution_stats"), dict) else {}
    playwright_bucket = pollution.get("playwright_duckduckgo") if isinstance(pollution.get("playwright_duckduckgo"), dict) else {}
    playwright_calls = int(playwright_bucket.get("calls", 0) or 0)
    playwright_raw = int(playwright_bucket.get("raw", 0) or 0)
    rescue_success_gate = str(stats.get("rescue_success_gate") or "")
    rescue_roi_state = str(stats.get("rescue_roi_state") or "")
    if playwright_rescued > 0 or playwright_raw > 0 or rescue_success_gate or rescue_roi_state in {"search_result_recovered", "detail_content_recovered", "detail_candidates_recovered"}:
        return "playwright_rescue_succeeded"
    if playwright_calls > 0 or playwright_queries or serp_count > 0 or detail_count > 0:
        return "playwright_rescue_failed"
    if skipped_reasons:
        return "playwright_rescue_skipped_by_policy"
    return ""


def playwright_rescue_mode_allowed(
    evidence_mode: str,
    centrality: str,
    source_intent: Optional[Dict[str, Any]] = None,
) -> bool:
    mode = effective_evidence_mode(source_intent or {}, evidence_mode)
    central = normalize_text(str(centrality or "supporting")) or "supporting"
    if mode in {"numeric_fact", "date_fact", "schedule_fact"}:
        return central in {"core", "supporting"}
    if mode == "route_fact":
        return central in {"core", "supporting"}
    if mode == "event_result":
        return central == "core"
    if mode == "entity_fact":
        return central in {"core", "supporting"}
    return False


def high_priority_search_source(source_name: str) -> bool:
    return source_name in {
        "domain_sitemap",
        "bing_news_zh_rss",
        "bing_news_rss",
        "bing_html",
        "duckduckgo_html",
        "bing_rss",
    }


def build_search_request(
    claim_item: Dict[str, Any],
    source_intent: Dict[str, Any],
    query_plan: List[Dict[str, Any]],
    evidence_mode: str,
) -> Dict[str, Any]:
    first_query = query_plan[0] if query_plan and isinstance(query_plan[0], dict) else {}
    return {
        "claim_id": str(claim_item.get("claim_id") or claim_item.get("id") or ""),
        "claim_family": normalize_text(str(claim_item.get("claim_family") or "")),
        "evidence_mode": normalize_text(str(evidence_mode or "")),
        "intended_decision_channel": normalize_text(str(claim_item.get("intended_decision_channel") or "")),
        "query_goal": normalize_text(str(first_query.get("goal") or "general_verify")) or "general_verify",
        "query_family_role": normalize_text(str(first_query.get("query_family_role") or "")),
        "query_variant_origin": normalize_text(str(first_query.get("origin") or "")) or "planner",
        "preferred_domains": preferred_domains_from_intent(source_intent)[:8],
    }


def build_search_policy(
    claim_query_limit: int,
    claim_source_limit: int,
    preferred_domains: List[str],
    source_plan: List[str],
    source_intent: Dict[str, Any],
    evidence_mode: str,
    centrality: str,
) -> Dict[str, Any]:
    return {
        "query_limit": int(claim_query_limit or 0),
        "source_limit": int(claim_source_limit or 0),
        "playwright_max_queries_per_claim": int(PLAYWRIGHT_MAX_QUERIES_PER_CLAIM or 0),
        "playwright_after_search": bool(PLAYWRIGHT_AFTER_SEARCH),
        "playwright_rescue_eligible": playwright_rescue_mode_allowed(evidence_mode, centrality, source_intent),
        "authority_first": bool(
            preferred_domains
            or effective_evidence_mode(source_intent, evidence_mode) in {"numeric_fact", "date_fact", "schedule_fact", "route_fact", "event_result"}
        ),
        "preferred_domains": [str(item) for item in preferred_domains][:8],
        "source_plan": [str(item) for item in source_plan][:8],
    }


def summarize_search_execution_trace(stats: Dict[str, Any]) -> Dict[str, Any]:
    executed_plan = stats.get("executed_query_source_plan") if isinstance(stats.get("executed_query_source_plan"), list) else []
    effective_source_plan = [str(item) for item in (stats.get("effective_source_plan") or []) if str(item)][:10]
    source_budget_cutoff = stats.get("source_budget_cutoff") if isinstance(stats.get("source_budget_cutoff"), dict) else {}
    provider_health_snapshot = stats.get("provider_health_snapshot") if isinstance(stats.get("provider_health_snapshot"), list) else []
    first_row = executed_plan[0] if executed_plan and isinstance(executed_plan[0], dict) else {}
    return {
        "query_count": int(stats.get("query_count", 0) or 0),
        "planned_query_count": int(stats.get("planned_query_count", 0) or 0),
        "executed_query_count": len(executed_plan),
        "executed_query_source_plan": executed_plan[:6],
        "effective_source_plan": effective_source_plan,
        "source_budget_cutoff": source_budget_cutoff,
        "provider_health_snapshot": provider_health_snapshot[:5],
        "playwright_rescue_roles": dedupe_keep_order([str(item) for item in (stats.get("playwright_roles") or []) if str(item)])[:4],
        "playwright_rescue_triggers": dedupe_keep_order([str(item) for item in (stats.get("playwright_reasons") or []) if str(item)])[:4],
        "detail_fetch_paths": stats.get("detail_fetch_paths", {}) if isinstance(stats.get("detail_fetch_paths"), dict) else {},
        "source_order_trace": first_row.get("source_order_trace", []) if isinstance(first_row, dict) else [],
        "final_executed_source_order": first_row.get("final_executed_source_order", []) if isinstance(first_row, dict) else [],
    }


def summarize_search_outcome(
    raw_results: int,
    kept_web: int,
    access_path_state: str,
    access_block_source: str,
    official_entry_hit: bool,
    playwright_rescue_state: str,
    answer_candidate_total: int,
) -> Dict[str, Any]:
    return {
        "raw_results": int(raw_results or 0),
        "kept_web": int(kept_web or 0),
        "answer_candidate_total": int(answer_candidate_total or 0),
        "access_path_state": normalize_text(str(access_path_state or "")),
        "access_block_source": normalize_text(str(access_block_source or "")),
        "official_entry_hit": bool(official_entry_hit),
        "playwright_rescue_state": normalize_text(str(playwright_rescue_state or "")),
    }


def build_specialized_queries(question: str, claim: str, time_value: str) -> List[str]:
    queries: List[str] = []
    features = detect_claim_features(question, claim)
    years = extract_year_tokens(f"{question} {claim} {time_value}")
    core_tokens = query_core_tokens(f"{question} {claim}")[:6]
    compact = " ".join(core_tokens)
    if compact:
        queries.append(compact)
    if compact and years:
        queries.append(f"{compact} {' '.join(years[:2])}")
    if compact and features["has_amount"]:
        queries.append(f"{compact} amount")
        without_numbers = strip_numeric_values(claim)
        if without_numbers and without_numbers != claim:
            queries.append(f"{without_numbers} 实际 数值 官方 新闻")
            queries.append(f"{without_numbers} actual value official news")
    if compact and features["has_time_event"]:
        queries.append(f"{compact} announcement")
    if compact and features["has_route"]:
        queries.append(f"{compact} route")
    if compact and features["has_score"]:
        queries.append(f"{compact} score")
    return dedupe_keep_order(queries)[:5]


def strip_numeric_values(text: str) -> str:
    text = normalize_text(text)
    text = re.sub(r"\d+(?:\.\d+)?\s*[-~—至到]\s*\d+(?:\.\d+)?\s*(?:万|亿)?\s*(?:元/吨|元/升|元|%|吨|升|公里|小时|分钟)?", " ", text)
    text = re.sub(r"\d+(?:\.\d+)?\s*(?:万|亿)?\s*(?:元/吨|元/升|元|%|吨|升|公里|小时|分钟)", " ", text)
    text = re.sub(r"\b(?:19|20)\d{2}\b", " ", text)
    return normalize_text(text)


def evidence_relevance_score(query: str, item: Dict[str, Any]) -> int:
    text = f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')}".lower()
    query_text = query.lower()
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{3,}", query_text)
    tokens = dedupe_keep_order(tokens)
    score = 0
    for token in tokens:
        if token.lower() in text:
            score += 2 if len(token) >= 4 else 1
    source_type = item.get("source_type")
    if source_type == "official":
        score += 3
    elif source_type in {"news", "encyclopedia"}:
        score += 1
    if item.get("source") == "wikipedia" and re.search(r"\d{4}|今天|今日|目前|最新|开盘|休市|比赛|比分", query):
        score -= 3
    return score


def evidence_directness_score(query: str, item: Dict[str, Any], evidence_mode: str = "") -> int:
    text = f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')}".lower()
    query_text = query.lower()
    mode = (evidence_mode or "").lower()
    score = 0
    if mode == "route_fact":
        sentence = route_sentence_analysis(query, item)
        marker_hits = sum(1 for marker in ROUTE_RELATION_MARKERS if route_marker_present(text, marker))
        token_hits = sum(1 for token in route_entity_tokens(query_text) if token.lower() in text)
        if marker_hits <= 0:
            return 0
        if sentence.get("direct_sentence"):
            score += 3
        else:
            score += 1
        if token_hits >= 2:
            score += 2
        elif token_hits >= 1 and marker_hits >= 1:
            score += 1
        if len(route_entity_tokens(query_text)) >= 2 and token_hits >= 1:
            score += 1
        if marker_hits >= 1 and token_hits >= 1:
            score += 1
        return score
    elif mode == "numeric_fact":
        markers = ["amount", "price", "score", "rate", "million", "billion", "金额", "奖金", "涨幅", "元", "%"]
    elif mode in {"date_fact", "schedule_fact"}:
        markers = ["date", "announced", "announcement", "schedule", "公布", "日期", "时间", "休市", "交易日"]
    elif mode == "policy_fact":
        markers = ["policy", "rule", "notice", "statement", "公告", "政策", "规则", "声明"]
    else:
        markers = []
    score += sum(1 for marker in markers if marker in text)
    if mode == "numeric_fact" and re.search(r"\d", text):
        score += 1
    if mode in {"date_fact", "schedule_fact"} and extract_temporal_markers(text):
        score += 1
    if mode in {"entity_fact", "event_result"}:
        token_hits = sum(1 for token in query_core_tokens(query_text) if token.lower() in text)
        if token_hits >= 3:
            score += 2
        elif token_hits >= 2:
            score += 1
    return score


def extract_numeric_markers(text: str) -> List[str]:
    markers = re.findall(r"\d+(?:\.\d+)?\s*(?:万|亿)?\s*(?:%|元/吨|元/升|元|吨|升|公里|千米|美元|人民币|克朗|sek|分|比|:)?", text or "", flags=re.I)
    return dedupe_keep_order([normalize_text(marker).lower() for marker in markers if normalize_text(marker)])[:10]


STRUCTURED_TABLE_HEADER_ALIASES = {
    "spot_buying_price": ["现汇买入价", "spot buying", "buying rate", "bid"],
    "cash_buying_price": ["现钞买入价", "cash buying"],
    "selling_price": ["现汇卖出价", "卖出价", "selling rate", "ask"],
    "middle_price": ["中行折算价", "中间价", "reference rate", "middle rate"],
    "publish_time": ["发布时间", "更新日期", "更新时间", "日期", "时间", "publish time", "update time", "date"],
    "currency": ["货币名称", "币种", "currency", "currency name"],
}


STRUCTURED_TABLE_ROW_STOPWORDS = {
    "下一页", "上一页", "首页", "尾页", "共", "页", "查询", "重置",
}


def normalize_structured_table_header(text: str) -> str:
    normalized = normalize_text(text).lower()
    if not normalized:
        return ""
    for field_name, aliases in STRUCTURED_TABLE_HEADER_ALIASES.items():
        if any(alias.lower() in normalized for alias in aliases):
            return field_name
    return ""


def is_structured_table_value(value: str) -> bool:
    normalized = normalize_text(value)
    if not normalized:
        return False
    if any(stopword == normalized for stopword in STRUCTURED_TABLE_ROW_STOPWORDS):
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?", normalized):
        return True
    if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?", normalized):
        return True
    if re.fullmatch(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{1,12}", normalized):
        return True
    return False


def extract_structured_table_points(
    item: Dict[str, Any],
    source_intent: Dict[str, Any],
    timeout_sec: int = 10,
    max_points: int = 64,
    fetch_trace: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    url = str(item.get("url") or "")
    source_type = str(item.get("source_type") or "")
    if not url or BeautifulSoup is None or source_type != "official":
        return []
    source_authority = normalize_text(
        str(metric_slots_from_intent(source_intent).get("source_authority") or "")
    ).lower()
    if source_authority != "bank_rate_table":
        return []
    try:
        html = fetch_page_html(url, timeout_sec=timeout_sec, trace=fetch_trace)
    except Exception:
        return []
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    points: List[Dict[str, Any]] = []
    seen_keys = set()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header_fields: List[str] = []
        for row in rows[:2]:
            cells = row.find_all(["th", "td"])
            candidate_headers = [normalize_structured_table_header(cell.get_text(" ", strip=True)) for cell in cells]
            recognized = [field for field in candidate_headers if field]
            if len(recognized) >= 2 and ("currency" in recognized or "publish_time" in recognized):
                header_fields = candidate_headers
                break
        if not header_fields:
            continue
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) != len(header_fields):
                continue
            field_map: Dict[str, str] = {}
            for field_name, cell in zip(header_fields, cells):
                if not field_name:
                    continue
                value = normalize_text(cell.get_text(" ", strip=True))
                if not is_structured_table_value(value):
                    continue
                field_map[field_name] = value
            if not field_map:
                continue
            currency = normalize_text(str(field_map.get("currency") or ""))
            publish_time = normalize_text(str(field_map.get("publish_time") or ""))
            if not currency and not publish_time:
                continue
            numeric_fields = {
                key: value
                for key, value in field_map.items()
                if key not in {"currency", "publish_time"} and re.search(r"\d", value)
            }
            if not numeric_fields:
                continue
            key = (
                currency.lower(),
                publish_time.lower(),
                tuple(sorted((field, value) for field, value in numeric_fields.items())),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            points.append(
                {
                    "source_url": url,
                    "source_title": normalize_text(str(item.get("title") or "")),
                    "currency": currency,
                    "publish_time": publish_time,
                    "fields": numeric_fields,
                }
            )
            if len(points) >= max_points:
                return points
    return points


def structured_table_point_contract(
    point: Dict[str, Any],
    source_intent: Dict[str, Any],
) -> Dict[str, Any]:
    metric_slots = metric_slots_from_intent(source_intent)
    binding = core_binding_from_intent(source_intent)
    query_subject = normalize_text(
        str(binding.get("subject_entity") or metric_slots.get("subject_entity") or "")
    )
    time_scope = normalize_text(str(binding.get("time_scope") or metric_slots.get("time_scope") or ""))
    value_type = normalize_text(str(metric_slots.get("value_type") or "")).lower()
    point_currency = normalize_text(str(point.get("currency") or ""))
    publish_time = normalize_text(str(point.get("publish_time") or ""))
    fields = point.get("fields") if isinstance(point.get("fields"), dict) else {}
    signals: List[str] = []
    risks: List[str] = []
    score = 0

    if point_currency:
        score += 12
        signals.append("point_currency_present")
    if publish_time:
        score += 10
        signals.append("point_publish_time_present")
    if value_type and value_type in fields:
        score += 22
        signals.append("point_metric_field_present")
    else:
        risks.append("point_metric_field_missing")
    if time_scope:
        if metric_time_scope_matches_context(
            source_intent,
            publish_time=publish_time,
            title=str(point.get("title") or ""),
            url=str(point.get("url") or ""),
            detail=" ".join(str(value) for value in fields.values()),
        ):
            score += 22
            signals.append("point_time_scope_match")
        else:
            risks.append("point_time_scope_mismatch")
    if query_subject:
        subject_lower = query_subject.lower()
        currency_lower = point_currency.lower()
        if any(token in currency_lower for token in ["美元", "usd"]) and any(token in subject_lower for token in ["美元", "usd"]):
            score += 14
            signals.append("point_subject_currency_match")
        else:
            risks.append("point_subject_currency_mismatch")
    point_value = normalize_text(str(fields.get(value_type) or ""))
    if point_value:
        score += 12
        signals.append("point_metric_value_present")
    else:
        risks.append("point_metric_value_missing")

    status = "failed"
    if "point_metric_field_present" in signals and "point_time_scope_match" in signals and "point_subject_currency_match" in signals:
        status = "satisfied"
    elif score >= 28:
        status = "partial"
    return {
        "status": status,
        "score": score,
        "signals": signals[:6],
        "risks": risks[:6],
        "value": point_value,
    }


def best_structured_table_point(
    points: List[Dict[str, Any]],
    source_intent: Dict[str, Any],
) -> Dict[str, Any]:
    best_point: Dict[str, Any] = {}
    best_score = -1
    for point in points:
        contract = structured_table_point_contract(point, source_intent)
        enriched = dict(point)
        enriched["point_contract"] = contract
        score = int(contract.get("score") or 0)
        if score > best_score:
            best_point = enriched
            best_score = score
    return best_point


def enrich_structured_table_evidence(
    item: Dict[str, Any],
    source_intent: Dict[str, Any],
    timeout_sec: int = 10,
    fetch_trace: Optional[Dict[str, Any]] = None,
) -> None:
    points = extract_structured_table_points(item, source_intent, timeout_sec=timeout_sec, fetch_trace=fetch_trace)
    if not points:
        return
    scored_points: List[Dict[str, Any]] = []
    for point in points:
        contract = structured_table_point_contract(point, source_intent)
        enriched_point = dict(point)
        enriched_point["point_contract"] = contract
        scored_points.append(enriched_point)
    scored_points.sort(key=lambda point: int(((point.get("point_contract") or {}).get("score") or 0)), reverse=True)
    best_point = scored_points[0] if scored_points else {}
    item["structured_table_points"] = scored_points[:8]
    if best_point:
        item["structured_table_best_point"] = best_point
        point_contract = best_point.get("point_contract") if isinstance(best_point.get("point_contract"), dict) else {}
        item["structured_point_contract_status"] = point_contract.get("status")
        item["structured_point_contract_score"] = point_contract.get("score")
        item["structured_point_contract_signals"] = point_contract.get("signals", [])
        item["structured_point_contract_risks"] = point_contract.get("risks", [])


def structured_metric_page_features(query: str, item: Dict[str, Any], source_intent: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(source_intent.get("evidence_mode") or "")
    target = str(source_intent.get("evidence_target") or "")
    if mode not in {"numeric_fact", "date_fact", "schedule_fact"} and target not in {
        "market_price",
        "market_calendar",
        "prize_amount",
        "position_distance",
    }:
        return {"metric_table_score": 0, "metric_table_signals": [], "metric_table_risks": []}
    text = normalize_text(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')} {item.get('url', '')}")
    lower = text.lower()
    query_lower = (query or "").lower()
    source_type = str(item.get("source_type") or "unknown")
    site_domain = normalize_domain(extract_site_constraint(query))
    site_domain_mismatch = bool(site_domain and not url_matches_domain(str(item.get("url") or ""), site_domain))
    signals: List[str] = []
    risks: List[str] = []
    score = 0

    value_markers = extract_numeric_markers(lower)
    query_values = extract_numeric_markers(query_lower)
    if value_markers:
        score += 2
        signals.append("numeric_value_present")
    else:
        risks.append("missing_numeric_value")
    if query_values and any(value in value_markers for value in query_values):
        score += 2
        signals.append("claim_value_present")

    query_dates = extract_temporal_markers(query)
    evidence_dates = extract_temporal_markers(text)
    if evidence_dates:
        score += 1
        signals.append("temporal_marker_present")
    elif query_dates:
        risks.append("missing_time_scope")

    table_markers = [
        "table", "data", "quote", "rate", "price", "exchange", "forex", "historical", "archive",
        "表", "数据", "牌价", "汇率", "报价", "买入价", "卖出价", "中间价", "开盘", "收盘", "涨跌",
    ]
    table_hits = [marker for marker in table_markers if marker in lower]
    if table_hits:
        score += 2
        signals.append("table_or_quote_shape")
    else:
        risks.append("missing_table_or_quote_shape")

    value_type_markers = [
        "买入价", "卖出价", "现汇", "现钞", "中间价", "实时", "即期", "开盘", "收盘", "涨幅", "涨跌",
        "buying", "selling", "bid", "ask", "central parity", "close", "open", "change",
    ]
    if any(marker in lower for marker in value_type_markers) or any(marker in query_lower for marker in value_type_markers):
        score += 1
        signals.append("value_type_marker_present")
    elif target == "market_price":
        risks.append("missing_value_type_marker")

    unit_markers = ["元", "人民币", "美元", "cny", "usd", "%", "基点", "点", "per", "/100", "每"]
    if any(marker in lower for marker in unit_markers):
        score += 1
        signals.append("unit_marker_present")
    elif mode == "numeric_fact":
        risks.append("missing_unit_marker")

    binding_terms = source_strategy_binding_terms(source_intent, mode or "numeric_fact")
    required_binding_keys = ["subject_entity", "relation_or_metric", "time_scope"]
    if mode == "numeric_fact" or target == "market_price":
        required_binding_keys.append("unit")
    binding_hits: List[str] = []
    for key in required_binding_keys:
        value = str(binding_terms.get(key) or "")
        if not value:
            continue
        if binding_slot_present(text, key, value, source_intent, mode or "numeric_fact"):
            binding_hits.append(key)
    if binding_hits:
        score += min(4, len(binding_hits))
        signals.extend([f"binding_{key}_hit" for key in binding_hits])
    for key in required_binding_keys:
        value = str(binding_terms.get(key) or "")
        if value and key not in binding_hits:
            risks.append(f"missing_binding_{key}")

    if source_type in {"official", "news", "finance"}:
        score += 1
        signals.append("source_type_usable")
    elif source_type in {"forum", "unknown"}:
        score = max(0, score - 3)
        risks.append("weak_source_not_metric_record")
    elif source_type == "encyclopedia":
        score = max(0, score - 2)
        risks.append("reference_page_not_metric_record")
    if site_domain_mismatch:
        score = max(0, score - 4)
        risks.append("site_domain_mismatch")
    if is_search_engine_result_page(item):
        score = max(0, score - 2)
        risks.append("search_result_page_not_metric_table")

    return {
        "metric_table_score": min(10, score),
        "metric_table_signals": dedupe_keep_order(signals)[:8],
        "metric_table_risks": dedupe_keep_order(risks)[:8],
        "metric_binding_hits": dedupe_keep_order(binding_hits)[:6],
        "metric_binding_coverage": len(dedupe_keep_order(binding_hits)),
        "metric_site_domain_mismatch": site_domain_mismatch,
    }


def structured_noise_features(query: str, item: Dict[str, Any], evidence_mode: str = "") -> Dict[str, Any]:
    mode = str(evidence_mode or "")
    if mode not in {"numeric_fact", "date_fact", "schedule_fact"}:
        return {}
    text = normalize_text(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')} {item.get('url', '')}")
    lower = text.lower()
    query_lower = (query or "").lower()
    query_tokens = [token.lower() for token in query_core_tokens(query) if not re.fullmatch(r"(?:19|20)\d{2}", token)]
    entity_hits = [token for token in query_tokens if len(token) >= 3 and token in lower]
    query_numbers = extract_numeric_markers(query_lower)
    evidence_numbers = extract_numeric_markers(lower)
    query_dates = extract_temporal_markers(query)
    evidence_dates = extract_temporal_markers(text)
    noise_reasons: List[str] = []
    penalty = 0

    if len(entity_hits) == 0:
        noise_reasons.append("structured_no_entity_hit")
        penalty += 8
    elif len(entity_hits) == 1:
        noise_reasons.append("structured_single_entity_hit")
        penalty += 3

    if mode == "numeric_fact":
        if not evidence_numbers:
            noise_reasons.append("numeric_no_value_in_evidence")
            penalty += 8
        elif query_numbers and not any(number in evidence_numbers for number in query_numbers):
            if int(item.get("directness_score") or 0) < 3:
                noise_reasons.append("numeric_values_not_tied_to_claim")
                penalty += 7
        if evidence_numbers and len(entity_hits) == 0:
            noise_reasons.append("numeric_value_without_entity_context")
            penalty += 6

    if mode in {"date_fact", "schedule_fact"}:
        if query_dates and evidence_dates and not any(date.lower() in lower for date in query_dates):
            noise_reasons.append("date_window_mismatch")
            penalty += 8
        if not evidence_dates and int(item.get("directness_score") or 0) < 2:
            noise_reasons.append("date_no_temporal_marker")
            penalty += 5

    source_type = str(item.get("source_type") or "unknown")
    if source_type in {"forum", "unknown"} and penalty >= 8:
        noise_reasons.append("weak_source_structured_noise")
        penalty += 5
    if source_type == "encyclopedia" and (query_dates or query_numbers) and int(item.get("directness_score") or 0) < 3:
        noise_reasons.append("encyclopedia_structured_not_direct")
        penalty += 4

    score = (
        min(18, len(entity_hits) * 5)
        + min(10, int(item.get("directness_score") or 0) * 3)
        + min(8, int(item.get("temporal_score") or 0) + int(item.get("event_window_score") or 0) + 4)
        + {"official": 12, "news": 9, "encyclopedia": 5, "forum": 1, "unknown": 2}.get(source_type, 3)
        - penalty
    )
    return {
        "structured_noise_penalty": penalty,
        "structured_noise_reasons": dedupe_keep_order(noise_reasons),
        "structured_rerank_score": score,
        "structured_hits": {
            "entity": entity_hits[:6],
            "query_numbers": query_numbers[:6],
            "evidence_numbers": evidence_numbers[:6],
            "query_dates": query_dates[:6],
            "evidence_dates": evidence_dates[:6],
        },
    }


def structured_title_marker_hit(evidence_mode: str, item: Dict[str, Any]) -> bool:
    mode = policy_mode_label(evidence_mode)
    text = normalize_text(f"{item.get('title', '')} {item.get('snippet', '')}").lower()
    marker_patterns = {
        "numeric_fact": r"(汇率|中间价|牌价|外汇|fx|forex|rate|price|quote|usd|cny|eur|gbp|jpy)",
        "date_fact": r"(日期|公布|发布|时间|date|announce|release|notice|calendar)",
        "schedule_fact": r"(休市|交易日|开市|开盘|收盘|schedule|calendar|holiday|trading|market)",
        "event_result": r"(赛果|比分|冠军|胜|负|result|winner|beat|score|final)",
    }
    pattern = marker_patterns.get(mode)
    if not pattern:
        return False
    return bool(re.search(pattern, text, flags=re.I))


def is_recoverable_structured_penalty_item(
    query: str,
    item: Dict[str, Any],
    evidence_mode: str,
) -> bool:
    mode = policy_mode_label(evidence_mode)
    if mode not in {"numeric_fact", "date_fact", "schedule_fact", "event_result"}:
        return False
    source_type = str(item.get("source_type") or "")
    if source_type not in {"official", "news", "finance", "unknown"}:
        return False
    if str(item.get("page_utility_llm_decision") or "") == "drop":
        return False
    page_type = str(item.get("page_utility_page_type") or "")
    if page_type in {"landing_page", "search_result_page"}:
        return False
    page_retention_score = int(item.get("page_retention_score") or 0)
    page_utility_score = int(item.get("page_utility_score") or 0)
    answer_quality = int(item.get("answer_candidate_quality_score") or 0)
    metric_score = int(item.get("metric_table_score") or 0)
    directness = int(item.get("directness_score") or 0)
    relevance = int(item.get("relevance_score") or 0)
    entity_hits = int(item.get("entity_match_count") or 0)
    task_card_score = int(item.get("task_card_score") or 0)
    evidence_contract_status = normalize_text(str(item.get("evidence_contract_status") or "")).lower()
    evidence_contract_score = int(item.get("evidence_contract_score") or 0)
    structured_point_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
    structured_penalty = int(item.get("structured_noise_penalty") or 0)
    strong_page_type = page_type in STRUCTURED_REVIEW_PAGE_TYPES
    title_marker_hit = structured_title_marker_hit(mode, item)
    query_has_numeric = bool(extract_numeric_markers(query or ""))
    strong_signal = (
        answer_quality >= 8
        or metric_score >= 6
        or directness >= 2
        or (evidence_contract_status in {"partial", "satisfied"} and evidence_contract_score >= 35)
        or structured_point_status in {"partial", "satisfied"}
    )
    if not strong_signal:
        return False
    if page_retention_score < 46 and page_utility_score < 48:
        return False
    if relevance < 1 and entity_hits < 1 and task_card_score < 10:
        return False
    if not (strong_page_type or title_marker_hit or source_type in {"official", "finance"}):
        return False
    if source_type == "unknown" and not (strong_page_type and title_marker_hit and answer_quality >= 10):
        return False
    if query_has_numeric and not title_marker_hit and metric_score < 6 and answer_quality < 10:
        return False
    if structured_penalty >= 24 and source_type not in {"official", "finance"}:
        return False
    return True


def extract_temporal_markers(text: str) -> List[str]:
    markers: List[str] = []
    patterns = [
        r"\b(?:19|20)\d{2}-\d{1,2}-\d{1,2}\b",
        r"(?:19|20)\d{2}年\d{1,2}月\d{1,2}日",
        r"(?:19|20)\d{2}年\d{1,2}月",
        r"(?:19|20)\d{2}年",
        r"\d{1,2}月\d{1,2}日",
        r"\b(?:19|20)\d{2}\b",
    ]
    for pattern in patterns:
        markers.extend(normalize_text(match.group(0)) for match in re.finditer(pattern, text or ""))
    return dedupe_keep_order(markers)[:6]


def temporal_anchor_for_query(anchor: str, query: str) -> str:
    anchor = normalize_text(anchor)
    query = normalize_text(query)
    if not anchor:
        return ""
    if not is_english_query(query):
        return anchor
    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    match = re.fullmatch(r"((?:19|20)\d{2})年(\d{1,2})月(\d{1,2})日", anchor)
    if match:
        year, month, day = match.groups()
        month_num = int(month)
        if 1 <= month_num <= 12:
            return f"{month_names[month_num]} {int(day)}, {year}"
        return f"{year}-{int(month):02d}-{int(day):02d}"
    match = re.fullmatch(r"((?:19|20)\d{2})年(\d{1,2})月", anchor)
    if match:
        year, month = match.groups()
        month_num = int(month)
        if 1 <= month_num <= 12:
            return f"{month_names[month_num]} {year}"
        return f"{year}-{int(month):02d}"
    match = re.fullmatch(r"((?:19|20)\d{2})年", anchor)
    if match:
        return match.group(1)
    match = re.fullmatch(r"(\d{1,2})月(\d{1,2})日", anchor)
    if match:
        month, day = match.groups()
        month_num = int(month)
        if 1 <= month_num <= 12:
            return f"{month_names[month_num]} {int(day)}"
        return f"{int(month):02d}-{int(day):02d}"
    return anchor


def event_window_score(query: str, item: Dict[str, Any], evidence_mode: str = "") -> int:
    mode = (evidence_mode or "").lower()
    if mode not in {"date_fact", "schedule_fact", "numeric_fact", "event_result", "policy_fact"}:
        return 0
    query_markers = extract_temporal_markers(query)
    if not query_markers:
        return 0
    title = str(item.get("title") or "").lower()
    snippet = str(item.get("snippet") or "").lower()
    detail = str(item.get("detail") or "").lower()
    text = f"{title} {snippet} {detail}"
    text_markers = extract_temporal_markers(text)
    if not text_markers:
        return -1
    query_month_day = [marker for marker in query_markers if "月" in marker and "日" in marker]
    title_month_day = [marker for marker in extract_temporal_markers(title) if "月" in marker and "日" in marker]
    if query_month_day and title_month_day and not any(marker.lower() in title for marker in query_month_day):
        return -2
    if any(marker.lower() in title for marker in query_markers):
        return 3
    if any(marker.lower() in text for marker in query_markers):
        if any(token in text for token in ["window", "调整", "调价", "公告", "announce", "official", "published", "公布", "schedule", "24时"]):
            return 2
        return 1
    text_month_day = [marker for marker in text_markers if "月" in marker and "日" in marker]
    if query_month_day and text_month_day:
        return -2
    if query_month_day and any(token in text for token in ["since", "以来", "之后", "after"]):
        return -1
    return 0


def add_temporal_anchors_to_queries(
    query_plan: List[Dict[str, str]],
    answer: str,
    time_value: str,
    evidence_mode: str,
) -> List[Dict[str, str]]:
    if evidence_mode not in {"numeric_fact", "date_fact", "schedule_fact", "event_result", "policy_fact"}:
        return query_plan
    anchors = extract_temporal_markers(answer)
    if not anchors and time_value:
        anchors = extract_temporal_markers(time_value[:10])
    anchors = [anchor for anchor in anchors if anchor][:2]
    if not anchors:
        return query_plan
    anchored: List[Dict[str, str]] = []
    for item in query_plan:
        query = normalize_text(item.get("q") or "")
        if not query or extract_temporal_markers(query):
            continue
        anchor_text = temporal_anchor_for_query(anchors[0], query)
        if not anchor_text:
            continue
        anchored_item: Dict[str, Any] = {
            "q": f"{query} {anchor_text}",
            "goal": item.get("goal") or "general_verify",
            "origin": item.get("origin") or "",
        }
        source_preference = item.get("source_preference") if isinstance(item.get("source_preference"), list) else []
        if source_preference:
            anchored_item["source_preference"] = [str(value) for value in source_preference[:3]]
        anchored.append(anchored_item)
    return dedupe_query_plan_keep_order(normalize_query_items(anchored + query_plan), MAX_QUERIES_PER_CLAIM)


def evidence_temporal_score(query: str, item: Dict[str, Any]) -> int:
    markers = extract_temporal_markers(query)
    if not markers:
        return 0
    text = f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')}".lower()
    if any(marker.lower() in text for marker in markers):
        return 2
    query_month_days = [marker for marker in markers if "月" in marker and "日" in marker]
    evidence_month_days = extract_temporal_markers(text)
    evidence_month_days = [marker for marker in evidence_month_days if "月" in marker and "日" in marker]
    if query_month_days and evidence_month_days:
        return -2
    if query_month_days:
        return -1
    return 0


def extract_site_constraint(query: str) -> str:
    match = re.search(r"\bsite:([^\s]+)", query or "", flags=re.I)
    if not match:
        return ""
    domain = match.group(1).strip().lower()
    return domain.lstrip(".")


def url_matches_domain(url: str, domain: str) -> bool:
    if not domain:
        return True
    host = (urlparse(url).netloc or "").lower()
    domain = domain.lower().lstrip(".")
    return host == domain or host.endswith("." + domain)


def query_core_tokens(query: str) -> List[str]:
    cleaned = re.sub(r"\bsite:[^\s]+", " ", query or "", flags=re.I)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}|\d{4}", cleaned)
    stop = {
        "the", "and", "for", "with", "official", "announcement", "date", "when",
        "what", "who", "whose", "result", "results", "prize", "amount", "site",
        "官方", "结果", "时间", "公布", "发布", "新闻", "信息", "详情",
    } | GENERIC_QUERY_NOISE_TOKENS
    out = []
    for token in tokens:
        t = token.strip()
        if not t or t.lower() in stop:
            continue
        out.append(t)
    return dedupe_keep_order(out)[:8]


def compact_query_seed_tokens(text: str, limit: int = 6) -> List[str]:
    cleaned = re.sub(r"\bsite:[^\s]+", " ", text or "", flags=re.I)
    cleaned = re.sub(r"[\[\]()*_#`>]+", " ", cleaned)
    cleaned = re.sub(r"[，。；、,.!?！？:：/\\]+", " ", cleaned)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,4}|[A-Za-z][A-Za-z0-9_-]{2,}|\d{4}", cleaned)
    stop = {
        "the", "and", "for", "with", "official", "announcement", "date", "when",
        "what", "who", "whose", "result", "results", "prize", "amount", "site",
        "官方", "结果", "时间", "公布", "发布", "新闻", "信息", "详情",
    } | GENERIC_QUERY_NOISE_TOKENS
    out: List[str] = []
    for token in tokens:
        token = normalize_text(token)
        if not token or token.lower() in stop:
            continue
        out.append(token)
    return dedupe_keep_order(out)[: max(1, limit)]


def retrieval_query_seed_text(question: str, claim: str, existing_queries: Optional[List[Dict[str, str]]] = None, limit: int = 6) -> str:
    candidates: List[str] = []
    for item in existing_queries or []:
        if not isinstance(item, dict):
            continue
        query_text = normalize_text(str(item.get("q") or ""))
        if query_text and not extract_site_constraint(query_text):
            candidates.append(query_text)
    candidates.extend([f"{question} {claim}", claim, question])
    for text in candidates:
        tokens = compact_query_seed_tokens(text, limit)
        if len(tokens) >= min(3, limit):
            return " ".join(tokens[:limit])
    for text in candidates:
        tokens = compact_query_seed_tokens(text, limit)
        if tokens:
            return " ".join(tokens[:limit])
    return ""


def preferred_probe_seed_text(
    question: str,
    claim: str,
    source_intent: Dict[str, Any],
    existing_queries: Optional[List[Dict[str, str]]] = None,
    limit: int = 8,
) -> str:
    if not prefer_news_first_for_intent(source_intent):
        return retrieval_query_seed_text(question, claim, existing_queries, limit=min(limit, 6))
    tokens: List[str] = []
    combined = normalize_text(f"{question} {claim}")
    for marker in extract_temporal_markers(combined)[:3]:
        if marker:
            tokens.append(marker)
    for token in query_core_tokens(question)[:5]:
        if token:
            tokens.append(token)
    for token in query_core_tokens(claim)[:6]:
        if token:
            tokens.append(token)
    tokens = dedupe_keep_order(tokens)
    if len(tokens) >= 4:
        return compact_text_for_query(" ".join(tokens[:limit]), 96)
    return retrieval_query_seed_text(question, claim, existing_queries, limit=min(limit, 8))


def entity_match_count(query: str, item: Dict[str, Any]) -> int:
    text = f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')} {item.get('url', '')}".lower()
    count = 0
    for token in query_core_tokens(query):
        if token.lower() in text:
            count += 1
    return count


def route_keyword_profile(query: str, claim: str = "") -> Dict[str, Any]:
    text = normalize_text(f"{query} {claim}")
    entity_terms = [
        token
        for token in route_entity_tokens(text)
        if not re.fullmatch(r"(?:19|20)\d{2}", token)
    ][:6]
    time_terms = extract_temporal_markers(text)[:4]
    relation_terms = [
        marker
        for marker in ROUTE_RELATION_MARKERS
        if route_marker_present(text, marker)
    ][:6]
    action_terms = [
        token
        for token in query_core_tokens(text)
        if token not in entity_terms
        and token not in time_terms
        and token.lower() not in ROUTE_QUERY_STOPWORDS
        and not re.fullmatch(r"(?:19|20)\d{2}", token)
    ][:6]
    return {
        "entity_terms": entity_terms,
        "relation_terms": relation_terms,
        "action_terms": action_terms,
        "time_terms": time_terms,
    }


def route_rerank_features(query: str, item: Dict[str, Any], claim: str = "") -> Dict[str, Any]:
    profile = route_keyword_profile(query, claim)
    text = normalize_text(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')} {item.get('url', '')}")
    lower = text.lower()
    entity_hits = [term for term in profile["entity_terms"] if term.lower() in lower]
    action_hits = [term for term in profile["action_terms"] if term.lower() in lower]
    time_hits = [term for term in profile["time_terms"] if term.lower() in lower]
    relation_hits = [
        marker
        for marker in ROUTE_RELATION_MARKERS
        if route_marker_present(text, marker)
    ]
    directional_relation = route_directional_relation_present(text)
    route_sentence = item.get("route_sentence") if isinstance(item.get("route_sentence"), dict) else {}
    source_type = str(item.get("source_type") or "unknown")
    title = normalize_text(str(item.get("title") or ""))
    title_lower = title.lower()
    noise_reasons: List[str] = []
    penalty = 0
    if not relation_hits and not route_sentence.get("has_relation_marker") and not directional_relation:
        noise_reasons.append("no_route_relation_marker")
        penalty += 8
    if len(entity_hits) <= 1:
        noise_reasons.append("single_or_no_entity_hit")
        penalty += 6
    if entity_hits and all(re.fullmatch(r"(?:19|20)\d{2}", hit) for hit in entity_hits):
        noise_reasons.append("year_only_hit")
        penalty += 10
    if source_type in {"forum", "unknown"} and not route_sentence.get("direct_sentence"):
        noise_reasons.append("weak_source_without_direct_route")
        penalty += 8
    if source_type == "encyclopedia" and not route_sentence.get("direct_sentence"):
        noise_reasons.append("encyclopedia_without_direct_route")
        penalty += 5
    if re.search(r"(知乎|百度知道|topic/|question/)", title_lower + " " + str(item.get("url") or "").lower()):
        noise_reasons.append("forum_or_qa_page")
        penalty += 8
    if len(title) <= 18 and len(entity_hits) <= 1 and not relation_hits:
        noise_reasons.append("generic_entity_title")
        penalty += 5

    keyword_score = min(18, len(entity_hits) * 5 + len(action_hits) * 2 + len(time_hits) * 2)
    relation_score = 18 if route_sentence.get("direct_sentence") else (10 if relation_hits or directional_relation else 0)
    source_score = {"official": 14, "news": 12, "encyclopedia": 7, "forum": 1, "unknown": 2}.get(source_type, 3)
    direct_score = min(12, int(item.get("directness_score") or 0) * 3)
    time_score = max(-6, min(6, int(item.get("event_window_score") or 0) + int(item.get("temporal_score") or 0)))
    page_intent_score = int(item.get("page_intent_score") or 0)
    intent_score = 10 if page_intent_score >= 75 else 6 if page_intent_score >= 60 else 2 if page_intent_score >= 45 else -6
    score = keyword_score + relation_score + source_score + direct_score + time_score + intent_score - penalty
    return {
        "keyword_profile": profile,
        "keyword_hits": {
            "entity": entity_hits,
            "relation": relation_hits[:6],
            "action": action_hits,
            "time": time_hits,
        },
        "directional_relation": directional_relation,
        "noise_penalty": penalty,
        "noise_reasons": noise_reasons,
        "route_rerank_score": score,
        "route_rerank_components": {
            "keyword": keyword_score,
            "relation": relation_score,
            "source": source_score,
            "direct": direct_score,
            "time": time_score,
            "intent": intent_score,
            "penalty": penalty,
        },
    }


def route_marker_present(text: str, marker: str) -> bool:
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


def route_object_marker_present(text: str) -> bool:
    return any(route_marker_present(text, marker) for marker in ROUTE_OBJECT_MARKERS)


def route_directional_relation_present(text: str) -> bool:
    lower = text.lower()
    if any(route_marker_present(text, marker) for marker in ROUTE_DIRECTIONAL_MARKERS):
        return True
    if not route_object_marker_present(text):
        return False
    return bool(
        re.search(
            r"(?:向|朝|往|赴|前往|飞向|驶向|进入|到达|抵达|直达|运往|射向|指向)\s*[^。！？,.]{0,20}(?:[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{1,})",
            text,
        )
        or re.search(r"\b(?:toward|towards|headed to|bound for|entered|enter|reached|into)\b", lower)
    )


def route_transit_relation_present(text: str) -> bool:
    transit_markers = [
        "airspace", "route", "via", "through", "transit", "cross", "crossed", "corridor",
        "flight path", "trajectory", "overfly", "overflight", "flew over", "passed through",
        "entered", "enter", "reached", "into",
        "经过", "经由", "通过", "穿越", "飞越", "领空", "路线", "通道", "进入", "到达", "抵达",
    ]
    lower = text.lower()
    if any(route_marker_present(text, marker) for marker in transit_markers):
        return True
    return bool(
        re.search(r"\b(?:pass(?:ed)? through|flew over|overf(?:ly|light)|cross(?:ed)?|enter(?:ed)?|reach(?:ed)?|into|via|through|transit)\b", lower)
        or re.search(r"(?:经过|经由|通过|穿越|飞越|进入|到达|抵达)\s*[^。！？,.]{0,20}(?:领空|空域|地区|东部|西部|南部|北部)", text)
    )


def route_entity_tokens(query: str) -> List[str]:
    return [
        token
        for token in query_core_tokens(query)
        if len(token) >= 2
        and token.lower() not in ROUTE_QUERY_STOPWORDS
        and token.lower() not in ROUTE_ENTITY_QUERY_STOPWORDS
    ][:8]


def split_evidence_sentences(text: str) -> List[str]:
    pieces = re.split(r"(?<=[。！？.!?])\s+|[。！？!?]\s*", text or "")
    return [normalize_text(piece) for piece in pieces if normalize_text(piece)][:20]


def route_analysis_units(item: Dict[str, Any]) -> List[str]:
    units: List[str] = []
    for field in ("title", "snippet", "detail"):
        raw_text = normalize_text(str(item.get(field) or ""))
        if not raw_text:
            continue
        field_units = [raw_text] if field == "title" else split_evidence_sentences(raw_text)
        for sentence in field_units:
            if not sentence:
                continue
            clauses: List[str] = []
            if len(sentence) >= 80:
                for clause in re.split(r"[，；;:：]\s*", sentence):
                    clause = normalize_text(clause)
                    if len(clause) < 8 or clause == sentence:
                        continue
                    clauses.append(clause)
            if clauses:
                units.extend(clauses)
            else:
                units.append(sentence)
    deduped: List[str] = []
    seen = set()
    for sentence in units:
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sentence)
    return deduped[:30]


ANSWER_MARKER_GROUPS = {
    "event_result": ["won", "beat", "defeated", "lost", "retired", "withdraw", "walkover", "胜", "负", "战胜", "击败", "退赛", "弃权", "不战而胜"],
    "date_fact": ["announced", "award", "published", "confirmed", "closed", "公布", "宣布", "发布", "确认", "休市"],
    "numeric_fact": ["price", "amount", "rate", "score", "distance", "奖金", "价格", "汇率", "比分", "距离"],
    "route_fact": ["located", "distance", "route", "airspace", "via", "through", "位于", "距离", "路线", "领空", "经过"],
}


def answer_marker_candidates(query: str) -> List[str]:
    features = detect_claim_features(query, query)
    markers: List[str] = []
    if features.get("has_score"):
        markers.extend(ANSWER_MARKER_GROUPS["event_result"])
    if features.get("has_time_event") or features.get("has_date"):
        markers.extend(ANSWER_MARKER_GROUPS["date_fact"])
    if features.get("has_amount") or features.get("has_number"):
        markers.extend(ANSWER_MARKER_GROUPS["numeric_fact"])
    if features.get("has_route"):
        markers.extend(ANSWER_MARKER_GROUPS["route_fact"])
    if not markers:
        markers.extend(["announced", "confirmed", "won", "beat", "located", "公布", "确认", "获奖", "位于"])
    return dedupe_keep_order(markers)


def evidence_sentence_units(item: Dict[str, Any]) -> List[Dict[str, str]]:
    units: List[Dict[str, str]] = []
    for field in ("title", "snippet", "detail"):
        raw_text = normalize_text(str(item.get(field) or ""))
        if not raw_text:
            continue
        sentences = [raw_text] if field == "title" else split_evidence_sentences(raw_text)
        for sentence in sentences:
            units.append({"field": field, "sentence": sentence})
    return units


def query_numeric_markers(query: str) -> List[str]:
    return extract_numeric_markers(query)[:6]


def candidate_slot_match_from_scored(query: str, sentence: str, scored: Dict[str, Any], evidence_mode: str = "") -> str:
    token_hits = bool(scored.get("token_hits"))
    numeric_hits = bool(scored.get("numeric_hits"))
    time_hits = bool(scored.get("time_hits"))
    route_hits = bool(scored.get("route_hits"))
    status_hit = bool(scored.get("answer_markers")) or bool(
        re.search(
            r"(战胜|击败|获胜|赢|比分|赛果|结果|发布|公布|宣布|生效|实施|休市|开盘|won|beat|result|score|announced|released|effective|open|closed)",
            sentence,
            flags=re.I,
        )
    )
    if evidence_mode == "route_fact" or route_hits:
        return build_candidate_slot_signature(
            has_subject=token_hits,
            has_metric=route_hits,
            has_status=status_hit,
        )
    if token_hits and time_hits and (numeric_hits or status_hit):
        return build_candidate_slot_signature(
            has_subject=True,
            has_time=True,
            has_metric=numeric_hits,
            has_status=status_hit,
        )
    if token_hits and (numeric_hits or status_hit):
        return build_candidate_slot_signature(
            has_subject=True,
            has_metric=numeric_hits,
            has_status=status_hit,
        )
    if time_hits and (numeric_hits or status_hit):
        return build_candidate_slot_signature(
            has_time=True,
            has_metric=numeric_hits,
            has_status=status_hit,
        )
    if token_hits and time_hits:
        return build_candidate_slot_signature(has_subject=True, has_time=True)
    if numeric_hits or status_hit:
        return build_candidate_slot_signature(has_metric=numeric_hits, has_status=status_hit)
    if time_hits:
        return build_candidate_slot_signature(has_time=True)
    return "weak_anchor"


def build_candidate_slot_signature(
    *,
    has_subject: bool = False,
    has_time: bool = False,
    has_metric: bool = False,
    has_status: bool = False,
) -> str:
    slots: List[str] = []
    if has_subject:
        slots.append("subject")
    if has_time:
        slots.append("time_scope")
    if has_metric:
        slots.append("metric_or_relation")
    if has_status:
        slots.append("status_or_result")
    return "+".join(slots) if slots else "weak_anchor"


def candidate_slot_match_flags(slot_match: str) -> Dict[str, bool]:
    parts = {
        normalize_text(str(part or ""))
        for part in str(slot_match or "").split("+")
        if normalize_text(str(part or ""))
    }
    return {
        "subject": "subject" in parts,
        "time_scope": "time_scope" in parts,
        "metric_or_relation": "metric_or_relation" in parts,
        "status_or_result": "status_or_result" in parts,
    }


def candidate_slot_coverage_from_scored(
    query: str,
    sentence: str,
    scored: Dict[str, Any],
    slot_match: str,
    evidence_mode: str = "",
    gap_reason: str = "",
) -> Dict[str, Any]:
    flags = candidate_slot_match_flags(slot_match)
    coverage = {
        "subject": bool(flags.get("subject")),
        "time_scope": bool(flags.get("time_scope")),
        "metric_or_relation": bool(flags.get("metric_or_relation")),
        "status_or_result": bool(flags.get("status_or_result")),
        "date_role": evidence_mode in {"date_fact", "schedule_fact"} and gap_reason != "date_role_mismatch",
        "result_granularity": evidence_mode == "event_result" and gap_reason != "result_granularity_mismatch",
    }
    coverage["slot_count"] = sum(
        1 for key in ("subject", "time_scope", "metric_or_relation", "status_or_result")
        if coverage.get(key)
    )
    coverage["slot_match_signature"] = slot_match
    coverage["query_needs_open"] = bool(re.search(r"(开盘|开市|opening|opened)", query, flags=re.I))
    coverage["sentence_has_open"] = bool(re.search(r"(开盘|开市|高开|opening|opened|open price|open gain)", sentence, flags=re.I))
    coverage["sentence_has_intraday"] = bool(re.search(r"(盘中|一度|曾|瞬时|最高|新高|intraday|at one point|session high|hit as high as)", sentence, flags=re.I))
    coverage["sentence_has_close"] = bool(re.search(r"(收盘|尾盘|close|closed)", sentence, flags=re.I))
    coverage["token_hit_count"] = len(scored.get("token_hits") or []) if isinstance(scored.get("token_hits"), list) else 0
    coverage["numeric_hit_count"] = len(scored.get("numeric_hits") or []) if isinstance(scored.get("numeric_hits"), list) else 0
    coverage["time_hit_count"] = len(scored.get("time_hits") or []) if isinstance(scored.get("time_hits"), list) else 0
    return coverage


def candidate_directness_rank(
    profile: str,
    slot_match: str,
    gap_reason: str,
    coverage: Optional[Dict[str, Any]] = None,
) -> int:
    flags = candidate_slot_match_flags(slot_match)
    slot_count = int(
        (coverage or {}).get("slot_count")
        or sum(
            1
            for key in ("subject", "time_scope", "metric_or_relation", "status_or_result")
            if flags.get(key)
        )
    )
    if profile == "direct_candidate":
        if flags.get("subject") and flags.get("time_scope") and (flags.get("metric_or_relation") or flags.get("status_or_result")):
            return 5
        return 4
    if gap_reason in {"date_role_mismatch", "result_granularity_mismatch", "opening_slot_mismatch", "route_relation_indirect"}:
        return 3
    if profile == "slot_hit_but_indirect":
        return 3 if slot_count >= 2 else 2
    if profile in {"numeric_reference_only", "date_reference_only"}:
        return 2
    if profile == "background_commentary":
        return 1
    return 0


def candidate_gap_reason_from_scored(
    query: str,
    sentence: str,
    scored: Dict[str, Any],
    slot_match: str,
    evidence_mode: str = "",
) -> str:
    slot_flags = candidate_slot_match_flags(slot_match)
    slot_count = sum(1 for key in ("subject", "time_scope", "metric_or_relation", "status_or_result") if slot_flags.get(key))
    query_needs_open = bool(re.search(r"(开盘|开市|opening|opened)", query, flags=re.I))
    sentence_has_open = bool(re.search(r"(开盘|开市|高开|opening|opened|open price|open gain)", sentence, flags=re.I))
    sentence_has_intraday = bool(re.search(r"(盘中|一度|曾|瞬时|最高|新高|intraday|at one point|session high|hit as high as)", sentence, flags=re.I))
    sentence_has_close = bool(re.search(r"(收盘|尾盘|close|closed)", sentence, flags=re.I))
    sentence_has_commentary = bool(re.search(r"(代表|意味着|反映|说明|主要因为|reflects|means|suggests|because)", sentence, flags=re.I))
    if query_needs_open and (sentence_has_intraday or sentence_has_close) and not sentence_has_open:
        return "opening_slot_mismatch"
    if evidence_mode in {"date_fact", "schedule_fact"}:
        query_publish = bool(re.search(r"(发布|公布|宣布|announced|released)", query, flags=re.I))
        query_effective = bool(re.search(r"(生效|实施|effective|in force)", query, flags=re.I))
        sentence_publish = bool(re.search(r"(发布|公布|宣布|announced|released)", sentence, flags=re.I))
        sentence_effective = bool(re.search(r"(生效|实施|effective|in force)", sentence, flags=re.I))
        if (query_publish and sentence_effective and not sentence_publish) or (query_effective and sentence_publish and not sentence_effective):
            return "date_role_mismatch"
    if evidence_mode == "event_result":
        query_needs_final = bool(re.search(r"(比分|赛果|结果|获胜|winner|won|beat|result|score)", query, flags=re.I))
        sentence_partial = bool(re.search(r"(首节|次节|半场|加时|单盘|盘点|quarter|period|half|set|inning)", sentence, flags=re.I))
        if query_needs_final and sentence_partial:
            return "result_granularity_mismatch"
    if sentence_has_commentary and slot_count <= 1:
        return "commentary_only"
    if evidence_mode == "numeric_fact" and slot_count <= 1 and scored.get("numeric_hits"):
        return "numeric_reference_only"
    if evidence_mode in {"date_fact", "schedule_fact"} and slot_flags.get("time_scope") and slot_count == 1 and scored.get("time_hits"):
        return "date_reference_only"
    if sentence_has_commentary:
        return "commentary_only"
    return ""


def candidate_profile_from_scored(
    query: str,
    sentence: str,
    scored: Dict[str, Any],
    slot_match: str,
    gap_reason: str,
    evidence_mode: str = "",
) -> str:
    score = int(scored.get("score") or 0)
    token_hits = bool(scored.get("token_hits"))
    numeric_hits = bool(scored.get("numeric_hits"))
    time_hits = bool(scored.get("time_hits"))
    route_hits = bool(scored.get("route_hits"))
    answer_hits = bool(scored.get("answer_markers"))
    slot_flags = candidate_slot_match_flags(slot_match)
    strong_fact_slots = slot_flags.get("subject") and slot_flags.get("time_scope") and (slot_flags.get("metric_or_relation") or slot_flags.get("status_or_result"))
    medium_fact_slots = (
        (slot_flags.get("subject") and (slot_flags.get("metric_or_relation") or slot_flags.get("status_or_result")))
        or (slot_flags.get("time_scope") and (slot_flags.get("metric_or_relation") or slot_flags.get("status_or_result")))
    )
    if gap_reason == "commentary_only":
        return "background_commentary"
    if evidence_mode == "numeric_fact" and gap_reason == "numeric_reference_only":
        return "numeric_reference_only"
    if evidence_mode in {"date_fact", "schedule_fact"} and gap_reason == "date_reference_only":
        return "date_reference_only"
    if strong_fact_slots and score >= 12 and (numeric_hits or answer_hits or route_hits):
        return "direct_candidate"
    if (
        evidence_mode in {"numeric_fact", "date_fact", "schedule_fact", "event_result"}
        and not gap_reason
        and medium_fact_slots
        and score >= 14
        and (answer_hits or numeric_hits or route_hits or token_hits)
    ):
        return "direct_candidate"
    if slot_flags.get("subject") or slot_flags.get("time_scope") or slot_flags.get("metric_or_relation") or slot_flags.get("status_or_result"):
        return "slot_hit_but_indirect"
    if evidence_mode == "numeric_fact" and numeric_hits:
        return "numeric_reference_only"
    if evidence_mode in {"date_fact", "schedule_fact"} and time_hits:
        return "date_reference_only"
    if token_hits or answer_hits or route_hits:
        return "slot_hit_but_indirect"
    return "background_commentary"


def answer_candidate_sentence_score(query: str, sentence: str, field: str) -> Dict[str, Any]:
    generic = {
        "赛果", "比分", "结果", "比赛", "今日", "今天", "小组赛", "实际", "最终",
        "result", "results", "score", "match", "game", "official", "news",
    }
    lower = sentence.lower()
    tokens = [token.lower() for token in query_core_tokens(query) if token.lower() not in generic]
    token_hits = [token for token in tokens if token and token in lower]
    numeric_hits = [marker for marker in query_numeric_markers(query) if marker and marker in lower]
    time_hits = [marker for marker in extract_temporal_markers(query) if marker and marker in lower]
    answer_markers = [marker for marker in answer_marker_candidates(query) if marker in lower or marker in sentence]
    route_hits = []
    if any(route_marker_present(query, marker) for marker in ROUTE_RELATION_MARKERS):
        route_hits = [marker for marker in ROUTE_RELATION_MARKERS if route_marker_present(sentence, marker)]

    score = 0
    reasons: List[str] = []
    if token_hits:
        score += min(12, len(token_hits) * 3)
        reasons.append("token_hits")
    if numeric_hits:
        score += min(6, len(numeric_hits) * 2)
        reasons.append("numeric_match")
    if time_hits:
        score += min(4, len(time_hits) * 2)
        reasons.append("time_match")
    if route_hits:
        score += min(6, len(route_hits) * 2)
        reasons.append("route_relation")
    if re.search(r"\d+\s*[-:：比]\s*\d+|\b\d+-\d+\b", sentence):
        score += 4
        reasons.append("score_pattern")
    if answer_markers:
        score += min(6, len(answer_markers))
        reasons.append("answer_marker")

    query_needs_open = bool(re.search(r"(开盘|开市|opening|opened)", query, flags=re.I))
    sentence_has_open = bool(re.search(r"(开盘|开市|高开|opening|opened|open price|open gain)", sentence, flags=re.I))
    sentence_has_intraday = bool(re.search(r"(盘中|一度|曾|瞬时|最高|新高|intraday|at one point|session high|hit as high as)", sentence, flags=re.I))
    sentence_has_close = bool(re.search(r"(收盘|尾盘|close|closed)", sentence, flags=re.I))
    sentence_has_commentary = bool(re.search(r"(代表|意味着|反映|说明|主要因为|reflects|means|suggests|because)", sentence, flags=re.I))
    if query_needs_open and sentence_has_open:
        score += 7
        reasons.append("opening_fact_slot_hit")
    if query_needs_open and sentence_has_intraday and not sentence_has_open:
        score -= 7
        reasons.append("intraday_not_opening_slot")
    if query_needs_open and sentence_has_close and not sentence_has_open:
        score -= 6
        reasons.append("closing_not_opening_slot")
    if query_needs_open and sentence_has_commentary:
        score -= 4
        reasons.append("commentary_not_opening_quote")

    if field == "title":
        score += 3
        reasons.append("title_bonus")
    elif field == "detail":
        score += 2
        reasons.append("detail_bonus")

    if len(sentence) < 12:
        score -= 2
        reasons.append("too_short")
    elif len(sentence) > 220:
        score -= 1
        reasons.append("too_long")

    return {
        "score": score,
        "token_hits": token_hits[:6],
        "numeric_hits": numeric_hits[:4],
        "time_hits": time_hits[:4],
        "route_hits": route_hits[:4],
        "answer_markers": answer_markers[:4],
        "reasons": reasons,
    }


def answer_candidate_sentences(query: str, item: Dict[str, Any], max_items: int = 3, evidence_mode: str = "") -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    seen = set()
    for unit in evidence_sentence_units(item):
        sentence = unit["sentence"]
        field = unit["field"]
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        scored = answer_candidate_sentence_score(query, sentence, field)
        if int(scored.get("score") or 0) <= 0:
            continue
        if not scored.get("token_hits") and not scored.get("numeric_hits") and not scored.get("route_hits"):
            continue
        slot_match = candidate_slot_match_from_scored(query, sentence, scored, evidence_mode)
        gap_reason = candidate_gap_reason_from_scored(query, sentence, scored, slot_match, evidence_mode)
        profile = candidate_profile_from_scored(query, sentence, scored, slot_match, gap_reason, evidence_mode)
        coverage = candidate_slot_coverage_from_scored(query, sentence, scored, slot_match, evidence_mode, gap_reason)
        directness_rank = candidate_directness_rank(profile, slot_match, gap_reason, coverage)
        direct_candidate_promotion_used = profile == "direct_candidate" and not (
            coverage.get("subject") and coverage.get("time_scope") and (coverage.get("metric_or_relation") or coverage.get("status_or_result"))
        )
        candidates.append(
            {
                "sentence": sentence[:260],
                "score": int(scored.get("score") or 0),
                "hits": list(scored.get("token_hits") or [])[:6],
                "field": field,
                "numeric_hits": list(scored.get("numeric_hits") or [])[:4],
                "time_hits": list(scored.get("time_hits") or [])[:4],
                "route_hits": list(scored.get("route_hits") or [])[:4],
                "reasons": list(scored.get("reasons") or [])[:6],
                "sentence_candidate_profile": profile,
                "candidate_slot_match": slot_match,
                "candidate_slot_coverage": coverage,
                "direct_candidate_gap_reason": gap_reason,
                "candidate_directness_rank": directness_rank,
                "direct_candidate_promotion_used": direct_candidate_promotion_used,
            }
        )
    route_directed = query_looks_route_directed(query)
    profile_rank = {
        "direct_candidate": 4,
        "slot_hit_but_indirect": 3,
        "numeric_reference_only": 2,
        "date_reference_only": 2,
        "background_commentary": 1,
    }
    candidates.sort(
        key=lambda row: (
            int(row.get("candidate_directness_rank") or 0),
            profile_rank.get(str(row.get("sentence_candidate_profile") or ""), 0),
            int((row.get("candidate_slot_coverage") or {}).get("slot_count") or 0),
            bool(row.get("direct_candidate_promotion_used")),
            route_directed and bool(row.get("route_hits")),
            route_directed and row.get("field") == "detail",
            route_directed and row.get("field") == "snippet",
            int(row.get("score") or 0),
            (not route_directed) and row.get("field") == "title",
            row.get("field") == "detail",
            len(str(row.get("hits") or [])),
        ),
        reverse=True,
    )
    return candidates[:max_items]


def claim_program_query(claim_item: Optional[Dict[str, Any]], fallback_query: str = "") -> str:
    if not isinstance(claim_item, dict):
        return fallback_query
    program = claim_program_from_claim_item(claim_item)
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    parts = [
        str(program.get("normalized_assertion") or ""),
        str(direct_need.get("must_answer") or ""),
        str(claim_item.get("claim") or ""),
        str(decision_slots.get("subject") or ""),
        str(decision_slots.get("object") or ""),
        str(decision_slots.get("time_scope") or ""),
        str(decision_slots.get("metric_or_relation") or ""),
        str(decision_slots.get("status_or_result") or ""),
    ]
    compact = normalize_text(" ".join(part for part in parts if normalize_text(part)))
    return compact or fallback_query


def direct_result_markers() -> List[str]:
    return [
        "战胜", "击败", "赢", "获胜", "比分", "赛果", "结果",
        "won", "beat", "defeated", "result", "score", "winner",
        "休市", "开盘", "生效", "发布", "公布", "取消",
        "open", "closed", "effective", "announced", "released",
    ]


def deterministic_candidate_rescue(
    claim_item: Dict[str, Any],
    item: Dict[str, Any],
    evidence_mode: str,
    fallback_query: str,
) -> Dict[str, Any]:
    if str(evidence_mode or "") not in {"numeric_fact", "date_fact", "schedule_fact", "event_result"}:
        return {}
    program_query = claim_program_query(claim_item, fallback_query)
    if not program_query:
        return {}
    best: Dict[str, Any] = {}
    markers = direct_result_markers()
    claim_needs_open = bool(re.search(r"(开盘|开市|opening|opened)", program_query, flags=re.I))
    for unit in evidence_sentence_units(item):
        sentence = str(unit.get("sentence") or "")
        field = str(unit.get("field") or "")
        if not sentence:
            continue
        scored = answer_candidate_sentence_score(program_query, sentence, field)
        lower = sentence.lower()
        has_number = bool(re.search(r"\d", sentence))
        has_time = bool(scored.get("time_hits"))
        has_numeric = bool(scored.get("numeric_hits"))
        has_result_marker = any(marker in sentence or marker in lower for marker in markers)
        sentence_has_open = bool(re.search(r"(开盘|开市|高开|opening|opened|open price|open gain)", sentence, flags=re.I))
        sentence_has_intraday = bool(re.search(r"(盘中|一度|曾|瞬时|最高|新高|intraday|at one point|session high|hit as high as)", sentence, flags=re.I))
        sentence_has_close = bool(re.search(r"(收盘|尾盘|close|closed)", sentence, flags=re.I))
        rescue_ok = False
        if evidence_mode == "numeric_fact":
            rescue_ok = (has_numeric and (has_time or has_number)) or (has_number and int(scored.get("score") or 0) >= 6)
        elif evidence_mode in {"date_fact", "schedule_fact"}:
            rescue_ok = has_time and (has_result_marker or int(scored.get("score") or 0) >= 6)
        elif evidence_mode == "event_result":
            rescue_ok = has_result_marker and (bool(scored.get("token_hits")) or re.search(r"\d+\s*[-:：比]\s*\d+|\b\d+-\d+\b", sentence))
        if claim_needs_open and (sentence_has_intraday or sentence_has_close) and not sentence_has_open:
            rescue_ok = False
        if not rescue_ok:
            continue
        slot_match = candidate_slot_match_from_scored(program_query, sentence, scored, evidence_mode)
        gap_reason = candidate_gap_reason_from_scored(program_query, sentence, scored, slot_match, evidence_mode)
        profile = candidate_profile_from_scored(program_query, sentence, scored, slot_match, gap_reason, evidence_mode)
        coverage = candidate_slot_coverage_from_scored(program_query, sentence, scored, slot_match, evidence_mode, gap_reason)
        directness_rank = candidate_directness_rank(profile, slot_match, gap_reason, coverage)
        candidate = {
            "sentence": sentence[:260],
            "score": max(6, int(scored.get("score") or 0) + 2),
            "hits": list(scored.get("token_hits") or [])[:6],
            "field": field,
            "numeric_hits": list(scored.get("numeric_hits") or [])[:4],
            "time_hits": list(scored.get("time_hits") or [])[:4],
            "route_hits": list(scored.get("route_hits") or [])[:4],
            "reasons": dedupe_keep_order(list(scored.get("reasons") or []) + ["deterministic_candidate_rescue"])[:6],
            "sentence_candidate_profile": profile,
            "candidate_slot_match": slot_match,
            "candidate_slot_coverage": coverage,
            "direct_candidate_gap_reason": gap_reason,
            "candidate_directness_rank": directness_rank,
            "direct_candidate_promotion_used": profile == "direct_candidate" and not (
                coverage.get("subject") and coverage.get("time_scope") and (coverage.get("metric_or_relation") or coverage.get("status_or_result"))
            ),
        }
        if not best or (
            int(candidate.get("candidate_directness_rank") or 0),
            int((candidate.get("candidate_slot_coverage") or {}).get("slot_count") or 0),
            int(candidate.get("score") or 0),
            field == "detail",
            field == "snippet",
        ) > (
            int(best.get("candidate_directness_rank") or 0),
            int((best.get("candidate_slot_coverage") or {}).get("slot_count") or 0),
            int(best.get("score") or 0),
            str(best.get("field") or "") == "detail",
            str(best.get("field") or "") == "snippet",
        ):
            best = candidate
    return best


def maybe_apply_deterministic_candidate_rescue(
    claim_item: Dict[str, Any],
    item: Dict[str, Any],
    evidence_mode: str,
    source_query: str,
) -> None:
    existing = item.get("answer_candidates") if isinstance(item.get("answer_candidates"), list) else []
    if existing and answer_candidate_quality_score(item) >= 7:
        return
    rescue_candidate = deterministic_candidate_rescue(claim_item, item, evidence_mode, source_query)
    if not rescue_candidate:
        return
    merged: List[Dict[str, Any]] = []
    seen = set()
    for candidate in [rescue_candidate] + list(existing):
        if not isinstance(candidate, dict):
            continue
        sentence_key = normalize_text(str(candidate.get("sentence") or "")).lower()
        if not sentence_key or sentence_key in seen:
            continue
        seen.add(sentence_key)
        merged.append(candidate)
    item["answer_candidates"] = merged[:3]
    item["direct_candidate_rescue_used"] = True
    item["direct_candidate_rescue_source"] = str(rescue_candidate.get("field") or "")


def finalize_direct_candidate_rescue_progress(item: Dict[str, Any], default_stage: str = "post_keep") -> None:
    if not item.get("direct_candidate_rescue_used"):
        return
    stage = normalize_text(str(item.get("direct_candidate_rescue_stage") or default_stage)) or default_stage
    item["direct_candidate_rescue_stage"] = stage
    if item.get("rescue_promoted_from_filter"):
        item["program_used_for_retention"] = True


def answer_candidate_quality_score(item: Dict[str, Any]) -> int:
    candidates = item.get("answer_candidates") if isinstance(item.get("answer_candidates"), list) else []
    if not candidates:
        return 0
    best = candidates[0] if isinstance(candidates[0], dict) else {}
    best_score = int(best.get("score") or 0)
    best_field = str(best.get("field") or "")
    route_hits = len(best.get("route_hits") or []) if isinstance(best.get("route_hits"), list) else 0
    numeric_hits = len(best.get("numeric_hits") or []) if isinstance(best.get("numeric_hits"), list) else 0
    time_hits = len(best.get("time_hits") or []) if isinstance(best.get("time_hits"), list) else 0
    hit_count = len(best.get("hits") or []) if isinstance(best.get("hits"), list) else 0
    field_bonus = 3 if best_field == "title" else (2 if best_field == "detail" else 1 if best_field == "snippet" else 0)
    signal_bonus = min(4, route_hits + numeric_hits + time_hits + hit_count // 2)
    profile = str(best.get("sentence_candidate_profile") or "")
    directness_rank = int(best.get("candidate_directness_rank") or 0)
    slot_coverage = best.get("candidate_slot_coverage") if isinstance(best.get("candidate_slot_coverage"), dict) else {}
    slot_count_bonus = min(4, int(slot_coverage.get("slot_count") or 0))
    profile_bonus = {
        "direct_candidate": 4,
        "slot_hit_but_indirect": 2,
        "numeric_reference_only": 0,
        "date_reference_only": 0,
        "background_commentary": -3,
    }.get(profile, 0)
    promotion_bonus = 1 if best.get("direct_candidate_promotion_used") else 0
    return min(20, max(0, best_score + field_bonus + signal_bonus + profile_bonus + directness_rank + slot_count_bonus + promotion_bonus))


def task_card_match_features(item: Dict[str, Any], task_card: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(task_card, dict):
        return {
            "task_card_score": 0,
            "task_card_reasons": [],
            "task_card_must_match_hits": [],
            "task_card_direct_need_hit": False,
        }
    text = normalize_text(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')}")
    must_match = [normalize_text(str(term or "")) for term in task_card.get("must_match", []) if normalize_text(str(term or ""))]
    direct_need = normalize_text(str(task_card.get("direct_answer_need") or ""))
    score = 0
    reasons: List[str] = []
    must_hits: List[str] = []
    for term in must_match:
        if term and term in text:
            must_hits.append(term)
    if must_hits:
        score += min(24, 8 * len(must_hits))
        reasons.append("must_match_hit")
    candidates = item.get("answer_candidates") if isinstance(item.get("answer_candidates"), list) else []
    candidate_text = normalize_text(" ".join(str(candidate.get("sentence") or "") for candidate in candidates[:3] if isinstance(candidate, dict)))
    numeric_direct_markers = [
        "汇率", "中间价", "牌价", "报价", "买入价", "卖出价", "price", "rate", "amount", "score",
        "基点", "点", "美元", "人民币", "奖金", "货币", "currency",
    ]
    date_direct_markers = ["发布", "公布", "日期", "时间", "window", "announced", "date", "time"]
    result_direct_markers = ["比分", "战胜", "获奖", "retired", "withdraw", "won", "beat", "winner", "laureate"]
    direct_need_hit = False
    if direct_need:
        if any(term in direct_need for term in ["经过", "路线", "领空", "区域"]) and any(term in candidate_text for term in ["经过", "飞越", "领空", "route", "airspace", "via", "through"]):
            direct_need_hit = True
        elif (
            any(term in direct_need for term in ["数值", "金额", "指标"])
            and re.search(r"\d", candidate_text)
            and (
                any(term in candidate_text for term in numeric_direct_markers)
                or any(term in candidate_text for term in must_match[:2])
            )
        ):
            direct_need_hit = True
        elif (
            any(term in direct_need for term in ["日期", "窗口期", "发布"])
            and any(term in candidate_text for term in ["202", "月", "日", "window", "announced"])
            and (
                any(term in candidate_text for term in date_direct_markers)
                or any(term in candidate_text for term in must_match[:2])
            )
        ):
            direct_need_hit = True
        elif (
            any(term in direct_need for term in ["结果", "比分", "退赛", "获奖"])
            and any(term in candidate_text for term in result_direct_markers)
        ):
            direct_need_hit = True
        elif candidate_text:
            direct_need_hit = True
    if direct_need_hit:
        score += 12
        reasons.append("direct_answer_need_hit")
    priority_label = str(task_card.get("priority_label") or "")
    if priority_label in {"critical", "high"}:
        score += 6
        reasons.append(f"priority_{priority_label}")
    return {
        "task_card_score": min(50, max(0, score)),
        "task_card_reasons": reasons[:6],
        "task_card_must_match_hits": must_hits[:4],
        "task_card_direct_need_hit": direct_need_hit,
    }


def is_search_engine_result_page(item: Dict[str, Any]) -> bool:
    url = str(item.get("url") or "")
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    source = str(item.get("source") or "").lower()
    if "sogou.com" in host and (path.startswith("/web") or path.startswith("/sogou")):
        return True
    if host.endswith("bing.com") and (path.startswith("/search") or path.startswith("/news/search")):
        return True
    if "duckduckgo.com" in host and path in {"", "/"} and "q=" in query:
        return True
    if "google." in host and path.startswith("/search"):
        return True
    if source in {"sogou_html", "bing_html", "duckduckgo_html"} and any(
        engine in host for engine in ["sogou.com", "bing.com", "duckduckgo.com", "google."]
    ):
        return True
    return False


def source_quality_features(
    query: str,
    item: Dict[str, Any],
    evidence_mode: str = "",
    preferred_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    evidence_mode = policy_mode_label(evidence_mode)
    title = normalize_text(str(item.get("title") or ""))
    snippet = normalize_text(str(item.get("snippet") or ""))
    detail = normalize_text(str(item.get("detail") or ""))
    text = normalize_text(f"{title} {snippet} {detail}")
    lower = text.lower()
    surface_text = normalize_text(f"{title} {snippet}")
    surface_lower = surface_text.lower()
    url = str(item.get("url") or "")
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    source_type = str(item.get("source_type") or "unknown")
    site_constraint = normalize_domain(extract_site_constraint(query))
    relevance = int(item.get("relevance_score") or evidence_relevance_score(query, item) or 0)
    matches = int(item.get("entity_match_count") or entity_match_count(query, item) or 0)
    directness = int(item.get("directness_score") or 0)
    temporal = int(item.get("temporal_score") or 0)
    event_window = int(item.get("event_window_score") or 0)
    answer_candidates = item.get("answer_candidates") if isinstance(item.get("answer_candidates"), list) else []
    reasons: List[str] = []
    penalty = 0
    score = {
        "official": 42,
        "news": 34,
        "encyclopedia": 28,
        "unknown": 18,
        "forum": 10,
        "input_context": 70,
        "computed": 65,
    }.get(source_type, 18)

    if preferred_domains and any(url_matches_domain(url, domain) for domain in preferred_domains):
        score += 18
        reasons.append("preferred_domain_match")
    if site_constraint and not url_matches_domain(url, site_constraint):
        penalty += 28
        reasons.append("site_constraint_mismatch")
    score += min(24, relevance * 3)
    score += min(18, matches * 6)
    score += min(12, directness * 3)
    if temporal > 0:
        score += min(8, temporal * 2)
    if event_window > 0:
        score += min(8, event_window * 2)
    if answer_candidates:
        score += min(10, max(int(candidate.get("score") or 0) for candidate in answer_candidates))
        reasons.append("has_answer_candidate")

    if not host:
        penalty += 12
        reasons.append("missing_host")
    if not normalize_text(str(item.get("title") or "")):
        penalty += 8
        reasons.append("missing_title")
    if not normalize_text(str(item.get("snippet") or "")) and not normalize_text(str(item.get("detail") or "")):
        penalty += 10
        reasons.append("missing_snippet_and_detail")

    hard_noise_terms = [
        "porn", "xxx", "adult", "casino", "betting", "gambling",
        "movie", "movies", "streaming", "torrent", "download", "apk",
        "app store", "play.google", "login", "sign in",
        "成人视频", "博彩", "赌场", "电影", "电视剧", "下载", "安装包", "破解版", "网盘",
    ]
    hard_noise_host_hit = any(term in host or term in path for term in hard_noise_terms)
    hard_noise_surface_hit = any(term in surface_lower for term in hard_noise_terms)
    if hard_noise_host_hit or (
        hard_noise_surface_hit
        and source_type in {"unknown", "forum"}
        and matches <= 1
        and directness < 2
    ):
        penalty += 35
        reasons.append("hard_noise_page")

    if source_type in {"unknown", "forum"} and matches == 0:
        penalty += 18
        reasons.append("weak_source_no_entity_match")
    if source_type == "forum" and directness < 3:
        penalty += 12
        reasons.append("forum_without_direct_answer")
    generic_utility_patterns = [
        r"(?:^|[\s\-_/])(contact\s*us|all\s*products|help\s*center|customer\s*service|support)(?:$|[\s\-_/])",
        r"(联系(?:我们)?|帮助中心|客服中心|产品大全|全部产品)",
    ]
    if (
        any(re.search(pattern, surface_lower, flags=re.I) for pattern in generic_utility_patterns)
        or re.search(r"/(?:contact(?:us)?|support|help|all-products|products|category|categories|tag|tags)(?:/|$)", path)
    ):
        penalty += 20
        reasons.append("generic_site_utility_page")
    if is_search_engine_result_page(item):
        penalty += 45
        reasons.append("search_engine_result_page")
    if path in {"", "/"} and matches == 0 and directness < 2:
        penalty += 16
        reasons.append("generic_site_homepage")
    if temporal <= -2:
        penalty += 18
        reasons.append("temporal_mismatch")
    if event_window <= -2:
        penalty += 18
        reasons.append("event_window_mismatch")
    if evidence_mode in {"event_result", "schedule_fact", "numeric_fact", "date_fact"} and source_type == "unknown" and relevance < 3:
        penalty += 12
        reasons.append("structured_event_unknown_low_relevance")
    if evidence_mode in {"event_result", "schedule_fact"} and re.search(r"/(?:help|support|tag|category|search|login|account)(?:/|$)", path):
        penalty += 12
        reasons.append("generic_site_utility_page")

    final_score = max(0, min(100, score - penalty))
    if final_score >= 70:
        label = "good"
    elif final_score >= 50:
        label = "usable"
    elif final_score >= 35:
        label = "weak"
    else:
        label = "bad"
    return {
        "source_quality_score": final_score,
        "source_quality_label": label,
        "source_quality_reasons": dedupe_keep_order(reasons)[:8],
        "source_quality_penalty": penalty,
    }


PAGE_INTENT_TYPES = {
    "official_notice",
    "historical_table",
    "event_detail",
    "route_analysis_page",
    "result_page",
    "calendar_page",
    "award_detail",
    "quote_page",
    "current_status_page",
    "general_page",
}


def normalize_page_intent(source_intent: Dict[str, Any]) -> Dict[str, Any]:
    page_intent = source_intent.get("page_intent") if isinstance(source_intent.get("page_intent"), dict) else {}
    needed = str(page_intent.get("needed_page_type") or "").strip()
    effective_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    if needed not in PAGE_INTENT_TYPES:
        shape = normalize_evidence_shape(source_intent)
        shape_page = {
            "authoritative_notice": "official_notice",
            "structured_historical_data": "historical_table",
            "event_detail_page": "event_detail",
            "current_status_update": "current_status_page",
            "open_news_analysis": "route_analysis_page" if effective_mode == "route_fact" else "event_detail",
            "general_evidence_page": "general_page",
        }.get(shape, "")
        if shape_page in PAGE_INTENT_TYPES:
            needed = shape_page
    if needed not in PAGE_INTENT_TYPES:
        target = str(source_intent.get("evidence_target") or "")
        needed = {
            "market_price": "quote_page",
            "match_result": "event_detail",
            "withdrawal_status": "event_detail",
            "market_calendar": "calendar_page",
            "census_phase": "official_notice",
            "position_distance": "current_status_page",
            "current_status": "current_status_page",
            "prize_amount": "award_detail",
            "route_relation": "route_analysis_page",
        }.get(target, "historical_table" if effective_mode in {"numeric_fact", "date_fact", "schedule_fact"} else "general_page")
    must_contain = page_intent.get("must_contain") if isinstance(page_intent.get("must_contain"), list) else []
    avoid_page_type = page_intent.get("avoid_page_type") if isinstance(page_intent.get("avoid_page_type"), list) else []
    return {
        "needed_page_type": needed,
        "evidence_shape": normalize_evidence_shape(source_intent),
        "must_contain": [str(item) for item in must_contain[:6]],
        "avoid_page_type": [str(item) for item in avoid_page_type[:6]],
        "why": str(page_intent.get("why") or "")[:180],
    }


def page_intent_markers(needed_page_type: str) -> List[str]:
    return {
        "official_notice": ["notice", "announcement", "press", "release", "公告", "通知", "声明", "发布"],
        "historical_table": ["history", "historical", "archive", "table", "data", "历史", "查询", "数据", "表"],
        "event_detail": ["game", "match", "boxscore", "recap", "result", "fixture", "赛果", "比分", "战报", "详情"],
        "route_analysis_page": [
            "route", "routing", "trajectory", "track", "path", "airspace", "overflight", "flight path", "corridor", "map",
            "路线", "航线", "轨迹", "航迹", "路径", "领空", "过境", "经由", "飞越", "示意图", "地图",
        ],
        "result_page": ["result", "results", "score", "winner", "赛果", "结果", "比分", "获胜"],
        "calendar_page": ["calendar", "schedule", "holiday", "trading", "日历", "安排", "休市", "交易日"],
        "award_detail": ["award", "prize", "laureate", "press-release", "summary", "获奖", "奖金", "奖项"],
        "quote_page": ["quote", "price", "rate", "exchange", "forex", "牌价", "汇率", "报价", "买入价", "卖出价"],
        "current_status_page": ["status", "live", "tracking", "position", "location", "current", "状态", "位置", "距离", "实时"],
        "general_page": [],
    }.get(needed_page_type, [])


def page_intent_query_phrases(needed_page_type: str, language: str) -> List[str]:
    language = normalize_text(language).lower()
    if needed_page_type == "route_analysis_page":
        return {
            "en": ["flight path analysis", "route map"],
            "zh": ["飞行路线分析", "路线示意图"],
        }.get(language, ["flight path analysis", "route map"])
    if needed_page_type == "route_passage_page":
        return {
            "en": ["route passage", "airspace passage"],
            "zh": ["过境路线", "通行路径"],
        }.get(language, ["route passage", "airspace passage"])
    if needed_page_type == "current_status_page":
        return {
            "en": ["current status", "live tracking"],
            "zh": ["当前状态", "实时追踪"],
        }.get(language, ["current status", "live tracking"])
    return []


# These are generic page-shape signals, not route-only vocabulary.
PAGE_BACKGROUND_MARKERS = [
    "strike", "strikes", "attack", "attacks", "ceasefire", "retaliation", "retaliatory",
    "killed", "injured", "war", "conflict", "deal", "truce",
    "袭击", "打击", "停火", "报复", "战争", "冲突", "伤亡", "局势", "战况",
]

PAGE_SUMMARY_MARKERS = [
    "live updates", "live blog", "timeline", "roundup", "summary", "what we know", "latest",
    "更新", "汇总", "盘点", "时间线", "最新", "局势速览",
]

PAGE_LANDING_MARKERS = [
    "home", "homepage", "index", "section", "channel", "category",
    "首页", "频道", "栏目", "专题",
]


def count_text_markers(text: str, markers: List[str]) -> int:
    if not text:
        return 0
    lower = text.lower()
    count = 0
    for marker in markers:
        marker_text = str(marker).strip()
        if not marker_text:
            continue
        if re.search(r"[A-Za-z]", marker_text):
            if marker_text.lower() in lower:
                count += 1
        elif marker_text in text:
            count += 1
    return count


def route_page_profile(
    query: str,
    item: Dict[str, Any],
    title: str,
    snippet: str,
    detail: str,
    entity_grounding: int,
    path: str,
) -> Dict[str, Any]:
    route_sentence = item.get("route_sentence") if isinstance(item.get("route_sentence"), dict) else {}
    if not route_sentence and query:
        route_sentence = route_sentence_analysis(query, item)
    route_candidates = route_sentence.get("candidates") if isinstance(route_sentence.get("candidates"), list) else []
    relation_sentence_count = 0
    directional_sentence_count = 0
    strong_relation_sentence_count = 0
    direct_relation_sentence_count = 0
    object_relation_sentence_count = 0
    for candidate in route_candidates:
        if not isinstance(candidate, dict):
            continue
        has_relation = bool(candidate.get("has_relation_marker"))
        has_directional = bool(candidate.get("has_directional_relation"))
        entity_hits = int(candidate.get("entity_hit_count") or 0)
        has_object = bool(candidate.get("has_route_object_marker"))
        has_extra_anchor = bool(candidate.get("has_extra_route_anchor"))
        is_direct = bool(candidate.get("direct_sentence"))
        if has_relation:
            relation_sentence_count += 1
        if has_directional:
            directional_sentence_count += 1
        if has_relation and has_object:
            object_relation_sentence_count += 1
        if has_relation and entity_hits >= 2 and (has_extra_anchor or has_directional or is_direct):
            strong_relation_sentence_count += 1
        if is_direct:
            direct_relation_sentence_count += 1
    text_fields = {"title": title, "snippet": snippet, "detail": detail}
    route_signal_fields = [
        field_name
        for field_name, value in text_fields.items()
        if value and (
            any(route_marker_present(value, marker) for marker in ROUTE_RELATION_MARKERS)
            or route_directional_relation_present(value)
        )
    ]
    background_hits = sum(count_text_markers(value, PAGE_BACKGROUND_MARKERS) for value in text_fields.values())
    summary_hits = sum(count_text_markers(value, PAGE_SUMMARY_MARKERS) for value in text_fields.values())
    generic_landing = (
        path in {"", "/", "home", "index", "news", "en", "cn", "zh"}
        or len([part for part in path.split("/") if part]) <= 1
        or count_text_markers(f"{title} {snippet}", PAGE_LANDING_MARKERS) >= 1
    )
    page_type = "other_page"
    page_focus = "background_reference"
    focus_score = 0
    signals: List[str] = []
    risks: List[str] = []
    if direct_relation_sentence_count >= 1:
        page_type = "route_analysis_page" if len(route_signal_fields) >= 2 or len(detail) >= 240 else "route_passage_page"
        page_focus = "decidable_route_relation"
        focus_score = 3
        signals.append("direct_route_relation_sentence")
    elif strong_relation_sentence_count >= 1:
        page_type = "route_passage_page" if len(detail) >= 120 or "detail" in route_signal_fields else "mixed_page"
        page_focus = "route_relation_candidate"
        focus_score = 2
        signals.append("strong_route_relation_candidate")
    elif object_relation_sentence_count >= 1 and relation_sentence_count >= 1 and entity_grounding >= 2:
        page_type = "mixed_page"
        page_focus = "mixed_reference"
        focus_score = 1
        signals.append("object_relation_without_path_anchor")
        risks.append("route_relation_sentence_not_decidable")
    elif relation_sentence_count >= 1 and entity_grounding >= 2:
        if background_hits >= 2 or summary_hits >= 1:
            page_type = "event_background_page" if background_hits >= summary_hits else "war_summary_page"
            page_focus = "background_reference"
            focus_score = 0
            risks.append("relation_mention_without_decidable_route")
        else:
            page_type = "mixed_page"
            page_focus = "mixed_reference"
            focus_score = 1
            signals.append("entity_relation_mixed_page")
    elif summary_hits >= 1 and entity_grounding >= 1:
        page_type = "war_summary_page"
        page_focus = "background_reference"
        focus_score = 0
        risks.append("summary_page_without_route_sentence")
    elif background_hits >= 2 and entity_grounding >= 1:
        page_type = "event_background_page"
        page_focus = "background_reference"
        focus_score = 0
        risks.append("background_page_without_route_sentence")
    elif generic_landing:
        page_type = "landing_page"
        page_focus = "navigation_or_landing"
        focus_score = 0
        risks.append("generic_landing_page")
    if route_signal_fields:
        signals.append("route_signal_fields_" + "_".join(route_signal_fields[:3]))
    if relation_sentence_count <= 0:
        risks.append("no_route_relation_sentence")
    elif strong_relation_sentence_count <= 0 and direct_relation_sentence_count <= 0:
        risks.append("route_relation_sentence_not_decidable")
    return {
        "route_sentence": route_sentence,
        "relation_sentence_count": relation_sentence_count,
        "directional_sentence_count": directional_sentence_count,
        "strong_relation_sentence_count": strong_relation_sentence_count,
        "direct_relation_sentence_count": direct_relation_sentence_count,
        "object_relation_sentence_count": object_relation_sentence_count,
        "route_signal_fields": route_signal_fields,
        "background_hits": background_hits,
        "summary_hits": summary_hits,
        "page_type": page_type,
        "page_focus": page_focus,
        "page_focus_score": focus_score,
        "signals": dedupe_keep_order(signals)[:8],
        "risks": dedupe_keep_order(risks)[:8],
    }


def route_page_capability_features(
    route_profile: Dict[str, Any],
    detail: str,
    entity_grounding: int,
) -> Dict[str, Any]:
    route_sentence = route_profile.get("route_sentence") if isinstance(route_profile.get("route_sentence"), dict) else {}
    route_candidates = route_sentence.get("candidates") if isinstance(route_sentence.get("candidates"), list) else []
    route_signal_fields = route_profile.get("route_signal_fields") if isinstance(route_profile.get("route_signal_fields"), list) else []
    relation_sentence_count = int(route_profile.get("relation_sentence_count") or 0)
    strong_relation_sentence_count = int(route_profile.get("strong_relation_sentence_count") or 0)
    direct_relation_sentence_count = int(route_profile.get("direct_relation_sentence_count") or 0)
    object_relation_sentence_count = int(route_profile.get("object_relation_sentence_count") or 0)
    background_hits = int(route_profile.get("background_hits") or 0)
    summary_hits = int(route_profile.get("summary_hits") or 0)
    detail_has_route_signal = "detail" in route_signal_fields
    route_signal_field_count = len(route_signal_fields)
    cooccurrence_sentence_count = 0
    passage_candidate_count = 0
    for candidate in route_candidates:
        if not isinstance(candidate, dict):
            continue
        has_relation = bool(candidate.get("has_relation_marker"))
        if not has_relation:
            continue
        entity_hits = int(candidate.get("entity_hit_count") or 0)
        has_object = bool(candidate.get("has_route_object_marker"))
        has_directional = bool(candidate.get("has_directional_relation"))
        has_extra_anchor = bool(candidate.get("has_extra_route_anchor"))
        if entity_hits >= 2 and (has_object or has_directional or has_extra_anchor):
            cooccurrence_sentence_count += 1
            if detail_has_route_signal or len(detail) >= 140 or route_signal_field_count >= 2:
                passage_candidate_count += 1
        elif entity_hits >= 2 and (detail_has_route_signal or len(detail) >= 180):
            passage_candidate_count += 1
    decidability = 0
    if direct_relation_sentence_count >= 1:
        decidability = 3
    elif strong_relation_sentence_count >= 1 or cooccurrence_sentence_count >= 2:
        decidability = 2
    elif relation_sentence_count >= 1 and entity_grounding >= 2:
        decidability = 1
    passage_support = 0
    if direct_relation_sentence_count >= 1 and (detail_has_route_signal or len(detail) >= 240):
        passage_support = 3
    elif (strong_relation_sentence_count >= 1 or passage_candidate_count >= 1) and (
        detail_has_route_signal or len(detail) >= 140 or route_signal_field_count >= 2
    ):
        passage_support = 2
    elif relation_sentence_count >= 1 and (detail_has_route_signal or len(detail) >= 80 or route_signal_field_count >= 1):
        passage_support = 1
    cooccurrence_strength = 0
    if direct_relation_sentence_count >= 1 and object_relation_sentence_count >= 1:
        cooccurrence_strength = 3
    elif cooccurrence_sentence_count >= 1:
        cooccurrence_strength = 2
    elif relation_sentence_count >= 1 and entity_grounding >= 2:
        cooccurrence_strength = 1
    background_total = background_hits + summary_hits
    background_dominance = 0
    if background_total >= max(3, relation_sentence_count + 2) and direct_relation_sentence_count <= 0 and strong_relation_sentence_count <= 0:
        background_dominance = 3
    elif background_total >= max(2, relation_sentence_count + 1) and direct_relation_sentence_count <= 0:
        background_dominance = 2
    elif background_total > relation_sentence_count:
        background_dominance = 1
    page_focus = str(route_profile.get("page_focus") or "")
    focus_consistency = 0
    if page_focus == "decidable_route_relation" and passage_support >= 2:
        focus_consistency = 3
    elif page_focus == "route_relation_candidate" and passage_support >= 1:
        focus_consistency = 2
    elif page_focus == "mixed_reference" and cooccurrence_strength >= 1:
        focus_consistency = 1
    headline_only_signal = bool(route_signal_fields) and not detail_has_route_signal and route_signal_field_count == 1 and "title" in route_signal_fields and len(detail) < 80
    return {
        "decidability": decidability,
        "passage_support": passage_support,
        "cooccurrence_strength": cooccurrence_strength,
        "focus_consistency": focus_consistency,
        "background_dominance": background_dominance,
        "cooccurrence_sentence_count": cooccurrence_sentence_count,
        "passage_candidate_count": passage_candidate_count,
        "route_signal_field_count": route_signal_field_count,
        "detail_has_route_signal": detail_has_route_signal,
        "headline_only_signal": headline_only_signal,
    }


def evidence_page_contract_features(
    item: Dict[str, Any],
    source_intent: Dict[str, Any],
    route_profile: Dict[str, Any],
    capability: Dict[str, Any],
    utility_components: Dict[str, Any],
    query: str = "",
) -> Dict[str, Any]:
    evidence_mode = str(source_intent.get("evidence_mode") or "entity_fact")
    evidence_target = str(source_intent.get("evidence_target") or evidence_mode or "general")
    mechanism_type = mechanism_type_from_intent(source_intent)
    role = "related_page"
    status = "partial"
    signals: List[str] = []
    risks: List[str] = []
    score = 0

    if relation_sentence_intent(source_intent):
        relation_count = int(route_profile.get("relation_sentence_count") or 0)
        strong_count = int(route_profile.get("strong_relation_sentence_count") or 0)
        direct_count = int(route_profile.get("direct_relation_sentence_count") or 0)
        object_count = int(route_profile.get("object_relation_sentence_count") or 0)
        page_type = str(route_profile.get("page_type") or "")
        background_dominance = int(capability.get("background_dominance") or 0)
        passage_support = int(capability.get("passage_support") or 0)
        decidability = int(capability.get("decidability") or 0)
        entity_grounding = int(utility_components.get("entity_grounding") or 0)
        structural_extractability = int(utility_components.get("structural_extractability") or 0)

        if direct_count >= 1 and passage_support >= 2:
            role = "evidence_sentence_page"
            status = "satisfied"
            score = 90
            signals.extend(["direct_route_sentence", "passage_support_ready"])
        elif strong_count >= 1 and passage_support >= 1 and entity_grounding >= 2:
            role = "route_explainer"
            status = "partial"
            score = 68
            signals.extend(["strong_route_sentence_candidate", "entity_grounding_ready"])
        elif relation_count >= 1 and entity_grounding >= 2:
            role = "related_page"
            status = "partial"
            score = 48
            signals.append("relation_mentioned")
            risks.append("not_yet_decidable")
        else:
            status = "failed"
            score = 20
            risks.append("missing_required_sentence_shape")

        if page_type in {"event_background_page", "war_summary_page"} or background_dominance >= 2:
            if status != "satisfied":
                role = "background_report"
                status = "failed"
                score = min(score, 35)
            risks.append("background_or_result_dominant")
        if object_count <= 0 and relation_count >= 1:
            risks.append("missing_route_object_or_intermediate")
        if structural_extractability <= 0:
            risks.append("no_extractable_body")
        if decidability <= 1 and relation_count >= 1:
            risks.append("low_sentence_decidability")

        required_shape = "subject + route/transit relation + intermediate place/object in an extractable sentence"
        reject_shape = "only strike/result/interception/background reporting, with route mentioned incidentally"
        answer_target = "verify_route_relation"
    else:
        answerability = int(utility_components.get("answerability") or 0)
        structural_extractability = int(utility_components.get("structural_extractability") or 0)
        entity_grounding = int(utility_components.get("entity_grounding") or 0)
        metric_features = structured_metric_page_features(query, item, source_intent)
        metric_score = int(metric_features.get("metric_table_score") or 0)
        metric_risks = [str(value) for value in metric_features.get("metric_table_risks", []) if str(value)]
        metric_binding_coverage = int(metric_features.get("metric_binding_coverage") or 0)
        metric_site_domain_mismatch = bool(metric_features.get("metric_site_domain_mismatch"))
        source_type = str(item.get("source_type") or "unknown")
        structured_point_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
        structured_point_score = int(item.get("structured_point_contract_score") or 0)
        structured_point_risks = [
            str(value)
            for value in (item.get("structured_point_contract_risks") if isinstance(item.get("structured_point_contract_risks"), list) else [])
            if str(value)
        ]
        path = urlparse(str(item.get("url") or "")).path.lower().strip("/")
        text = normalize_text(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')}")
        homepage_like = (
            path in {"", "/", "home", "index", "news", "en", "cn", "zh"}
            or any(marker in text.lower() for marker in ["首页", "门户", "global web site", "homepage", "home page"])
        )
        metric_mode = mechanism_type in {"structured_numeric_authority", "date_authority"} or evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"} or evidence_target in {
            "market_price",
            "market_calendar",
            "prize_amount",
            "position_distance",
        }
        if metric_mode and structured_point_status == "satisfied":
            role = "structured_metric_table_page"
            status = "satisfied"
            score = max(88, min(96, 70 + structured_point_score // 3))
            signals.extend(
                ["structured_point_contract_satisfied"]
                + [str(value) for value in metric_features.get("metric_table_signals", []) if str(value)]
            )
        elif metric_mode and structured_point_status == "partial":
            role = "structured_metric_table_page"
            status = "partial"
            score = max(72, min(84, 48 + structured_point_score // 3))
            signals.extend(
                ["structured_point_contract_partial"]
                + [str(value) for value in metric_features.get("metric_table_signals", []) if str(value)]
            )
            risks.extend(structured_point_risks)
        elif metric_mode and homepage_like:
            role = "structured_metric_candidate_page"
            status = "partial" if metric_score >= 4 else "failed"
            score = 58 if metric_score >= 4 else 28
            signals.extend([str(value) for value in metric_features.get("metric_table_signals", []) if str(value)])
            risks.extend([str(value) for value in metric_features.get("metric_table_risks", []) if str(value)])
            risks.append("homepage_portal_not_direct_metric_record")
        elif metric_mode and metric_score >= 6 and structural_extractability >= 1 and metric_binding_coverage >= 2 and entity_grounding >= 1 and source_type not in {"forum", "unknown"} and not metric_site_domain_mismatch:
            role = "structured_metric_table_page"
            status = "satisfied"
            score = 86
            signals.extend(["structured_metric_shape"] + [str(item) for item in metric_features.get("metric_table_signals", []) if str(item)])
        elif metric_mode and metric_score >= 4 and metric_binding_coverage >= 1 and not metric_site_domain_mismatch:
            role = "structured_metric_candidate_page"
            status = "partial"
            score = 62
            signals.extend(["metric_table_candidate"] + [str(item) for item in metric_features.get("metric_table_signals", []) if str(item)])
            risks.extend([str(item) for item in metric_features.get("metric_table_risks", []) if str(item)])
        elif answerability >= 2 and structural_extractability >= 1:
            role = "evidence_sentence_page"
            status = "satisfied"
            score = 82
            signals.append("answerable_extractable_page")
        elif answerability >= 1:
            role = "related_page"
            status = "partial"
            score = 52
            risks.append("answerability_partial")
        else:
            role = "related_page"
            status = "failed"
            score = 20
            risks.append("missing_direct_answer_shape")
        risks.extend(metric_risks)
        if metric_mode and metric_site_domain_mismatch:
            role = "related_page"
            status = "failed"
            score = min(score, 18)
            risks.append("site_domain_mismatch")
        if metric_mode and (
            "point_time_scope_mismatch" in structured_point_risks
            or (metric_time_scope_has_explicit_year(source_intent) and "missing_binding_time_scope" in metric_risks)
        ):
            if status == "satisfied":
                role = "structured_metric_candidate_page"
                status = "partial"
                score = min(score, 52)
            elif status == "partial":
                role = "related_page"
                score = min(score, 42)
            risks.append("time_scope_not_bound_to_metric_point")
        if metric_mode and source_type in {"forum", "unknown"}:
            if status == "satisfied":
                role = "structured_metric_candidate_page"
                status = "partial"
                score = min(score, 52)
            elif status == "partial":
                score = min(score, 48)
            risks.append("weak_source_not_direct_metric_record")
        elif metric_mode and source_type == "encyclopedia":
            if status == "satisfied":
                role = "structured_metric_candidate_page"
                status = "partial"
                score = min(score, 56)
            risks.append("reference_page_not_direct_metric_record")
        if metric_mode and metric_binding_coverage <= 0:
            if status == "satisfied":
                role = "structured_metric_candidate_page"
                status = "partial"
                score = min(score, 54)
            elif status == "partial":
                score = min(score, 46)
            risks.append("binding_not_grounded_to_page")
        if metric_mode and homepage_like and "homepage_portal_not_direct_metric_record" not in risks and structured_point_status not in {"satisfied", "partial"} and any(
            risk in metric_risks for risk in ["missing_time_scope", "missing_table_or_quote_shape", "missing_unit_marker"]
        ):
            role = "structured_metric_candidate_page"
            status = "partial"
            score = min(score, 58) if score else 58
            risks.append("homepage_portal_not_direct_metric_record")
        if metric_mode:
            required_shape = "date/time + metric/entity + value type + numeric/date value + unit in a table, quote page, official notice, or extractable sentence"
            reject_shape = "related financial/news page without matching date, value type, unit, or a comparable numeric/date value"
        else:
            required_shape = "subject + checkable relation/value/date/result in an extractable sentence"
            reject_shape = "topic-related page without a sentence that can support or refute the claim"
        answer_target = f"verify_{evidence_target}"

    return {
        "evidence_contract_role": role,
        "evidence_contract_answer_target": answer_target,
        "evidence_contract_required_sentence_shape": required_shape,
        "evidence_contract_reject_shape": reject_shape,
        "evidence_contract_status": status,
        "evidence_contract_score": score,
        "evidence_contract_signals": dedupe_keep_order(signals)[:6],
        "evidence_contract_risks": dedupe_keep_order(risks)[:8],
    }


def title_fact_date_pairs(text: str) -> List[Tuple[str, str, str]]:
    normalized = normalize_text(text)
    pairs: List[Tuple[str, str, str]] = []
    for match in re.finditer(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", normalized):
        pairs.append((match.group(1), str(int(match.group(2))), str(int(match.group(3)))))
    for match in re.finditer(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日", normalized):
        pairs.append(("", str(int(match.group(1))), str(int(match.group(2)))))
    seen: set[Tuple[str, str, str]] = set()
    out: List[Tuple[str, str, str]] = []
    for pair in pairs:
        if pair in seen:
            continue
        seen.add(pair)
        out.append(pair)
    return out


def title_fact_date_scope_conflicts(claim_time_scope: str, surface: str) -> bool:
    claim_dates = title_fact_date_pairs(claim_time_scope)
    surface_dates = title_fact_date_pairs(surface)
    if not claim_dates or not surface_dates:
        return False
    for claim_year, claim_month, claim_day in claim_dates:
        for surface_year, surface_month, surface_day in surface_dates:
            if claim_month == surface_month and claim_day == surface_day and (not claim_year or not surface_year or claim_year == surface_year):
                return False
    return True


def title_level_fact_evidence_ready(
    item: Dict[str, Any],
    source_intent: Dict[str, Any],
    evidence_mode: str,
) -> Tuple[bool, str]:
    mode = effective_evidence_mode(source_intent, evidence_mode)
    if mode not in {"numeric_fact", "date_fact", "schedule_fact", "event_result"}:
        return False, ""
    source_type = normalize_text(str(item.get("source_type") or "")).lower()
    if source_type not in {"official", "news", "finance", "sports"}:
        return False, ""
    title = normalize_text(str(item.get("title") or ""))
    snippet = normalize_text(str(item.get("snippet") or ""))
    binding_terms = source_strategy_binding_terms(source_intent, mode)
    if len(title) < 8:
        return False, ""
    url = str(item.get("url") or "")
    path = urlparse(url).path.lower().strip("/")
    path_tail = path.rsplit("/", 1)[-1] if path else ""
    if path in {"", "/", "home", "index", "news", "en", "cn", "zh"} or path_tail in {"", "index.html", "index.htm"}:
        return False, ""
    surface = f"{title} {snippet}"
    surface_l = normalize_text(surface).lower()
    if re.search(r"(首页|主页|频道|栏目|列表|入口|话题|百科|评论|解读|analysis|commentary|topic|wiki|portal|homepage|search|list)", title, flags=re.I):
        return False, ""
    temporal = int(item.get("temporal_score") or 0)
    event_window = int(item.get("event_window_score") or 0)
    relevance = int(item.get("relevance_score") or 0)
    entity_hits = int(item.get("entity_match_count") or 0)
    directness = int(item.get("directness_score") or 0)
    if mode in {"numeric_fact", "date_fact", "schedule_fact"} and (temporal < 0 or event_window < 0):
        return False, "title_fact_time_mismatch"
    if mode == "event_result" and event_window < -1:
        return False, "title_fact_event_window_mismatch"
    grounded = entity_hits >= 1 or relevance >= 4 or directness >= 3
    if not grounded:
        return False, "title_fact_not_claim_grounded"
    claim_time_scope = str(binding_terms.get("time_scope") or "")
    if mode == "numeric_fact" and title_fact_date_scope_conflicts(claim_time_scope, surface):
        return False, "title_fact_time_scope_mismatch"
    has_time = bool(re.search(r"(20\d{2}|[01]?\d\s*月\s*[0-3]?\d\s*日|\d{4}[-/]\d{1,2}[-/]\d{1,2}|today|yesterday)", surface_l, flags=re.I))
    if mode == "numeric_fact":
        metric_marker = bool(re.search(r"(中间价|汇率|牌价|人民币对美元|兑美元|美元兑人民币|报|报价|上调|下调|上涨|下跌|涨|跌|基点|price|rate|quote|points?)", surface_l, flags=re.I))
        value_marker = bool(re.search(r"(报|为|约为|上调|下调|上涨|下跌|涨|跌)\s*[0-9]+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?\s*(?:个?基点|%|％|元|点|美元|人民币|港元)", surface_l, flags=re.I))
        if metric_marker and value_marker and (has_time or temporal >= 1):
            return True, "trusted_title_numeric_fact_ready"
        return False, "title_numeric_fact_missing_value_or_time"
    if mode in {"date_fact", "schedule_fact"}:
        schedule_marker = bool(re.search(r"(公告|通知|安排|日历|休市|开市|生效|发布|calendar|notice|schedule|holiday)", surface_l, flags=re.I))
        if schedule_marker and has_time:
            return True, "trusted_title_schedule_fact_ready"
        return False, "title_schedule_fact_missing_marker_or_time"
    if mode == "event_result":
        result_marker = bool(re.search(r"(战报|赛果|比分|结果|获胜|击败|轻取|大胜|result|score|won|beat|defeated|\d+\s*[-:：]\s*\d+)", surface_l, flags=re.I))
        if result_marker:
            return True, "trusted_title_event_result_ready"
        return False, "title_event_result_missing_result_marker"
    return False, ""


def page_role_contract_features(
    item: Dict[str, Any],
    source_intent: Dict[str, Any],
    contract: Dict[str, Any],
) -> Dict[str, Any]:
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    role = normalize_text(str(contract.get("evidence_contract_role") or "")).lower()
    status = normalize_text(str(contract.get("evidence_contract_status") or "")).lower()
    score = int(contract.get("evidence_contract_score") or 0)
    risks = [normalize_text(str(value)) for value in (contract.get("evidence_contract_risks") or []) if str(value)]
    source = normalize_text(str(item.get("source") or "")).lower()
    source_type = normalize_text(str(item.get("source_type") or "")).lower()
    detail_error = normalize_text(str(item.get("detail_error") or item.get("detail_error_type") or "")).lower()
    page_type = normalize_text(str(item.get("page_utility_page_type") or "")).lower()
    page_focus = normalize_text(str(item.get("page_utility_page_focus") or "")).lower()
    title = normalize_text(str(item.get("title") or "")).lower()
    snippet = normalize_text(str(item.get("snippet") or "")).lower()
    url = normalize_text(str(item.get("url") or "")).lower()
    surface = " ".join([title, snippet, url, page_type, page_focus])
    structured_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
    structured_best = item.get("structured_table_best_point") if isinstance(item.get("structured_table_best_point"), dict) else {}
    homepage_like = official_homepage_like(item)
    trusted_fact_source = source_type in {"official", "news", "finance", "sports", "encyclopedia"}
    generic_surface = bool(re.search(r"(首页|主页|频道|栏目|列表|入口|话题|百科|评论|解读|analysis|commentary|topic|wiki|portal|homepage|index|search|list)", surface, flags=re.I))
    fact_like_surface = False
    if evidence_mode == "event_result":
        fact_like_surface = bool(re.search(r"(战报|赛果|比分|结果|获胜|击败|轻取|大胜|result|score|won|beat|defeated|\d+\s*[-:：]\s*\d+)", surface, flags=re.I))
    elif evidence_mode in {"numeric_fact", "numeric_count_detail"}:
        fact_like_surface = bool(
            re.search(r"(开盘|收盘|涨幅|跌幅|报价|牌价|汇率|中间价|数据|基点|%|％|quote|rate|price|points?)", surface, flags=re.I)
            or re.search(r"(?:^|[\s，。；:：])报\s*[0-9]+(?:\.[0-9]+)?", surface, flags=re.I)
        )
    elif evidence_mode in {"date_fact", "schedule_fact"}:
        fact_like_surface = bool(re.search(r"(公告|通知|日历|安排|休市|开市|发布|生效|日期|calendar|notice|schedule|holiday)", surface, flags=re.I))
    elif evidence_mode == "route_fact":
        fact_like_surface = bool(re.search(r"(路线|航线|通道|经过|途经|绕行|替代|route|corridor|bypass|alternative)", surface, flags=re.I))

    role_name = "generic_page"
    reason = "not_direct_evidence_shape"
    contract_score = max(0, min(100, score))
    evidence_ready = False
    follow_required = False
    generic_block_reason = ""
    title_fact_ready, title_fact_reason = title_level_fact_evidence_ready(item, source_intent, evidence_mode)

    if detail_error and any(marker in detail_error for marker in ["403", "anti_bot", "blocked", "captcha", "login"]):
        role_name = "blocked_page"
        reason = "access_blocked_or_login_required"
        contract_score = min(contract_score, 20)
    elif status == "satisfied" and role in {"evidence_sentence_page", "structured_metric_table_page"}:
        role_name = "evidence_page"
        reason = "contract_satisfied_direct_page"
        evidence_ready = True
        contract_score = max(contract_score, 82)
    elif structured_status == "satisfied" or (structured_best and role == "structured_metric_table_page"):
        role_name = "evidence_page"
        reason = "structured_table_point_ready"
        evidence_ready = True
        contract_score = max(contract_score, 84)
    elif title_fact_ready:
        role_name = "evidence_page"
        reason = title_fact_reason or "title_level_fact_evidence_ready"
        evidence_ready = True
        contract_score = max(contract_score, 78)
    elif (
        trusted_fact_source
        and fact_like_surface
        and not homepage_like
        and not generic_surface
        and not any(risk in {"missing_binding_subject_entity", "missing_binding_relation_or_metric", "missing_binding_time_scope"} for risk in risks)
    ):
        role_name = "evidence_page"
        reason = "trusted_fact_like_page_shape"
        evidence_ready = True
        contract_score = max(contract_score, 74)
    elif (
        homepage_like
        or "homepage_portal_not_direct_metric_record" in risks
        or source in {"official_discovery", "domain_sitemap"}
        or role in {"structured_metric_candidate_page"}
        or page_type in {"landing_page", "search_page", "portal_page"}
        or re.search(r"(首页|主页|频道|栏目|列表|查询|入口|portal|homepage|index|search|list)", surface, flags=re.I)
    ):
        role_name = "entry_page"
        reason = "authority_or_portal_entry_requires_follow"
        follow_required = source_type in {"official", "news", "finance", "sports", "encyclopedia"} or source in {"official_discovery", "domain_sitemap"}
        if evidence_mode not in {"numeric_fact", "date_fact", "schedule_fact", "route_fact", "event_result"}:
            follow_required = False
        contract_score = min(max(contract_score, 45), 70)
    elif role in {"background_report", "related_page"} or status == "failed":
        role_name = "generic_page"
        reason = "contract_failed_or_related_only"
        generic_block_reason = "related_but_not_decidable"
        contract_score = min(contract_score, 45)
    elif source_type in {"forum", "qa"} or re.search(r"(知乎|话题|百科|评论|解读|analysis|commentary|topic|wiki)", surface, flags=re.I):
        role_name = "generic_page"
        reason = "weak_or_background_source_shape"
        generic_block_reason = "background_or_discussion_page"
        contract_score = min(contract_score, 40)
    else:
        role_name = "generic_page"
        generic_block_reason = "no_direct_decision_contract"

    if role_name == "entry_page":
        generic_block_reason = ""
    elif role_name != "generic_page":
        generic_block_reason = ""
    return {
        "page_role": role_name,
        "page_role_reason": reason,
        "page_role_contract_score": contract_score,
        "entry_page_follow_required": follow_required,
        "evidence_page_ready": evidence_ready,
        "generic_page_block_reason": generic_block_reason,
        "title_level_fact_evidence_ready": title_fact_ready,
        "title_level_fact_evidence_reason": title_fact_reason,
    }


def page_utility_features(item: Dict[str, Any], source_intent: Dict[str, Any], query: str = "") -> Dict[str, Any]:
    evidence_mode = str(source_intent.get("evidence_mode") or "")
    mechanism_type = mechanism_type_from_intent(source_intent)
    title = normalize_text(str(item.get("title") or ""))
    snippet = normalize_text(str(item.get("snippet") or ""))
    detail = normalize_text(str(item.get("detail") or ""))
    url = str(item.get("url") or "")
    source_type = str(item.get("source_type") or "unknown")
    path = urlparse(url).path.lower().strip("/")
    text = f"{title} {snippet} {detail} {url}".lower()
    relation_evidence = 0
    answerability = 0
    entity_grounding = min(3, int(item.get("entity_match_count") or entity_match_count(query, item) or 0))
    structural_extractability = 0
    specificity = 0
    trust_temporal_fitness = 0
    noise_penalty = 0
    page_type = "general_page"
    page_focus = "general_reference"
    page_focus_score = 0
    page_type_signals: List[str] = []
    page_type_risks: List[str] = []
    route_profile: Dict[str, Any] = {}
    capability: Dict[str, Any] = {}
    positive_signals: List[str] = []
    risks: List[str] = []

    if detail:
        structural_extractability = 3 if len(detail) >= 240 else 2
        positive_signals.append("detail_body_available")
    elif snippet:
        structural_extractability = 2 if len(snippet) >= 100 else 1
        positive_signals.append("snippet_available")
    elif title:
        structural_extractability = 1
        risks.append("title_only_page")
    if path in {"", "/", "home", "index", "news", "en", "cn", "zh"}:
        structural_extractability = max(0, structural_extractability - 1)
        noise_penalty += 1
        risks.append("generic_path_shape")

    if source_type == "official":
        trust_temporal_fitness = 3
        positive_signals.append("official_source")
    elif source_type == "news":
        trust_temporal_fitness = 2
        positive_signals.append("news_source")
    elif source_type == "encyclopedia":
        trust_temporal_fitness = 1
    else:
        trust_temporal_fitness = 0
    temporal = int(item.get("temporal_score") or 0)
    event_window = int(item.get("event_window_score") or 0)
    if temporal <= -2 or event_window <= -2:
        trust_temporal_fitness = max(0, trust_temporal_fitness - 1)
        noise_penalty += 1
        risks.append("temporal_fit_weak")

    if relation_sentence_intent(source_intent):
        route_profile = route_page_profile(query, item, title, snippet, detail, entity_grounding, path)
        capability = route_page_capability_features(route_profile, detail, entity_grounding)
        route_sentence = route_profile.get("route_sentence") if isinstance(route_profile.get("route_sentence"), dict) else {}
        route_candidates = route_sentence.get("candidates") if isinstance(route_sentence.get("candidates"), list) else []
        has_directional = any(candidate.get("has_directional_relation") for candidate in route_candidates if isinstance(candidate, dict))
        has_object = bool(route_sentence.get("has_route_object_marker"))
        route_decidability = int(capability.get("decidability") or 0)
        passage_support = int(capability.get("passage_support") or 0)
        cooccurrence_strength = int(capability.get("cooccurrence_strength") or 0)
        focus_consistency = int(capability.get("focus_consistency") or 0)
        background_dominance = int(capability.get("background_dominance") or 0)
        page_type = str(route_profile.get("page_type") or "other_page")
        page_focus = str(route_profile.get("page_focus") or "background_reference")
        page_focus_score = int(route_profile.get("page_focus_score") or 0)
        page_type_signals.extend([str(item) for item in route_profile.get("signals", []) if str(item).strip()])
        page_type_risks.extend([str(item) for item in route_profile.get("risks", []) if str(item).strip()])
        if route_sentence.get("direct_sentence"):
            relation_evidence = 3
            answerability = 3
            specificity = 3
            positive_signals.append("direct_relation_sentence")
        elif int(route_profile.get("strong_relation_sentence_count") or 0) >= 1:
            relation_evidence = 2
            answerability = 2 if (has_object or not route_sentence.get("query_requires_route_object")) else 1
            specificity = 2
            positive_signals.append("strong_relation_with_entity_grounding")
        elif route_sentence.get("has_relation_marker") and int(route_sentence.get("entity_hit_count") or 0) >= 2:
            relation_evidence = 2
            answerability = 1 if (has_object or not route_sentence.get("query_requires_route_object")) else 0
            specificity = 2
            positive_signals.append("relation_with_entity_grounding")
        elif route_sentence.get("has_relation_marker") or has_directional:
            relation_evidence = 1
            answerability = 1 if entity_grounding >= 1 else 0
            specificity = 1 if entity_grounding >= 1 else 0
            positive_signals.append("weak_relation_signal")
        elif entity_grounding >= 2:
            specificity = 1
            risks.append("entity_only_without_relation")
        else:
            risks.append("missing_relation_signal")
        relation_evidence = max(relation_evidence, route_decidability)
        answerability = max(answerability, route_decidability if passage_support >= 1 else max(0, route_decidability - 1))
        specificity = max(specificity, cooccurrence_strength)
        if passage_support >= 2:
            structural_extractability = max(structural_extractability, 2)
            positive_signals.append("decidable_passage_support")
        elif route_decidability >= 1 and passage_support <= 0:
            noise_penalty += 1
            risks.append("relation_signal_without_passage_support")
        if cooccurrence_strength >= 2:
            positive_signals.append("entity_relation_region_cooccurrence")
        elif relation_evidence >= 1 and entity_grounding >= 2:
            risks.append("route_cooccurrence_weak")
        if focus_consistency >= 2:
            positive_signals.append("route_focus_consistent")
        elif page_focus == "background_reference" and route_decidability <= 1:
            noise_penalty += 1
            risks.append("page_focus_not_decidable")
        if background_dominance >= 2 and route_decidability <= 1:
            noise_penalty += 1
            risks.append("background_dominates_route_signal")
        if capability.get("headline_only_signal"):
            noise_penalty += 1
            risks.append("headline_only_route_signal")
        if page_focus_score >= 2:
            answerability = max(answerability, min(3, page_focus_score))
            specificity = max(specificity, min(3, page_focus_score))
            positive_signals.append("route_page_focus_strong")
        elif page_type in {"event_background_page", "war_summary_page", "landing_page"}:
            noise_penalty += 1
            risks.append("route_page_type_low_decidability")
        if route_sentence.get("query_requires_route_object") and not has_object:
            noise_penalty += 1
            risks.append("missing_required_route_object")
        if entity_grounding >= 2:
            positive_signals.append("entity_grounding_present")
        elif entity_grounding <= 0:
            noise_penalty += 1
            risks.append("missing_entity_grounding")
    else:
        directness = int(item.get("directness_score") or 0)
        answerability = 3 if directness >= 4 else 2 if directness >= 2 else 1 if directness >= 1 else 0
        relation_evidence = answerability
        specificity = 3 if directness >= 4 else 2 if directness >= 2 else 1 if entity_grounding >= 1 else 0
        metric_features = structured_metric_page_features(query, item, source_intent)
        metric_score = int(metric_features.get("metric_table_score") or 0)
        metric_mode = mechanism_type in {"structured_numeric_authority", "date_authority"} or evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}
        site_domain_mismatch = bool(metric_features.get("metric_site_domain_mismatch"))
        if metric_score >= 6:
            answerability = max(answerability, 2)
            relation_evidence = max(relation_evidence, 2)
            specificity = max(specificity, 2)
            structural_extractability = max(structural_extractability, 1)
            positive_signals.extend([str(signal) for signal in metric_features.get("metric_table_signals", []) if str(signal)])
        elif metric_score >= 4:
            answerability = max(answerability, 1)
            specificity = max(specificity, 1)
            positive_signals.extend([str(signal) for signal in metric_features.get("metric_table_signals", []) if str(signal)])
        for risk in metric_features.get("metric_table_risks", []) if isinstance(metric_features.get("metric_table_risks"), list) else []:
            if str(risk):
                risks.append(str(risk))
        if metric_mode and site_domain_mismatch:
            noise_penalty += 2
        if metric_mode and source_type in {"forum", "unknown"}:
            answerability = min(answerability, 1)
            relation_evidence = min(relation_evidence, 1)
            specificity = min(specificity, 1)
            noise_penalty += 2
            risks.append("weak_source_metric_candidate")
        elif metric_mode and source_type == "encyclopedia":
            answerability = min(answerability, 1)
            specificity = min(specificity, 1)
            noise_penalty += 1
            risks.append("reference_source_metric_candidate")
        if metric_mode and int(metric_features.get("metric_binding_coverage") or 0) <= 0:
            answerability = min(answerability, 1)
            relation_evidence = min(relation_evidence, 1)
            specificity = min(specificity, 1)
            noise_penalty += 1
            risks.append("metric_binding_not_grounded")

    if is_search_engine_result_page(item):
        noise_penalty += 3
        risks.append("search_result_page")
    if int(item.get("source_quality_score") or 0) < 35:
        noise_penalty += 1
        risks.append("low_source_quality")
    if re.search(r"(发布于|官方账号|you are using an outdated browser|_腾讯新闻|login|sign in)", text, flags=re.I):
        noise_penalty += 1
        risks.append("page_meta_noise")

    total_score = max(
        0,
        min(
            100,
            18
            + answerability * 14
            + relation_evidence * 12
            + entity_grounding * 8
            + structural_extractability * 7
            + specificity * 9
            + trust_temporal_fitness * 6
            - noise_penalty * 12,
        ),
    )
    label = "good" if total_score >= 75 else "usable" if total_score >= 60 else "weak" if total_score >= 40 else "bad"
    utility_components = {
        "answerability": answerability,
        "relation_evidence": relation_evidence,
        "entity_grounding": entity_grounding,
        "structural_extractability": structural_extractability,
        "specificity": specificity,
        "trust_temporal_fitness": trust_temporal_fitness,
        "noise_penalty": noise_penalty,
    }
    metric_features_for_components = structured_metric_page_features(query, item, source_intent)
    if int(metric_features_for_components.get("metric_table_score") or 0) > 0:
        utility_components["metric_table_score"] = int(metric_features_for_components.get("metric_table_score") or 0)
        utility_components["metric_table_signal_count"] = len(metric_features_for_components.get("metric_table_signals", []))
        utility_components["metric_table_risk_count"] = len(metric_features_for_components.get("metric_table_risks", []))
    contract = evidence_page_contract_features(item, source_intent, route_profile, capability, utility_components, query)
    page_role = page_role_contract_features(item, source_intent, contract)
    return {
        "page_utility_score": total_score,
        "page_utility_label": label,
        "page_utility_components": utility_components,
        "page_utility_positive_signals": dedupe_keep_order(positive_signals)[:8],
        "page_utility_risks": dedupe_keep_order(risks)[:8],
        "page_utility_page_type": page_type,
        "page_utility_page_focus": page_focus,
        "page_utility_page_focus_score": page_focus_score,
        "page_utility_page_type_signals": dedupe_keep_order(page_type_signals)[:8],
        "page_utility_page_type_risks": dedupe_keep_order(page_type_risks)[:8],
        "page_utility_relation_sentence_count": int(route_profile.get("relation_sentence_count") or 0),
        "page_utility_strong_relation_sentence_count": int(route_profile.get("strong_relation_sentence_count") or 0),
        "page_utility_direct_relation_sentence_count": int(route_profile.get("direct_relation_sentence_count") or 0),
        "page_utility_route_signal_fields": route_profile.get("route_signal_fields", []) if isinstance(route_profile.get("route_signal_fields"), list) else [],
        "page_utility_capability": capability,
        **contract,
        **page_role,
    }


def page_intent_features(
    item: Dict[str, Any],
    source_intent: Dict[str, Any],
    query: str = "",
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    page_intent = normalize_page_intent(source_intent)
    evidence_mode = str(source_intent.get("evidence_mode") or "")
    needed = str(page_intent.get("needed_page_type") or "general_page")
    title = str(item.get("title") or "")
    url = str(item.get("url") or "")
    snippet = str(item.get("snippet") or "")
    detail = str(item.get("detail") or "")
    text = f"{title} {url} {snippet} {detail}".lower()
    path = urlparse(url).path.lower().strip("/")
    score = 50
    issues: List[str] = []
    matched: List[str] = []
    for marker in page_intent_markers(needed):
        if marker.lower() in text:
            matched.append(marker)
    if matched:
        if needed == "route_analysis_page":
            score += min(14, 3 + 2 * len(set(matched)))
        else:
            score += min(25, 5 + 4 * len(set(matched)))
    elif needed != "general_page":
        score -= 12
        issues.append("missing_page_type_marker")
    must_hits: List[str] = []
    for token in page_intent.get("must_contain") or []:
        token_text = str(token).strip().lower()
        if token_text and token_text in text:
            must_hits.append(str(token))
    if page_intent.get("must_contain"):
        if must_hits:
            score += min(20, 5 + 3 * len(must_hits))
        else:
            score -= 10
            issues.append("missing_must_contain")
    generic_path = path in {"", "/", "home", "index", "news", "en", "cn", "zh"} or len([p for p in path.split("/") if p]) <= 1
    generic_title = title.strip().lower() in {"nba.com", "google translate"} or any(
        marker in title.lower() for marker in ["首页", "主页", "global portal", "门户首页"]
    )
    if generic_path or generic_title:
        score -= 20
        issues.append("generic_landing_page")
    avoid = " ".join(str(item) for item in page_intent.get("avoid_page_type") or []).lower()
    if "homepage" in avoid and (generic_path or generic_title):
        score -= 10
        issues.append("avoid_homepage_hit")
    if "navigation_page" in avoid and any(marker in text for marker in ["navigation", "登录", "login", "category", "栏目"]):
        score -= 8
        issues.append("avoid_navigation_hit")
    utility = page_utility_features(item, source_intent, query)
    utility_score = int(utility.get("page_utility_score") or 0)
    utility_components = utility.get("page_utility_components") if isinstance(utility.get("page_utility_components"), dict) else {}
    if utility_score >= 75:
        score += 10
    elif utility_score >= 60:
        score += 5
    elif utility_score < 40:
        score -= 10
        issues.append("low_page_utility")
    if needed == "route_analysis_page":
        utility_page_type = str(utility.get("page_utility_page_type") or "")
        utility_page_focus = str(utility.get("page_utility_page_focus") or "")
        focus_score = int(utility.get("page_utility_page_focus_score") or 0)
        relation_sentence_count = int(utility.get("page_utility_relation_sentence_count") or 0)
        strong_relation_sentence_count = int(utility.get("page_utility_strong_relation_sentence_count") or 0)
        direct_relation_sentence_count = int(utility.get("page_utility_direct_relation_sentence_count") or 0)
        route_signal_fields = utility.get("page_utility_route_signal_fields") if isinstance(utility.get("page_utility_route_signal_fields"), list) else []
        utility_capability = utility.get("page_utility_capability") if isinstance(utility.get("page_utility_capability"), dict) else {}
        decidability = int(utility_capability.get("decidability") or 0)
        passage_support = int(utility_capability.get("passage_support") or 0)
        cooccurrence_strength = int(utility_capability.get("cooccurrence_strength") or 0)
        background_dominance = int(utility_capability.get("background_dominance") or 0)
        if utility_page_type == "route_analysis_page":
            score += 18
        elif utility_page_type == "route_passage_page":
            score += 12
        elif utility_page_type == "mixed_page":
            score += 2
            issues.append("route_page_type_mixed")
        elif utility_page_type == "event_background_page":
            score -= 12
            issues.append("route_page_type_background")
        elif utility_page_type == "war_summary_page":
            score -= 14
            issues.append("route_page_type_summary")
        elif utility_page_type == "landing_page":
            score -= 18
            issues.append("route_page_type_landing")
        else:
            score -= 8
            issues.append("missing_route_relation_signal")
        if focus_score >= 2:
            score += 6
        elif utility_page_focus == "background_reference":
            score -= 6
            issues.append("route_page_focus_background")
        if direct_relation_sentence_count >= 1:
            score += 8
        elif strong_relation_sentence_count >= 1:
            score += 4
        elif relation_sentence_count >= 1:
            score -= 2
            issues.append("route_relation_without_path_anchor")
        if decidability >= 2:
            score += 8
        elif relation_sentence_count >= 1:
            score -= 6
            issues.append("route_page_decidability_low")
        if passage_support >= 2:
            score += 6
        elif decidability >= 1 and passage_support <= 0:
            score -= 6
            issues.append("route_passage_support_low")
        if cooccurrence_strength >= 2:
            score += 6
        elif relation_sentence_count >= 1 and int(utility_components.get("entity_grounding") or 0) >= 2:
            score -= 4
            issues.append("route_cooccurrence_weak")
        if background_dominance >= 2 and direct_relation_sentence_count <= 0:
            score -= 8
            issues.append("route_background_dominant")
        if len(route_signal_fields) >= 2:
            score += 4
        if int(utility_components.get("relation_evidence") or 0) >= 2:
            score += 8
        elif int(utility_components.get("relation_evidence") or 0) <= 0:
            score -= 8
            issues.append("route_relation_answerability_low")
        if int(utility_components.get("structural_extractability") or 0) >= 2:
            score += 4
        elif int(utility_components.get("noise_penalty") or 0) >= 2:
            score -= 6
            issues.append("route_page_noise_high")
    if item.get("source_type") in {"official", "news"} and matched:
        score += 5
    score = max(0, min(100, score))
    label = "good" if score >= 75 else "usable" if score >= 60 else "weak" if score >= 40 else "bad"
    rule_utility_score = utility_score
    rule_utility_label = str(utility.get("page_utility_label") or "")
    rule_intent_score = score
    retention_score = max(0, min(100, round(score * 0.45 + utility_score * 0.55)))
    retention_rule_score = retention_score
    llm_result: Dict[str, Any] = {}
    llm_applied = False
    llm_call_count = int(stats.get("page_utility_llm_calls", 0) or 0) if isinstance(stats, dict) else 0
    if page_utility_llm_candidate(item, source_intent, retention_score) and llm_call_count < PAGE_UTILITY_LLM_MAX_ITEMS_PER_CLAIM:
        raw_llm = call_page_utility_llm(query, query, source_intent, item)
        if isinstance(raw_llm, dict):
            llm_result = normalize_page_utility_llm_result(raw_llm)
            llm_score = int(llm_result.get("page_utility_llm_score") or 0)
            utility_score = max(0, min(100, round(rule_utility_score * 0.72 + llm_score * 0.28)))
            utility["page_utility_score"] = utility_score
            utility["page_utility_label"] = "good" if utility_score >= 75 else "usable" if utility_score >= 60 else "weak" if utility_score >= 40 else "bad"
            retention_score = max(
                0,
                min(
                    100,
                    round(
                        rule_intent_score * 0.38
                        + utility_score * 0.47
                        + int(llm_result.get("page_utility_llm_retention_adjustment") or 0)
                    ),
                ),
            )
            llm_applied = True
            if isinstance(stats, dict):
                stats["page_utility_llm_calls"] = llm_call_count + 1
    if llm_result:
        contract_status = str(utility.get("evidence_contract_status") or "")
        llm_decision = str(llm_result.get("page_utility_llm_decision") or "")
        if contract_status in {"satisfied", "partial"} and llm_decision in {"drop", "borderline"}:
            utility["evidence_contract_risks"] = dedupe_keep_order(
                [str(risk) for risk in utility.get("evidence_contract_risks", []) if str(risk)]
                + ["contract_utility_conflict"]
            )[:8]
    retention_label = "keep" if retention_score >= 72 else "borderline_keep" if retention_score >= 55 else "drop"
    return {
        "page_intent": page_intent,
        "page_intent_score": score,
        "page_intent_label": label,
        "page_intent_matched": dedupe_keep_order([str(item) for item in matched])[:8],
        "page_intent_issues": dedupe_keep_order(issues),
        "page_intent_must_hits": must_hits[:6],
        "page_utility_rule_score": rule_utility_score,
        "page_utility_rule_label": rule_utility_label,
        "page_retention_rule_score": retention_rule_score,
        "page_retention_score": retention_score,
        "page_retention_label": retention_label,
        "page_utility_llm_applied": llm_applied,
        **llm_result,
        **utility,
    }


def page_retention_context(item: Dict[str, Any], source_type: str = "") -> Dict[str, Any]:
    page_utility_components = item.get("page_utility_components") if isinstance(item.get("page_utility_components"), dict) else {}
    page_utility_capability = item.get("page_utility_capability") if isinstance(item.get("page_utility_capability"), dict) else {}
    return {
        "source_type": str(source_type or item.get("source_type") or ""),
        "route_rerank": int(item.get("route_rerank_score") or 0),
        "page_utility_score": int(item.get("page_utility_score") or 0),
        "page_retention_score": int(item.get("page_retention_score") or 0),
        "llm_keep": str(item.get("page_utility_llm_decision") or "") == "keep",
        "page_type": str(item.get("page_utility_page_type") or ""),
        "page_focus": str(item.get("page_utility_page_focus") or ""),
        "relation_sentence_count": int(item.get("page_utility_relation_sentence_count") or 0),
        "strong_relation_sentence_count": int(item.get("page_utility_strong_relation_sentence_count") or 0),
        "direct_relation_sentence_count": int(item.get("page_utility_direct_relation_sentence_count") or 0),
        "relation_evidence": int(page_utility_components.get("relation_evidence") or 0),
        "answerability": int(page_utility_components.get("answerability") or 0),
        "entity_grounding": int(page_utility_components.get("entity_grounding") or 0),
        "structural_extractability": int(page_utility_components.get("structural_extractability") or 0),
        "decidability": int(page_utility_capability.get("decidability") or 0),
        "passage_support": int(page_utility_capability.get("passage_support") or 0),
        "cooccurrence_strength": int(page_utility_capability.get("cooccurrence_strength") or 0),
        "background_dominance": int(page_utility_capability.get("background_dominance") or 0),
        "headline_only_signal": bool(page_utility_capability.get("headline_only_signal")),
    }


def page_retention_profile_matches(context: Dict[str, Any], profile: Dict[str, Any]) -> bool:
    page_types = profile.get("page_types") if isinstance(profile.get("page_types"), set) else None
    if page_types and context.get("page_type") not in page_types:
        return False
    source_types = profile.get("source_types") if isinstance(profile.get("source_types"), set) else None
    if source_types and context.get("source_type") not in source_types:
        return False
    page_focus_exclude = profile.get("page_focus_exclude") if isinstance(profile.get("page_focus_exclude"), set) else None
    if page_focus_exclude and context.get("page_focus") in page_focus_exclude:
        return False
    for field in profile.get("require_true") or set():
        if not context.get(field):
            return False
    for field, minimum in (profile.get("min") or {}).items():
        if int(context.get(field) or 0) < int(minimum):
            return False
    for field, maximum in (profile.get("max") or {}).items():
        if int(context.get(field) or 0) > int(maximum):
            return False
    return True


def route_page_retention_decision(item: Dict[str, Any], source_type: str) -> Optional[tuple[bool, str]]:
    route_sentence = item.get("route_sentence") if isinstance(item.get("route_sentence"), dict) else {}
    context = page_retention_context(item, source_type)
    strong_route_sources = {"official", "news", "encyclopedia"}
    route_candidates = route_sentence.get("candidates") if isinstance(route_sentence.get("candidates"), list) else []
    has_strong_route_candidate = any(
        isinstance(candidate, dict)
        and candidate.get("has_relation_marker")
        and candidate.get("has_route_object_marker")
        and int(candidate.get("entity_hit_count") or 0) >= 4
        and (candidate.get("has_directional_relation") or candidate.get("has_extra_route_anchor"))
        for candidate in route_candidates
    )
    if route_sentence.get("direct_sentence"):
        return True, "kept_route_direct_sentence"
    if (
        context["page_type"] in {"route_analysis_page", "route_passage_page"}
        and context["page_retention_score"] >= 68
        and has_strong_route_candidate
    ):
        return True, "kept_route_candidate_sentence_page"
    if context["page_type"] == "landing_page":
        return False, "route_page_type_landing"
    if (
        context["background_dominance"] >= 2
        and context["decidability"] <= 1
        and context["direct_relation_sentence_count"] <= 0
        and context["strong_relation_sentence_count"] <= 0
    ):
        return False, "route_background_dominant_low_decidability"
    if (
        context["background_dominance"] >= 2
        and context["passage_support"] <= 1
        and context["direct_relation_sentence_count"] <= 0
    ):
        return False, "route_background_dominant_candidate_only"
    if context["headline_only_signal"] and context["decidability"] <= 1 and context["page_retention_score"] < 66:
        return False, "route_headline_only_signal"
    object_marker_gate_ready = bool(
        int(route_sentence.get("entity_hit_count") or 0) >= 1
        or context["entity_grounding"] >= 1
        or context["passage_support"] >= 1
        or context["page_retention_score"] >= 40
        or context["route_rerank"] >= 8
    )
    if (
        route_sentence.get("query_requires_route_object")
        and object_marker_gate_ready
        and not route_sentence.get("has_route_object_marker")
        and context["relation_evidence"] <= 1
        and context["cooccurrence_strength"] <= 1
    ):
        return False, "route_missing_required_object_marker"
    if page_retention_profile_matches(
        context,
        {
            "page_types": {"route_analysis_page", "route_passage_page"},
            "source_types": strong_route_sources,
            "min": {
                "decidability": 2,
                "passage_support": 1,
                "cooccurrence_strength": 1,
                "page_retention_score": 62,
                "relation_evidence": 2,
                "entity_grounding": 2,
                "structural_extractability": 1,
            },
        },
    ):
        return True, "kept_route_decidable_page"
    if page_retention_profile_matches(
        context,
        {
            "page_types": {"mixed_page"},
            "source_types": strong_route_sources,
            "min": {
                "decidability": 1,
                "passage_support": 1,
                "cooccurrence_strength": 2,
                "page_retention_score": 66,
                "route_rerank": 8,
            },
            "max": {"background_dominance": 1},
            "page_focus_exclude": {"background_reference"},
        },
    ):
        return True, "kept_route_mixed_passage_candidate"
    if page_retention_profile_matches(
        context,
        {
            "source_types": strong_route_sources,
            "min": {
                "passage_support": 2,
                "decidability": 1,
                "relation_evidence": 1,
                "answerability": 1,
                "entity_grounding": 2,
                "page_retention_score": 60,
                "route_rerank": 8,
            },
        },
    ):
        return True, "kept_route_passage_support_page"
    if page_retention_profile_matches(
        context,
        {
            "source_types": strong_route_sources | {"unknown"},
            "require_true": {"llm_keep"},
            "min": {
                "decidability": 1,
                "passage_support": 1,
                "page_retention_score": 58,
                "relation_evidence": 1,
            },
            "max": {"background_dominance": 1},
        },
    ):
        return True, "kept_route_llm_utility_page"
    if context["page_type"] in {"event_background_page", "war_summary_page"} and context["direct_relation_sentence_count"] <= 0:
        return False, "route_page_type_background"
    if context["relation_sentence_count"] >= 1 and context["passage_support"] <= 0 and context["strong_relation_sentence_count"] <= 0:
        return False, "route_relation_without_passage_support"
    if context["page_utility_score"] < 40 and context["relation_evidence"] <= 0 and context["decidability"] <= 0:
        return False, "route_page_utility_too_low"
    if context["route_rerank"] < 8 and context["page_retention_score"] < 55 and context["decidability"] <= 1:
        return False, "route_rerank_low_quality"
    return None


def route_sentence_analysis(query: str, item: Dict[str, Any]) -> Dict[str, Any]:
    tokens = route_entity_tokens(query)
    extra_route_tokens = tokens[3:] if len(tokens) > 3 else []
    query_requires_object = route_object_marker_present(query)
    best_sentence = ""
    best_hits: List[str] = []
    best_has_relation = False
    best_has_object = False
    candidates: List[Dict[str, Any]] = []
    for sentence in route_analysis_units(item):
        lower = sentence.lower()
        token_hits = [token for token in tokens if token.lower() in lower]
        has_transit_relation = route_transit_relation_present(sentence)
        has_directional_relation = route_directional_relation_present(sentence)
        has_relation = any(route_marker_present(sentence, marker) for marker in ROUTE_RELATION_MARKERS) or has_directional_relation
        has_object = route_object_marker_present(sentence)
        has_extra_route_anchor = any(token in token_hits for token in extra_route_tokens)
        direct_sentence = bool(
            has_transit_relation
            and len(token_hits) >= 2
            and (has_object or not query_requires_object)
            and (not extra_route_tokens or has_extra_route_anchor)
        )
        if has_relation or token_hits:
            candidates.append(
                {
                    "sentence": sentence[:280],
                    "entity_hit_count": len(token_hits),
                    "has_relation_marker": has_relation,
                    "has_directional_relation": has_directional_relation,
                    "has_route_object_marker": has_object,
                    "has_extra_route_anchor": has_extra_route_anchor,
                    "entity_hits": token_hits,
                    "direct_sentence": direct_sentence,
                }
            )
        if direct_sentence and len(token_hits) >= len(best_hits):
            best_sentence = sentence
            best_hits = token_hits
            best_has_relation = True
            best_has_object = has_object
        elif has_relation and len(token_hits) > len(best_hits) and not best_sentence:
            best_sentence = sentence
            best_hits = token_hits
            best_has_relation = True
            best_has_object = has_object
        elif not best_sentence and token_hits:
            best_sentence = sentence
            best_hits = token_hits
            best_has_relation = has_relation
            best_has_object = has_object
    candidates = sorted(
        candidates,
        key=lambda candidate: (
            int(candidate.get("direct_sentence") or 0),
            int(candidate.get("entity_hit_count") or 0),
            int(candidate.get("has_relation_marker") or 0),
        ),
        reverse=True,
    )[:5]
    return {
        "direct_sentence": bool(best_has_relation and len(best_hits) >= 2 and (best_has_object or not query_requires_object)),
        "entity_hit_count": len(best_hits),
        "has_relation_marker": best_has_relation,
        "has_route_object_marker": best_has_object,
        "query_requires_route_object": query_requires_object,
        "entity_hits": best_hits,
        "sentence": best_sentence[:280],
        "candidates": candidates,
    }


def query_looks_route_directed(query: str) -> bool:
    return (
        any(route_marker_present(query, marker) for marker in ROUTE_RELATION_MARKERS)
        and len(route_entity_tokens(query)) >= 2
    )


def web_items(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [item for item in evidence if item.get("source_type") not in {"input_context", "computed"}]


def has_direct_web_evidence(evidence: List[Dict[str, Any]], evidence_mode: str) -> bool:
    mode = str(evidence_mode or "")
    for item in web_items(evidence):
        source_type = item.get("source_type")
        directness = int(item.get("directness_score") or 0)
        if mode == "route_fact":
            route_sentence = item.get("route_sentence") if isinstance(item.get("route_sentence"), dict) else {}
            if route_sentence.get("direct_sentence") and directness >= 2:
                return True
        elif mode in {"numeric_fact", "date_fact", "schedule_fact"}:
            structured_point_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
            evidence_contract_status = normalize_text(str(item.get("evidence_contract_status") or "")).lower()
            evidence_contract_role = normalize_text(str(item.get("evidence_contract_role") or "")).lower()
            if structured_point_status == "satisfied":
                return True
            if bool(item.get("evidence_page_ready")) and normalize_text(str(item.get("page_role") or "")).lower() == "evidence_page":
                return True
            if (
                source_type in {"official", "news"}
                and evidence_contract_status == "satisfied"
                and evidence_contract_role in {"structured_metric_table_page", "evidence_sentence_page"}
            ):
                return True
            if (
                source_type in {"official", "news"}
                and directness >= 3
                and evidence_contract_role in {"structured_metric_table_page", "evidence_sentence_page"}
                and evidence_contract_status != "failed"
            ):
                return True
        elif source_type in {"official", "news", "encyclopedia"} and directness >= 2:
            return True
    return False


def should_stop_querying_after_web_budget(
    claim_evidence: List[Dict[str, Any]],
    evidence_mode: str,
    source_intent: Optional[Dict[str, Any]],
    max_results_per_query: int,
) -> bool:
    if max_results_per_query <= 0:
        return True
    web_count = sum(1 for ev in claim_evidence if ev.get("source_type") not in {"input_context", "computed"})
    if web_count < max_results_per_query:
        return False
    mode = effective_evidence_mode(source_intent or {}, evidence_mode)
    if mode in {"numeric_fact", "date_fact", "schedule_fact", "route_fact"} and not has_direct_web_evidence(claim_evidence, mode):
        return False
    return True


def effective_evidence_mode(source_intent: Dict[str, Any], fallback_mode: str = "") -> str:
    mechanism_type = mechanism_type_from_intent(source_intent)
    mode = str(fallback_mode or source_intent.get("evidence_mode") or "")
    if mechanism_type == "relation_sentence":
        return "route_fact"
    if mechanism_type == "structured_numeric_authority":
        return "numeric_fact"
    if mechanism_type == "date_authority":
        return "date_fact"
    if mechanism_type == "event_result_page":
        return "event_result"
    if mechanism_type == "current_status_update":
        return mode or "entity_fact"
    return mode or "entity_fact"


def policy_mode_label(evidence_mode: str = "") -> str:
    mode = str(evidence_mode or "")
    if mode == "relation_sentence":
        return "route_fact"
    if mode == "structured_numeric_authority":
        return "numeric_fact"
    if mode == "date_authority":
        return "date_fact"
    if mode == "event_result_page":
        return "event_result"
    if mode == "current_status_update":
        return "entity_fact"
    return mode or "entity_fact"


def is_route_like_mode(mode: str) -> bool:
    normalized = policy_mode_label(mode)
    return normalized in {"route_fact", "relation_sentence"}


def is_structured_fact_mode(mode: str) -> bool:
    normalized = policy_mode_label(mode)
    return normalized in {"numeric_fact", "date_fact", "schedule_fact", "structured_numeric_authority", "date_authority"}


def is_event_like_mode(mode: str) -> bool:
    normalized = policy_mode_label(mode)
    return normalized in {"event_result", "event_result_page"}


def should_use_playwright_fallback(
    claim_evidence: List[Dict[str, Any]],
    evidence_mode: str,
    centrality: str,
    source_intent: Dict[str, Any],
) -> tuple[bool, str]:
    mode = effective_evidence_mode(source_intent, evidence_mode)
    central = str(centrality or "supporting")
    if has_direct_web_evidence(claim_evidence, mode):
        return False, "skip_playwright_direct_evidence_exists"
    if central == "peripheral":
        return False, "skip_playwright_peripheral_claim"
    if mode == "route_fact":
        return True, "use_playwright_route_fact"
    if mode in {"numeric_fact", "date_fact", "schedule_fact"}:
        if central in {"core", "supporting"} or source_intent.get("_is_retry"):
            return True, "use_playwright_structured_fact"
        return False, "skip_playwright_noncore_structured_fact"
    if mode == "event_result":
        if central == "core" and not web_items(claim_evidence):
            return True, "use_playwright_core_event_result"
        return False, "skip_playwright_noncore_or_has_web"
    if mode == "policy_fact":
        if central == "core" and not web_items(claim_evidence):
            return True, "use_playwright_core_no_web"
        return False, "skip_playwright_noncore_or_has_web"
    if mode == "entity_fact":
        if central in {"core", "supporting"} and not web_items(claim_evidence):
            return True, "use_playwright_entity_fact_no_web"
        return False, "skip_playwright_entity_fact_has_web"
    return False, "skip_playwright_mode_not_suitable"


def should_keep_web_evidence(query: str, item: Dict[str, Any]) -> bool:
    keep, _ = web_evidence_filter_reason(query, item)
    return keep


CLAIM_ALIGNED_FACT_PAGE_TYPES = {
    "news_article",
    "event_detail",
    "result_page",
    "calendar_page",
    "current_status_page",
    "mixed_page",
    "quote_page",
    "historical_table",
    "official_notice",
}
CLAIM_ALIGNED_FACT_LOW_REASONS = {
    "low_official_relevance",
    "official_structured_alignment_weak",
    "low_strong_source_relevance",
    "weak_source_low_relevance",
    "low_relevance",
    "source_quality_bad",
    "structured_noise_review_candidate",
}
PREFILTER_RESCUE_ALLOWED_MODES = {"numeric_fact", "date_fact", "schedule_fact", "event_result", "entity_fact"}
PREFILTER_RESCUE_ALLOWED_SOURCE_TYPES = {"official", "news", "encyclopedia"}
PREFILTER_RESCUE_NEAR_MISS_REASONS = CLAIM_ALIGNED_FACT_LOW_REASONS | {
    "filtered_low_claim_anchor",
    "filtered_page_shape_mismatch",
    "filtered_low_source_relevance",
    "filtered_utility_drop_conflict",
    "structured_noise_value_without_context",
    "structured_noise_date_window_mismatch",
}
PREFILTER_RESCUE_HARD_FILTER_REASONS = {
    "site_domain_mismatch",
    "sitemap_generic_landing_page",
    "search_engine_result_page",
    "temporal_mismatch",
    "event_window_mismatch",
    "structured_noise_high_penalty",
    "structured_noise_no_entity_weak_source",
    "official_structured_discovery_stub",
    "route_retention_policy_not_satisfied",
    "route_weak_no_direct_sentence",
    "route_noise_no_relation_single_entity",
}
FACT_PAGE_KEEP_REVIEW_ALLOWED_MODES = {"numeric_fact", "date_fact", "schedule_fact", "event_result", "entity_fact"}
FACT_PAGE_KEEP_REVIEW_ALLOWED_SOURCE_TYPES = {"official", "news", "encyclopedia", "unknown", "finance"}
FACT_PAGE_KEEP_REVIEW_NEAR_MISS_REASONS = CLAIM_ALIGNED_FACT_LOW_REASONS | {
    "filtered_low_claim_anchor",
    "filtered_page_shape_mismatch",
    "filtered_low_source_relevance",
    "filtered_utility_drop_conflict",
}
FACT_PAGE_KEEP_REVIEW_HARD_DROP_REASONS = PREFILTER_RESCUE_HARD_FILTER_REASONS | {
    "search_engine_result_page",
    "landing_page",
    "hard_noise_page",
}

STRUCTURED_REVIEW_PAGE_TYPES = {
    "quote_page",
    "historical_table",
    "official_notice",
    "calendar_page",
    "result_page",
    "event_detail",
    "current_status_page",
    "mixed_page",
}


def claim_program_from_claim_item(claim_item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(claim_item, dict):
        return {}
    if isinstance(claim_item.get("evidence_need_program"), dict):
        return claim_item.get("evidence_need_program") or {}
    source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
    return source_intent.get("evidence_need_program") if isinstance(source_intent.get("evidence_need_program"), dict) else {}


def program_false_friend_hits_for_item(item: Dict[str, Any], claim_item: Optional[Dict[str, Any]]) -> List[str]:
    program = claim_program_from_claim_item(claim_item)
    if not program:
        return []
    text = normalize_text(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')}").lower()
    source_intent = claim_item.get("source_intent") if isinstance(claim_item, dict) and isinstance(claim_item.get("source_intent"), dict) else {}
    evidence_mode = str(source_intent.get("evidence_mode") or "")
    hits: List[str] = []
    if evidence_mode == "numeric_fact" and any(term in text for term in ["analysis", "commentary", "走势", "解读"]) and not re.search(r"\d", text):
        hits.append("analysis_without_same_numeric_slot")
    if evidence_mode in {"date_fact", "schedule_fact"} and any(term in text for term in ["history", "historical", "旧", "往年"]) and not re.search(r"(20\d{2}|\d{1,2}月\d{1,2}日|today|current)", text):
        hits.append("historical_without_same_time_window")
    if evidence_mode == "event_result" and any(term in text for term in ["preview", "赛前", "odds", "history", "交手"]):
        hits.append("event_context_without_final_result")
    if (evidence_mode == "route_fact" or str(source_intent.get("evidence_target") or "") == "route_relation") and any(term in text for term in ["map", "路线图", "示意图", "importance", "strategic", "战略"]) and not any(term in text for term in ["must pass", "only route", "必经", "唯一", "经过", "经由", "绕开"]):
        hits.append("route_background_without_direct_relation")
    if evidence_mode == "policy_fact" and any(term in text for term in ["analysis", "commentary", "speculation", "猜测", "解读"]):
        hits.append("policy_commentary_without_official_status")
    return dedupe_keep_order(hits)[:3]


def claim_anchor_bucket_hits(query: str, item: Dict[str, Any], evidence_mode: str, claim_item: Optional[Dict[str, Any]] = None) -> List[str]:
    text = normalize_text(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('detail', '')}").lower()
    query_text = normalize_text(query).lower()
    hits: List[str] = []
    if int(item.get("entity_match_count") or 0) >= 1 or (
        item.get("task_card_must_match_hits") if isinstance(item.get("task_card_must_match_hits"), list) else []
    ):
        hits.append("entity")
    query_has_date = bool(re.search(r"(20\d{2}|[0-1]?\d月|[0-3]?\d日|\bapril\b|\bmay\b|\bmar\b|\bjan\b|\bfeb\b)", query_text))
    text_has_date = bool(re.search(r"(20\d{2}|[0-1]?\d月|[0-3]?\d日|\bapril\b|\bmay\b|\bmar\b|\bjan\b|\bfeb\b|today|current)", text))
    if query_has_date and (text_has_date or int(item.get("temporal_score") or 0) >= 0 or int(item.get("event_window_score") or 0) >= 0):
        hits.append("time")
    mode_markers = {
        "schedule_fact": ["休市", "开盘", "交易", "高开", "market", "calendar", "trading", "open"],
        "event_result": ["战胜", "比分", "赛果", "result", "won", "beat", "winner", "finished"],
        "numeric_fact": ["汇率", "中间价", "牌价", "报价", "price", "rate", "buying", "selling", "基点"],
        "date_fact": ["公布", "发布", "日期", "时间", "announce", "announced", "release", "date", "time"],
        "entity_fact": ["属于", "担任", "提交", "宣布", "确认", "named", "announced", "confirmed", "filed", "submitted"],
    }
    markers = mode_markers.get(str(evidence_mode or ""), [])
    if markers and any(marker in text for marker in markers):
        hits.append("event")
    program = claim_program_from_claim_item(claim_item)
    if program:
        decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
        bucket_terms = decision_slots.get("anchor_terms_by_bucket") if isinstance(decision_slots.get("anchor_terms_by_bucket"), dict) else {}
        for bucket, terms in bucket_terms.items():
            if not isinstance(terms, list) or not terms:
                continue
            normalized_terms = [normalize_text(str(term)).lower() for term in terms if normalize_text(str(term))]
            if normalized_terms and any(term in text for term in normalized_terms):
                hits.append(bucket)
    return dedupe_keep_order(hits)


def claim_aligned_page_shape_ok(item: Dict[str, Any]) -> bool:
    page_type = str(item.get("page_utility_page_type") or "")
    if page_type in {"landing_page", "search_result_page"}:
        return False
    source_quality_reasons = item.get("source_quality_reasons") if isinstance(item.get("source_quality_reasons"), list) else []
    if any(reason in {"search_engine_result_page", "hard_noise_page"} for reason in source_quality_reasons):
        return False
    return True


def fact_like_keep_review_allowed(claim_item: Optional[Dict[str, Any]], evidence_mode: str) -> bool:
    if str(evidence_mode or "") not in FACT_PAGE_KEEP_REVIEW_ALLOWED_MODES:
        return False
    if not isinstance(claim_item, dict):
        return False
    centrality = str(claim_item.get("centrality") or "")
    if centrality == "core":
        return True
    return centrality == "supporting" and str(evidence_mode or "") in {"numeric_fact", "date_fact", "schedule_fact", "event_result", "entity_fact"}


CORE_SECOND_PASS_ALLOWED_MODES = {"numeric_fact", "date_fact", "schedule_fact", "route_fact", "event_result", "entity_fact"}
CORE_SECOND_PASS_ALLOWED_PAGE_TYPES = {
    "result_page",
    "event_detail",
    "calendar_page",
    "quote_page",
    "historical_table",
    "official_notice",
    "current_status_page",
    "mixed_page",
    "route_analysis_page",
    "route_passage_page",
}
CORE_SECOND_PASS_STRONG_PAGE_TYPES = {
    "result_page",
    "event_detail",
    "calendar_page",
    "quote_page",
    "historical_table",
    "official_notice",
}
CORE_SECOND_PASS_ROUTE_PAGE_TYPES = {
    "route_analysis_page",
    "route_passage_page",
    "mixed_page",
}
CORE_SECOND_PASS_ALLOWED_SOURCE_TYPES = {"official", "news", "encyclopedia", "unknown"}
CORE_SECOND_PASS_STRUCTURED_SOURCE_TYPES = CORE_SECOND_PASS_ALLOWED_SOURCE_TYPES | {"finance"}
DETAIL_RESCUE_ALLOWED_PAGE_TYPES = {
    "official_notice",
    "calendar_page",
    "historical_table",
    "result_page",
    "event_detail",
    "current_status_page",
}


def core_second_pass_keep_review_allowed(
    claim_item: Optional[Dict[str, Any]],
    evidence_mode: str,
    raw_results_so_far: int,
    kept_web_so_far: int,
) -> bool:
    if str(evidence_mode or "") not in CORE_SECOND_PASS_ALLOWED_MODES:
        return False
    if not isinstance(claim_item, dict):
        return False
    centrality = str(claim_item.get("centrality") or "")
    priority = str(claim_item.get("_claim_budget_priority") or "")
    mode = policy_mode_label(evidence_mode)
    allowed = centrality == "core" and priority == "core_critical"
    if not allowed and mode == "route_fact":
        allowed = centrality == "supporting" and priority == "supporting_high_risk"
    if not allowed:
        return False
    return raw_results_so_far > 0 and kept_web_so_far <= 0


def core_second_pass_source_type_allowed(source_type: str, evidence_mode: str) -> bool:
    mode = policy_mode_label(evidence_mode)
    if mode in {"numeric_fact", "date_fact", "schedule_fact"}:
        return source_type in CORE_SECOND_PASS_STRUCTURED_SOURCE_TYPES
    return source_type in CORE_SECOND_PASS_ALLOWED_SOURCE_TYPES


def core_second_pass_signal_summary(
    query: str,
    item: Dict[str, Any],
    evidence_mode: str,
    claim_item: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    signal = fact_slot_signal_summary(query, item, evidence_mode, claim_item)
    page_type = str(item.get("page_utility_page_type") or "")
    route_sentence = item.get("route_sentence") if isinstance(item.get("route_sentence"), dict) else {}
    page_components = item.get("page_utility_components") if isinstance(item.get("page_utility_components"), dict) else {}
    relation_evidence = int(page_components.get("relation_evidence") or 0)
    answerability = int(page_components.get("answerability") or 0)
    entity_grounding = int(page_components.get("entity_grounding") or 0)
    structural_extractability = int(page_components.get("structural_extractability") or 0)
    has_answer_candidates = bool(item.get("answer_candidates")) and isinstance(item.get("answer_candidates"), list)
    route_signal = (
        page_type in CORE_SECOND_PASS_ROUTE_PAGE_TYPES
        and (
            relation_evidence >= 1
            or answerability >= 1
            or bool(route_sentence.get("direct_sentence"))
            or bool(route_sentence.get("has_relation_marker"))
            or bool(route_sentence.get("has_route_object_marker"))
        )
        and entity_grounding >= 1
        and structural_extractability >= 1
    )
    signal.update(
        {
            "page_type": page_type,
            "strong_page_type": page_type in CORE_SECOND_PASS_STRONG_PAGE_TYPES,
            "route_signal": route_signal,
            "route_relation_evidence": relation_evidence,
            "route_answerability": answerability,
            "route_entity_grounding": entity_grounding,
            "route_structural_extractability": structural_extractability,
            "has_answer_candidates": has_answer_candidates,
        }
    )
    return signal


def maybe_promote_core_second_pass_keep_review(
    query: str,
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
    claim_item: Optional[Dict[str, Any]],
    raw_results_so_far: int,
    kept_web_so_far: int,
) -> tuple[bool, str]:
    if not core_second_pass_keep_review_allowed(claim_item, evidence_mode, raw_results_so_far, kept_web_so_far):
        return False, filter_reason
    item["second_pass_keep_review_used"] = True
    item["second_pass_keep_review_reason"] = filter_reason
    mode = policy_mode_label(evidence_mode)
    source_type = str(item.get("source_type") or "")
    signal = core_second_pass_signal_summary(query, item, mode, claim_item)
    if not core_second_pass_source_type_allowed(source_type, mode):
        item["core_keep_review_block_reason"] = "source_type_not_allowed"
        item["page_keep_review_state"] = "core_near_miss_still_rejected"
        return False, filter_reason
    allow_structured_noise_exception = (
        filter_reason == "structured_noise_high_penalty"
        and mode in {"numeric_fact", "date_fact", "schedule_fact"}
        and bool(signal.get("strong_page_type"))
        and bool(signal.get("subject_time_hit"))
        and bool(signal.get("metric_or_status_hit"))
        and (
            bool(signal.get("has_answer_candidates"))
            or int(signal.get("answer_quality") or 0) >= 4
            or int(signal.get("directness") or 0) >= 2
        )
    )
    if ((filter_reason in FACT_PAGE_KEEP_REVIEW_HARD_DROP_REASONS) and not allow_structured_noise_exception) or not claim_aligned_page_shape_ok(item):
        item["core_keep_review_block_reason"] = "page_shape_hard_drop"
        item["page_keep_review_state"] = "core_near_miss_still_rejected"
        return False, filter_reason
    if str(item.get("page_utility_llm_decision") or "") == "drop":
        item["core_keep_review_block_reason"] = "utility_drop_decision"
        item["page_keep_review_state"] = "core_near_miss_still_rejected"
        return False, filter_reason
    page_type = str(item.get("page_utility_page_type") or "")
    if page_type not in CORE_SECOND_PASS_ALLOWED_PAGE_TYPES:
        item["core_keep_review_block_reason"] = "page_type_not_decision_useful"
        item["page_keep_review_state"] = "core_near_miss_still_rejected"
        return False, filter_reason
    anchor_hits = signal.get("anchor_hits") if isinstance(signal.get("anchor_hits"), list) else claim_anchor_bucket_hits(query, item, mode, claim_item)
    anchor_hit_set = {str(hit) for hit in anchor_hits if str(hit)}
    subject_like = bool(anchor_hit_set & {"subject", "entity", "actor"})
    time_like = bool(anchor_hit_set & {"time", "time_scope"})
    fact_like = bool(anchor_hit_set & {"event", "status", "metric", "metric_or_relation", "status_or_result"})
    route_mode = is_route_like_mode(mode)
    if route_mode:
        if not subject_like or not bool(signal.get("route_signal")):
            item["core_keep_review_block_reason"] = "anchor_slots_not_closed"
            item["page_keep_review_state"] = "core_near_miss_still_rejected"
            return False, filter_reason
    elif len(anchor_hits) < 2 or not ((subject_like and time_like) or (subject_like and fact_like) or (time_like and fact_like)):
        item["core_keep_review_block_reason"] = "anchor_slots_not_closed"
        item["page_keep_review_state"] = "core_near_miss_still_rejected"
        return False, filter_reason
    page_retention_score = int(signal.get("page_retention_score") or item.get("page_retention_score") or 0)
    page_utility_score = int(signal.get("page_utility_score") or item.get("page_utility_score") or 0)
    directness = int(signal.get("directness") or item.get("directness_score") or 0)
    relevance = int(item.get("relevance_score") or 0)
    entity_hits = int(item.get("entity_match_count") or 0)
    answer_quality = int(signal.get("answer_quality") or item.get("answer_candidate_quality_score") or 0)
    evidence_contract_status = normalize_text(str(item.get("evidence_contract_status") or "")).lower()
    structured_point_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
    strong_page_type = bool(signal.get("strong_page_type"))
    has_answer_candidates = bool(signal.get("has_answer_candidates"))
    promotable_signal = (
        directness >= (1 if strong_page_type else 2)
        or answer_quality >= (4 if strong_page_type else 5)
        or evidence_contract_status in {"partial", "satisfied"}
        or structured_point_status in {"partial", "satisfied"}
        or (has_answer_candidates and strong_page_type and answer_quality >= 3)
        or (route_mode and bool(signal.get("route_signal")))
    )
    min_retention_score = 34
    min_utility_score = 34
    if strong_page_type:
        min_retention_score = 30
        min_utility_score = 30
    if route_mode and bool(signal.get("route_signal")):
        min_retention_score = 32
        min_utility_score = 30
    if page_retention_score < min_retention_score or page_utility_score < min_utility_score or (relevance < 1 and entity_hits < 1):
        item["core_keep_review_block_reason"] = "page_signal_too_weak"
        item["page_keep_review_state"] = "core_near_miss_still_rejected"
        return False, filter_reason
    if not promotable_signal:
        item["core_keep_review_block_reason"] = "candidate_signal_too_weak"
        item["page_keep_review_state"] = "core_near_miss_still_rejected"
        return False, filter_reason
    item["page_keep_review_state"] = "core_near_miss_kept"
    item["page_keep_review_reason"] = filter_reason
    item["core_keep_review_profile"] = (
        "route_relation_near_miss"
        if route_mode
        else ("strong_fact_page_near_miss" if strong_page_type else "general_fact_page_near_miss")
    )
    item["kept_progress_from_raw"] = True
    item["kept_candidate_source_type"] = source_type
    item["second_pass_keep_recovered_count"] = 1
    item["program_used_for_retention"] = True
    item["soft_keep_anchor_buckets"] = anchor_hits
    item["program_anchor_buckets"] = list(anchor_hits or [])[:6]
    item["program_false_friend_hits"] = program_false_friend_hits_for_item(item, claim_item)
    return True, "core_second_pass_keep_review"


def should_allow_playwright_detail_rescue(
    item: Dict[str, Any],
    claim_item: Optional[Dict[str, Any]],
    evidence_mode: str,
    used_playwright_detail_rescues: int,
) -> tuple[bool, str]:
    if used_playwright_detail_rescues >= 1:
        return False, "detail_rescue_budget_exhausted"
    centrality = str((claim_item or {}).get("centrality") or "supporting")
    source_intent = (claim_item or {}).get("source_intent") if isinstance((claim_item or {}).get("source_intent"), dict) else {}
    if not playwright_rescue_mode_allowed(evidence_mode, centrality, source_intent):
        return False, "detail_rescue_policy_not_allowed"
    if not claim_aligned_page_shape_ok(item):
        return False, "detail_rescue_page_shape_not_allowed"
    if str(item.get("source_quality_label") or "") == "bad":
        return False, "detail_rescue_bad_source_quality"
    page_type = str(item.get("page_utility_page_type") or "")
    if page_type not in DETAIL_RESCUE_ALLOWED_PAGE_TYPES:
        return False, "detail_rescue_page_type_not_allowed"
    return True, ""


def finalize_detail_rescue_effect(stats: Dict[str, Any], item: Dict[str, Any], keep_item: bool) -> None:
    if not item.get("_detail_rescue_playwright_used"):
        return
    candidate_gain = len(item.get("answer_candidates") or []) if isinstance(item.get("answer_candidates"), list) else 0
    page_type = str(item.get("page_utility_page_type") or "") or "detail_page"
    stats["detail_rescue_target_page_type"] = page_type
    if candidate_gain > 0:
        stats["detail_rescue_roi_state"] = "detail_candidates_recovered"
        stats["detail_rescue_effect_delta"] = {"candidate_gain": candidate_gain, "kept_gain": 1 if keep_item else 0}
        stats["rescue_success_gate"] = "detail_candidates_recovered"
        stats["rescue_progress_delta"] = {"raw_delta": 0, "kept_delta": 1 if keep_item else 0, "stage": "detail_candidates_recovered"}
        stats["rescue_roi_state"] = "detail_candidates_recovered"
        return
    if keep_item:
        stats["detail_rescue_roi_state"] = "detail_page_kept_after_rescue"
        stats["detail_rescue_effect_delta"] = {"candidate_gain": 0, "kept_gain": 1}
        stats["rescue_roi_state"] = "detail_page_kept_after_rescue"
        return
    stats["detail_rescue_failure_reason"] = "detail_rescue_content_loaded_but_not_extractable"


def claim_needs_opening_slot(claim_item: Optional[Dict[str, Any]], evidence_mode: str, query: str = "") -> bool:
    if str(evidence_mode or "") != "numeric_fact":
        return False
    program = claim_program_from_claim_item(claim_item)
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    direct_need = program.get("direct_evidence_need") if isinstance(program.get("direct_evidence_need"), dict) else {}
    combined = " ".join(
        normalize_text(str(part or ""))
        for part in [
            query,
            claim_item.get("claim") if isinstance(claim_item, dict) else "",
            program.get("normalized_assertion") if isinstance(program, dict) else "",
            decision_slots.get("object") if isinstance(decision_slots, dict) else "",
            decision_slots.get("status_or_result") if isinstance(decision_slots, dict) else "",
            direct_need.get("must_answer") if isinstance(direct_need, dict) else "",
        ]
        if normalize_text(str(part or ""))
    )
    return bool(re.search(r"(开盘|开市|opening|opened)", combined, flags=re.I))


def fact_slot_signal_summary(
    query: str,
    item: Dict[str, Any],
    evidence_mode: str,
    claim_item: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    anchor_hits = claim_anchor_bucket_hits(query, item, evidence_mode, claim_item)
    answer_quality = answer_candidate_quality_score(item)
    page_retention_score = int(item.get("page_retention_score") or 0)
    page_utility_score = int(item.get("page_utility_score") or 0)
    directness = int(item.get("directness_score") or 0)
    evidence_contract_status = normalize_text(str(item.get("evidence_contract_status") or "")).lower()
    structured_point_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
    text = normalize_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("snippet") or ""),
                str(item.get("detail") or ""),
                " ".join(
                    str(candidate.get("sentence") or "")
                    for candidate in (item.get("answer_candidates") or [])
                    if isinstance(candidate, dict)
                ),
            ]
        )
    )
    needs_opening = claim_needs_opening_slot(claim_item, evidence_mode, query)
    has_opening = bool(re.search(r"(开盘|开市|高开|opening|opened|open price|open gain)", text, flags=re.I))
    has_intraday = bool(re.search(r"(盘中|一度|曾|瞬时|最高|新高|intraday|at one point|session high|hit as high as)", text, flags=re.I))
    has_close = bool(re.search(r"(收盘|尾盘|close|closed)", text, flags=re.I))
    text_has_current_marker = bool(re.search(r"(今天|今日|current|latest|实时|live|now)", text, flags=re.I))
    entity_like_mode = policy_mode_label(evidence_mode) == "entity_fact"
    subject_time_hit = "entity" in anchor_hits and (
        entity_like_mode
        or "time" in anchor_hits
        or text_has_current_marker
        or (needs_opening and directness >= 2)
    )
    metric_or_status_hit = (
        any(bucket in anchor_hits for bucket in {"numeric", "event", "status"})
        or (entity_like_mode and len(anchor_hits) >= 2)
        or evidence_contract_status in {"partial", "satisfied"}
        or structured_point_status in {"partial", "satisfied"}
        or answer_quality >= 5
        or directness >= 3
        or (needs_opening and has_opening)
    )
    promotable_signal = (
        answer_quality >= 4
        or directness >= 3
        or page_retention_score >= 30
        or page_utility_score >= 28
        or evidence_contract_status in {"partial", "satisfied"}
        or structured_point_status in {"partial", "satisfied"}
        or (needs_opening and has_opening and directness >= 2)
    )
    return {
        "anchor_hits": anchor_hits,
        "answer_quality": answer_quality,
        "directness": directness,
        "page_retention_score": page_retention_score,
        "page_utility_score": page_utility_score,
        "subject_time_hit": subject_time_hit,
        "metric_or_status_hit": metric_or_status_hit,
        "promotable_signal": promotable_signal,
        "needs_opening": needs_opening,
        "has_opening": has_opening,
        "has_intraday": has_intraday,
        "has_close": has_close,
    }


def apply_fact_page_keep_review_annotations(
    item: Dict[str, Any],
    profile: str,
    filter_reason: str,
    signal: Dict[str, Any],
) -> None:
    item["filter_decision_profile"] = profile
    item["candidate_strength_before_keep"] = int(signal.get("answer_quality") or 0)
    if profile.startswith("recoverable"):
        item["recoverable_filter_reason"] = filter_reason
    elif profile.startswith("hard_drop"):
        item["hard_drop_reason"] = filter_reason


def maybe_promote_fact_page_keep_review(
    query: str,
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
    claim_item: Optional[Dict[str, Any]] = None,
) -> tuple[bool, str]:
    if not fact_like_keep_review_allowed(claim_item, evidence_mode):
        return False, filter_reason
    source_type = str(item.get("source_type") or "")
    if source_type not in FACT_PAGE_KEEP_REVIEW_ALLOWED_SOURCE_TYPES:
        return False, filter_reason
    if filter_reason in FACT_PAGE_KEEP_REVIEW_HARD_DROP_REASONS or not claim_aligned_page_shape_ok(item):
        apply_fact_page_keep_review_annotations(item, "hard_drop", filter_reason, {"answer_quality": answer_candidate_quality_score(item)})
        return False, filter_reason
    if filter_reason not in FACT_PAGE_KEEP_REVIEW_NEAR_MISS_REASONS and filter_reason != "source_quality_bad":
        return False, filter_reason
    if str(item.get("page_utility_llm_decision") or "") == "drop":
        apply_fact_page_keep_review_annotations(item, "hard_drop", "utility_drop_decision", {"answer_quality": answer_candidate_quality_score(item)})
        return False, filter_reason
    signal = fact_slot_signal_summary(query, item, evidence_mode, claim_item)
    if not signal.get("subject_time_hit") or not signal.get("metric_or_status_hit"):
        apply_fact_page_keep_review_annotations(item, "low_signal_drop", filter_reason, signal)
        return False, filter_reason
    if signal.get("needs_opening") and (signal.get("has_intraday") or signal.get("has_close")) and not signal.get("has_opening"):
        apply_fact_page_keep_review_annotations(item, "recoverable_opening_slot_mismatch", "opening_slot_mismatch", signal)
        return False, filter_reason
    if not signal.get("promotable_signal"):
        apply_fact_page_keep_review_annotations(item, "recoverable_but_too_weak", filter_reason, signal)
        return False, filter_reason
    apply_fact_page_keep_review_annotations(item, "recoverable_near_miss_promoted", filter_reason, signal)
    item["readiness_promotion_used"] = True
    item["readiness_promotion_source"] = "fact_page_keep_review"
    item["page_keep_review_state"] = "kept_review"
    item["page_keep_review_reason"] = filter_reason
    item["kept_progress_from_raw"] = True
    item["kept_candidate_source_type"] = str(item.get("source_type") or "")
    item["soft_keep_anchor_buckets"] = claim_anchor_bucket_hits(query, item, evidence_mode, claim_item)
    item["program_anchor_buckets"] = list(item.get("soft_keep_anchor_buckets") or [])[:6]
    item["program_false_friend_hits"] = program_false_friend_hits_for_item(item, claim_item)
    item["program_used_for_retention"] = True
    return True, "fact_page_keep_review"


def remap_claim_aligned_filter_reason(default_reason: str, query: str, item: Dict[str, Any], evidence_mode: str) -> str:
    if default_reason not in CLAIM_ALIGNED_FACT_LOW_REASONS:
        return default_reason
    source_type = str(item.get("source_type") or "")
    if source_type not in {"news", "official", "encyclopedia"}:
        return default_reason
    if str(evidence_mode or "") not in {"schedule_fact", "event_result", "numeric_fact", "date_fact", "entity_fact"}:
        return default_reason
    if not claim_aligned_page_shape_ok(item):
        return "filtered_page_shape_mismatch"
    anchor_hits = claim_anchor_bucket_hits(query, item, evidence_mode)
    if str(item.get("page_utility_llm_decision") or "") == "drop" and len(anchor_hits) >= 2:
        return "filtered_utility_drop_conflict"
    if len(anchor_hits) < 2:
        return "filtered_low_claim_anchor"
    return "filtered_low_source_relevance"


def should_soft_keep_claim_aligned_fact_item(
    query: str,
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
    claim_item: Optional[Dict[str, Any]] = None,
) -> bool:
    if filter_reason not in CLAIM_ALIGNED_FACT_LOW_REASONS | {
        "filtered_low_claim_anchor",
        "filtered_page_shape_mismatch",
        "filtered_low_source_relevance",
        "filtered_utility_drop_conflict",
    }:
        return False
    if str(evidence_mode or "") not in {"schedule_fact", "event_result", "numeric_fact", "date_fact", "entity_fact"}:
        return False
    source_type = str(item.get("source_type") or "")
    if source_type not in {"news", "official", "encyclopedia"}:
        return False
    if not claim_aligned_page_shape_ok(item):
        return False
    if str(item.get("page_utility_llm_decision") or "") == "drop":
        return False
    if len(claim_anchor_bucket_hits(query, item, evidence_mode, claim_item)) < 2:
        return False
    if int(item.get("page_retention_score") or 0) < 48 and int(item.get("page_utility_score") or 0) < 45:
        return False
    if int(item.get("relevance_score") or 0) < 1 and int(item.get("entity_match_count") or 0) < 1:
        return False
    return True


def should_try_prefilter_candidate_rescue(
    query: str,
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
    claim_item: Optional[Dict[str, Any]] = None,
) -> bool:
    if str(evidence_mode or "") not in PREFILTER_RESCUE_ALLOWED_MODES:
        return False
    if str(item.get("source_type") or "") not in PREFILTER_RESCUE_ALLOWED_SOURCE_TYPES:
        return False
    if filter_reason in PREFILTER_RESCUE_HARD_FILTER_REASONS:
        return False
    if filter_reason not in PREFILTER_RESCUE_NEAR_MISS_REASONS:
        return False
    if not claim_aligned_page_shape_ok(item):
        return False
    if str(item.get("page_utility_llm_decision") or "") == "drop":
        return False
    if item.get("source_quality_label") == "bad":
        source_quality_reasons = item.get("source_quality_reasons") if isinstance(item.get("source_quality_reasons"), list) else []
        if "hard_noise_page" in source_quality_reasons:
            return False
    anchor_hits = claim_anchor_bucket_hits(query, item, evidence_mode, claim_item)
    evidence_contract_status = normalize_text(str(item.get("evidence_contract_status") or "")).lower()
    structured_point_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
    answer_quality = answer_candidate_quality_score(item)
    has_answer_candidates = bool(item.get("answer_candidates")) and isinstance(item.get("answer_candidates"), list)
    return (
        has_answer_candidates
        and answer_quality >= 6
        and (
            len(anchor_hits) >= 2
            or evidence_contract_status in {"partial", "satisfied"}
            or structured_point_status in {"partial", "satisfied"}
        )
    )


def maybe_promote_prefilter_candidate_rescue(
    query: str,
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
    claim_item: Optional[Dict[str, Any]] = None,
) -> tuple[bool, str]:
    if not should_try_prefilter_candidate_rescue(query, item, filter_reason, evidence_mode, claim_item):
        return False, filter_reason
    if not item.get("direct_candidate_rescue_used"):
        candidates = item.get("answer_candidates") if isinstance(item.get("answer_candidates"), list) else []
        best_candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        item["direct_candidate_rescue_used"] = True
        item["direct_candidate_rescue_source"] = str(best_candidate.get("field") or "candidate")
    item["rescue_promoted_from_filter"] = True
    item["direct_candidate_rescue_stage"] = "pre_filter"
    item["direct_candidate_rescue_filter_reason"] = filter_reason
    item["soft_keep_anchor_buckets"] = claim_anchor_bucket_hits(query, item, evidence_mode, claim_item)
    item["program_anchor_buckets"] = list(item.get("soft_keep_anchor_buckets") or [])[:6]
    item["program_false_friend_hits"] = program_false_friend_hits_for_item(item, claim_item)
    item["program_used_for_retention"] = True
    return True, "candidate_rescued_before_filter"


def annotate_soft_kept_claim_aligned_item(
    item: Dict[str, Any],
    query: str,
    evidence_mode: str,
    original_filter_reason: str,
    claim_item: Optional[Dict[str, Any]] = None,
) -> None:
    item["kept_by_soft_claim_alignment"] = True
    item["soft_keep_anchor_buckets"] = claim_anchor_bucket_hits(query, item, evidence_mode, claim_item)
    item["soft_keep_original_filter_reason"] = original_filter_reason
    item["program_anchor_buckets"] = list(item.get("soft_keep_anchor_buckets") or [])[:6]
    item["program_false_friend_hits"] = program_false_friend_hits_for_item(item, claim_item)
    item["program_used_for_retention"] = True


def annotate_soft_kept_structured_metric_item(
    item: Dict[str, Any],
    query: str,
    evidence_mode: str,
    original_filter_reason: str,
    claim_item: Optional[Dict[str, Any]] = None,
) -> None:
    item["page_keep_review_state"] = "kept_review"
    item["page_keep_review_reason"] = original_filter_reason
    item["kept_progress_from_raw"] = True
    item["kept_candidate_source_type"] = str(item.get("source_type") or "")
    item["soft_keep_anchor_buckets"] = claim_anchor_bucket_hits(query, item, evidence_mode, claim_item)
    item["program_anchor_buckets"] = list(item.get("soft_keep_anchor_buckets") or [])[:6]
    item["program_false_friend_hits"] = program_false_friend_hits_for_item(item, claim_item)
    item["program_used_for_retention"] = True


KEY_EVIDENCE_KEEP_PAGE_TYPES = {
    "result_page",
    "event_detail",
    "calendar_page",
    "quote_page",
    "historical_table",
    "official_notice",
    "mixed_page",
    "current_status_page",
}


def should_soft_keep_key_evidence_page(
    query: str,
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
    claim_item: Optional[Dict[str, Any]] = None,
) -> bool:
    mode = policy_mode_label(evidence_mode)
    if mode not in {"numeric_fact", "date_fact", "schedule_fact", "route_fact", "event_result"}:
        return False
    if filter_reason in {
        "site_domain_mismatch",
        "search_engine_result_page",
        "sitemap_generic_landing_page",
        "official_structured_discovery_stub",
    }:
        return False
    source_type = str(item.get("source_type") or "")
    if source_type not in {"official", "news", "encyclopedia"}:
        return False
    if str(item.get("page_utility_llm_decision") or "") == "drop":
        return False
    claim_item = claim_item if isinstance(claim_item, dict) else {}
    task_card = claim_item.get("evidence_task_card") if isinstance(claim_item.get("evidence_task_card"), dict) else {}
    centrality = str(claim_item.get("centrality") or "supporting")
    priority_label = str(task_card.get("priority_label") or "normal")
    page_type = str(item.get("page_utility_page_type") or "")
    if page_type not in KEY_EVIDENCE_KEEP_PAGE_TYPES:
        return False
    page_retention_score = int(item.get("page_retention_score") or 0)
    page_utility_score = int(item.get("page_utility_score") or 0)
    directness = int(item.get("directness_score") or 0)
    relevance = int(item.get("relevance_score") or 0)
    entity_hits = int(item.get("entity_match_count") or 0)
    answer_quality = int(item.get("answer_candidate_quality_score") or 0)
    anchor_hits = claim_anchor_bucket_hits(query, item, mode, claim_item)
    anchor_hit_set = {str(hit) for hit in anchor_hits if str(hit)}
    subject_like = bool(anchor_hit_set & {"subject", "entity", "actor"})
    time_like = bool(anchor_hit_set & {"time", "time_scope"})
    fact_like = bool(anchor_hit_set & {"event", "status", "metric", "metric_or_relation", "status_or_result"})
    if len(anchor_hits) < 2:
        return False
    if not ((subject_like and time_like) or (subject_like and fact_like) or (time_like and fact_like)):
        return False
    if centrality == "core" or priority_label in {"critical", "high"}:
        return (
            page_retention_score >= 44
            and page_utility_score >= 42
            and relevance >= 1
            and (entity_hits >= 1 or directness >= 2 or answer_quality >= 6)
        )
    return (
        page_retention_score >= 52
        and page_utility_score >= 48
        and relevance >= 2
        and entity_hits >= 1
        and (directness >= 1 or answer_quality >= 6)
    )


def annotate_key_evidence_page_keep(
    item: Dict[str, Any],
    query: str,
    evidence_mode: str,
    original_filter_reason: str,
    claim_item: Optional[Dict[str, Any]] = None,
) -> None:
    item["page_keep_review_state"] = "kept_review"
    item["page_keep_review_reason"] = original_filter_reason
    item["kept_progress_from_raw"] = True
    item["kept_candidate_source_type"] = str(item.get("source_type") or "")
    item["soft_keep_anchor_buckets"] = claim_anchor_bucket_hits(query, item, evidence_mode, claim_item)
    item["program_anchor_buckets"] = list(item.get("soft_keep_anchor_buckets") or [])[:6]
    item["program_false_friend_hits"] = program_false_friend_hits_for_item(item, claim_item)
    item["program_used_for_retention"] = True


def is_official_structured_discovery_stub(item: Dict[str, Any]) -> bool:
    source_type = str(item.get("source_type") or "")
    if source_type != "official":
        return False
    source = str(item.get("source") or "")
    bridge_type = str(item.get("bridge_type") or "")
    if source not in {"official_discovery", "official_inner_link", "domain_sitemap"} and bridge_type != "official_inner_link":
        return False
    answer_candidates = item.get("answer_candidates") if isinstance(item.get("answer_candidates"), list) else []
    if answer_candidates:
        return False
    structured_point_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
    if structured_point_status in {"partial", "satisfied"}:
        return False
    evidence_contract_role = normalize_text(str(item.get("evidence_contract_role") or "")).lower()
    evidence_contract_score = int(item.get("evidence_contract_score") or 0)
    if evidence_contract_role in {"structured_metric_table_page", "structured_metric_candidate_page"} and evidence_contract_score >= 60:
        return False
    metric_table_score = int(item.get("metric_table_score") or 0)
    directness = int(item.get("directness_score") or 0)
    if metric_table_score >= 6 or directness >= 3:
        return False
    page_retention_score = int(item.get("page_retention_score") or 0)
    page_utility_score = int(item.get("page_utility_score") or 0)
    page_type = str(item.get("page_utility_page_type") or "")
    if page_type in {"quote_page", "historical_table", "official_notice"} and (page_retention_score >= 62 or page_utility_score >= 58):
        return False
    return True


def web_evidence_filter_reason(query: str, item: Dict[str, Any], evidence_mode: str = "") -> tuple[bool, str]:
    mode = policy_mode_label(evidence_mode)
    site_domain = extract_site_constraint(query)
    if site_domain and not url_matches_domain(str(item.get("url", "")), site_domain):
        return False, "site_domain_mismatch"
    source_type = item.get("source_type") or "unknown"
    relevance = int(item.get("relevance_score") or 0)
    directness = int(item.get("directness_score") or 0)
    temporal = int(item.get("temporal_score") or 0)
    event_window = int(item.get("event_window_score") or 0)
    matches = entity_match_count(query, item)
    route_sentence = item.get("route_sentence") if isinstance(item.get("route_sentence"), dict) else {}
    route_rerank = int(item.get("route_rerank_score") or 0)
    noise_reasons = item.get("noise_reasons") if isinstance(item.get("noise_reasons"), list) else []
    structured_penalty = int(item.get("structured_noise_penalty") or 0)
    structured_reasons = item.get("structured_noise_reasons") if isinstance(item.get("structured_noise_reasons"), list) else []
    source_quality_score = int(item.get("source_quality_score") or 0)
    source_quality_label = str(item.get("source_quality_label") or "")
    source_quality_reasons = item.get("source_quality_reasons") if isinstance(item.get("source_quality_reasons"), list) else []
    page_utility_score = int(item.get("page_utility_score") or 0)
    page_retention_score = int(item.get("page_retention_score") or 0)
    page_utility_llm_decision = str(item.get("page_utility_llm_decision") or "")
    page_utility_components = item.get("page_utility_components") if isinstance(item.get("page_utility_components"), dict) else {}
    page_utility_page_type = str(item.get("page_utility_page_type") or "")
    page_relation_evidence = int(page_utility_components.get("relation_evidence") or 0)
    page_answerability = int(page_utility_components.get("answerability") or 0)
    structural_extractability = int(page_utility_components.get("structural_extractability") or 0)
    task_card_score = int(item.get("task_card_score") or 0)
    answer_quality = int(item.get("answer_candidate_quality_score") or 0)
    structured_point_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
    evidence_contract_role = normalize_text(str(item.get("evidence_contract_role") or "")).lower()
    evidence_contract_score = int(item.get("evidence_contract_score") or 0)
    official_like_structured = (
        is_structured_fact_mode(mode)
        and source_type not in {"forum", "encyclopedia"}
        and (
            structured_point_status in {"partial", "satisfied"}
            or (
                evidence_contract_role in {"structured_metric_table_page", "structured_metric_candidate_page"}
                and evidence_contract_score >= 60
            )
            or (
                page_utility_page_type in {"quote_page", "historical_table", "official_notice", "result_page", "event_detail", "calendar_page"}
                and page_retention_score >= 60
                and matches >= 1
                and directness >= 2
            )
        )
    )
    news_critical_mode = mode in {"date_fact", "schedule_fact", "event_result"} or str(evidence_mode or "") == "current_status_update"
    strong_news_fact_page = (
        source_type == "news"
        and news_critical_mode
        and (
            (
                relevance >= 2
                and matches >= 1
                and directness >= 2
                and (temporal >= 0 or event_window >= 0)
            )
            or (
                relevance >= 1
                and directness >= 2
                and (page_retention_score >= 55 or page_utility_score >= 60)
            )
            or (
                matches >= 1
                and (temporal >= 1 or event_window >= 1)
                and (page_retention_score >= 50 or page_utility_score >= 48 or answer_quality >= 6)
            )
            or (
                page_utility_page_type in {"news_article", "event_detail", "result_page", "calendar_page", "current_status_page", "mixed_page"}
                and matches >= 1
                and directness >= 2
                and page_retention_score >= 48
            )
        )
    )
    if item.get("source") == "domain_sitemap":
        parsed = urlparse(str(item.get("url") or ""))
        path = (parsed.path or "/").strip().lower()
        if path in {"", "/", "/news", "/news/"}:
            return False, "sitemap_generic_landing_page"
    if (
        source_type != "official"
        and source_quality_label == "bad"
        and ("hard_noise_page" in source_quality_reasons or source_quality_score < 25)
    ):
        if not (
            strong_news_fact_page
            or
            is_route_like_mode(mode)
            and page_utility_page_type in {"route_analysis_page", "route_passage_page", "mixed_page"}
            and page_retention_score >= 52
            and structural_extractability >= 1
            and (
                page_relation_evidence >= 1
                or page_answerability >= 1
                or route_sentence.get("has_relation_marker")
                or route_sentence.get("direct_sentence")
            )
            and page_utility_llm_decision != "drop"
        ):
            return False, remap_claim_aligned_filter_reason("source_quality_bad", query, item, mode)
    if "search_engine_result_page" in source_quality_reasons:
        return False, "search_engine_result_page"
    if temporal <= -2 and source_type != "official":
        return False, "temporal_mismatch"
    if event_window <= -2 and source_type != "official":
        return False, "event_window_mismatch"
    if is_route_like_mode(mode):
        route_decision = route_page_retention_decision(item, str(source_type))
        if route_decision is not None:
            return route_decision
        if "no_route_relation_marker" in noise_reasons and "single_or_no_entity_hit" in noise_reasons:
            if page_retention_score < 60:
                return False, "route_noise_no_relation_single_entity"
        if source_type not in {"forum", "unknown"}:
            return False, "route_retention_policy_not_satisfied"
    if is_route_like_mode(mode) and source_type in {"forum", "unknown"}:
        if route_sentence.get("direct_sentence"):
            return True, "kept_weak_route_direct_sentence"
        if (
            page_retention_score >= 78
            and page_relation_evidence >= 2
            and page_answerability >= 2
            and matches >= 2
        ):
            return True, "kept_weak_route_utility_page"
        return False, "route_weak_no_direct_sentence"
    if is_structured_fact_mode(mode):
        recoverable_structured_penalty = (
            structured_penalty >= 14
            and source_type != "official"
            and is_recoverable_structured_penalty_item(query, item, mode)
        )
        if structured_penalty >= 14 and source_type != "official":
            if (official_like_structured or strong_news_fact_page) and structured_penalty < 22:
                return True, "kept_official_like_structured_despite_penalty"
            if recoverable_structured_penalty:
                return False, "structured_noise_review_candidate"
            return False, "structured_noise_high_penalty"
        if "structured_no_entity_hit" in structured_reasons and source_type in {"unknown", "forum", "encyclopedia"}:
            return False, "structured_noise_no_entity_weak_source"
        if "date_window_mismatch" in structured_reasons and source_type != "official":
            return False, "structured_noise_date_window_mismatch"
        if "numeric_value_without_entity_context" in structured_reasons and directness < 3 and source_type != "official":
            return False, "structured_noise_value_without_context"
        if official_like_structured:
            return True, "kept_official_like_structured_contract"
        if strong_news_fact_page:
            return True, "kept_news_fact_page"
    if source_type == "official":
        if is_structured_fact_mode(mode) and is_official_structured_discovery_stub(item):
            return False, "official_structured_discovery_stub"
        if is_structured_fact_mode(mode) and structured_point_status in {"partial", "satisfied"}:
            return True, "kept_official_structured_point"
        if (
            is_structured_fact_mode(mode)
            and evidence_contract_role in {"structured_metric_table_page", "structured_metric_candidate_page"}
            and evidence_contract_score >= 60
        ):
            return True, "kept_official_structured_contract"
        if is_structured_fact_mode(mode) and directness >= 3 and structured_penalty < 16:
            return True, "kept_official_structured_direct"
        if (
            is_structured_fact_mode(mode)
            and relevance >= 4
            and matches >= 2
            and (page_retention_score >= 58 or page_utility_score >= 55 or task_card_score >= 10 or answer_quality >= 8)
        ):
            return True, "kept_official_structured_aligned"
        if is_structured_fact_mode(mode):
            return False, remap_claim_aligned_filter_reason("official_structured_alignment_weak", query, item, mode)
        if relevance >= 2 and matches >= 1:
            return True, "kept_official"
        if relevance >= 6 and directness >= 4:
            return True, "kept_official_direct"
        return False, remap_claim_aligned_filter_reason("low_official_relevance", query, item, mode)
    if source_type in {"news", "encyclopedia"}:
        if strong_news_fact_page:
            return True, "kept_strong_news_fact_page"
        if relevance >= 3 and matches >= 1:
            return True, "kept_strong_source"
        return False, remap_claim_aligned_filter_reason("low_strong_source_relevance", query, item, mode)
    if source_type in {"forum", "unknown"}:
        if relevance >= 5 and matches >= 2:
            return True, "kept_weak_source"
        return False, "weak_source_low_relevance"
    if relevance >= 4 and matches >= 1:
        return True, "kept_other"
    return False, remap_claim_aligned_filter_reason("low_relevance", query, item, mode)


def should_soft_keep_high_priority_item(
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
    task_card: Dict[str, Any],
) -> bool:
    priority_label = str(task_card.get("priority_label") or "")
    if priority_label not in {"critical", "high"}:
        return False
    if not (is_structured_fact_mode(evidence_mode) or is_event_like_mode(evidence_mode)):
        return False
    if filter_reason not in {"temporal_mismatch", "structured_noise_high_penalty", "structured_noise_date_window_mismatch"}:
        return False
    source_type = str(item.get("source_type") or "")
    if source_type not in {"official", "news"}:
        return False
    directness = int(item.get("directness_score") or 0)
    relevance = int(item.get("relevance_score") or 0)
    entity_hits = int(item.get("entity_match_count") or 0)
    temporal = int(item.get("temporal_score") or 0)
    event_window = int(item.get("event_window_score") or 0)
    task_card_score = int(item.get("task_card_score") or 0)
    answer_quality = int(item.get("answer_candidate_quality_score") or 0)
    if directness < 3:
        return False
    if relevance < 3 or entity_hits < 1:
        return False
    if task_card_score < 10 and answer_quality < 8:
        return False
    if temporal < -4 and event_window < -4:
        return False
    return True


def should_soft_keep_structured_metric_item(
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
    task_card: Dict[str, Any],
) -> bool:
    if not is_structured_fact_mode(evidence_mode):
        return False
    if filter_reason not in {"source_quality_bad", "weak_source_low_relevance", "structured_noise_high_penalty", "structured_noise_review_candidate", "low_relevance"}:
        return False
    priority_label = str(task_card.get("priority_label") or "")
    if priority_label not in {"critical", "high", "normal"}:
        return False
    source_type = str(item.get("source_type") or "")
    if source_type not in {"official", "news", "finance", "unknown"}:
        return False
    metric_score = int(item.get("metric_table_score") or 0)
    page_retention_score = int(item.get("page_retention_score") or 0)
    page_utility_score = int(item.get("page_utility_score") or 0)
    directness = int(item.get("directness_score") or 0)
    relevance = int(item.get("relevance_score") or 0)
    entity_hits = int(item.get("entity_match_count") or 0)
    answer_quality = int(item.get("answer_candidate_quality_score") or 0)
    evidence_contract_status = normalize_text(str(item.get("evidence_contract_status") or "")).lower()
    evidence_contract_score = int(item.get("evidence_contract_score") or 0)
    title_marker_hit = structured_title_marker_hit(evidence_mode, item)
    page_type = str(item.get("page_utility_page_type") or "")
    strong_page_type = page_type in STRUCTURED_REVIEW_PAGE_TYPES
    if (
        evidence_contract_status in {"partial", "satisfied"}
        and evidence_contract_score >= 45
        and directness >= 3
        and answer_quality >= 8
        and source_type in {"official", "news", "finance", "unknown"}
    ):
        return True
    if filter_reason == "structured_noise_review_candidate":
        if page_retention_score < 46 and page_utility_score < 48:
            return False
        if directness < 2 and answer_quality < 8 and metric_score < 6:
            return False
        if relevance < 1 and entity_hits < 1 and answer_quality < 10:
            return False
        if not (strong_page_type or title_marker_hit or source_type in {"official", "finance"}):
            return False
        if source_type == "unknown" and not (strong_page_type and title_marker_hit and answer_quality >= 10):
            return False
        return True
    if metric_score < 6:
        return False
    if page_retention_score < 50 or page_utility_score < 45:
        return False
    if directness < 2 or relevance < 2 or entity_hits < 1:
        return False
    if filter_reason == "source_quality_bad" and source_type == "unknown" and metric_score < 8:
        return False
    return True


def should_soft_keep_route_review_item(
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
) -> bool:
    if not is_route_like_mode(evidence_mode):
        return False
    if filter_reason not in {
        "route_missing_required_object_marker",
        "route_rerank_low_quality",
        "route_page_utility_too_low",
        "route_weak_no_direct_sentence",
        "source_quality_bad",
    }:
        return False
    source_type = str(item.get("source_type") or "")
    if source_type not in {"official", "news", "encyclopedia", "unknown"}:
        return False
    if str(item.get("page_utility_llm_decision") or "") == "drop":
        return False
    page_retention_score = int(item.get("page_retention_score") or 0)
    page_utility_score = int(item.get("page_utility_score") or 0)
    route_rerank_score = int(item.get("route_rerank_score") or 0)
    directness = int(item.get("directness_score") or 0)
    page_components = item.get("page_utility_components") if isinstance(item.get("page_utility_components"), dict) else {}
    relation_evidence = int(page_components.get("relation_evidence") or 0)
    answerability = int(page_components.get("answerability") or 0)
    entity_grounding = int(page_components.get("entity_grounding") or 0)
    structural_extractability = int(page_components.get("structural_extractability") or 0)
    evidence_contract_status = normalize_text(str(item.get("evidence_contract_status") or "")).lower()
    evidence_contract_score = int(item.get("evidence_contract_score") or 0)
    page_type = str(item.get("page_utility_page_type") or "")
    route_sentence = item.get("route_sentence") if isinstance(item.get("route_sentence"), dict) else {}
    if page_retention_score < 54 or page_utility_score < 48:
        return False
    if entity_grounding < 2 or structural_extractability < 1:
        return False
    if relation_evidence <= 0 and route_rerank_score < 10 and directness < 3:
        return False
    if filter_reason == "source_quality_bad":
        if source_type == "unknown" and page_type not in {"route_analysis_page", "route_passage_page"}:
            return False
        return (
            (evidence_contract_status in {"partial", "satisfied"} and evidence_contract_score >= 38)
            or route_sentence.get("direct_sentence")
            or (
                relation_evidence >= 1
                and answerability >= 1
                and (
                    route_sentence.get("has_relation_marker")
                    or route_sentence.get("has_route_object_marker")
                )
            )
        )
    if filter_reason == "route_weak_no_direct_sentence":
        return (
            page_type in {"route_analysis_page", "route_passage_page", "mixed_page"}
            and relation_evidence >= 1
            and answerability >= 1
            and (
                evidence_contract_status in {"partial", "satisfied"}
                or route_sentence.get("has_relation_marker")
            )
        )
    if filter_reason == "route_missing_required_object_marker":
        if route_sentence.get("direct_sentence"):
            return True
        if relation_evidence >= 1 and answerability >= 1:
            return True
        if route_rerank_score >= 12 and directness >= 2:
            return True
        return False
    if filter_reason == "route_rerank_low_quality":
        return relation_evidence >= 1 and answerability >= 1 and directness >= 2
    if filter_reason == "route_page_utility_too_low":
        return relation_evidence >= 2 and directness >= 2
    return False


def add_filter_reason(stats: Dict[str, Any], reason: str) -> None:
    reasons = stats.setdefault("filtered_reasons", {})
    reasons[reason] = int(reasons.get(reason, 0) or 0) + 1


def record_page_intent_stats(stats: Dict[str, Any], item: Dict[str, Any]) -> None:
    score = item.get("page_intent_score")
    if isinstance(score, int):
        stats.setdefault("page_intent_scores", []).append(score)
    label = str(item.get("page_intent_label") or "")
    if label:
        labels = stats.setdefault("page_intent_labels", {})
        labels[label] = int(labels.get(label, 0) or 0) + 1
    for issue in item.get("page_intent_issues", []) if isinstance(item.get("page_intent_issues"), list) else []:
        issues = stats.setdefault("page_intent_issues", {})
        issues[str(issue)] = int(issues.get(str(issue), 0) or 0) + 1
    utility_score = item.get("page_utility_score")
    if isinstance(utility_score, int):
        stats.setdefault("page_utility_scores", []).append(utility_score)
    utility_label = str(item.get("page_utility_label") or "")
    if utility_label:
        labels = stats.setdefault("page_utility_labels", {})
        labels[utility_label] = int(labels.get(utility_label, 0) or 0) + 1
    llm_score = item.get("page_utility_llm_score")
    if isinstance(llm_score, int):
        stats.setdefault("page_utility_llm_scores", []).append(llm_score)
    llm_decision = str(item.get("page_utility_llm_decision") or "")
    if llm_decision:
        decisions = stats.setdefault("page_utility_llm_decisions", {})
        decisions[llm_decision] = int(decisions.get(llm_decision, 0) or 0) + 1
    page_type = str(item.get("page_utility_page_type") or "")
    if page_type:
        counts = stats.setdefault("page_utility_page_types", {})
        counts[page_type] = int(counts.get(page_type, 0) or 0) + 1
    page_focus = str(item.get("page_utility_page_focus") or "")
    if page_focus:
        counts = stats.setdefault("page_utility_page_focuses", {})
        counts[page_focus] = int(counts.get(page_focus, 0) or 0) + 1
    for risk in item.get("page_utility_risks", []) if isinstance(item.get("page_utility_risks"), list) else []:
        risks = stats.setdefault("page_utility_risks", {})
        risks[str(risk)] = int(risks.get(str(risk), 0) or 0) + 1
    for risk in item.get("page_utility_llm_risks", []) if isinstance(item.get("page_utility_llm_risks"), list) else []:
        risks = stats.setdefault("page_utility_llm_risks", {})
        risks[str(risk)] = int(risks.get(str(risk), 0) or 0) + 1
    contract_role = str(item.get("evidence_contract_role") or "")
    if contract_role:
        roles = stats.setdefault("evidence_contract_roles", {})
        roles[contract_role] = int(roles.get(contract_role, 0) or 0) + 1
    contract_status = str(item.get("evidence_contract_status") or "")
    if contract_status:
        statuses = stats.setdefault("evidence_contract_statuses", {})
        statuses[contract_status] = int(statuses.get(contract_status, 0) or 0) + 1
    for risk in item.get("evidence_contract_risks", []) if isinstance(item.get("evidence_contract_risks"), list) else []:
        risks = stats.setdefault("evidence_contract_risks", {})
        risks[str(risk)] = int(risks.get(str(risk), 0) or 0) + 1
    page_role = str(item.get("page_role") or "")
    if page_role:
        roles = stats.setdefault("page_roles", {})
        roles[page_role] = int(roles.get(page_role, 0) or 0) + 1
    page_role_reason = str(item.get("page_role_reason") or "")
    if page_role_reason:
        reasons = stats.setdefault("page_role_reasons", {})
        reasons[page_role_reason] = int(reasons.get(page_role_reason, 0) or 0) + 1
    generic_block = str(item.get("generic_page_block_reason") or "")
    if generic_block:
        blocks = stats.setdefault("generic_page_block_reasons", {})
        blocks[generic_block] = int(blocks.get(generic_block, 0) or 0) + 1
    entry_state = str(item.get("entry_follow_state") or "")
    if entry_state:
        states = stats.setdefault("entry_follow_states", {})
        states[entry_state] = int(states.get(entry_state, 0) or 0) + 1
    if contract_role or contract_status:
        origin = normalize_text(str(item.get("query_origin") or "")) or "unknown"
        by_origin = stats.setdefault("evidence_contract_by_query_origin", {})
        bucket = by_origin.setdefault(
            origin,
            {
                "total": 0,
                "score_sum": 0,
                "roles": {},
                "statuses": {},
                "risks": {},
                "page_types": {},
                "llm_decisions": {},
                "goals": {},
            },
        )
        bucket["total"] = int(bucket.get("total", 0) or 0) + 1
        bucket["score_sum"] = int(bucket.get("score_sum", 0) or 0) + int(item.get("evidence_contract_score") or 0)
        if contract_role:
            roles = bucket.setdefault("roles", {})
            roles[contract_role] = int(roles.get(contract_role, 0) or 0) + 1
        if contract_status:
            statuses = bucket.setdefault("statuses", {})
            statuses[contract_status] = int(statuses.get(contract_status, 0) or 0) + 1
        page_type = str(item.get("page_utility_page_type") or "")
        if page_type:
            page_types = bucket.setdefault("page_types", {})
            page_types[page_type] = int(page_types.get(page_type, 0) or 0) + 1
        llm_decision = str(item.get("page_utility_llm_decision") or "")
        if llm_decision:
            decisions = bucket.setdefault("llm_decisions", {})
            decisions[llm_decision] = int(decisions.get(llm_decision, 0) or 0) + 1
        query_goal = str(item.get("query_goal") or "")
        if query_goal:
            goals = bucket.setdefault("goals", {})
            goals[query_goal] = int(goals.get(query_goal, 0) or 0) + 1
        for risk in item.get("evidence_contract_risks", []) if isinstance(item.get("evidence_contract_risks"), list) else []:
            risks = bucket.setdefault("risks", {})
            risks[str(risk)] = int(risks.get(str(risk), 0) or 0) + 1


def compact_evidence_contract_by_query_origin(stats: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = stats.get("evidence_contract_by_query_origin") if isinstance(stats.get("evidence_contract_by_query_origin"), dict) else {}
    out: Dict[str, Dict[str, Any]] = {}
    for origin, bucket in raw.items():
        if not isinstance(bucket, dict):
            continue
        total = int(bucket.get("total", 0) or 0)
        statuses = bucket.get("statuses") if isinstance(bucket.get("statuses"), dict) else {}
        if total <= 0:
            continue
        out[str(origin)] = {
            "total": total,
            "avg_score": round(int(bucket.get("score_sum", 0) or 0) / total, 1),
            "satisfied_rate": round(int(statuses.get("satisfied", 0) or 0) / total, 3),
            "partial_rate": round(int(statuses.get("partial", 0) or 0) / total, 3),
            "failed_rate": round(int(statuses.get("failed", 0) or 0) / total, 3),
            "roles": top_count_items(bucket.get("roles", {}), 4),
            "statuses": top_count_items(statuses, 3),
            "risks": top_count_items(bucket.get("risks", {}), 5),
            "page_types": top_count_items(bucket.get("page_types", {}), 4),
            "llm_decisions": top_count_items(bucket.get("llm_decisions", {}), 3),
            "goals": top_count_items(bucket.get("goals", {}), 3),
        }
    return dict(sorted(out.items(), key=lambda item: (item[1].get("satisfied_rate", 0), item[1].get("avg_score", 0)), reverse=True))


def source_pollution_bucket(stats: Dict[str, Any], source_name: str) -> Dict[str, Any]:
    buckets = stats.setdefault("source_pollution_stats", {})
    bucket = buckets.setdefault(
        source_name or "unknown",
        {
            "calls": 0,
            "raw": 0,
            "kept": 0,
            "filtered": 0,
            "bad": 0,
            "quality_sum": 0,
            "quality_count": 0,
            "filter_reasons": {},
            "quality_reasons": {},
            "errors": 0,
            "detail_fetch_paths": {},
            "environment_block_reasons": {},
            "playwright_used": 0,
            "playwright_rescued": 0,
            "playwright_failed": 0,
            "detail_read_failed": 0,
            "requests_blocked_playwright_rescued": 0,
            "requests_blocked_playwright_failed": 0,
            "detail_read_failed_after_fetch": 0,
        },
    )
    return bucket


def record_source_call(
    stats: Dict[str, Any],
    source_name: str,
    raw_count: int = 0,
    error: bool = False,
    error_reason: str = "",
) -> None:
    bucket = source_pollution_bucket(stats, source_name)
    bucket["calls"] = int(bucket.get("calls", 0) or 0) + 1
    bucket["raw"] = int(bucket.get("raw", 0) or 0) + max(0, int(raw_count or 0))
    if error:
        bucket["errors"] = int(bucket.get("errors", 0) or 0) + 1
        if error_reason == "anti_bot_blocked":
            bucket["anti_bot_blocks"] = int(bucket.get("anti_bot_blocks", 0) or 0) + 1


def record_source_item_quality(
    stats: Dict[str, Any],
    source_name: str,
    item: Dict[str, Any],
    kept: bool,
    filter_reason: str = "",
) -> None:
    bucket = source_pollution_bucket(stats, source_name)
    if kept:
        bucket["kept"] = int(bucket.get("kept", 0) or 0) + 1
    else:
        bucket["filtered"] = int(bucket.get("filtered", 0) or 0) + 1
    quality = int(item.get("source_quality_score") or 0)
    bucket["quality_sum"] = int(bucket.get("quality_sum", 0) or 0) + quality
    bucket["quality_count"] = int(bucket.get("quality_count", 0) or 0) + 1
    if item.get("source_quality_label") == "bad" or filter_reason == "source_quality_bad":
        bucket["bad"] = int(bucket.get("bad", 0) or 0) + 1
    if filter_reason:
        reasons = bucket.setdefault("filter_reasons", {})
        reasons[filter_reason] = int(reasons.get(filter_reason, 0) or 0) + 1
    for reason_item in item.get("source_quality_reasons", []) if isinstance(item.get("source_quality_reasons"), list) else []:
        reasons = bucket.setdefault("quality_reasons", {})
        reasons[reason_item] = int(reasons.get(reason_item, 0) or 0) + 1
    environment_block_reason = normalize_text(str(item.get("environment_block_reason") or ""))
    if environment_block_reason == "requests_blocked_playwright_rescued":
        bucket["requests_blocked_playwright_rescued"] = int(bucket.get("requests_blocked_playwright_rescued", 0) or 0) + 1
    elif environment_block_reason == "requests_blocked_playwright_failed":
        bucket["requests_blocked_playwright_failed"] = int(bucket.get("requests_blocked_playwright_failed", 0) or 0) + 1
    elif environment_block_reason == "detail_read_failed_after_fetch":
        bucket["detail_read_failed_after_fetch"] = int(bucket.get("detail_read_failed_after_fetch", 0) or 0) + 1


def compact_source_pollution_stats(stats: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    compact: Dict[str, Dict[str, Any]] = {}
    buckets = stats.get("source_pollution_stats") if isinstance(stats.get("source_pollution_stats"), dict) else {}
    for source_name, bucket in buckets.items():
        raw = int(bucket.get("raw", 0) or 0)
        kept = int(bucket.get("kept", 0) or 0)
        filtered = int(bucket.get("filtered", 0) or 0)
        bad = int(bucket.get("bad", 0) or 0)
        quality_count = int(bucket.get("quality_count", 0) or 0)
        compact[str(source_name)] = {
            "calls": int(bucket.get("calls", 0) or 0),
            "raw": raw,
            "kept": kept,
            "filtered": filtered,
            "bad": bad,
            "bad_rate": round(bad / raw, 3) if raw else None,
            "kept_rate": round(kept / raw, 3) if raw else None,
            "quality_avg": round(int(bucket.get("quality_sum", 0) or 0) / quality_count, 1) if quality_count else None,
            "errors": int(bucket.get("errors", 0) or 0),
            "anti_bot_blocks": int(bucket.get("anti_bot_blocks", 0) or 0),
            "detail_fetch_paths": bucket.get("detail_fetch_paths", {}),
            "environment_block_reasons": bucket.get("environment_block_reasons", {}),
            "playwright_used": int(bucket.get("playwright_used", 0) or 0),
            "playwright_rescued": int(bucket.get("playwright_rescued", 0) or 0),
            "playwright_failed": int(bucket.get("playwright_failed", 0) or 0),
            "detail_read_failed": int(bucket.get("detail_read_failed", 0) or 0),
            "requests_blocked_playwright_rescued": int(bucket.get("requests_blocked_playwright_rescued", 0) or 0),
            "requests_blocked_playwright_failed": int(bucket.get("requests_blocked_playwright_failed", 0) or 0),
            "detail_read_failed_after_fetch": int(bucket.get("detail_read_failed_after_fetch", 0) or 0),
            "filter_reasons": bucket.get("filter_reasons", {}),
            "quality_reasons": bucket.get("quality_reasons", {}),
        }
    return compact


def source_health_key(source_name: str, evidence_mode: str, query_goal: str, query: str) -> str:
    language = "en" if is_english_query(query) else "zh_or_mixed"
    site_flag = "site" if extract_site_constraint(query) else "open"
    return "|".join([source_name or "unknown", policy_mode_label(evidence_mode), query_goal or "general_verify", language, site_flag])


def health_bucket_score(bucket: Dict[str, Any]) -> int:
    raw = int(bucket.get("raw", 0) or 0)
    kept = int(bucket.get("kept", 0) or 0)
    bad = int(bucket.get("bad", 0) or 0)
    empty = int(bucket.get("empty", 0) or 0)
    errors = int(bucket.get("errors", 0) or 0)
    anti_bot_blocks = int(bucket.get("anti_bot_blocks", 0) or 0)
    playwright_rescued = int(bucket.get("playwright_rescued", 0) or 0)
    requests_blocked_playwright_rescued = int(bucket.get("requests_blocked_playwright_rescued", 0) or 0)
    requests_blocked_playwright_failed = int(bucket.get("requests_blocked_playwright_failed", 0) or 0)
    detail_read_failed_after_fetch = int(bucket.get("detail_read_failed_after_fetch", 0) or 0)
    score = 0
    if kept > 0:
        score += 20 + kept * 5
    if raw > 0 and bad >= raw and kept == 0:
        score -= 20
    if empty >= 2 and raw == 0:
        score -= 8
    if errors:
        score -= 8 * errors
    if requests_blocked_playwright_rescued > 0:
        score += min(8, requests_blocked_playwright_rescued * 3)
    if playwright_rescued > 0:
        score += min(6, playwright_rescued * 2)
    if requests_blocked_playwright_failed > 0:
        score -= 10 * requests_blocked_playwright_failed
    if detail_read_failed_after_fetch > 0:
        score -= 6 * detail_read_failed_after_fetch
    unresolved_anti_bot_blocks = max(0, anti_bot_blocks - requests_blocked_playwright_rescued)
    if unresolved_anti_bot_blocks:
        score -= 14 * unresolved_anti_bot_blocks
    return score


def reorder_sources_by_health(
    source_jobs: List[tuple[str, str]],
    source_health: Dict[str, Dict[str, Any]],
    evidence_mode: str,
    query_goal: str,
) -> tuple[List[tuple[str, str]], List[Dict[str, Any]]]:
    scored: List[tuple[int, int, tuple[str, str], str]] = []
    actions: List[Dict[str, Any]] = []
    for index, (source_name, query) in enumerate(source_jobs):
        key = source_health_key(source_name, evidence_mode, query_goal, query)
        any_key = source_health_key(source_name, evidence_mode, "any", "")
        bucket = source_health.get(key) or source_health.get(any_key, {})
        score = health_bucket_score(bucket)
        scored.append((score, -index, (source_name, query), key))
        if bucket and score != 0:
            actions.append(
                {
                    "source": source_name,
                    "key": key,
                    "score": score,
                    "raw": int(bucket.get("raw", 0) or 0),
                    "kept": int(bucket.get("kept", 0) or 0),
                    "bad": int(bucket.get("bad", 0) or 0),
                    "empty": int(bucket.get("empty", 0) or 0),
                    "anti_bot_blocks": int(bucket.get("anti_bot_blocks", 0) or 0),
                    "playwright_rescued": int(bucket.get("playwright_rescued", 0) or 0),
                    "requests_blocked_playwright_rescued": int(bucket.get("requests_blocked_playwright_rescued", 0) or 0),
                    "requests_blocked_playwright_failed": int(bucket.get("requests_blocked_playwright_failed", 0) or 0),
                }
            )
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    reordered = [item[2] for item in scored]
    if [item[0] for item in reordered] == [item[0] for item in source_jobs]:
        return source_jobs, actions
    return reordered, actions


def update_source_health_from_stats(
    source_health: Dict[str, Dict[str, Any]],
    stats: Dict[str, Any],
    evidence_mode: str,
) -> None:
    pollution = stats.get("source_pollution_stats") if isinstance(stats.get("source_pollution_stats"), dict) else {}
    for source_name, source_stats in pollution.items():
        if not isinstance(source_stats, dict):
            continue
        key = source_health_key(str(source_name), evidence_mode, "any", "")
        bucket = source_health.setdefault(
            key,
            {
                "raw": 0,
                "kept": 0,
                "bad": 0,
                "empty": 0,
                "errors": 0,
                "anti_bot_blocks": 0,
                "playwright_rescued": 0,
                "requests_blocked_playwright_rescued": 0,
                "requests_blocked_playwright_failed": 0,
                "detail_read_failed_after_fetch": 0,
            },
        )
        raw = int(source_stats.get("raw", 0) or 0)
        bucket["raw"] = int(bucket.get("raw", 0) or 0) + raw
        bucket["kept"] = int(bucket.get("kept", 0) or 0) + int(source_stats.get("kept", 0) or 0)
        bucket["bad"] = int(bucket.get("bad", 0) or 0) + int(source_stats.get("bad", 0) or 0)
        bucket["errors"] = int(bucket.get("errors", 0) or 0) + int(source_stats.get("errors", 0) or 0)
        bucket["anti_bot_blocks"] = int(bucket.get("anti_bot_blocks", 0) or 0) + int(source_stats.get("anti_bot_blocks", 0) or 0)
        bucket["playwright_rescued"] = int(bucket.get("playwright_rescued", 0) or 0) + int(source_stats.get("playwright_rescued", 0) or 0)
        bucket["requests_blocked_playwright_rescued"] = int(bucket.get("requests_blocked_playwright_rescued", 0) or 0) + int(source_stats.get("requests_blocked_playwright_rescued", 0) or 0)
        bucket["requests_blocked_playwright_failed"] = int(bucket.get("requests_blocked_playwright_failed", 0) or 0) + int(source_stats.get("requests_blocked_playwright_failed", 0) or 0)
        bucket["detail_read_failed_after_fetch"] = int(bucket.get("detail_read_failed_after_fetch", 0) or 0) + int(source_stats.get("detail_read_failed_after_fetch", 0) or 0)
        if raw == 0:
            bucket["empty"] = int(bucket.get("empty", 0) or 0) + int(source_stats.get("calls", 0) or 0)


def should_precheck_source(source_name: str, query: str, max_results: int) -> bool:
    if not ENABLE_SOURCE_TOP1_PRECHECK:
        return False
    if max_results <= 1:
        return False
    if source_name in {"domain_sitemap", "playwright_duckduckgo", "wikipedia"}:
        return False
    return True


def source_precheck_passes(
    stats: Dict[str, Any],
    source_name: str,
    query: str,
    evidence_mode: str,
    preferred_domains: List[str],
    timeout_sec: int,
) -> bool:
    precheck_stats = stats.setdefault("source_precheck_stats", {})
    bucket = precheck_stats.setdefault(
        source_name,
        {"calls": 0, "empty": 0, "passed": 0, "skipped": 0, "reasons": {}, "examples": []},
    )
    bucket["calls"] = int(bucket.get("calls", 0) or 0) + 1
    try:
        started = time.perf_counter()
        items = search_source(source_name, query, 1, timeout_sec)
        add_timing(stats, f"{source_name}_precheck", time.perf_counter() - started)
    except Exception as exc:
        add_timing(stats, f"{source_name}_precheck", time.perf_counter() - started if "started" in locals() else 0.0)
        reasons = bucket.setdefault("reasons", {})
        reason_key = "precheck_anti_bot" if exception_looks_like_anti_bot(exc) else "precheck_error"
        reasons[reason_key] = int(reasons.get(reason_key, 0) or 0) + 1
        bucket["skipped"] = int(bucket.get("skipped", 0) or 0) + 1
        return False
    if not items:
        bucket["empty"] = int(bucket.get("empty", 0) or 0) + 1
        reasons = bucket.setdefault("reasons", {})
        reasons["precheck_empty"] = int(reasons.get("precheck_empty", 0) or 0) + 1
        return False
    item = dict(items[0])
    item["query"] = query
    item["source_type"] = dynamic_source_type(str(item.get("url", "")), query, preferred_domains)
    item["relevance_score"] = evidence_relevance_score(query, item)
    item["entity_match_count"] = entity_match_count(query, item)
    item["temporal_score"] = evidence_temporal_score(query, item)
    item["event_window_score"] = event_window_score(query, item, evidence_mode)
    item.update(source_quality_features(query, item, evidence_mode, preferred_domains))
    quality_label = str(item.get("source_quality_label") or "")
    quality_score = int(item.get("source_quality_score") or 0)
    hard_bad = quality_label == "bad" and (
        quality_score < 25
        or "hard_noise_page" in (item.get("source_quality_reasons") or [])
        or "weak_source_no_entity_match" in (item.get("source_quality_reasons") or [])
    )
    if hard_bad:
        bucket["skipped"] = int(bucket.get("skipped", 0) or 0) + 1
        reasons = bucket.setdefault("reasons", {})
        for reason_item in item.get("source_quality_reasons", []) or ["precheck_bad"]:
            reasons[str(reason_item)] = int(reasons.get(str(reason_item), 0) or 0) + 1
        examples = bucket.setdefault("examples", [])
        if len(examples) < 3:
            examples.append(
                {
                    "query": query,
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "quality_score": quality_score,
                    "quality_reasons": item.get("source_quality_reasons", []),
                }
            )
        return False
    bucket["passed"] = int(bucket.get("passed", 0) or 0) + 1
    return True


def add_timing(stats: Dict[str, Any], name: str, elapsed: float) -> None:
    timings = stats.setdefault("source_timings", {})
    item = timings.setdefault(name, {"calls": 0, "seconds": 0.0})
    item["calls"] = int(item.get("calls", 0) or 0) + 1
    item["seconds"] = round(float(item.get("seconds", 0.0) or 0.0) + elapsed, 3)


def timing_seconds(stats: Dict[str, Any], name: str) -> float:
    timings = stats.get("source_timings") if isinstance(stats.get("source_timings"), dict) else {}
    bucket = timings.get(name) if isinstance(timings.get(name), dict) else {}
    return float(bucket.get("seconds", 0.0) or 0.0)


def record_rescue_budget_event(
    stats: Dict[str, Any],
    rescue_type: str,
    family: str,
    state: str,
    latency_ms: float = 0.0,
    skip_reason: str = "",
) -> None:
    family_key = normalize_text(str(family or "")) or "unknown"
    rescue_key = f"{normalize_text(str(rescue_type or 'unknown'))}_count"
    budget = stats.setdefault(
        "family_rescue_budget_used",
        {
            "serp_count": 0,
            "detail_count": 0,
            "families": {},
        },
    )
    budget[rescue_key] = int(budget.get(rescue_key, 0) or 0) + (1 if state in {"succeeded", "failed"} else 0)
    families = budget.setdefault("families", {})
    family_bucket = families.setdefault(
        family_key,
        {"serp": {"succeeded": 0, "failed": 0}, "detail": {"succeeded": 0, "failed": 0}},
    )
    if state in {"succeeded", "failed"}:
        family_bucket.setdefault(rescue_type, {"succeeded": 0, "failed": 0})
        family_bucket[rescue_type][state] = int(family_bucket[rescue_type].get(state, 0) or 0) + 1
    if latency_ms > 0:
        stats["rescue_latency_ms"] = round(float(stats.get("rescue_latency_ms", 0.0) or 0.0) + latency_ms, 1)
    if skip_reason:
        skips = stats.setdefault("rescue_skip_reasons", {})
        skips[skip_reason] = int(skips.get(skip_reason, 0) or 0) + 1


def source_timing_stage_profile(stats: Dict[str, Any]) -> Dict[str, Any]:
    timings = stats.get("source_timings") if isinstance(stats.get("source_timings"), dict) else {}
    search_seconds = 0.0
    detail_seconds = 0.0
    official_discovery_seconds = timing_seconds(stats, "official_discovery")
    slow_sources: List[Dict[str, Any]] = []
    for name, bucket in timings.items():
        if not isinstance(bucket, dict):
            continue
        seconds = float(bucket.get("seconds", 0.0) or 0.0)
        calls = int(bucket.get("calls", 0) or 0)
        if name == "fetch_detail":
            detail_seconds += seconds
            continue
        if name.endswith("_precheck") or name == "official_discovery":
            continue
        search_seconds += seconds
        if calls > 0 and seconds >= 4.0:
            slow_sources.append(
                {
                    "source": str(name),
                    "seconds": round(seconds, 3),
                    "calls": calls,
                }
            )
    slow_sources.sort(key=lambda item: (item.get("seconds", 0.0), item.get("calls", 0)), reverse=True)
    return {
        "official_discovery_seconds": round(official_discovery_seconds, 3),
        "search_seconds": round(search_seconds, 3),
        "detail_fetch_seconds": round(detail_seconds, 3),
        "slow_sources": slow_sources[:5],
    }


def source_family_stop_loss_triggered(
    stats: Dict[str, Any],
    source_name: str,
    slow_threshold_sec: float = 6.0,
) -> str:
    bucket = source_pollution_bucket(stats, source_name)
    seconds = timing_seconds(stats, source_name)
    if source_name == "sogou_html" and ENABLE_PLAYWRIGHT and int(bucket.get("calls", 0) or 0) >= 1 and seconds >= max(3.0, float(SOGOU_TIMEOUT_CAP_SEC or 4)):
        return "sogou_slow_after_rescue_available"
    if int(bucket.get("anti_bot_blocks", 0) or 0) >= 1 and int(bucket.get("requests_blocked_playwright_failed", 0) or 0) >= 1:
        return "anti_bot_and_rescue_failed"
    if int(bucket.get("raw", 0) or 0) <= 0 and int(bucket.get("calls", 0) or 0) >= 1 and seconds >= slow_threshold_sec:
        return "empty_and_slow"
    if int(bucket.get("playwright_failed", 0) or 0) >= 1:
        return "repeated_rescue_failed"
    return ""


def filtered_rescue_pool_score(item: Dict[str, Any]) -> int:
    answer_quality = int(item.get("answer_candidate_quality_score") or answer_candidate_quality_score(item) or 0)
    return (
        answer_quality * 10
        + int(item.get("directness_score") or 0) * 6
        + int(item.get("page_retention_score") or 0)
        + int(item.get("page_utility_score") or 0)
        + int(item.get("relevance_score") or 0) * 4
        + int(item.get("entity_match_count") or 0) * 4
        + int(item.get("evidence_contract_score") or 0)
        + int(item.get("structured_point_contract_score") or 0)
    )


def should_record_filtered_rescue_pool_candidate(
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
    claim_item: Optional[Dict[str, Any]],
) -> bool:
    if not isinstance(claim_item, dict):
        return False
    if str(claim_item.get("centrality") or "") == "peripheral":
        return False
    mode = policy_mode_label(evidence_mode)
    if mode not in {"numeric_fact", "date_fact", "schedule_fact", "event_result", "entity_fact", "route_fact"}:
        return False
    if filter_reason in PREFILTER_RESCUE_HARD_FILTER_REASONS:
        return False
    if str(item.get("source_type") or "") not in {"official", "news", "encyclopedia", "unknown", "finance"}:
        return False
    if str(item.get("page_utility_llm_decision") or "") == "drop":
        return False
    if not claim_aligned_page_shape_ok(item):
        return False
    answer_candidates = item.get("answer_candidates") if isinstance(item.get("answer_candidates"), list) else []
    evidence_contract_status = normalize_text(str(item.get("evidence_contract_status") or "")).lower()
    structured_point_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
    if not answer_candidates and evidence_contract_status not in {"partial", "satisfied"} and structured_point_status not in {"partial", "satisfied"}:
        return False
    return filtered_rescue_pool_score(item) >= 95


def record_filtered_rescue_pool_candidate(
    stats: Dict[str, Any],
    query: str,
    item: Dict[str, Any],
    filter_reason: str,
    evidence_mode: str,
    claim_item: Optional[Dict[str, Any]],
) -> None:
    if not should_record_filtered_rescue_pool_candidate(item, filter_reason, evidence_mode, claim_item):
        return
    score = filtered_rescue_pool_score(item)
    current = stats.get("_filtered_rescue_pool_best") if isinstance(stats.get("_filtered_rescue_pool_best"), dict) else {}
    if current and int(current.get("score") or 0) >= score:
        return
    candidate = dict(item)
    candidate["_filtered_rescue_pool_query"] = query
    candidate["_filtered_rescue_pool_reason"] = filter_reason
    candidate["_filtered_rescue_pool_score"] = score
    stats["_filtered_rescue_pool_best"] = {"score": score, "item": candidate}
    stats["filtered_rescue_pool_state"] = "candidate_ready"
    stats["filtered_rescue_pool_reason"] = filter_reason
    stats["filtered_rescue_pool_score"] = score


def promote_filtered_rescue_pool_if_needed(
    stats: Dict[str, Any],
    claim_evidence: List[Dict[str, Any]],
    kept_web_before_query: int,
) -> bool:
    kept_web_now = sum(1 for ev in claim_evidence if isinstance(ev, dict) and ev.get("source_type") not in {"input_context", "computed"})
    if kept_web_now > kept_web_before_query:
        return False
    current = stats.get("_filtered_rescue_pool_best") if isinstance(stats.get("_filtered_rescue_pool_best"), dict) else {}
    item = current.get("item") if isinstance(current.get("item"), dict) else {}
    if not item:
        return False
    item = dict(item)
    item["filtered_rescue_pool_kept"] = True
    item["page_keep_review_state"] = item.get("page_keep_review_state") or "filtered_pool_kept"
    item["page_keep_review_reason"] = item.get("page_keep_review_reason") or str(item.get("_filtered_rescue_pool_reason") or "filtered_pool_best_candidate")
    item["kept_progress_from_raw"] = True
    item["readiness_promotion_used"] = True
    item["readiness_promotion_source"] = "filtered_rescue_pool"
    item["filter_decision_profile"] = item.get("filter_decision_profile") or "filtered_pool_kept"
    item["rescue_promoted_from_filter"] = True
    item["direct_candidate_rescue_stage"] = item.get("direct_candidate_rescue_stage") or "filtered_pool"
    if not item.get("direct_candidate_rescue_used"):
        candidates = item.get("answer_candidates") if isinstance(item.get("answer_candidates"), list) else []
        best_candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        item["direct_candidate_rescue_used"] = bool(best_candidate)
        item["direct_candidate_rescue_source"] = str(best_candidate.get("field") or "filtered_pool")
    finalize_direct_candidate_rescue_progress(item, default_stage="filtered_pool")
    claim_evidence.append(item)
    stats["filtered_rescue_pool_state"] = "promoted_best_candidate"
    stats["filtered_rescue_pool_promoted"] = int(stats.get("filtered_rescue_pool_promoted", 0) or 0) + 1
    stats["readiness_promotion_used"] = int(stats.get("readiness_promotion_used", 0) or 0) + 1
    increment_named_counter(stats, "readiness_promotion_source", "filtered_rescue_pool")
    return True


def add_filtered_sample(stats: Dict[str, Any], reason: str, item: Dict[str, Any]) -> None:
    samples = stats.setdefault("filtered_samples", [])
    if len(samples) >= 8:
        return
    samples.append(
        {
            "reason": reason,
            "source": item.get("source"),
            "source_type": item.get("source_type"),
            "query_origin": item.get("query_origin"),
            "query_goal": item.get("query_goal"),
            "title": item.get("title"),
            "url": item.get("url"),
            "relevance_score": item.get("relevance_score", 0),
            "entity_match_count": item.get("entity_match_count", 0),
            "directness_score": item.get("directness_score", 0),
            "source_quality_score": item.get("source_quality_score"),
            "source_quality_label": item.get("source_quality_label"),
            "source_quality_reasons": item.get("source_quality_reasons", []),
            "page_intent_score": item.get("page_intent_score"),
            "page_intent_label": item.get("page_intent_label"),
            "page_intent_issues": item.get("page_intent_issues", []),
            "page_intent_matched": item.get("page_intent_matched", []),
            "page_utility_rule_score": item.get("page_utility_rule_score"),
            "page_utility_score": item.get("page_utility_score"),
            "page_utility_label": item.get("page_utility_label"),
            "page_retention_rule_score": item.get("page_retention_rule_score"),
            "page_retention_score": item.get("page_retention_score"),
            "page_retention_label": item.get("page_retention_label"),
            "page_utility_llm_applied": item.get("page_utility_llm_applied"),
            "page_utility_llm_decision": item.get("page_utility_llm_decision"),
            "page_utility_llm_score": item.get("page_utility_llm_score"),
            "page_utility_llm_page_type": item.get("page_utility_llm_page_type"),
            "page_utility_llm_reason": item.get("page_utility_llm_reason"),
            "page_utility_llm_risks": item.get("page_utility_llm_risks", []),
            "page_utility_page_type": item.get("page_utility_page_type"),
            "page_utility_page_focus": item.get("page_utility_page_focus"),
            "page_utility_page_focus_score": item.get("page_utility_page_focus_score"),
            "page_utility_page_type_signals": item.get("page_utility_page_type_signals", []),
            "page_utility_page_type_risks": item.get("page_utility_page_type_risks", []),
            "page_utility_relation_sentence_count": item.get("page_utility_relation_sentence_count"),
            "page_utility_strong_relation_sentence_count": item.get("page_utility_strong_relation_sentence_count"),
            "page_utility_direct_relation_sentence_count": item.get("page_utility_direct_relation_sentence_count"),
            "page_utility_route_signal_fields": item.get("page_utility_route_signal_fields", []),
            "page_utility_capability": item.get("page_utility_capability", {}),
            "evidence_contract_role": item.get("evidence_contract_role"),
            "evidence_contract_answer_target": item.get("evidence_contract_answer_target"),
            "evidence_contract_required_sentence_shape": item.get("evidence_contract_required_sentence_shape"),
            "evidence_contract_reject_shape": item.get("evidence_contract_reject_shape"),
            "evidence_contract_status": item.get("evidence_contract_status"),
            "evidence_contract_score": item.get("evidence_contract_score"),
            "evidence_contract_signals": item.get("evidence_contract_signals", []),
            "evidence_contract_risks": item.get("evidence_contract_risks", []),
            "page_role": item.get("page_role"),
            "page_role_reason": item.get("page_role_reason"),
            "page_role_contract_score": item.get("page_role_contract_score"),
            "entry_page_follow_required": item.get("entry_page_follow_required"),
            "evidence_page_ready": item.get("evidence_page_ready"),
            "generic_page_block_reason": item.get("generic_page_block_reason"),
            "entry_follow_state": item.get("entry_follow_state"),
            "entry_follow_trigger": item.get("entry_follow_trigger"),
            "entry_follow_block_reason": item.get("entry_follow_block_reason"),
            "route_rerank_score": item.get("route_rerank_score"),
            "noise_penalty": item.get("noise_penalty"),
            "noise_reasons": item.get("noise_reasons", []),
            "keyword_hits": item.get("keyword_hits", {}),
            "route_sentence": item.get("route_sentence", {}),
            "detail_error": item.get("detail_error", ""),
            "detail_error_type": item.get("detail_error_type", ""),
            "answer_candidates": item.get("answer_candidates", [])[:2],
            "answer_candidate_quality_score": item.get("answer_candidate_quality_score"),
            "filter_decision_profile": item.get("filter_decision_profile", ""),
            "recoverable_filter_reason": item.get("recoverable_filter_reason", ""),
            "hard_drop_reason": item.get("hard_drop_reason", ""),
            "readiness_promotion_used": item.get("readiness_promotion_used", False),
            "readiness_promotion_source": item.get("readiness_promotion_source", ""),
            "candidate_strength_before_keep": item.get("candidate_strength_before_keep"),
            "structured_table_best_point": item.get("structured_table_best_point", {}),
            "structured_point_contract_status": item.get("structured_point_contract_status"),
            "structured_point_contract_score": item.get("structured_point_contract_score"),
            "structured_point_contract_signals": item.get("structured_point_contract_signals", []),
            "structured_point_contract_risks": item.get("structured_point_contract_risks", []),
        }
    )


def record_fact_filter_diagnostic(stats: Dict[str, Any], item: Dict[str, Any], kept: bool, filter_reason: str) -> None:
    profile = normalize_text(str(item.get("filter_decision_profile") or ""))
    if not profile:
        if kept:
            profile = "kept"
        elif filter_reason in FACT_PAGE_KEEP_REVIEW_HARD_DROP_REASONS:
            profile = "hard_drop"
        else:
            profile = "filtered"
    increment_named_counter(stats, "filter_decision_profile", profile)
    recoverable_reason = normalize_text(str(item.get("recoverable_filter_reason") or ""))
    if recoverable_reason:
        increment_named_counter(stats, "recoverable_filter_reason", recoverable_reason)
    hard_drop_reason = normalize_text(str(item.get("hard_drop_reason") or ""))
    if hard_drop_reason:
        increment_named_counter(stats, "hard_drop_reason", hard_drop_reason)


def filtered_item_deepen_risk(item: Dict[str, Any], filter_reason: str) -> Dict[str, Any]:
    score = 0
    reasons: List[str] = []
    source_type = str(item.get("source_type") or "")
    quality = int(item.get("source_quality_score") or 0)
    relevance = int(item.get("relevance_score") or 0)
    directness = int(item.get("directness_score") or 0)
    matches = int(item.get("entity_match_count") or 0)
    candidates = item.get("answer_candidates") if isinstance(item.get("answer_candidates"), list) else []
    quality_reasons = item.get("source_quality_reasons") if isinstance(item.get("source_quality_reasons"), list) else []
    if matches >= 2:
        score += 20
        reasons.append("multi_entity_match")
    elif matches == 1:
        score += 8
        reasons.append("entity_match")
    if relevance >= 6:
        score += 18
        reasons.append("relevance_ok")
    elif relevance >= 3:
        score += 8
        reasons.append("relevance_weak")
    if directness >= 4:
        score += 18
        reasons.append("directness_possible")
    elif directness >= 1:
        score += 6
        reasons.append("directness_weak")
    if quality >= 60:
        score += 16
        reasons.append("source_quality_usable")
    elif quality >= 45:
        score += 8
        reasons.append("source_quality_borderline")
    if candidates:
        score += min(16, 6 + 2 * len(candidates))
        reasons.append("has_answer_candidates")
    if source_type in {"official", "news", "finance", "sports"}:
        score += 10
        reasons.append("trusted_source_type")
    if source_type in {"forum", "qa", "encyclopedia"}:
        score -= 10
        reasons.append("weak_or_generic_source_type")
    if "hard_noise_page" in quality_reasons or "weak_source_no_entity_match" in quality_reasons:
        score -= 25
        reasons.append("hard_noise_signal")
    if filter_reason in {"site_domain_mismatch", "sitemap_generic_landing_page"}:
        score -= 20
        reasons.append("reasonable_domain_or_landing_filter")
    score = max(0, min(100, score))
    label = "high" if score >= 70 else "medium" if score >= 45 else "low" if score >= 25 else "very_low"
    return {"score": score, "label": label, "reasons": reasons}


def should_deepen_filtered_item(item: Dict[str, Any], filter_reason: str) -> tuple[bool, Dict[str, Any]]:
    risk = filtered_item_deepen_risk(item, filter_reason)
    if str(risk.get("label")) not in {"high", "medium"}:
        return False, risk
    source_type = str(item.get("source_type") or "")
    if source_type in {"forum", "qa", "encyclopedia"}:
        return False, risk
    if item.get("source") == "domain_sitemap":
        return False, risk
    quality_reasons = item.get("source_quality_reasons") if isinstance(item.get("source_quality_reasons"), list) else []
    if "hard_noise_page" in quality_reasons or "weak_source_no_entity_match" in quality_reasons or "search_engine_result_page" in quality_reasons:
        return False, risk
    parsed = urlparse(str(item.get("url") or ""))
    domain = (parsed.netloc or "").lower()
    if not domain or "." not in domain:
        return False, risk
    if any(blocked in domain for blocked in ["google.", "baidu.com", "sogou.com", "bing.com", "translate.google"]):
        return False, risk
    return True, risk


def add_trusted_deepen_jobs(
    stats: Dict[str, Any],
    source_jobs: List[tuple[str, str]],
    item: Dict[str, Any],
    filter_reason: str,
    source_query: str,
    max_jobs: int = 2,
) -> None:
    if not ENABLE_TRUSTED_FILTER_DEEPEN:
        return
    used = int(stats.get("trusted_deepen_used", 0) or 0)
    if used >= max_jobs:
        return
    should_deepen, risk = should_deepen_filtered_item(item, filter_reason)
    stats.setdefault("filtered_deepen_risk_counts", {})
    risk_counts = stats["filtered_deepen_risk_counts"]
    label = str(risk.get("label") or "unknown")
    risk_counts[label] = int(risk_counts.get(label, 0) or 0) + 1
    if not should_deepen:
        return
    domain = (urlparse(str(item.get("url") or "")).netloc or "").lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain:
        return
    seen_domains = set(stats.get("trusted_deepen_domains") or [])
    if domain in seen_domains:
        return
    sanitized_query = re.sub(r"\bsite:[^\s]+", " ", source_query or "", flags=re.I).strip()
    refined_query = f"site:{domain} {sanitized_query}".strip()
    source_jobs.append(("domain_sitemap", refined_query))
    source_jobs.append(("bing_rss", refined_query))
    stats["trusted_deepen_used"] = used + 1
    stats.setdefault("trusted_deepen_domains", []).append(domain)
    stats.setdefault("trusted_deepen_jobs", []).append(
        {
            "domain": domain,
            "query": refined_query,
            "from_title": item.get("title"),
            "from_url": item.get("url"),
            "filter_reason": filter_reason,
            "risk": risk,
        }
    )


ENTRY_FOLLOW_EVIDENCE_MODES = {"numeric_fact", "date_fact", "schedule_fact", "route_fact", "event_result"}


def should_follow_entry_page(
    item: Dict[str, Any],
    source_intent: Dict[str, Any],
    evidence_mode: str,
) -> Tuple[bool, str]:
    mode = effective_evidence_mode(source_intent, evidence_mode)
    if mode not in ENTRY_FOLLOW_EVIDENCE_MODES:
        return False, "mode_not_entry_follow_target"
    source_type = normalize_text(str(item.get("source_type") or "")).lower()
    source = normalize_text(str(item.get("source") or "")).lower()
    if source_type != "official" and source not in {"official_discovery", "domain_sitemap", "official_inner_link"}:
        return False, "not_authority_entry_source"
    if bool(item.get("evidence_page_ready")):
        return False, "already_evidence_page"
    page_role = normalize_text(str(item.get("page_role") or "")).lower()
    risks = item.get("evidence_contract_risks") if isinstance(item.get("evidence_contract_risks"), list) else []
    if (
        page_role == "entry_page"
        or bool(item.get("entry_page_follow_required"))
        or official_homepage_like(item)
        or "homepage_portal_not_direct_metric_record" in {normalize_text(str(risk)) for risk in risks}
    ):
        return True, "entry_page_requires_inner_evidence"
    return False, "not_entry_page"


def expand_official_inner_link_candidates(
    claim_evidence: List[Dict[str, Any]],
    stats: Dict[str, Any],
    homepage_item: Dict[str, Any],
    source_query: str,
    source_intent: Dict[str, Any],
    claim_item: Dict[str, Any],
    evidence_mode: str,
    evidence_target: str,
    preferred_domains: List[str],
    fetch_details: int,
    detail_fetches: int,
    timeout_sec: int,
    max_results_per_query: int,
) -> int:
    if OFFICIAL_INNER_LINK_MAX_PER_CLAIM <= 0:
        return detail_fetches
    follow_started_at = time.perf_counter()
    homepage_item["entry_follow_state"] = "entry_follow_skipped"
    homepage_item["entry_follow_trigger"] = ""
    homepage_item["entry_follow_block_reason"] = ""
    if str(homepage_item.get("source_type") or "") != "official":
        homepage_item["entry_follow_block_reason"] = "not_official_source"
        return detail_fetches
    should_follow, follow_reason = should_follow_entry_page(homepage_item, source_intent, evidence_mode)
    if not should_follow:
        homepage_item["entry_follow_block_reason"] = follow_reason
        return detail_fetches
    homepage_item["entry_follow_state"] = "entry_follow_attempted"
    homepage_item["entry_follow_trigger"] = follow_reason
    stats["entry_follow_state"] = "entry_follow_attempted"
    stats.setdefault("entry_follow_triggers", {})[follow_reason] = int(stats.setdefault("entry_follow_triggers", {}).get(follow_reason, 0) or 0) + 1
    used = int(stats.get("official_inner_link_bridge_used", 0) or 0)
    if used >= OFFICIAL_INNER_LINK_MAX_PER_CLAIM:
        homepage_item["entry_follow_state"] = "entry_follow_skipped"
        homepage_item["entry_follow_block_reason"] = "entry_follow_budget_exhausted"
        stats["entry_follow_block_reason"] = "entry_follow_budget_exhausted"
        return detail_fetches
    seen_domains = set(stats.get("official_inner_link_bridge_domains") or [])
    homepage_domain = normalize_domain(urlparse(str(homepage_item.get("url") or "")).netloc)
    if homepage_domain in seen_domains:
        homepage_item["entry_follow_state"] = "entry_follow_skipped"
        homepage_item["entry_follow_block_reason"] = "entry_domain_already_followed"
        stats["entry_follow_block_reason"] = "entry_domain_already_followed"
        return detail_fetches
    bridge_candidates = official_inner_link_candidates(
        str(homepage_item.get("url") or ""),
        source_intent,
        preferred_domains=preferred_domains,
        timeout_sec=timeout_sec,
        max_candidates=min(3, max(1, OFFICIAL_INNER_LINK_MAX_PER_CLAIM)),
    )
    if not bridge_candidates:
        homepage_item["entry_follow_state"] = "entry_follow_failed"
        homepage_item["entry_follow_block_reason"] = "no_inner_link_candidates"
        stats["entry_follow_state"] = "entry_follow_failed"
        stats["entry_follow_block_reason"] = "no_inner_link_candidates"
        stats["entry_follow_latency_ms"] = round((time.perf_counter() - follow_started_at) * 1000.0, 1)
        return detail_fetches
    stats["official_inner_link_bridge_used"] = used + 1
    stats.setdefault("official_inner_link_bridge_domains", []).append(homepage_domain)
    stats.setdefault("official_inner_link_bridge_examples", []).append(
        {
            "from_url": homepage_item.get("url"),
            "query": source_query,
            "candidate_urls": [item.get("url") for item in bridge_candidates[:4]],
        }
    )
    stats["entry_follow_candidates"] = [
        {
            "title": str(item.get("title") or ""),
            "url": str(item.get("url") or ""),
            "snippet": str(item.get("snippet") or ""),
        }
        for item in bridge_candidates[:4]
    ]
    existing_urls = {str(item.get("url") or "") for item in claim_evidence if isinstance(item, dict)}
    kept_before = int(stats.get("official_inner_link_kept", 0) or 0)
    kept_evidence_pages = 0
    for item in bridge_candidates:
        if sum(1 for ev in claim_evidence if ev.get("source_type") not in {"input_context", "computed"}) >= max_results_per_query:
            break
        if str(item.get("url") or "") in existing_urls:
            continue
        item["query_origin"] = str(homepage_item.get("query_origin") or "official_inner_link")
        item["query_goal"] = str(homepage_item.get("query_goal") or "find_metric_source_page")
        item["bridge_from_url"] = str(homepage_item.get("url") or "")
        item["bridge_type"] = "official_inner_link"
        item["entry_follow_state"] = "entry_follow_child"
        item["entry_follow_trigger"] = follow_reason
        item["relevance_score"] = evidence_relevance_score(source_query, item)
        item["entity_match_count"] = entity_match_count(source_query, item)
        item["temporal_score"] = evidence_temporal_score(source_query, item)
        item["event_window_score"] = event_window_score(source_query, item, evidence_mode)
        item.update(source_quality_features(source_query, item, evidence_mode, preferred_domains))
        item.update(page_intent_features(item, source_intent, source_query, stats))
        record_page_intent_stats(stats, item)
        if (
            fetch_details > 0
            and item.get("url")
            and detail_fetches < FETCH_DETAILS_PER_CLAIM
        ):
            stats["detail_attempts"] = int(stats.get("detail_attempts", 0) or 0) + 1
            detail_trace: Dict[str, Any] = {}
            try:
                detail_started = time.perf_counter()
                raw_chars = 5000 if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"} else 1600
                passage_chars = 1800 if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"} else 900
                page_text = fetch_page_text(str(item["url"]), max_chars=raw_chars, timeout_sec=timeout_sec, trace=detail_trace)
                item["detail"] = extract_relevant_passage(page_text, passage_focus_terms(source_query, str(item.get("title") or "")), max_chars=passage_chars)
                enrich_structured_table_evidence(item, source_intent, timeout_sec=timeout_sec, fetch_trace=detail_trace)
                apply_detail_fetch_trace(stats, item, detail_trace, "official_inner_link")
                detail_fetches += 1
                stats["detail_successes"] = int(stats.get("detail_successes", 0) or 0) + 1
                add_timing(stats, "fetch_detail", time.perf_counter() - detail_started)
            except Exception as exc:
                add_timing(stats, "fetch_detail", time.perf_counter() - detail_started if "detail_started" in locals() else 0.0)
                apply_detail_fetch_trace(stats, item, detail_trace, "official_inner_link")
                record_detail_fetch_failure(stats, item, exc, "official_inner_link")
        item["relevance_score"] = evidence_relevance_score(source_query, item)
        item["entity_match_count"] = entity_match_count(source_query, item)
        item["directness_score"] = evidence_directness_score(source_query, item, evidence_mode)
        item["temporal_score"] = evidence_temporal_score(source_query, item)
        item["event_window_score"] = event_window_score(source_query, item, evidence_mode)
        item["answer_candidates"] = answer_candidate_sentences(source_query, item, evidence_mode=evidence_mode)
        maybe_apply_deterministic_candidate_rescue(claim_item, item, evidence_mode, source_query)
        item["answer_candidate_quality_score"] = answer_candidate_quality_score(item)
        if item.get("direct_candidate_rescue_used"):
            stats["direct_candidate_rescue_used"] = int(stats.get("direct_candidate_rescue_used", 0) or 0) + 1
            source_field = str(item.get("direct_candidate_rescue_source") or "")
            if source_field:
                increment_named_counter(stats, "direct_candidate_rescue_sources", source_field)
        item.update(task_card_match_features(item, claim_item.get("evidence_task_card", {}) if isinstance(claim_item.get("evidence_task_card"), dict) else {}))
        item.update(source_quality_features(source_query, item, evidence_mode, preferred_domains))
        item.update(page_intent_features(item, source_intent, source_query, stats))
        record_page_intent_stats(stats, item)
        if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}:
            item.update(structured_noise_features(source_query, item, evidence_mode))
        keep_item, filter_reason = web_evidence_filter_reason(source_query, item, evidence_mode)
        task_card = claim_item.get("evidence_task_card", {}) if isinstance(claim_item.get("evidence_task_card"), dict) else {}
        if not keep_item and should_soft_keep_high_priority_item(item, filter_reason, evidence_mode, task_card):
            keep_item = True
            filter_reason = "soft_keep_high_priority_structured_candidate"
        if not keep_item and should_soft_keep_structured_metric_item(item, filter_reason, evidence_mode, task_card):
            original_filter_reason = filter_reason
            keep_item = True
            filter_reason = "soft_keep_structured_metric_table_candidate"
            annotate_soft_kept_structured_metric_item(item, source_query, evidence_mode, original_filter_reason, claim_item)
        if not keep_item and should_soft_keep_claim_aligned_fact_item(source_query, item, filter_reason, evidence_mode, claim_item):
            original_filter_reason = filter_reason
            keep_item = True
            filter_reason = "soft_keep_claim_aligned_fact_page"
            annotate_soft_kept_claim_aligned_item(item, source_query, evidence_mode, original_filter_reason, claim_item)
        if not keep_item:
            keep_item, filter_reason = maybe_promote_prefilter_candidate_rescue(
                source_query,
                item,
                filter_reason,
                evidence_mode,
                claim_item,
            )
        if keep_item:
            finalize_direct_candidate_rescue_progress(item, default_stage="post_keep")
            record_source_item_quality(stats, "official_inner_link", item, kept=True)
            claim_evidence.append(item)
            existing_urls.add(str(item.get("url") or ""))
            stats["official_inner_link_kept"] = int(stats.get("official_inner_link_kept", 0) or 0) + 1
            if str(item.get("page_role") or "") == "evidence_page":
                kept_evidence_pages += 1
        else:
            record_source_item_quality(stats, "official_inner_link", item, kept=False, filter_reason=filter_reason)
            stats["filtered_results"] = int(stats.get("filtered_results", 0) or 0) + 1
            add_filter_reason(stats, filter_reason)
            add_filtered_sample(stats, filter_reason, item)
    kept_after = int(stats.get("official_inner_link_kept", 0) or 0)
    if kept_evidence_pages > 0:
        homepage_item["entry_follow_state"] = "entry_follow_succeeded"
        stats["entry_follow_state"] = "entry_follow_succeeded"
        stats["entry_follow_kept_evidence_pages"] = kept_evidence_pages
    elif kept_after > kept_before:
        homepage_item["entry_follow_state"] = "entry_follow_partial_entry_only"
        homepage_item["entry_follow_block_reason"] = "inner_link_kept_but_not_evidence_page"
        stats["entry_follow_state"] = "entry_follow_partial_entry_only"
        stats["entry_follow_block_reason"] = "inner_link_kept_but_not_evidence_page"
        stats["entry_follow_kept_evidence_pages"] = 0
    else:
        homepage_item["entry_follow_state"] = "entry_follow_failed"
        homepage_item["entry_follow_block_reason"] = "inner_link_candidates_not_kept"
        stats["entry_follow_state"] = "entry_follow_failed"
        stats["entry_follow_block_reason"] = "inner_link_candidates_not_kept"
        stats["entry_follow_kept_evidence_pages"] = 0
    stats["entry_follow_latency_ms"] = round((time.perf_counter() - follow_started_at) * 1000.0, 1)
    return detail_fetches


def apply_evidence_budget(evidence: List[Dict[str, Any]], max_web: int) -> List[Dict[str, Any]]:
    context_items = [item for item in evidence if item.get("source_type") == "input_context"][:1]
    computed_items = [item for item in evidence if item.get("source_type") == "computed"][:2]
    strong_web = [
        item
        for item in evidence
        if item.get("source_type") in {"official", "news", "encyclopedia"}
    ]
    weak_web = [
        item
        for item in evidence
        if item.get("source_type") in {"forum", "unknown"}
    ]
    strong_web.sort(
        key=lambda item: (
            item.get("source_type") == "official",
            item.get("source_quality_score", 0),
            answer_candidate_quality_score(item),
            item.get("route_rerank_score", 0),
            item.get("directness_score", 0),
            item.get("event_window_score", 0),
            item.get("temporal_score", 0),
            item.get("relevance_score", 0),
            item.get("entity_match_count", 0),
        ),
        reverse=True,
    )
    weak_web.sort(
        key=lambda item: (
            answer_candidate_quality_score(item),
            item.get("directness_score", 0),
            item.get("source_quality_score", 0),
            item.get("route_rerank_score", 0),
            item.get("event_window_score", 0),
            item.get("relevance_score", 0),
            item.get("entity_match_count", 0),
        ),
        reverse=True,
    )
    selected = context_items + computed_items
    selected.extend(strong_web[:max_web])
    if len(strong_web) < max_web:
        selected.extend(weak_web[: max(0, max_web - len(strong_web))])

    deduped = []
    seen = set()
    for item in selected:
        key = item.get("url") or f"{item.get('source_type')}:{item.get('title')}:{item.get('snippet')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def should_prioritize_english_queries(evidence_mode: str) -> bool:
    mode = policy_mode_label(evidence_mode)
    return mode in {"event_result", "policy_fact"}


def is_english_query(query: str) -> bool:
    letters = sum(1 for ch in query if "a" <= ch.lower() <= "z")
    cjk = sum(1 for ch in query if "\u4e00" <= ch <= "\u9fff")
    return letters >= 12 and letters >= cjk


def order_query_plan(query_plan: List[Dict[str, str]], evidence_mode: str, source_intent: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    if not should_prioritize_english_queries(evidence_mode):
        return query_plan
    indexed_plan = list(enumerate(query_plan or []))
    ranked = sorted(
        indexed_plan,
        key=lambda pair: (
            query_priority_score(pair[1], evidence_mode, source_intent),
            1 if is_english_query(pair[1].get("q", "")) else 0,
            -pair[0],
        ),
        reverse=True,
    )
    return [item for _, item in ranked]


def select_query_plan(query_plan: List[Dict[str, Any]], limit: int, evidence_mode: str = "", source_intent: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    if len(query_plan) <= limit:
        return query_plan
    indexed_plan = list(enumerate(query_plan))
    ranked = sorted(
        indexed_plan,
        key=lambda pair: (query_priority_score(pair[1], evidence_mode, source_intent), -pair[0]),
        reverse=True,
    )
    qa_items = [item for item in query_plan if item.get("goal") == "verification_question"]
    selected = [item for _, item in ranked[:limit]]
    if qa_items and not any(item.get("goal") == "verification_question" for item in selected):
        selected = selected[: max(0, limit - 1)] + [qa_items[0]]
    if selected and all(extract_site_constraint(item.get("q", "")) for item in selected):
        fallback = next((item for _, item in ranked if not extract_site_constraint(item.get("q", ""))), None)
        if fallback:
            selected = selected[: max(0, limit - 1)] + [fallback]
    deduped: List[Dict[str, str]] = []
    seen = set()
    for item in selected:
        key = normalize_text(item.get("q") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:limit]


def dedupe_query_plan_keep_order(query_plan: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in query_plan or []:
        if not isinstance(item, dict):
            continue
        key = normalize_text(item.get("q") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:limit]


def should_preserve_preferred_domain_query(
    source_intent: Dict[str, Any],
    task_card: Optional[Dict[str, Any]] = None,
    evidence_mode: str = "",
) -> bool:
    preferred_domains = preferred_domains_from_intent(source_intent)
    if not preferred_domains:
        return False
    shape = normalize_evidence_shape(source_intent)
    if shape in {"authoritative_notice", "structured_historical_data"}:
        return True
    if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}:
        return True
    preferred_types = [normalize_text(str(item)).lower() for item in source_intent.get("preferred_source_types") or []]
    if any("official" in item for item in preferred_types):
        return True
    source_strategy = source_intent.get("source_strategy") if isinstance(source_intent.get("source_strategy"), dict) else {}
    strategy_types = [normalize_text(str(item)).lower() for item in source_strategy.get("source_types") or []]
    if any("official" in item for item in strategy_types):
        return True
    if task_card and normalize_text(str(task_card.get("evidence_shape") or "")).lower() in {"authoritative_notice", "structured_historical_data"}:
        return True
    return False


def preferred_domain_query_item(
    query_plan: List[Dict[str, Any]],
    preferred_domains: List[str],
) -> Optional[Dict[str, Any]]:
    if not preferred_domains:
        return None
    preferred_set = {normalize_domain(domain) for domain in preferred_domains if normalize_domain(domain)}
    if not preferred_set:
        return None
    for item in query_plan or []:
        if not isinstance(item, dict):
            continue
        if normalize_text(str(item.get("origin") or "")) == "preferred_domain_probe":
            return item
    for item in query_plan or []:
        if not isinstance(item, dict):
            continue
        site = extract_site_constraint(item.get("q", ""))
        if site and site in preferred_set:
            return item
    return None


def preferred_domain_query_items(
    query_plan: List[Dict[str, Any]],
    preferred_domains: List[str],
) -> List[Dict[str, Any]]:
    if not preferred_domains:
        return []
    preferred_set = {normalize_domain(domain) for domain in preferred_domains if normalize_domain(domain)}
    if not preferred_set:
        return []
    selected: List[Dict[str, Any]] = []
    seen_sites = set()
    for item in query_plan or []:
        if not isinstance(item, dict):
            continue
        if normalize_text(str(item.get("origin") or "")) != "preferred_domain_probe":
            continue
        site = normalize_domain(extract_site_constraint(item.get("q", "")))
        if site and site in preferred_set and site not in seen_sites:
            selected.append(item)
            seen_sites.add(site)
    if selected:
        return selected
    fallback = preferred_domain_query_item(query_plan, preferred_domains)
    return [fallback] if isinstance(fallback, dict) else []


def metric_slots_from_intent(source_intent: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(source_intent, dict):
        return {}
    for key in ("metric_slots", "_retry_metric_slots"):
        metric_slots = source_intent.get(key)
        if isinstance(metric_slots, dict) and metric_slots:
            return metric_slots
    return {}


def core_binding_from_intent(source_intent: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(source_intent, dict):
        return {}
    binding = source_intent.get("core_binding") if isinstance(source_intent.get("core_binding"), dict) else {}
    metric_slots = metric_slots_from_intent(source_intent)
    return {
        "subject_entity": normalize_text(str(binding.get("subject_entity") or metric_slots.get("subject_entity") or "")),
        "object_entity": normalize_text(str(binding.get("object_entity") or "")),
        "relation_or_metric": normalize_text(str(binding.get("relation_or_metric") or metric_slots.get("metric_name") or "")),
        "time_scope": normalize_text(str(binding.get("time_scope") or metric_slots.get("time_scope") or "")),
        "authority_scope": normalize_text(str(binding.get("authority_scope") or metric_slots.get("source_authority") or "")),
        "expected_evidence_shape": normalize_text(str(binding.get("expected_evidence_shape") or metric_slots.get("expected_evidence_shape") or "")),
        "reject_evidence_shape": normalize_text(str(binding.get("reject_evidence_shape") or metric_slots.get("reject_evidence_shape") or "")),
    }


def typed_extension_from_intent(source_intent: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(source_intent, dict):
        return {}
    typed_extension = source_intent.get("typed_extension")
    return typed_extension if isinstance(typed_extension, dict) else {}


def looks_like_internal_schema_token(value: str) -> bool:
    text = normalize_text(value).lower()
    if not text:
        return False
    return bool(re.fullmatch(r"[a-z0-9_:-]{4,}", text))


def binding_term_present(text: str, value: str, max_tokens: int = 4) -> bool:
    haystack = normalize_text(text).lower()
    needle = normalize_text(value)
    if not haystack or not needle:
        return False
    if needle.lower() in haystack:
        return True
    tokens = [token.lower() for token in compact_query_seed_tokens(needle, max_tokens) if token]
    if not tokens:
        return False
    min_hits = 1 if len(tokens) <= 2 else 2
    hits = sum(1 for token in tokens if token in haystack)
    return hits >= min_hits


def binding_slot_search_values(
    key: str,
    value: str,
    source_intent: Dict[str, Any],
    evidence_mode: str,
) -> List[str]:
    normalized = normalize_text(value)
    if not normalized:
        return []
    metric_slots = metric_slots_from_intent(source_intent)
    typed_extension = typed_extension_from_intent(source_intent)
    numeric_extension = typed_extension.get("numeric") if isinstance(typed_extension.get("numeric"), dict) else {}
    evidence_shape = normalize_text(str(source_intent.get("evidence_shape") or ""))
    terms: List[str] = []

    if key == "authority_scope":
        authority = normalized.lower()
        for term in METRIC_SOURCE_AUTHORITY_QUERY_TERMS.get(authority, [])[:4]:
            append_query_term_unique(terms, term)
        extra_authority_terms = {
            "bank_rate_table": ["银行牌价", "外汇牌价"],
            "central_bank": ["央行", "中间价"],
            "exchange": ["交易所", "行情页面"],
            "official_notice": ["官网公告", "官方通知"],
            "financial_quote_page": ["行情页", "报价页"],
            "market_data_page": ["历史数据", "报价数据"],
            "price_monitoring_report": ["监测报告", "价格报告"],
        }
        for term in extra_authority_terms.get(authority, [])[:2]:
            append_query_term_unique(terms, term)
        if not terms and not looks_like_internal_schema_token(normalized):
            append_query_term_unique(terms, normalized)
        return terms[:5]

    if key == "relation_or_metric":
        cleaned_relation = normalize_text(
            re.sub(
                r"(及其对应数值|对应数值|实际数值|牌价中的|对应的|数值结果|具体数值)",
                " ",
                normalized,
                flags=re.I,
            )
        )
        if cleaned_relation and len(cleaned_relation) <= 20:
            append_query_term_unique(terms, cleaned_relation)
        else:
            for token in compact_query_seed_tokens(cleaned_relation or normalized, 4):
                append_query_term_unique(terms, token)
        metric_scope = normalize_text(str(numeric_extension.get("metric_scope") or ""))
        if metric_scope:
            append_query_term_unique(terms, metric_scope)
        value_type = normalize_text(str(metric_slots.get("value_type") or ""))
        include_generic_value_terms = not (
            value_type == "generic_value"
            and (
                any(token in " ".join(terms) for token in ["买入价", "卖出价", "牌价", "汇率", "中间价"])
                or "bank_rate_table" == normalize_text(str(metric_slots.get("source_authority") or "")).lower()
            )
        )
        if include_generic_value_terms:
            for term in METRIC_VALUE_TYPE_QUERY_TERMS.get(value_type, [])[:3]:
                append_query_term_unique(terms, term)
        return terms[:5]

    if key == "expected_evidence_shape":
        shape_terms = {
            "structured_historical_data": ["结构化记录", "历史数据表", "数据表"],
            "authoritative_notice": ["公告", "通知", "官方发布"],
        }
        for term in shape_terms.get(evidence_shape, []):
            append_query_term_unique(terms, term)
        if "牌价" in normalized or str(metric_slots.get("source_authority") or "").lower() == "bank_rate_table":
            for term in ["牌价表", "报价表"]:
                append_query_term_unique(terms, term)
        if "表" in normalized:
            append_query_term_unique(terms, "表")
        if not terms and not looks_like_internal_schema_token(normalized):
            append_query_term_unique(terms, normalized)
        return terms[:4]

    if key in {"unit", "time_scope", "time_window"}:
        append_query_term_unique(terms, normalized)
        return terms[:1]

    if not looks_like_internal_schema_token(normalized):
        append_query_term_unique(terms, normalized)
    return terms[:3]


def binding_slot_present(
    text: str,
    key: str,
    value: str,
    source_intent: Dict[str, Any],
    evidence_mode: str,
) -> bool:
    terms = binding_slot_search_values(key, value, source_intent, evidence_mode)
    return any(binding_term_present(text, term) for term in terms)


def best_binding_slot_term(
    key: str,
    value: str,
    source_intent: Dict[str, Any],
    evidence_mode: str,
) -> str:
    terms = binding_slot_search_values(key, value, source_intent, evidence_mode)
    return terms[0] if terms else normalize_text(value)


AUTHORITY_ENTITY_SUFFIXES_ZH = (
    "委员会", "研究院", "基金会", "交易所", "银行", "大学", "学院", "中心",
    "集团", "公司", "部门", "协会", "机构", "政府", "部", "厅", "局",
    "院", "署", "馆", "社", "会",
)

AUTHORITY_ENTITY_SUFFIXES_EN = (
    "bank", "university", "college", "ministry", "department", "administration",
    "committee", "commission", "exchange", "association", "agency", "office",
    "foundation", "corporation", "company", "group", "prize",
)


def extract_authority_entity_hint(source_intent: Dict[str, Any]) -> str:
    binding = core_binding_from_intent(source_intent)
    metric_slots = metric_slots_from_intent(source_intent)
    candidates = [
        str(source_intent.get("authority_subject_hint") or ""),
        str(binding.get("subject_entity") or ""),
        str(metric_slots.get("subject_entity") or ""),
    ]
    for raw in candidates:
        text = normalize_text(raw)
        if not text:
            continue
        text = strip_numeric_values(text)
        zh_match = re.search(rf"(.+?(?:{'|'.join(AUTHORITY_ENTITY_SUFFIXES_ZH)}))", text)
        if zh_match:
            return normalize_text(zh_match.group(1))
        tokens = re.findall(r"[A-Za-z][A-Za-z.&-]*", text)
        if tokens:
            acc: List[str] = []
            for token in tokens:
                acc.append(token)
                if token.lower().rstrip(".,") in AUTHORITY_ENTITY_SUFFIXES_EN:
                    return normalize_text(" ".join(acc))
    return ""


def shared_authority_hint_key(source_intent: Dict[str, Any]) -> Tuple[str, str]:
    binding = core_binding_from_intent(source_intent)
    metric_slots = metric_slots_from_intent(source_intent)
    authority_scope = normalize_text(
        str(binding.get("authority_scope") or metric_slots.get("source_authority") or "")
    ).lower()
    time_scope = normalize_text(str(binding.get("time_scope") or metric_slots.get("time_scope") or ""))
    return authority_scope, time_scope


def build_shared_authority_subject_hints(claims: List[Dict[str, Any]]) -> Dict[Tuple[str, str], str]:
    hints: Dict[Tuple[str, str], str] = {}
    for claim_item in claims:
        source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
        if not source_intent:
            continue
        key = shared_authority_hint_key(source_intent)
        authority_scope, _time_scope = key
        if not authority_scope:
            continue
        hint = extract_authority_entity_hint(source_intent)
        if not hint:
            continue
        previous = hints.get(key, "")
        if len(hint) > len(previous):
            hints[key] = hint
        fallback_key = (authority_scope, "")
        previous_fallback = hints.get(fallback_key, "")
        if len(hint) > len(previous_fallback):
            hints[fallback_key] = hint
    return hints


def enrich_source_intent_with_shared_authority_hint(
    source_intent: Dict[str, Any],
    shared_hints: Dict[Tuple[str, str], str],
) -> Dict[str, Any]:
    if not shared_hints or extract_authority_entity_hint(source_intent):
        return source_intent
    key = shared_authority_hint_key(source_intent)
    authority_scope, _time_scope = key
    if not authority_scope:
        return source_intent
    shared_hint = shared_hints.get(key) or shared_hints.get((authority_scope, ""))
    shared_hint = normalize_text(shared_hint)
    if not shared_hint:
        return source_intent
    binding = core_binding_from_intent(source_intent)
    metric_slots = metric_slots_from_intent(source_intent)
    binding_subject = normalize_text(str(binding.get("subject_entity") or ""))
    metric_subject = normalize_text(str(metric_slots.get("subject_entity") or ""))
    updated = dict(source_intent)
    updated["authority_subject_hint"] = shared_hint
    if binding_subject and shared_hint not in binding_subject:
        new_binding = dict(binding)
        new_binding["subject_entity"] = normalize_text(f"{shared_hint} {binding_subject}")
        updated["core_binding"] = new_binding
    if metric_subject and shared_hint not in metric_subject:
        new_metric_slots = dict(metric_slots)
        new_metric_slots["subject_entity"] = normalize_text(f"{shared_hint} {metric_subject}")
        updated["metric_slots"] = new_metric_slots
    return updated


def source_strategy_binding_terms(source_intent: Dict[str, Any], evidence_mode: str) -> Dict[str, str]:
    binding = core_binding_from_intent(source_intent)
    metric_slots = metric_slots_from_intent(source_intent)
    typed_extension = typed_extension_from_intent(source_intent)
    numeric_extension = typed_extension.get("numeric") if isinstance(typed_extension.get("numeric"), dict) else {}
    date_extension = typed_extension.get("date") if isinstance(typed_extension.get("date"), dict) else {}
    out = {
        "subject_entity": str(binding.get("subject_entity") or ""),
        "relation_or_metric": str(binding.get("relation_or_metric") or ""),
        "time_scope": str(binding.get("time_scope") or ""),
        "authority_scope": str(binding.get("authority_scope") or ""),
        "expected_evidence_shape": str(binding.get("expected_evidence_shape") or ""),
    }
    if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}:
        out["unit"] = normalize_text(str(numeric_extension.get("unit") or metric_slots.get("unit") or ""))
    if evidence_mode in {"date_fact", "schedule_fact"}:
        out["time_window"] = normalize_text(str(date_extension.get("time_window") or ""))
    return {key: value for key, value in out.items() if value}


def ranked_query_plan_items(query_plan: List[Dict[str, Any]], evidence_mode: str = "", source_intent: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    indexed_plan = list(enumerate(query_plan or []))
    ranked = sorted(
        indexed_plan,
        key=lambda pair: (query_priority_score(pair[1], evidence_mode, source_intent), -pair[0]),
        reverse=True,
    )
    return [item for _, item in ranked]


def append_unique_query_item(
    selected: List[Dict[str, Any]],
    item: Optional[Dict[str, Any]],
    limit: int,
) -> None:
    if limit <= 0 or len(selected) >= limit or not isinstance(item, dict):
        return
    query_text = normalize_text(str(item.get("q") or ""))
    if not query_text:
        return
    if any(normalize_text(str(existing.get("q") or "")) == query_text for existing in selected):
        return
    selected.append(item)


def retry_operator_origin_hints(source_intent: Dict[str, Any]) -> Tuple[str, List[str], str]:
    if not isinstance(source_intent, dict):
        return "", [], ""
    primary_origin = normalize_text(str(source_intent.get("_retry_operator_origin") or source_intent.get("_retry_operator_origin_llm") or ""))
    variant_hint = normalize_text(str(source_intent.get("_retry_operator_variant_hint") or source_intent.get("_retry_operator_variant_hint_llm") or ""))
    supporting_origins_raw = source_intent.get("_retry_operator_supporting_origins") if isinstance(source_intent.get("_retry_operator_supporting_origins"), list) else []
    if not supporting_origins_raw:
        supporting_origins_raw = source_intent.get("_retry_operator_supporting_origins_llm") if isinstance(source_intent.get("_retry_operator_supporting_origins_llm"), list) else []
    supporting_origins = [
        normalize_text(str(item))
        for item in supporting_origins_raw
        if normalize_text(str(item))
    ][:4]
    return primary_origin, supporting_origins, variant_hint


def query_contract_anchor_items(
    query_plan: List[Dict[str, Any]],
    limit: int,
    source_intent: Dict[str, Any],
    task_card: Optional[Dict[str, Any]] = None,
    evidence_mode: str = "",
) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    profile = retrieval_profile(source_intent)
    preferred_domains = preferred_domains_from_intent(source_intent)
    evidence_target = str(source_intent.get("evidence_target") or "general")
    mechanism_type = mechanism_type_from_intent(source_intent)
    is_retry = bool(source_intent.get("_is_retry"))
    planner_query_keys = {
        normalize_text(str(item.get("q") or ""))
        for item in query_plan
        if (
            normalize_text(str(item.get("goal") or "")) in {"discover_truth", "find_news", "verify_original", "find_context"}
            or bool(item.get("source_preference"))
        )
    }
    site_planner_items = [
        item
        for item in query_plan
        if normalize_text(str(item.get("q") or "")) in planner_query_keys
        and extract_site_constraint(str(item.get("q") or ""))
    ]
    intent_origins = {"page_intent_retry", "gap_pseudo_page_probe", "page_shape_probe"}
    intent_query_keys = {
        normalize_text(str(item.get("q") or ""))
        for item in query_plan
        if normalize_text(str(item.get("origin") or "")) in intent_origins
    }
    selected: List[Dict[str, Any]] = []
    primary_retry_origin, supporting_retry_origins, variant_hint = retry_operator_origin_hints(source_intent)

    fact_slot_item = next(
        (
            item for item in query_plan
            if normalize_text(str(item.get("origin") or "")) == "fact_slot_query"
            or query_variant_origin_value(item).startswith("fact_slot_query")
        ),
        None,
    )
    append_unique_query_item(selected, fact_slot_item, limit)

    if is_retry and site_planner_items and (
        mechanism_type in {"structured_numeric_authority", "date_authority"}
        or evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}
        or evidence_target in {"market_price", "market_calendar", "prize_amount", "position_distance"}
    ):
        append_unique_query_item(selected, site_planner_items[0], limit)

    if primary_retry_origin:
        primary_items = [
            item
            for item in query_plan
            if normalize_text(str(item.get("origin") or "")) == primary_retry_origin
        ]
        if variant_hint:
            variant_match = next(
                (
                    item for item in primary_items
                    if normalize_text(str(item.get("variant") or "")) == variant_hint
                ),
                None,
            )
            append_unique_query_item(selected, variant_match, limit)
        append_unique_query_item(selected, next(iter(primary_items), None), limit)
        for support_origin in supporting_retry_origins[:2]:
            support_item = next(
                (
                    item for item in query_plan
                    if normalize_text(str(item.get("origin") or "")) == support_origin
                ),
                None,
            )
            append_unique_query_item(selected, support_item, limit)

    if should_preserve_preferred_domain_query(source_intent, task_card, evidence_mode):
        mechanism_type = mechanism_type_from_intent(source_intent)
        retry_gap_flags = source_intent.get("_retry_gap_flags") if isinstance(source_intent.get("_retry_gap_flags"), list) else []
        point_gap_retry = source_intent.get("_is_retry") and any(str(flag).startswith("point_") for flag in retry_gap_flags)
        preferred_items = preferred_domain_query_items(query_plan, preferred_domains)
        preferred_limit = 2 if (
            mechanism_type in {"structured_numeric_authority", "date_authority"}
            or evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}
        ) else 1
        if point_gap_retry and preferred_limit > 1:
            preferred_limit = 1
        for item in preferred_items[:preferred_limit]:
            append_unique_query_item(selected, item, limit)

    semantic_probe_item = next(
        (
            item for item in query_plan
            if normalize_text(str(item.get("origin") or "")) == "semantic_task_probe"
        ),
        None,
    )
    append_unique_query_item(selected, semantic_probe_item, limit)

    for required_goal in profile.get("required_goals", []):
        required_item = next((item for item in query_plan if item.get("goal") == required_goal), None)
        append_unique_query_item(selected, required_item, limit)

    retry_gap_flags = source_intent.get("_retry_gap_flags") if isinstance(source_intent.get("_retry_gap_flags"), list) else []
    point_retry_items = [
        item for item in query_plan
        if normalize_text(str(item.get("origin") or "")) == "structured_point_retry"
    ]
    if point_retry_items and any(str(flag).startswith("point_") for flag in retry_gap_flags):
        retry_keep_limit = 2 if ("point_time_scope_mismatch" in retry_gap_flags and limit >= 4) else 1
        for item in point_retry_items[:retry_keep_limit]:
            append_unique_query_item(selected, item, limit)

    metric_item = next(
        (
            item for item in query_plan
            if normalize_text(str(item.get("origin") or "")) == "metric_source_probe"
            or item.get("goal") == "find_metric_source_page"
        ),
        None,
    )
    metric_slots = metric_slots_from_intent(source_intent)
    if metric_item and (
        metric_slots
        or mechanism_type in {"structured_numeric_authority", "date_authority"}
        or evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}
        or evidence_target in {"market_price", "market_calendar", "prize_amount", "position_distance"}
    ):
        append_unique_query_item(selected, metric_item, limit)

    if relation_sentence_intent(source_intent) and limit >= 2:
        route_frame_item = next(
            (item for item in query_plan if normalize_text(str(item.get("origin") or "")) == "route_frame_probe"),
            None,
        )
        semantic_probe_item = next(
            (item for item in query_plan if normalize_text(str(item.get("origin") or "")) == "semantic_task_probe"),
            None,
        )
        gap_probe_item = next(
            (item for item in query_plan if normalize_text(str(item.get("origin") or "")) == "gap_pseudo_page_probe"),
            None,
        )
        append_unique_query_item(selected, semantic_probe_item, limit)
        append_unique_query_item(selected, route_frame_item, limit)
        append_unique_query_item(selected, gap_probe_item, limit)

    if intent_query_keys:
        intent_item = next(
            (
                item for item in query_plan
                if normalize_text(str(item.get("q") or "")) in intent_query_keys
            ),
            None,
        )
        append_unique_query_item(selected, intent_item, limit)

    if planner_query_keys:
        planner_item = next(
            (
                item for item in query_plan
                if normalize_text(str(item.get("q") or "")) in planner_query_keys
                and (
                    is_retry
                    or not extract_site_constraint(item.get("q", ""))
                )
            ),
            None,
        )
        if planner_item is None:
            planner_item = next(
                (
                    item for item in query_plan
                    if normalize_text(str(item.get("q") or "")) in planner_query_keys
                ),
                None,
            )
        append_unique_query_item(selected, planner_item, limit)

    if limit >= 3:
        qa_item = next((item for item in query_plan if item.get("goal") == "verification_question"), None)
        append_unique_query_item(selected, qa_item, limit)

    return selected[:limit]


def fill_query_plan_by_priority(
    selected: List[Dict[str, Any]],
    ranked: List[Dict[str, Any]],
    limit: int,
    preferred_domains: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    out = list(selected)
    preferred_domains = preferred_domains or []
    prefer_non_site = bool(preferred_domains) and any(
        extract_site_constraint(item.get("q", "")) in preferred_domains
        for item in out
    )
    if prefer_non_site and not any(not extract_site_constraint(item.get("q", "")) for item in out):
        for item in ranked:
            if extract_site_constraint(item.get("q", "")):
                continue
            append_unique_query_item(out, item, limit)
            if len(out) >= limit:
                return out[:limit]
    for item in ranked:
        append_unique_query_item(out, item, limit)
        if len(out) >= limit:
            break
    return out[:limit]


def select_query_plan_with_contract(
    query_plan: List[Dict[str, Any]],
    limit: int,
    source_intent: Dict[str, Any],
    task_card: Optional[Dict[str, Any]] = None,
    evidence_mode: str = "",
) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    if len(query_plan) <= limit:
        return dedupe_query_plan_keep_order(query_plan, limit)
    preferred_domains = preferred_domains_from_intent(source_intent)
    selected = query_contract_anchor_items(query_plan, limit, source_intent, task_card, evidence_mode)
    ranked = ranked_query_plan_items(query_plan, evidence_mode, source_intent)
    selected = fill_query_plan_by_priority(selected, ranked, limit, preferred_domains)
    return dedupe_query_plan_keep_order(selected, limit)


def apply_query_plan_policy(
    query_plan: List[Dict[str, Any]],
    limit: int,
    source_intent: Dict[str, Any],
    task_card: Optional[Dict[str, Any]] = None,
    evidence_mode: str = "",
) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    deduped: List[Dict[str, Any]] = []
    seen_query_keys = set()
    for item in query_plan or []:
        if not isinstance(item, dict):
            continue
        query_text = normalize_text(str(item.get("q") or ""))
        if not query_text or query_text in seen_query_keys:
            continue
        seen_query_keys.add(query_text)
        query_item: Dict[str, Any] = {
            "q": query_text,
            "goal": normalize_text(str(item.get("goal") or "general_verify")) or "general_verify",
            "origin": normalize_text(str(item.get("origin") or "")) or "planner",
        }
        raw_preference = item.get("source_preference") if isinstance(item.get("source_preference"), list) else []
        source_preference = [normalize_text(str(value)) for value in raw_preference if normalize_text(str(value))][:3]
        if source_preference:
            query_item["source_preference"] = source_preference
        for extra_key in ("operator", "variant", "gap_flag", "query_variant_origin", "atomic_claim_id", "atomic_risk_type", "atomic_claim_text"):
            extra_value = normalize_text(str(item.get(extra_key) or ""))
            if extra_value:
                query_item[extra_key] = extra_value
        if item.get("atomic_query"):
            query_item["atomic_query"] = True
        deduped.append(query_item)
    if not deduped:
        return []
    selected = select_query_plan_with_contract(deduped, limit, source_intent, task_card, evidence_mode)
    priority_label = str((task_card or {}).get("priority_label") or "")
    evidence_target = str(source_intent.get("evidence_target") or "general")
    if (
        priority_label in {"critical", "high"}
        and evidence_mode in {"entity_fact", "numeric_fact", "date_fact", "schedule_fact", "event_result", "policy_fact"}
        and selected
        and all(item.get("goal") == "verification_question" for item in selected)
    ):
        lexical_fallback = next(
            (
                item for item in deduped
                if item.get("goal") != "verification_question"
                and not extract_site_constraint(item.get("q", ""))
            ),
            None,
        )
        if lexical_fallback:
            merged = [lexical_fallback] + [item for item in selected if item.get("q") != lexical_fallback.get("q")]
            deduped_selected: List[Dict[str, Any]] = []
            seen_query_keys = set()
            for item in merged:
                key = normalize_text(str(item.get("q") or ""))
                if not key or key in seen_query_keys:
                    continue
                seen_query_keys.add(key)
                deduped_selected.append(item)
            selected = deduped_selected[:limit]
    if evidence_target in {"match_result", "withdrawal_status", "market_calendar", "census_phase", "position_distance", "current_status"}:
        target_fallback = next(
            (
                item for item in deduped
                if not extract_site_constraint(item.get("q", ""))
                and item.get("goal") in {"find_result", "verify_date_detail", "verify_numeric_detail"}
            ),
            None,
        )
        if target_fallback and all(item.get("q") != target_fallback.get("q") for item in selected):
            selected = selected[: max(0, limit - 1)] + [target_fallback]
    return dedupe_query_plan_keep_order(selected, limit)


def ensure_verification_query(
    query_plan: List[Dict[str, str]],
    claim_item: Dict[str, Any],
    claim: str,
    source_intent: Dict[str, Any],
    limit: int,
) -> List[Dict[str, str]]:
    if limit <= 0 or any(item.get("goal") == "verification_question" for item in query_plan):
        return query_plan
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or ""))
    mechanism_type = mechanism_type_from_intent(source_intent)
    preferred_domains = preferred_domains_from_intent(source_intent)
    if limit <= 2 and evidence_mode == "route_fact":
        return query_plan
    site_indexes = [
        idx for idx, item in enumerate(query_plan)
        if extract_site_constraint(item.get("q", ""))
    ]
    if (
        limit <= 3
        and len(site_indexes) >= 2
        and len(preferred_domains) >= 2
        and (
            mechanism_type in {"structured_numeric_authority", "date_authority"}
            or evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}
        )
        and any(
            normalize_text(str(item.get("origin") or "")) == "metric_source_probe"
            or normalize_text(str(item.get("goal") or "")) == "find_metric_source_page"
            or not extract_site_constraint(str(item.get("q") or ""))
            for item in query_plan
        )
    ):
        return query_plan
    retry_gap_flags = source_intent.get("_retry_gap_flags") if isinstance(source_intent.get("_retry_gap_flags"), list) else []
    if (
        limit <= 3
        and any(normalize_text(str(item.get("origin") or "")) == "structured_point_retry" for item in query_plan)
        and any(str(flag).startswith("point_") for flag in retry_gap_flags)
    ):
        return query_plan
    qa_items = verification_query_items(claim_item, claim, source_intent)
    if not qa_items:
        return query_plan
    qa_item = qa_items[0]
    if len(query_plan) < limit:
        return dedupe_query_plan_keep_order(query_plan + [qa_item], limit)
    protected_origins = {
        "preferred_domain_probe",
        "structured_point_retry",
        "metric_source_probe",
        "page_shape_probe",
        "page_intent_retry",
        "gap_pseudo_page_probe",
        "route_frame_probe",
    }
    replace_index = -1
    if len(site_indexes) >= 2:
        replace_index = site_indexes[-1]
    if replace_index < 0:
        for idx in range(len(query_plan) - 1, -1, -1):
            origin = normalize_text(str(query_plan[idx].get("origin") or ""))
            if origin not in protected_origins:
                replace_index = idx
                break
    if replace_index < 0:
        replace_index = len(query_plan) - 1
    selected = list(query_plan)
    selected[replace_index] = qa_item
    return dedupe_query_plan_keep_order(selected, limit)


def route_query_quality(
    web_items: List[Dict[str, Any]],
    strong_items: List[Dict[str, Any]],
    stats: Dict[str, Any],
    route_signal: Dict[str, Any],
) -> Dict[str, Any]:
    raw_results = int(stats.get("raw_results", 0) or 0)
    filtered_results = int(stats.get("filtered_results", 0) or 0)
    detail_attempts = int(stats.get("detail_attempts", 0) or 0)
    detail_successes = int(stats.get("detail_successes", 0) or 0)
    filtered_reasons = stats.get("filtered_reasons", {}) if isinstance(stats.get("filtered_reasons"), dict) else {}

    recall_score = 0
    if raw_results >= 8:
        recall_score = 20
    elif raw_results >= 3:
        recall_score = 14
    elif raw_results > 0:
        recall_score = 8

    source_score = 0
    if strong_items:
        source_score = min(20, 10 + len(strong_items) * 5)
    elif web_items:
        source_score = 8
    elif raw_results and filtered_results:
        source_score = 3

    has_relation = bool(route_signal.get("has_relation_marker"))
    has_two_entities = bool(route_signal.get("has_two_entities"))
    has_direct_sentence = bool(route_signal.get("has_direct_sentence"))
    route_sentence_count = int(route_signal.get("route_sentence_count") or 0)
    relation_score = 0
    if has_direct_sentence:
        relation_score = 25
    elif has_relation and has_two_entities:
        relation_score = 18
    elif has_relation:
        relation_score = 10
    elif has_two_entities:
        relation_score = 8
    elif route_sentence_count:
        relation_score = 4

    detail_score = 0
    if detail_successes:
        detail_score = min(15, 8 + detail_successes * 3)
    elif detail_attempts:
        detail_score = 4
    elif web_items:
        detail_score = 6

    focus_score = 20
    if raw_results == 0:
        focus_score = 0
    elif filtered_reasons.get("route_weak_no_direct_sentence") and not has_relation:
        focus_score = 4
    elif not web_items and filtered_results:
        focus_score = 6
    elif not has_relation and not has_two_entities:
        focus_score = 8
    elif has_relation or has_two_entities:
        focus_score = 14
    if has_direct_sentence:
        focus_score = 20

    components = {
        "recall": recall_score,
        "source": source_score,
        "route_relation": relation_score,
        "detail_read": detail_score,
        "query_focus": focus_score,
    }
    score = sum(components.values())
    if score >= 70:
        label = "good"
        issue = ""
    elif score >= 45:
        label = "borderline"
        issue = "route_query_needs_refinement"
    elif raw_results == 0:
        label = "poor"
        issue = "route_query_no_recall"
    elif not has_relation and filtered_reasons.get("route_weak_no_direct_sentence"):
        label = "poor"
        issue = "route_query_too_broad_no_relation"
    elif not strong_items:
        label = "poor"
        issue = "route_query_weak_sources"
    else:
        label = "poor"
        issue = "route_query_no_direct_relation"
    return {
        "score": score,
        "label": label,
        "issue": issue,
        "components": components,
    }


def retrieval_quality_from_diagnostics(
    evidence_mode: str,
    reason: str,
    route_failure_stage: str,
    route_failure_detail: str,
    raw_results: int,
    filtered_results: int,
    web_items: List[Dict[str, Any]],
    strong_items: List[Dict[str, Any]],
    direct_items: List[Dict[str, Any]],
    stats: Dict[str, Any],
    route_signal: Dict[str, Any],
    route_quality: Dict[str, Any],
) -> Dict[str, Any]:
    filtered_reasons = stats.get("filtered_reasons", {}) if isinstance(stats.get("filtered_reasons"), dict) else {}
    page_intent_labels = stats.get("page_intent_labels", {}) if isinstance(stats.get("page_intent_labels"), dict) else {}
    page_intent_issues = stats.get("page_intent_issues", {}) if isinstance(stats.get("page_intent_issues"), dict) else {}
    page_utility_labels = stats.get("page_utility_labels", {}) if isinstance(stats.get("page_utility_labels"), dict) else {}
    page_utility_risks = stats.get("page_utility_risks", {}) if isinstance(stats.get("page_utility_risks"), dict) else {}
    evidence_contract_roles = stats.get("evidence_contract_roles", {}) if isinstance(stats.get("evidence_contract_roles"), dict) else {}
    evidence_contract_statuses = stats.get("evidence_contract_statuses", {}) if isinstance(stats.get("evidence_contract_statuses"), dict) else {}
    evidence_contract_risks = stats.get("evidence_contract_risks", {}) if isinstance(stats.get("evidence_contract_risks"), dict) else {}
    evidence_contract_by_origin = compact_evidence_contract_by_query_origin(stats)
    source_quality_reasons = stats.get("source_quality_reasons", {}) if isinstance(stats.get("source_quality_reasons"), dict) else {}
    source_quality_scores = stats.get("source_quality_scores", []) if isinstance(stats.get("source_quality_scores"), list) else []
    page_utility_scores = stats.get("page_utility_scores", []) if isinstance(stats.get("page_utility_scores"), list) else []
    structured_point_risks: Dict[str, int] = {}
    structured_point_statuses: Dict[str, int] = {}
    for item in web_items:
        point_status = normalize_text(str(item.get("structured_point_contract_status") or "")).lower()
        if point_status:
            structured_point_statuses[point_status] = int(structured_point_statuses.get(point_status, 0) or 0) + 1
        for risk in item.get("structured_point_contract_risks", []) if isinstance(item.get("structured_point_contract_risks"), list) else []:
            risk_text = normalize_text(str(risk))
            if risk_text:
                structured_point_risks[risk_text] = int(structured_point_risks.get(risk_text, 0) or 0) + 1
    route_filtered = top_count_items(filtered_reasons, 5)
    top_filter_reason = next(iter(route_filtered.keys()), "") if route_filtered else ""
    source_quality_avg = (
        round(sum(int(score or 0) for score in source_quality_scores) / len(source_quality_scores), 1)
        if source_quality_scores else None
    )
    page_intent_scores = stats.get("page_intent_scores", []) if isinstance(stats.get("page_intent_scores"), list) else []
    page_intent_avg = (
        round(sum(int(score or 0) for score in page_intent_scores) / len(page_intent_scores), 1)
        if page_intent_scores else None
    )
    page_utility_avg = (
        round(sum(int(score or 0) for score in page_utility_scores) / len(page_utility_scores), 1)
        if page_utility_scores else None
    )
    source_recall_diagnosis = summarize_source_recall_diagnosis(stats, raw_results, filtered_results, web_items)
    stage_hint = route_failure_stage or reason
    gap_profile = {
        "no_search_result": raw_results == 0,
        "all_filtered": raw_results > 0 and not web_items,
        "weak_source_only": bool(web_items) and not strong_items,
        "no_direct_sentence": bool(web_items) and not direct_items,
        "background_dominant": any(
            key in filtered_reasons
            for key in {
                "route_background_dominant_low_decidability",
                "route_background_dominant_candidate_only",
                "route_page_type_background",
            }
        ) or bool(page_utility_risks.get("background_dominates_route_signal")),
        "low_decidability": any(
            key in filtered_reasons
            for key in {
                "route_page_utility_too_low",
                "route_relation_without_passage_support",
                "route_retention_policy_not_satisfied",
            }
        ) or bool(page_intent_issues.get("route_page_decidability_low")),
        "missing_relation": (
            stage_hint in {"route_sentence_extract", "directness"}
            and not route_signal.get("has_relation_marker")
        ),
        "missing_object": "route_missing_required_object_marker" in filtered_reasons,
        "poor_page_type": any(
            key in filtered_reasons
            for key in {
                "route_page_type_background",
                "route_page_type_landing",
            }
        ) or any(
            key in page_intent_issues
            for key in {
                "route_page_type_background",
                "route_page_type_summary",
                "route_page_type_landing",
                "route_page_focus_background",
            }
        ),
        "low_source_quality": (
            (source_quality_avg is not None and source_quality_avg < 35)
            or "source_quality_bad" in filtered_reasons
            or "low_source_quality" in source_quality_reasons
        ),
        "thin_direct_evidence": bool(web_items) and len(direct_items) < 2,
        "provider_error_present": bool(source_recall_diagnosis.get("provider_error_present")),
        "filtered_low_claim_anchor": "filtered_low_claim_anchor" in filtered_reasons,
        "filtered_page_shape_mismatch": "filtered_page_shape_mismatch" in filtered_reasons,
        "filtered_low_source_relevance": "filtered_low_source_relevance" in filtered_reasons,
        "filtered_utility_drop_conflict": "filtered_utility_drop_conflict" in filtered_reasons,
        "fallback_only_raw": bool(source_recall_diagnosis.get("fallback_only_raw")),
        "high_priority_source_empty": bool(source_recall_diagnosis.get("high_priority_empty")),
        "point_time_scope_mismatch": bool(structured_point_risks.get("point_time_scope_mismatch")),
        "point_metric_field_missing": bool(structured_point_risks.get("point_metric_field_missing")),
        "point_subject_currency_mismatch": bool(structured_point_risks.get("point_subject_currency_mismatch")),
        "point_metric_value_missing": bool(structured_point_risks.get("point_metric_value_missing")),
    }
    gap_profile["utility_judge_conflict"] = any(
        (
            str(item.get("page_utility_llm_decision") or "") == "drop"
            and (
                str(item.get("page_utility_label") or "") in {"good", "usable"}
                or str(item.get("page_retention_label") or "") in {"keep", "borderline_keep"}
            )
        )
        for item in web_items
    )
    gap_flags = [name for name, value in gap_profile.items() if value]
    if raw_results == 0:
        stage_label = "search_recall"
        score = 12
    elif not web_items:
        stage_label = "page_retention"
        score = 24
    elif not strong_items:
        stage_label = "page_retention"
        score = 34
    elif any(gap_profile.get(flag) for flag in {"point_time_scope_mismatch", "point_metric_field_missing", "point_subject_currency_mismatch", "point_metric_value_missing"}):
        stage_label = "point_readiness"
        score = 52
    elif not direct_items:
        stage_label = "sentence_readiness"
        score = 46
    elif evidence_mode == "route_fact" and len(direct_items) < 2:
        stage_label = "point_readiness"
        score = 58
    elif route_failure_stage in {"detail_read"}:
        stage_label = "detail_read"
        score = 40
    else:
        stage_label = "ready"
        score = 72

    if gap_profile["background_dominant"]:
        score -= 10
    if gap_profile["low_decidability"]:
        score -= 8
    if gap_profile["missing_relation"]:
        score -= 7
    if gap_profile["missing_object"]:
        score -= 5
    if gap_profile["poor_page_type"]:
        score -= 6
    if gap_profile.get("utility_judge_conflict"):
        score -= 5
    if gap_profile["low_source_quality"]:
        score -= 6
    if gap_profile["thin_direct_evidence"]:
        score -= 4
    if page_utility_avg is not None:
        if page_utility_avg >= 70:
            score += 4
        elif page_utility_avg < 40:
            score -= 4
    if page_intent_avg is not None:
        if page_intent_avg >= 70:
            score += 2
        elif page_intent_avg < 45:
            score -= 3
    if route_quality.get("label") == "good":
        score += 4
    elif route_quality.get("label") == "poor":
        score -= 4
    score = clamp_int(score, 0, 100)
    label = "good" if score >= 75 else "borderline" if score >= 55 else "bad"

    recommended_actions: List[str] = []
    if gap_profile["no_search_result"]:
        recommended_actions.extend(["change_source_plan", "add_gap_query"])
    elif gap_profile["all_filtered"] or gap_profile["background_dominant"]:
        recommended_actions.extend(["change_source_plan", "re_retrieve_with_page_intent"])
    elif gap_profile["poor_page_type"]:
        recommended_actions.extend(["re_retrieve_with_page_intent", "change_source_plan"])
    elif gap_profile["utility_judge_conflict"]:
        recommended_actions.extend(["re_retrieve_with_page_intent", "add_gap_query"])
    elif gap_profile["missing_relation"] or gap_profile["missing_object"]:
        recommended_actions.extend(["add_gap_query", "re_retrieve_with_page_intent"])
    elif any(gap_profile.get(flag) for flag in {"point_time_scope_mismatch", "point_metric_field_missing", "point_subject_currency_mismatch", "point_metric_value_missing"}):
        recommended_actions.extend(["add_gap_query", "keep_and_continue"])
    elif gap_profile["thin_direct_evidence"]:
        recommended_actions.extend(["keep_and_continue", "add_gap_query"])
    elif gap_profile["low_source_quality"]:
        recommended_actions.extend(["change_source_plan", "add_gap_query"])
    else:
        recommended_actions.append("keep_and_continue")
    recommended_actions = dedupe_keep_order(recommended_actions)

    summary_bits = [
        f"stage={stage_label}",
        f"gap={'|'.join(gap_flags[:4]) if gap_flags else 'none'}",
        f"action={'|'.join(recommended_actions[:2]) if recommended_actions else 'none'}",
    ]
    return {
        "retrieval_quality_score": score,
        "retrieval_quality_label": label,
        "retrieval_quality_stage": stage_label,
        "retrieval_quality_reason": reason,
        "retrieval_quality_reasons": dedupe_keep_order(
            [
                route_failure_detail,
                route_failure_stage,
                top_filter_reason,
                str(route_quality.get("issue") or ""),
            ]
        )[:6],
        "retrieval_gap_profile": gap_profile,
        "retrieval_gap_flags": gap_flags,
        "retrieval_dominant_filtered_reasons": route_filtered,
        "retrieval_dominant_page_intent_labels": top_count_items(page_intent_labels, 3),
        "retrieval_dominant_page_intent_issues": top_count_items(page_intent_issues, 3),
        "retrieval_dominant_page_utility_labels": top_count_items(page_utility_labels, 3),
        "retrieval_dominant_page_utility_risks": top_count_items(page_utility_risks, 3),
        "retrieval_dominant_evidence_contract_roles": top_count_items(evidence_contract_roles, 3),
        "retrieval_dominant_evidence_contract_statuses": top_count_items(evidence_contract_statuses, 3),
        "retrieval_dominant_evidence_contract_risks": top_count_items(evidence_contract_risks, 4),
        "retrieval_dominant_structured_point_statuses": top_count_items(structured_point_statuses, 3),
        "retrieval_dominant_structured_point_risks": top_count_items(structured_point_risks, 4),
        "retrieval_evidence_contract_by_query_origin": evidence_contract_by_origin,
        "recommended_actions": recommended_actions,
        "retrieval_quality_summary": "；".join(summary_bits),
        "source_recall_diagnosis": source_recall_diagnosis,
    }


def infer_readiness_block_reason(web_items: List[Dict[str, Any]], direct_items: List[Dict[str, Any]], stats: Dict[str, Any]) -> str:
    if direct_items:
        return ""
    answer_candidate_total = sum(
        len(item.get("answer_candidates") or [])
        for item in web_items
        if isinstance(item, dict) and isinstance(item.get("answer_candidates"), list)
    )
    soft_kept_items = [
        item for item in web_items
        if isinstance(item, dict) and item.get("kept_by_soft_claim_alignment")
    ]
    if answer_candidate_total <= 0 and soft_kept_items:
        return "kept_for_anchor_only"
    structured_unbound_items = [
        item for item in web_items
        if isinstance(item, dict)
        and str(item.get("evidence_contract_role") or "") in {"structured_metric_table_page", "structured_metric_candidate_page"}
        and str(item.get("structured_point_contract_status") or "") in {"partial", "failed", "unknown"}
    ]
    if structured_unbound_items and answer_candidate_total <= 0:
        return "structured_page_not_bound"
    if answer_candidate_total <= 0:
        return "no_answer_candidates"
    candidate_alignment_scores = []
    for item in web_items:
        if not isinstance(item, dict):
            continue
        for candidate in item.get("answer_candidates") or []:
            if not isinstance(candidate, dict):
                continue
            candidate_alignment_scores.append(int(candidate.get("score") or 0))
    if candidate_alignment_scores and max(candidate_alignment_scores) < 5:
        return "candidates_not_claim_aligned"
    return "candidate_not_direct"


def infer_readiness_block_layer(readiness_block_reason: str) -> str:
    if readiness_block_reason in {"kept_for_anchor_only", "structured_page_not_bound"}:
        return "page"
    if readiness_block_reason in {"no_answer_candidates", "candidates_not_claim_aligned", "candidate_not_direct"}:
        return "sentence"
    return ""


def aggregated_anchor_buckets(web_items: List[Dict[str, Any]]) -> set[str]:
    buckets: set[str] = set()
    for item in web_items:
        if not isinstance(item, dict):
            continue
        for key in ("program_anchor_buckets", "soft_keep_anchor_buckets"):
            values = item.get(key) if isinstance(item.get(key), list) else []
            for value in values:
                text = normalize_text(str(value))
                if text:
                    buckets.add(text)
    return buckets


def observed_slot_signals_from_web_items(web_items: List[Dict[str, Any]]) -> Tuple[set[str], Dict[str, List[str]]]:
    buckets = aggregated_anchor_buckets(web_items)
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

    for item in web_items:
        if not isinstance(item, dict):
            continue
        if int(item.get("entity_match_count") or 0) >= 1:
            buckets.add("entity")
            add_slot("subject", str(item.get("title") or item.get("snippet") or item.get("detail") or ""))
        if int(item.get("entity_match_count") or 0) >= 2:
            add_slot("object", str(item.get("title") or item.get("snippet") or item.get("detail") or ""))
        for candidate in item.get("answer_candidates") or []:
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
        best_point = item.get("structured_table_best_point") if isinstance(item.get("structured_table_best_point"), dict) else {}
        fields = best_point.get("fields") if isinstance(best_point.get("fields"), dict) else {}
        if fields:
            buckets.add("numeric")
            add_slot("metric_or_relation", " ".join(str(value) for value in fields.values()))
            if normalize_text(str(fields.get("publish_time") or "")):
                buckets.add("time")
                add_slot("time_scope", str(fields.get("publish_time") or ""))
    return buckets, observed_slots


def count_item_field_values(web_items: List[Dict[str, Any]], field_name: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in web_items:
        if not isinstance(item, dict):
            continue
        value = normalize_text(str(item.get(field_name) or ""))
        if not value:
            continue
        counts[value] = int(counts.get(value, 0) or 0) + 1
    return counts


def infer_missing_required_slots_for_claim(
    claim_item: Dict[str, Any],
    web_items: List[Dict[str, Any]],
    evidence_mode: str,
) -> List[str]:
    program = claim_program_from_claim_item(claim_item)
    decision_slots = program.get("decision_slots") if isinstance(program.get("decision_slots"), dict) else {}
    source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
    required_slots = (
        [str(slot) for slot in (program.get("required_slot_profile") or []) if str(slot)]
        if isinstance(program.get("required_slot_profile"), list)
        else shared_required_slot_profile_for_mode(
            evidence_mode,
            claim_text=str(claim_item.get("claim") or ""),
            source_intent=source_intent,
            decision_slots=decision_slots,
        )
    )
    observed_buckets, observed_slots = observed_slot_signals_from_web_items(web_items)
    return shared_infer_missing_required_slots(
        decision_slots,
        evidence_mode,
        claim_text=str(claim_item.get("claim") or ""),
        source_intent=source_intent,
        observed_buckets=observed_buckets,
        observed_slots=observed_slots,
        required_slots=required_slots,
    )


def infer_slot_alignment_status(
    claim_item: Dict[str, Any],
    web_items: List[Dict[str, Any]],
    direct_items: List[Dict[str, Any]],
    stats: Dict[str, Any],
    evidence_mode: str,
    readiness_block_reason: str,
) -> str:
    missing_required_slots = infer_missing_required_slots_for_claim(claim_item, web_items, evidence_mode)
    if missing_required_slots:
        return "missing_required_slots"
    if not web_items:
        return ""
    if readiness_block_reason == "kept_for_anchor_only":
        return "anchor_only"
    if readiness_block_reason == "structured_page_not_bound":
        return "structured_unbound"
    if readiness_block_reason in {"no_answer_candidates", "candidates_not_claim_aligned", "candidate_not_direct"} and not direct_items:
        return "candidate_slot_weak"
    if direct_items:
        return "slot_ready"
    return ""


def diagnose_claim_retrieval(
    claim_item: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> Dict[str, Any]:
    source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
    evidence_need_program = claim_program_from_claim_item(claim_item)
    task_card = claim_item.get("evidence_task_card") if isinstance(claim_item.get("evidence_task_card"), dict) else {}
    evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or "entity_fact"))
    web_items = [item for item in evidence if item.get("source_type") not in {"input_context", "computed"}]
    strong_items = [item for item in web_items if item.get("source_type") in {"official", "news", "encyclopedia"}]
    official_points = [
        item for item in web_items
        if item.get("source_type") == "official"
        or str(item.get("source") or "") in {"official_discovery", "official_inner_link", "domain_sitemap"}
    ]
    direct_items = [
        item for item in web_items
        if int(item.get("directness_score") or 0) >= 2 and not item.get("readiness_promotion_used")
    ]
    readiness_block_reason = infer_readiness_block_reason(web_items, direct_items, stats)
    readiness_block_layer = infer_readiness_block_layer(readiness_block_reason)
    missing_required_slots = infer_missing_required_slots_for_claim(claim_item, web_items, evidence_mode)
    slot_alignment_status = infer_slot_alignment_status(
        claim_item,
        web_items,
        direct_items,
        stats,
        evidence_mode,
        readiness_block_reason,
    )
    program_anchor_buckets = (
        ((evidence_need_program.get("decision_slots") or {}).get("anchor_buckets") or [])
        if isinstance(evidence_need_program, dict)
        else []
    )
    program_false_friend_hits = dedupe_keep_order(
        [
            hit
            for item in web_items
            if isinstance(item, dict)
            for hit in (
                item.get("program_false_friend_hits")
                if isinstance(item.get("program_false_friend_hits"), list)
                else program_false_friend_hits_for_item(item, claim_item)
            )
            if str(hit)
        ]
    )[:6]
    program_used_for_retention = any(bool(item.get("program_used_for_retention")) for item in web_items if isinstance(item, dict))
    raw_results = int(stats.get("raw_results", 0) or 0)
    filtered_results = int(stats.get("filtered_results", 0) or 0)
    answer_candidate_total = sum(
        len(item.get("answer_candidates") or [])
        for item in web_items
        if isinstance(item, dict) and isinstance(item.get("answer_candidates"), list)
    )
    source_pollution_stats = compact_source_pollution_stats(stats)
    anti_bot_blocks = sum(int(bucket.get("anti_bot_blocks", 0) or 0) for bucket in source_pollution_stats.values())
    detail_anti_bot_errors = int(stats.get("detail_anti_bot_errors", 0) or 0)
    detail_read_failed = int(stats.get("detail_read_failed", 0) or 0)
    playwright_rescued = int(stats.get("playwright_rescued", 0) or 0)
    detail_fetch_paths = count_item_field_values(web_items, "detail_fetch_path")
    direct_candidate_rescue_used = sum(1 for item in web_items if isinstance(item, dict) and item.get("direct_candidate_rescue_used"))
    direct_candidate_rescue_sources = count_item_field_values(web_items, "direct_candidate_rescue_source")
    direct_candidate_rescue_stages = count_item_field_values(web_items, "direct_candidate_rescue_stage")
    page_keep_review_state = count_item_field_values(web_items, "page_keep_review_state")
    page_keep_review_reason = count_item_field_values(web_items, "page_keep_review_reason")
    page_roles = count_item_field_values(web_items, "page_role")
    page_role_reasons = count_item_field_values(web_items, "page_role_reason")
    generic_page_block_reasons = count_item_field_values(web_items, "generic_page_block_reason")
    entry_follow_states = count_item_field_values(web_items, "entry_follow_state")
    evidence_page_ready_count = sum(1 for item in web_items if isinstance(item, dict) and item.get("evidence_page_ready"))
    entry_page_follow_required_count = sum(1 for item in web_items if isinstance(item, dict) and item.get("entry_page_follow_required"))
    kept_candidate_source_type = count_item_field_values(web_items, "kept_candidate_source_type")
    kept_progress_from_raw = sum(1 for item in web_items if isinstance(item, dict) and item.get("kept_progress_from_raw"))
    rescue_promoted_from_filter = sum(1 for item in web_items if isinstance(item, dict) and item.get("rescue_promoted_from_filter"))
    readiness_promotion_used = sum(1 for item in web_items if isinstance(item, dict) and item.get("readiness_promotion_used"))
    readiness_promotion_source = count_item_field_values(web_items, "readiness_promotion_source")
    candidate_strength_before_keep = max(
        [int(item.get("candidate_strength_before_keep") or 0) for item in web_items if isinstance(item, dict) and item.get("readiness_promotion_used")]
        + [int(score or 0) for score in (stats.get("candidate_strength_before_keep_scores") or [])],
        default=0,
    )
    environment_block_reason = ""
    if raw_results <= 0 and anti_bot_blocks > 0 and playwright_rescued <= 0:
        environment_block_reason = "source_access_blocked_without_rescue"
    elif detail_anti_bot_errors > 0 and playwright_rescued <= 0:
        environment_block_reason = "requests_blocked_playwright_failed"
    elif detail_read_failed > 0 and int(stats.get("detail_successes", 0) or 0) <= 0:
        environment_block_reason = "detail_read_failed_after_fetch"
    elif detail_anti_bot_errors > 0 and playwright_rescued > 0:
        environment_block_reason = "requests_blocked_playwright_rescued"
    official_discovery_block_reason = normalize_text(str(stats.get("official_discovery_block_reason") or ""))
    if not official_discovery_block_reason and isinstance(stats.get("official_discovery_logs"), list):
        official_discovery_block_reason = infer_official_discovery_block_reason(stats.get("official_discovery_logs") or [], stats.get("discovered_domains") or [])
    source_budget_cutoff = stats.get("source_budget_cutoff") if isinstance(stats.get("source_budget_cutoff"), dict) else {}
    provider_health_snapshot = stats.get("provider_health_snapshot") if isinstance(stats.get("provider_health_snapshot"), list) else []
    effective_source_plan = [str(item) for item in (stats.get("effective_source_plan") or []) if str(item)][:10]
    playwright_rescue_state = infer_playwright_rescue_state(stats)
    playwright_reasons = stats.get("playwright_reasons") if isinstance(stats.get("playwright_reasons"), list) else []
    playwright_skipped_reasons = stats.get("playwright_skipped_reasons") if isinstance(stats.get("playwright_skipped_reasons"), list) else []
    pollution_bucket = source_pollution_stats.get("playwright_duckduckgo") if isinstance(source_pollution_stats.get("playwright_duckduckgo"), dict) else {}
    playwright_rescue_result_count = int(pollution_bucket.get("raw", 0) or 0)
    if playwright_rescue_state == "playwright_rescue_skipped_by_policy":
        playwright_rescue_trigger = normalize_text(str(playwright_skipped_reasons[0] if playwright_skipped_reasons else "")) or "policy_skip"
    else:
        playwright_rescue_trigger = normalize_text(str(playwright_reasons[0] if playwright_reasons else "")) or ""
    playwright_rescue_source = "playwright_duckduckgo" if (playwright_rescue_state or pollution_bucket) else ""
    official_entry_attempted = bool(stats.get("official_discovery_attempted")) or "domain_sitemap" in effective_source_plan
    official_entry_hit = bool(stats.get("official_discovery_used")) or bool(official_points)
    official_entry_source_family = ""
    if bool(stats.get("official_discovery_used")):
        official_entry_source_family = "official_discovery"
    elif any(str(item.get("source") or "") == "domain_sitemap" for item in web_items if isinstance(item, dict)):
        official_entry_source_family = "sitemap"
    elif any(str(item.get("source_type") or "") == "official" for item in web_items if isinstance(item, dict)):
        official_entry_source_family = "official"
    access_path_state = ""
    access_block_source = ""
    anti_bot_sources = [
        str(source_name)
        for source_name, bucket in source_pollution_stats.items()
        if isinstance(bucket, dict) and int(bucket.get("anti_bot_blocks", 0) or 0) > 0
    ]
    partial_progress_available = len(web_items) > 0 or answer_candidate_total > 0 or direct_candidate_rescue_used > 0
    if source_budget_cutoff.get("applied") and raw_results <= 0 and not anti_bot_blocks:
        access_path_state = "source_budget_cutoff"
    elif official_entry_attempted and not official_entry_hit and official_discovery_block_reason and not partial_progress_available:
        access_path_state = "official_discovery_failed"
    elif environment_block_reason == "source_access_blocked_without_rescue":
        access_path_state = "access_blocked_but_rescuable"
    elif environment_block_reason in {"requests_blocked_playwright_failed", "detail_read_failed_after_fetch"}:
        access_path_state = "access_blocked_and_unresolved"
    elif raw_results <= 0:
        access_path_state = "provider_no_raw"
    elif partial_progress_available:
        access_path_state = "partial_progress_available"
    else:
        access_path_state = "raw_results_returned"
    if anti_bot_sources:
        access_block_source = normalize_text(str(anti_bot_sources[0]))
    elif environment_block_reason == "detail_read_failed_after_fetch":
        access_block_source = "detail_fetch_path"
    elif access_path_state == "official_discovery_failed" and official_discovery_block_reason:
        access_block_source = "official_discovery"
    search_request = stats.get("search_request") if isinstance(stats.get("search_request"), dict) else {}
    search_policy = stats.get("search_policy") if isinstance(stats.get("search_policy"), dict) else {}
    search_execution_trace = summarize_search_execution_trace(stats)
    executed_query_rows = stats.get("executed_query_source_plan") if isinstance(stats.get("executed_query_source_plan"), list) else []
    source_order_trace = []
    final_executed_source_order: List[str] = []
    priority_source_dropped_stage = ""
    final_source_selection_reason = ""
    authority_pair_preserved = False
    for row in executed_query_rows:
        if not isinstance(row, dict):
            continue
        if not source_order_trace and isinstance(row.get("source_order_trace"), list):
            source_order_trace = row.get("source_order_trace", [])[:8]
        final_executed_source_order.extend([str(item) for item in (row.get("final_executed_source_order") or []) if str(item)])
        if not priority_source_dropped_stage:
            priority_source_dropped_stage = str(row.get("priority_source_dropped_stage") or "")
        if not final_source_selection_reason:
            final_source_selection_reason = str(row.get("final_source_selection_reason") or "")
        authority_pair_preserved = authority_pair_preserved or bool(row.get("authority_pair_preserved"))
    source_latency_profile = source_timing_stage_profile(stats)
    rescue_skip_reasons = stats.get("rescue_skip_reasons") if isinstance(stats.get("rescue_skip_reasons"), dict) else {}
    rescue_skip_reason = next(iter(rescue_skip_reasons.keys()), "")
    rescue_latency_ms = round(float(stats.get("rescue_latency_ms", 0.0) or 0.0), 1)
    rescue_progress_delta = stats.get("rescue_progress_delta") if isinstance(stats.get("rescue_progress_delta"), dict) else {}
    rescue_success_gate = str(stats.get("rescue_success_gate") or "")
    rescue_target_page_type = str(stats.get("rescue_target_page_type") or "")
    rescue_non_roi_reason = str(stats.get("rescue_non_roi_reason") or "")
    detail_rescue_roi_state = str(stats.get("detail_rescue_roi_state") or "")
    detail_rescue_target_page_type = str(stats.get("detail_rescue_target_page_type") or "")
    detail_rescue_effect_delta = stats.get("detail_rescue_effect_delta") if isinstance(stats.get("detail_rescue_effect_delta"), dict) else {}
    detail_rescue_failure_reason = str(stats.get("detail_rescue_failure_reason") or "")
    family_rescue_budget_used = stats.get("family_rescue_budget_used") if isinstance(stats.get("family_rescue_budget_used"), dict) else {}
    claim_retrieve_stop_reason = str(stats.get("claim_retrieve_stop_reason") or "")
    refutation_target = stats.get("refutation_target") if isinstance(stats.get("refutation_target"), dict) else {}
    refutation_query_plan = stats.get("refutation_query_plan") if isinstance(stats.get("refutation_query_plan"), list) else []
    refutation_retry_trigger = str(stats.get("refutation_retry_trigger") or "")
    refutation_slot_gap = stats.get("refutation_slot_gap") if isinstance(stats.get("refutation_slot_gap"), list) else []
    refutation_search_result = str(stats.get("refutation_search_result") or "")
    refutation_retrieval_stop_reason = str(stats.get("refutation_retrieval_stop_reason") or "")
    contrastive_query_plan = stats.get("contrastive_query_plan") if isinstance(stats.get("contrastive_query_plan"), dict) else {}
    contrastive_retry_trigger = str(stats.get("contrastive_retry_trigger") or "")
    contrastive_slot_gap = stats.get("contrastive_slot_gap") if isinstance(stats.get("contrastive_slot_gap"), list) else []
    contrastive_search_result = str(stats.get("contrastive_search_result") or "")
    contrastive_stop_reason = str(stats.get("contrastive_stop_reason") or "")
    retrieval_cost_review = {
        "query_count": int(stats.get("query_count", 0) or 0),
        "executed_source_count": len(dedupe_keep_order(final_executed_source_order)),
        "detail_attempts": int(stats.get("detail_attempts", 0) or 0),
        "detail_successes": int(stats.get("detail_successes", 0) or 0),
        "rescue_latency_ms": rescue_latency_ms,
        "search_seconds": source_latency_profile.get("search_seconds", 0.0),
        "detail_fetch_seconds": source_latency_profile.get("detail_fetch_seconds", 0.0),
        "official_discovery_seconds": source_latency_profile.get("official_discovery_seconds", 0.0),
    }
    search_outcome = summarize_search_outcome(
        raw_results,
        len(web_items),
        access_path_state,
        access_block_source,
        official_entry_hit,
        playwright_rescue_state,
        answer_candidate_total,
    )
    needs_retry = False
    reason = "sufficient"
    if raw_results == 0:
        needs_retry = True
        reason = "no_result"
    elif not web_items:
        needs_retry = True
        reason = "all_filtered"
    elif not strong_items:
        needs_retry = True
        reason = "weak_source"
    elif not direct_items:
        needs_retry = True
        reason = "no_direct_evidence"
    elif evidence_mode == "route_fact" and len(direct_items) < 2:
        needs_retry = True
        reason = "route_evidence_too_thin"
    route_failure_detail = ""
    route_failure_stage = ""
    route_failure_summary = ""
    route_signal: Dict[str, Any] = {}
    route_quality: Dict[str, Any] = {}
    if evidence_mode == "route_fact" and needs_retry:
        filtered_reasons = stats.get("filtered_reasons", {}) if isinstance(stats.get("filtered_reasons"), dict) else {}
        route_sentences = [
            item.get("route_sentence")
            for item in web_items
            if isinstance(item.get("route_sentence"), dict)
        ]
        has_relation = any(item.get("has_relation_marker") for item in route_sentences)
        has_two_entities = any(int(item.get("entity_hit_count") or 0) >= 2 for item in route_sentences)
        has_direct_sentence = any(item.get("direct_sentence") for item in route_sentences)
        detail_attempts = int(stats.get("detail_attempts", 0) or 0)
        detail_successes = int(stats.get("detail_successes", 0) or 0)
        detail_errors = int(stats.get("detail_errors", 0) or 0)
        route_signal = {
            "has_relation_marker": has_relation,
            "has_two_entities": has_two_entities,
            "has_direct_sentence": has_direct_sentence,
            "route_sentence_count": len(route_sentences),
            "detail_attempts": detail_attempts,
            "detail_successes": detail_successes,
            "detail_errors": detail_errors,
        }
        if raw_results == 0:
            route_failure_detail = "route_no_search_result"
            route_failure_stage = "search_recall"
            route_failure_summary = "没有搜到任何候选网页结果。"
        elif not web_items and filtered_reasons.get("route_weak_no_direct_sentence"):
            route_failure_detail = "route_weak_source_without_direct_sentence"
            route_failure_stage = "source_filter"
            route_failure_summary = "搜到了结果，但主要是弱源或未知来源，且没有同一句直接路线关系。"
        elif not web_items:
            route_failure_detail = "route_all_results_filtered"
            route_failure_stage = "source_filter"
            route_failure_summary = "搜到了结果，但全部被过滤，未留下可用网页证据。"
        elif detail_attempts > 0 and detail_successes == 0:
            route_failure_detail = "route_detail_read_failed"
            route_failure_stage = "detail_read"
            route_failure_summary = "尝试读取详情页但未成功拿到可用正文。"
        elif has_relation and not has_two_entities:
            route_failure_detail = "route_terms_without_core_entities"
            route_failure_stage = "route_sentence_extract"
            route_failure_summary = "材料里有路线关系词，但同一句里缺少核心实体。"
        elif has_two_entities and not has_relation:
            route_failure_detail = "route_entities_without_relation"
            route_failure_stage = "route_sentence_extract"
            route_failure_summary = "材料里有核心实体，但同一句里缺少经过、飞越、领空等路线关系。"
        elif web_items and not has_direct_sentence:
            route_failure_detail = "route_no_same_sentence_direct_evidence"
            route_failure_stage = "route_sentence_extract"
            route_failure_summary = "有网页材料，但没有抽出同时包含核心实体和路线关系的直接句。"
        elif len(direct_items) < 2:
            route_failure_detail = "route_direct_evidence_too_thin"
            route_failure_stage = "directness"
            route_failure_summary = "抽到少量直接路线证据，但数量或强度仍不足。"
        else:
            route_failure_detail = reason
            route_failure_stage = "unknown"
            route_failure_summary = "路线证据不足，但当前诊断无法进一步细分。"
        route_quality = route_query_quality(web_items, strong_items, stats, route_signal)
    if stats.get("budget_exhausted") and reason == "sufficient":
        reason = "budget_exhausted"
    retrieval_quality = retrieval_quality_from_diagnostics(
        evidence_mode,
        reason,
        route_failure_stage,
        route_failure_detail,
        raw_results,
        filtered_results,
        web_items,
        strong_items,
        direct_items,
        stats,
        route_signal,
        route_quality,
    )
    responsibility_boundary = retrieval_responsibility_boundary(
        raw_results,
        web_items,
        strong_items,
        direct_items,
        retrieval_quality.get("source_recall_diagnosis", {})
        if isinstance(retrieval_quality, dict) else {},
        readiness_promotion_used,
        answer_candidate_total,
    )
    return {
        "claim_id": str(claim_item.get("claim_id") or claim_item.get("id") or ""),
        "evidence_task_card": task_card,
        "evidence_mode": evidence_mode,
        "evidence_target": str(source_intent.get("evidence_target") or "general"),
        "evidence_shape": normalize_evidence_shape(source_intent),
        "needs_retry": needs_retry,
        "reason": reason,
        "evidence_gap": (
            "no_search_result" if raw_results == 0 else
            "all_results_filtered" if not web_items else
            "weak_sources_only" if not strong_items else
            "no_direct_sentence" if not direct_items else
            "thin_direct_evidence" if needs_retry else
            "sufficient"
        ),
        "route_failure_detail": route_failure_detail,
        "route_failure_stage": route_failure_stage,
        "route_failure_summary": route_failure_summary,
        "route_signal": route_signal,
        "route_query_quality_score": route_quality.get("score"),
        "route_query_quality_label": route_quality.get("label", ""),
        "route_query_quality_issue": route_quality.get("issue", ""),
        "route_query_quality_components": route_quality.get("components", {}),
        "responsibility_boundary": responsibility_boundary,
        "responsibility_layer": responsibility_boundary.get("responsibility_layer", ""),
        "responsibility_stage": responsibility_boundary.get("stop_stage", ""),
        "readiness_block_reason": readiness_block_reason,
        "readiness_block_layer": readiness_block_layer,
        "answer_candidate_total": answer_candidate_total,
        "missing_required_slots": missing_required_slots[:4],
        "slot_alignment_status": slot_alignment_status,
        **retrieval_quality,
        "query_count": int(stats.get("query_count", 0) or 0),
        "qa_query_count": int(stats.get("qa_query_count", 0) or 0),
        "raw_results": raw_results,
        "kept_web": len(web_items),
        "official_points": len(official_points),
        "official_point_examples": [
            {
                "url": str(item.get("url") or ""),
                "source": str(item.get("source") or ""),
                "page_type": str(item.get("page_utility_page_type") or ""),
                "structured_point_contract_status": str(item.get("structured_point_contract_status") or ""),
            }
            for item in official_points[:5]
        ],
        "filtered_results": filtered_results,
        "filtered_reasons": stats.get("filtered_reasons", {}),
        "filtered_samples": stats.get("filtered_samples", []),
        "filtered_rescue_pool_state": stats.get("filtered_rescue_pool_state", ""),
        "filtered_rescue_pool_reason": stats.get("filtered_rescue_pool_reason", ""),
        "filtered_rescue_pool_score": int(stats.get("filtered_rescue_pool_score") or 0),
        "filtered_rescue_pool_promoted": int(stats.get("filtered_rescue_pool_promoted") or 0),
        "route_keyword_profiles": stats.get("route_keyword_profiles", [])[:3],
        "route_rerank_scores": stats.get("route_rerank_scores", [])[:20],
        "route_noise_reasons": stats.get("route_noise_reasons", {}),
        "structured_rerank_scores": stats.get("structured_rerank_scores", [])[:20],
        "structured_noise_reasons": stats.get("structured_noise_reasons", {}),
        "source_plan_used": stats.get("source_plan_used", []),
        "llm_source_strategy": stats.get("llm_source_strategy", {}),
        "source_strategy_score": stats.get("source_strategy_score"),
        "source_strategy_label": stats.get("source_strategy_label", ""),
        "source_strategy_issues": stats.get("source_strategy_issues", []),
        "source_strategy_components": stats.get("source_strategy_components", {}),
        "source_strategy_fallback": stats.get("source_strategy_fallback", ""),
        "source_strategy_sanitized": bool(stats.get("source_strategy_sanitized")),
        "source_strategy_sanitize_actions": stats.get("source_strategy_sanitize_actions", []),
        "source_strategy_before": stats.get("source_strategy_before", {}),
        "source_strategy_after": stats.get("source_strategy_after", {}),
        "query_limit": stats.get("query_limit"),
        "source_limit": stats.get("source_limit"),
        "planned_query_count": stats.get("planned_query_count"),
        "executed_query_plan": stats.get("executed_query_plan", []),
        "executed_query_source_plan": stats.get("executed_query_source_plan", [])[:6],
        "source_order_trace": source_order_trace,
        "priority_source_dropped_stage": priority_source_dropped_stage,
        "final_source_selection_reason": final_source_selection_reason,
        "final_executed_source_order": dedupe_keep_order(final_executed_source_order)[:10],
        "authority_pair_preserved": authority_pair_preserved,
        "query_variant_origin": stats.get("query_variant_origin", [])[:8],
        "recall_probe_used": int(stats.get("recall_probe_used", 0) or 0),
        "recall_probe_query": stats.get("recall_probe_query", ""),
        "recall_probe_source": stats.get("recall_probe_source", []),
        "recall_probe_raw_hits": int(stats.get("recall_probe_raw_hits", 0) or 0),
        "skipped_by_query_budget": stats.get("skipped_by_query_budget", 0),
        "skipped_sources_by_budget": stats.get("skipped_sources_by_budget", 0),
        "retrieval_budget_skip": stats.get("retrieval_budget_skip", ""),
        "preferred_domains": stats.get("preferred_domains", []),
        "official_discovery_attempted": bool(stats.get("official_discovery_attempted")),
        "official_domain_candidates": stats.get("official_domain_candidates", []),
        "discovered_domains": stats.get("discovered_domains", []),
        "official_discovery_score": int(stats.get("official_discovery_score", 0) or 0),
        "official_discovery_used": bool(stats.get("official_discovery_used")),
        "official_discovery_queries": stats.get("official_discovery_queries", []),
        "official_discovery_logs": stats.get("official_discovery_logs", []),
        "official_discovery_block_reason": official_discovery_block_reason,
        "route_retry_source_strategy": stats.get("route_retry_source_strategy", ""),
        "budget_exhausted": bool(stats.get("budget_exhausted")),
        "detail_fetches": int(stats.get("detail_fetches", 0) or 0),
        "detail_attempts": int(stats.get("detail_attempts", 0) or 0),
        "detail_successes": int(stats.get("detail_successes", 0) or 0),
        "detail_errors": int(stats.get("detail_errors", 0) or 0),
        "detail_read_failed": detail_read_failed,
        "detail_anti_bot_errors": detail_anti_bot_errors,
        "playwright_rescued": playwright_rescued,
        "environment_block_reason": environment_block_reason,
        "access_path_state": access_path_state,
        "access_block_source": access_block_source,
        "source_budget_cutoff": source_budget_cutoff,
        "provider_health_snapshot": provider_health_snapshot,
        "effective_source_plan": effective_source_plan,
        "playwright_rescue_state": playwright_rescue_state,
        "playwright_rescue_trigger": playwright_rescue_trigger,
        "playwright_rescue_source": playwright_rescue_source,
        "playwright_rescue_result_count": playwright_rescue_result_count,
        "rescue_roi_state": str(stats.get("rescue_roi_state") or ""),
        "rescue_skip_reason": rescue_skip_reason,
        "rescue_latency_ms": rescue_latency_ms,
        "rescue_progress_delta": rescue_progress_delta,
        "rescue_success_gate": rescue_success_gate,
        "rescue_target_page_type": rescue_target_page_type,
        "rescue_non_roi_reason": rescue_non_roi_reason,
        "detail_rescue_roi_state": detail_rescue_roi_state,
        "detail_rescue_target_page_type": detail_rescue_target_page_type,
        "detail_rescue_effect_delta": detail_rescue_effect_delta,
        "detail_rescue_failure_reason": detail_rescue_failure_reason,
        "family_rescue_budget_used": family_rescue_budget_used,
        "official_entry_attempted": official_entry_attempted,
        "official_entry_hit": official_entry_hit,
        "official_entry_source_family": official_entry_source_family,
        "search_request": search_request,
        "search_policy": search_policy,
        "search_execution_trace": search_execution_trace,
        "search_outcome": search_outcome,
        "detail_fetch_paths": detail_fetch_paths,
        "page_keep_review_state": page_keep_review_state,
        "page_keep_review_reason": page_keep_review_reason,
        "page_roles": page_roles,
        "page_role_reasons": page_role_reasons,
        "generic_page_block_reasons": generic_page_block_reasons,
        "entry_follow_states": entry_follow_states,
        "evidence_page_ready_count": evidence_page_ready_count,
        "entry_page_follow_required_count": entry_page_follow_required_count,
        "entry_follow_state": str(stats.get("entry_follow_state") or ""),
        "entry_follow_trigger": next(iter((stats.get("entry_follow_triggers") or {}).keys()), "") if isinstance(stats.get("entry_follow_triggers"), dict) else "",
        "entry_follow_candidates": stats.get("entry_follow_candidates", [])[:4] if isinstance(stats.get("entry_follow_candidates"), list) else [],
        "entry_follow_kept_evidence_pages": int(stats.get("entry_follow_kept_evidence_pages", 0) or 0),
        "entry_follow_block_reason": str(stats.get("entry_follow_block_reason") or ""),
        "entry_follow_latency_ms": round(float(stats.get("entry_follow_latency_ms", 0.0) or 0.0), 1),
        "second_pass_keep_review_used": sum(1 for item in web_items if isinstance(item, dict) and item.get("second_pass_keep_review_used")),
        "second_pass_keep_review_reason": count_item_field_values(web_items, "second_pass_keep_review_reason"),
        "second_pass_keep_recovered_count": sum(1 for item in web_items if isinstance(item, dict) and int(item.get("second_pass_keep_recovered_count") or 0) > 0),
        "core_keep_review_block_reason": stats.get("core_keep_review_block_reason", {}),
        "kept_candidate_source_type": kept_candidate_source_type,
        "kept_progress_from_raw": kept_progress_from_raw,
        "direct_candidate_rescue_used": direct_candidate_rescue_used,
        "direct_candidate_rescue_sources": direct_candidate_rescue_sources,
        "direct_candidate_rescue_stages": direct_candidate_rescue_stages,
        "rescue_promoted_from_filter": rescue_promoted_from_filter,
        "filter_decision_profile": stats.get("filter_decision_profile", {}),
        "recoverable_filter_reason": stats.get("recoverable_filter_reason", {}),
        "hard_drop_reason": stats.get("hard_drop_reason", {}),
        "readiness_promotion_used": readiness_promotion_used,
        "readiness_promotion_source": readiness_promotion_source,
        "candidate_strength_before_keep": candidate_strength_before_keep,
        "answer_candidate_count": int(stats.get("answer_candidate_count", 0) or 0),
        "answer_candidate_examples": stats.get("answer_candidate_examples", [])[:5],
        "soft_keep_claim_aligned_examples": [
            {
                "url": str(item.get("url") or ""),
                "source_type": str(item.get("source_type") or ""),
                "soft_keep_anchor_buckets": list(item.get("soft_keep_anchor_buckets") or [])[:4],
                "program_anchor_buckets": list(item.get("program_anchor_buckets") or [])[:4],
                "program_false_friend_hits": list(item.get("program_false_friend_hits") or [])[:3],
                "soft_keep_original_filter_reason": str(item.get("soft_keep_original_filter_reason") or ""),
            }
            for item in web_items
            if item.get("kept_by_soft_claim_alignment")
        ][:5],
        "program_anchor_buckets": list(program_anchor_buckets)[:6],
        "program_false_friend_hits": program_false_friend_hits,
        "program_used_for_retention": program_used_for_retention,
        "source_quality_scores": stats.get("source_quality_scores", [])[:30],
        "source_quality_avg": (
            round(sum(int(score or 0) for score in stats.get("source_quality_scores", [])) / len(stats.get("source_quality_scores", [])), 1)
            if stats.get("source_quality_scores") else None
        ),
        "task_card_scores": stats.get("task_card_scores", [])[:30],
        "task_card_reasons": stats.get("task_card_reasons", {}) if isinstance(stats.get("task_card_reasons"), dict) else {},
        "task_card_avg": (
            round(sum(int(score or 0) for score in stats.get("task_card_scores", [])) / len(stats.get("task_card_scores", [])), 1)
            if stats.get("task_card_scores") else None
        ),
        "source_quality_reasons": stats.get("source_quality_reasons", {}),
        "source_quality_detail_skipped": int(stats.get("source_quality_detail_skipped", 0) or 0),
        "page_intent": normalize_page_intent(source_intent),
        "page_intent_scores": stats.get("page_intent_scores", [])[:30],
        "page_intent_avg": (
            round(sum(int(score or 0) for score in stats.get("page_intent_scores", [])) / len(stats.get("page_intent_scores", [])), 1)
            if stats.get("page_intent_scores") else None
        ),
        "page_intent_labels": stats.get("page_intent_labels", {}),
        "page_intent_issues": stats.get("page_intent_issues", {}),
        "page_utility_scores": stats.get("page_utility_scores", [])[:30],
        "page_utility_labels": stats.get("page_utility_labels", {}),
        "page_utility_page_types": stats.get("page_utility_page_types", {}),
        "page_utility_page_focuses": stats.get("page_utility_page_focuses", {}),
        "page_utility_risks": stats.get("page_utility_risks", {}),
        "page_utility_llm_scores": stats.get("page_utility_llm_scores", [])[:20],
        "page_utility_llm_decisions": stats.get("page_utility_llm_decisions", {}),
        "page_utility_llm_risks": stats.get("page_utility_llm_risks", {}),
        "page_utility_llm_calls": int(stats.get("page_utility_llm_calls", 0) or 0),
        "evidence_contract_roles": stats.get("evidence_contract_roles", {}),
        "evidence_contract_statuses": stats.get("evidence_contract_statuses", {}),
        "evidence_contract_risks": stats.get("evidence_contract_risks", {}),
        "raw_page_roles": stats.get("page_roles", {}),
        "raw_page_role_reasons": stats.get("page_role_reasons", {}),
        "raw_generic_page_block_reasons": stats.get("generic_page_block_reasons", {}),
        "raw_entry_follow_states": stats.get("entry_follow_states", {}),
        "evidence_contract_by_query_origin": compact_evidence_contract_by_query_origin(stats),
        "source_pollution_stats": source_pollution_stats,
        "adaptive_source_fallback_used": int(stats.get("adaptive_source_fallback_used", 0) or 0),
        "adaptive_source_fallback_jobs": stats.get("adaptive_source_fallback_jobs", [])[:5],
        "source_precheck_stats": stats.get("source_precheck_stats", {}),
        "source_precheck_skipped_sources": int(stats.get("source_precheck_skipped_sources", 0) or 0),
        "source_health_before": stats.get("source_health_before", {}),
        "source_health_reorder_actions": stats.get("source_health_reorder_actions", [])[:10],
        "source_latency_profile": source_latency_profile,
        "slow_source_cutoff": source_latency_profile.get("slow_sources", []),
        "claim_retrieve_stop_reason": claim_retrieve_stop_reason,
        "retrieval_cost_review": retrieval_cost_review,
        "refutation_target": refutation_target,
        "refutation_query_plan": refutation_query_plan[:3],
        "refutation_retry_trigger": refutation_retry_trigger,
        "refutation_slot_gap": refutation_slot_gap[:5],
        "refutation_search_result": (
            "raw_positive" if refutation_retry_trigger and raw_results > 0
            else "no_raw" if refutation_retry_trigger
            else refutation_search_result
        ),
        "refutation_retrieval_stop_reason": refutation_retrieval_stop_reason or claim_retrieve_stop_reason,
        "contrastive_query_plan": contrastive_query_plan,
        "contrastive_retry_trigger": contrastive_retry_trigger,
        "contrastive_slot_gap": contrastive_slot_gap[:5],
        "contrastive_search_result": contrastive_search_result,
        "contrastive_stop_reason": contrastive_stop_reason or claim_retrieve_stop_reason,
        "atomic_query_plan": stats.get("atomic_query_plan", []),
        "atomic_retrieval_attempted": bool(stats.get("atomic_retrieval_attempted")),
        "atomic_query_limit": int(stats.get("atomic_query_limit") or 0),
        "atomic_search_results": stats.get("atomic_search_results", []),
        "atomic_gate_result": str(stats.get("atomic_gate_result") or ""),
        "atomic_stop_reason": str(stats.get("atomic_stop_reason") or claim_retrieve_stop_reason or ""),
        "trusted_deepen_used": int(stats.get("trusted_deepen_used", 0) or 0),
        "trusted_deepen_domains": stats.get("trusted_deepen_domains", []),
        "trusted_deepen_jobs": stats.get("trusted_deepen_jobs", [])[:6],
        "filtered_deepen_risk_counts": stats.get("filtered_deepen_risk_counts", {}),
        "tool_failure_stage": tool_failure_stage(reason, raw_results, web_items, strong_items, direct_items, stats),
        "source_timings": stats.get("source_timings", {}),
        "playwright_queries": stats.get("playwright_queries", []),
        "playwright_reasons": stats.get("playwright_reasons", []),
        "playwright_skipped_reasons": dedupe_keep_order(stats.get("playwright_skipped_reasons", []))[:5],
        "route_sentence_samples": [
            item.get("route_sentence")
            for item in web_items
            if isinstance(item.get("route_sentence"), dict)
        ][:3],
        "strong_web": len(strong_items),
        "direct_web": len(direct_items),
        "sources": dedupe_keep_order([str(item.get("source") or "") for item in web_items])[:5],
    }


def tool_failure_stage(
    reason: str,
    raw_results: int,
    web_items: List[Dict[str, Any]],
    strong_items: List[Dict[str, Any]],
    direct_items: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> str:
    if reason == "sufficient":
        return "sufficient"
    if raw_results == 0:
        return "no_search_result"
    if not web_items:
        return "all_results_filtered"
    if not strong_items:
        return "weak_sources_only"
    detail_attempts = int(stats.get("detail_attempts", 0) or 0)
    detail_successes = int(stats.get("detail_successes", 0) or 0)
    if detail_attempts > 0 and detail_successes == 0:
        return "detail_read_failed"
    if detail_successes > 0 and not direct_items:
        return "detail_read_no_answer"
    if not direct_items:
        return "answer_extraction_failed"
    return "stance_unknown_or_thin_evidence"


def build_queries_for_claim(question: str, claim: str, time_value: str = "", evidence_mode: str = "") -> List[str]:
    question = normalize_text(question)
    claim = normalize_text(claim)
    mode = policy_mode_label(evidence_mode)
    queries = []
    queries.extend(build_specialized_queries(question, claim, time_value))
    if claim:
        queries.append(claim)
    if question and question != claim:
        queries.append(question)
    if time_value and mode in {"date_fact", "schedule_fact", "event_result", "policy_fact"}:
        combined_text = f"{question} {claim}"
        if extract_temporal_markers(combined_text):
            return dedupe_keep_order(queries)[:3]
        queries.append(f"{claim} {time_value[:10]}")
    return dedupe_keep_order(queries)[:3]


def make_evidence(
    claim_id: str,
    source_type: str,
    title: str,
    snippet: str,
    url: str = "",
    relevance_score: int = 0,
    reliability_score: int = 0,
    temporal_score: int = 0,
) -> Dict[str, Any]:
    return {
        "claim_id": claim_id,
        "source_type": source_type,
        "title": normalize_text(title),
        "url": url,
        "snippet": normalize_text(snippet),
        "relevance_score": relevance_score,
        "reliability_score": reliability_score,
        "temporal_score": temporal_score,
        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def context_evidence(question: str, answer: str, history: List[Any], claim_id: str) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    history_text = " ".join(str(x) for x in history or [])
    if history_text:
        evidence.append(
            make_evidence(
                claim_id,
                "input_context",
                "多轮上下文",
                f"history_question: {history_text}",
                relevance_score=6,
                reliability_score=9,
                temporal_score=8,
            )
        )
    if any(token in answer for token in ["虚构", "假设", "剧本", "AI生成", "非真实新闻"]):
        if any(token in answer for token in ["目前", "现在", "当前", "正在", "已经", "进入第", "现实世界"]):
            evidence.append(
                make_evidence(
                    claim_id,
                    "input_context",
                    "回答内部虚构/现实状态冲突线索",
                    "回答包含虚构/假设/AI生成等免责声明，同时又包含目前/现在/当前/已经等现实状态展开，需重点检查是否主体误导。",
                    relevance_score=8,
                    reliability_score=8,
                    temporal_score=8,
                )
            )
    if question:
        evidence.append(
            make_evidence(
                claim_id,
                "input_context",
                "用户问题主需",
                f"question: {question}",
                relevance_score=5,
                reliability_score=9,
                temporal_score=8,
            )
        )
    return evidence


def parse_iso_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        except Exception:
            return None


def computational_evidence(question: str, answer: str, claim: str, claim_id: str, time_value: str) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    combined = f"{question}\n{answer}\n{claim}"
    claim_focus = claim
    sample_time = parse_iso_date(time_value)
    if sample_time:
        weekday_cn = "一二三四五六日"[sample_time.weekday()]
        date_tokens = r"\d{4}[-年]\d{1,2}[-月]\d{1,2}|今天|今日|星期|周[一二三四五六日天]|休市|开盘|交易日|节假日|清明"
        if re.search(date_tokens, claim_focus):
            evidence.append(
                make_evidence(
                    claim_id,
                    "computed",
                    "样本日期星期计算",
                    f"样本时间 {time_value} 对应星期{weekday_cn}。该证据只能证明星期/日期，不直接证明是否休市或节假日。",
                    relevance_score=7,
                    reliability_score=10,
                    temporal_score=10,
                )
            )

    ratio_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|小時).{0,12}(\d+(?:\.\d+)?)\s*天", combined)
    if ratio_match:
        hours = float(ratio_match.group(1))
        stated_days = float(ratio_match.group(2))
        actual_days = hours / 24
        evidence.append(
            make_evidence(
                claim_id,
                "computed",
                "小时与天数换算",
                f"{hours:g} 小时 = {actual_days:.2f} 天；回答中相关天数为 {stated_days:g} 天，可用于核对数量级。",
                relevance_score=7,
                reliability_score=10,
                temporal_score=9,
            )
        )

    if re.search(r"此前.{0,8}两次.{0,8}各胜一场|此前.{0,8}2次.{0,8}各胜一场", combined) and re.search(r"本场|加上", combined):
        evidence.append(
            make_evidence(
                claim_id,
                "computed",
                "交锋战绩逻辑计算",
                "若此前两次交手双方各胜一场，则此前为1-1；若本场其中一方获胜，总计应为2-1，而不是2-2。",
                relevance_score=9,
                reliability_score=10,
                temporal_score=9,
            )
        )

    fx_values = re.findall(r"(\d+\.\d{2,4})", combined)
    if any(token in combined for token in ["汇率", "美元", "人民币", "现汇", "买入价", "卖出价"]) and len(fx_values) >= 2:
        evidence.append(
            make_evidence(
                claim_id,
                "computed",
                "汇率数值换算线索",
                "回答包含汇率/美元/人民币相关数值；可用 100 美元牌价除以100 与 1美元换算表述交叉核对。",
                relevance_score=6,
                reliability_score=8,
                temporal_score=7,
            )
        )
    return evidence


def retrieve_evidence(
    question: str,
    answer: str,
    history: List[Any],
    claims: List[Dict[str, Any]],
    time_value: str = "",
    max_results_per_query: int = 3,
    fetch_details: int = 0,
    timeout_sec: int = 10,
    query_limits: Optional[Dict[str, int]] = None,
    source_limits: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    evidence_by_claim: Dict[str, List[Dict[str, Any]]] = {}
    diagnostics_by_claim: Dict[str, Dict[str, Any]] = {}
    all_logs: List[Dict[str, Any]] = []
    started_at = time.time()
    budget_sec = float(os.environ.get("V2_RETRIEVAL_BUDGET_SEC", "0") or 0)
    source_health: Dict[str, Dict[str, Any]] = {}
    shared_authority_hints = build_shared_authority_subject_hints(claims)

    def budget_exhausted() -> bool:
        return budget_sec > 0 and (time.time() - started_at) >= budget_sec

    for claim_item in claims:
        if budget_exhausted():
            all_logs.append({"source": "retrieval_budget", "error": "budget_exhausted_before_claim"})
            break
        claim_id = str(claim_item.get("claim_id") or claim_item.get("id") or "")
        claim_text = normalize_text(str(claim_item.get("claim") or ""))
        centrality = normalize_text(str(claim_item.get("centrality") or "supporting")) or "supporting"
        source_intent = claim_item.get("source_intent") if isinstance(claim_item.get("source_intent"), dict) else {}
        if not isinstance(source_intent.get("source_strategy"), dict) or not any(source_intent.get("source_strategy", {}).get(key) for key in ("source_types", "search_channels", "must_have")):
            source_intent = dict(source_intent)
            source_intent["source_strategy"] = default_source_strategy(source_intent, claim_text, question)
        source_intent = enrich_source_intent_with_shared_authority_hint(source_intent, shared_authority_hints)
        sanitize_result = sanitize_source_intent(source_intent)
        source_intent = sanitize_result.get("source_intent") if isinstance(sanitize_result.get("source_intent"), dict) else source_intent
        evidence_mode = effective_evidence_mode(source_intent, str(source_intent.get("evidence_mode") or "entity_fact"))
        evidence_target = str(source_intent.get("evidence_target") or "general")
        inline_query_domains = query_items_site_domains(normalize_query_items(claim_item.get("queries") or []))
        if inline_query_domains:
            source_intent = dict(source_intent)
            existing_domains = preferred_domains_from_intent(source_intent)
            source_intent["preferred_domains"] = dedupe_keep_order(existing_domains + inline_query_domains)
        should_attempt_official_discovery = (
            bool(preferred_domains_from_intent(source_intent))
            or evidence_mode in {"date_fact", "schedule_fact", "route_fact", "numeric_fact"}
            or (evidence_mode == "event_result" and centrality == "core")
        )
        if should_attempt_official_discovery:
            discovery_started = time.perf_counter()
            discovery_timeout = min(timeout_sec, 6 if evidence_mode in {"date_fact", "schedule_fact", "route_fact", "numeric_fact"} else 4)
            discovery_result = discover_official_domains(question, claim_text, source_intent, timeout_sec=discovery_timeout)
            discovery_elapsed = time.perf_counter() - discovery_started
        else:
            discovery_result = {
                "official_discovery_attempted": False,
                "official_domain_candidates": [],
                "discovered_domains": [],
                "official_discovery_score": 0,
                "official_discovery_used": False,
                "official_discovery_queries": [],
                "official_discovery_logs": [],
                "official_discovery_block_reason": "skipped_low_roi",
            }
            discovery_elapsed = 0.0
        if discovery_result.get("discovered_domains"):
            source_intent = dict(source_intent)
            existing_domains = preferred_domains_from_intent(source_intent)
            source_intent["preferred_domains"] = dedupe_keep_order(
                existing_domains + [str(domain) for domain in discovery_result.get("discovered_domains") or []]
            )
        preferred_domains = preferred_domains_from_intent(source_intent)
        source_strategy_eval = score_source_strategy(source_intent, claim_text, question)
        if source_strategy_eval.get("source_strategy_label") in {"weak", "bad"}:
            source_intent = dict(source_intent)
            source_intent["source_strategy"] = {}
        planned_claim_item = dict(claim_item)
        planned_claim_item["source_intent"] = source_intent
        query_plan = query_texts_from_plan(question, claim_text, time_value, planned_claim_item)
        query_plan = add_temporal_anchors_to_queries(query_plan, answer, time_value, evidence_mode)
        query_plan = order_query_plan(query_plan, evidence_mode, source_intent)
        original_query_count = len(query_plan)
        claim_query_limit = MAX_QUERIES_PER_CLAIM
        if isinstance(query_limits, dict) and claim_id in query_limits:
            try:
                claim_query_limit = max(0, int(query_limits.get(claim_id, MAX_QUERIES_PER_CLAIM)))
            except Exception:
                claim_query_limit = MAX_QUERIES_PER_CLAIM
        claim_source_limit = 0
        if isinstance(source_limits, dict) and claim_id in source_limits:
            try:
                claim_source_limit = max(0, int(source_limits.get(claim_id, 0)))
            except Exception:
                claim_source_limit = 0
        task_card = planned_claim_item.get("evidence_task_card") if isinstance(planned_claim_item.get("evidence_task_card"), dict) else {}
        query_plan = apply_query_plan_policy(query_plan, claim_query_limit, source_intent, task_card, evidence_mode)
        query_plan = ensure_verification_query(query_plan, planned_claim_item, claim_text, source_intent, claim_query_limit)
        recall_probe_item = build_recall_probe_query_item(planned_claim_item, claim_text, source_intent, query_plan, evidence_mode)
        execution_query_plan = list(query_plan)
        if recall_probe_item and not any(
            normalize_text(str(item.get("q") or "")) == normalize_text(str(recall_probe_item.get("q") or ""))
            and normalize_text(str(item.get("origin") or "")) == normalize_text(str(recall_probe_item.get("origin") or ""))
            for item in execution_query_plan
            if isinstance(item, dict)
        ):
            execution_query_plan.append(recall_probe_item)
        refutation_target = planned_claim_item.get("_refutation_target") if isinstance(planned_claim_item.get("_refutation_target"), dict) else {}
        refutation_query_text = normalize_text(str(refutation_target.get("query") or ""))
        if refutation_target.get("state") == "ready" and refutation_query_text and not any(
            normalize_text(str(item.get("q") or "")) == refutation_query_text
            for item in execution_query_plan
            if isinstance(item, dict)
        ):
            execution_query_plan.append(
                {
                    "q": refutation_query_text,
                    "goal": "find_refutation_target",
                    "origin": "refutation_target_execution",
                    "query_variant_origin": "refutation_target",
                    "source_preference": ["official", "news", "html"],
                }
            )
        contrastive_query_plan = (
            planned_claim_item.get("_contrastive_query_plan")
            if isinstance(planned_claim_item.get("_contrastive_query_plan"), dict)
            else {}
        )
        contrastive_query_text = normalize_text(str(contrastive_query_plan.get("query") or ""))
        if ENABLE_CONTRASTIVE_RETRIEVAL and contrastive_query_plan.get("state") == "ready" and contrastive_query_text and not any(
            normalize_text(str(item.get("q") or "")) == contrastive_query_text
            for item in execution_query_plan
            if isinstance(item, dict)
        ):
            execution_query_plan.append(
                {
                    "q": contrastive_query_text,
                    "goal": "find_contrastive_evidence",
                    "origin": "contrastive_query_execution",
                    "query_variant_origin": "contrastive_query",
                    "source_preference": ["official", "news", "html"],
                }
            )
        atomic_query_plan = atomic_claim_query_plan_rows(planned_claim_item)
        atomic_query_items = atomic_claim_query_items_from_plan(atomic_query_plan)
        atomic_items_to_prepend: List[Dict[str, Any]] = []
        for atomic_query_item in atomic_query_items:
            atomic_query_text = normalize_text(str(atomic_query_item.get("q") or ""))
            if not atomic_query_text:
                continue
            if any(
                normalize_text(str(item.get("q") or "")) == atomic_query_text
                and str(item.get("atomic_claim_id") or "") == str(atomic_query_item.get("atomic_claim_id") or "")
                for item in execution_query_plan
                if isinstance(item, dict)
            ):
                continue
            atomic_items_to_prepend.append(atomic_query_item)
        if atomic_items_to_prepend:
            execution_query_plan = atomic_items_to_prepend + execution_query_plan
        source_plan = source_plan_from_intent(question, claim_text, source_intent)
        search_request = build_search_request(planned_claim_item, source_intent, query_plan, evidence_mode)
        search_policy = build_search_policy(
            claim_query_limit,
            claim_source_limit,
            preferred_domains,
            source_plan,
            source_intent,
            evidence_mode,
            centrality,
        )
        claim_evidence: List[Dict[str, Any]] = []
        stats: Dict[str, Any] = {
            "query_count": 0,
            "qa_query_count": sum(1 for item in query_plan if item.get("goal") == "verification_question"),
            "query_limit": claim_query_limit,
            "source_limit": claim_source_limit,
            "planned_query_count": original_query_count,
            "executed_query_plan": execution_query_plan,
            "executed_query_source_plan": [],
            "query_variant_origin": query_variant_origin_rows(execution_query_plan),
            "skipped_by_query_budget": original_query_count if claim_query_limit <= 0 else max(0, original_query_count - len(query_plan)),
            "raw_results": 0,
            "filtered_results": 0,
            "recall_probe_used": 0,
            "recall_probe_query": "",
            "recall_probe_source": [],
            "recall_probe_raw_hits": 0,
            "source_plan_used": source_plan,
            "llm_source_strategy": source_intent.get("source_strategy", {}) if isinstance(source_intent.get("source_strategy"), dict) else {},
            "source_strategy_sanitized": bool(sanitize_result.get("changed")),
            "source_strategy_sanitize_actions": sanitize_result.get("actions", []),
            "source_strategy_before": sanitize_result.get("before", {}),
            "source_strategy_after": sanitize_result.get("after", {}),
            "preferred_domains": preferred_domains,
            "official_discovery_attempted": discovery_result.get("official_discovery_attempted", False),
            "official_domain_candidates": discovery_result.get("official_domain_candidates", []),
            "discovered_domains": discovery_result.get("discovered_domains", []),
            "official_discovery_score": discovery_result.get("official_discovery_score", 0),
            "official_discovery_used": discovery_result.get("official_discovery_used", False),
            "official_discovery_queries": discovery_result.get("official_discovery_queries", []),
            "official_discovery_logs": discovery_result.get("official_discovery_logs", []),
            "official_discovery_block_reason": discovery_result.get("official_discovery_block_reason", ""),
            "evidence_task_card": claim_item.get("evidence_task_card", {}) if isinstance(claim_item.get("evidence_task_card"), dict) else {},
            "search_request": search_request,
            "search_policy": search_policy,
            "refutation_target": planned_claim_item.get("_refutation_target", {}) if isinstance(planned_claim_item.get("_refutation_target"), dict) else {},
            "refutation_query_plan": [
                item for item in execution_query_plan
                if isinstance(item, dict) and query_variant_origin_value(item) == "refutation_target"
            ][:2],
            "refutation_retry_trigger": "slot_contract_target" if any(
                isinstance(item, dict) and query_variant_origin_value(item) == "refutation_target"
                for item in execution_query_plan
            ) else "",
            "refutation_slot_gap": (
                planned_claim_item.get("_refutation_target", {}).get("missing_slots")
                if isinstance(planned_claim_item.get("_refutation_target"), dict)
                else []
            ),
            "refutation_search_result": "planned" if any(
                isinstance(item, dict) and query_variant_origin_value(item) == "refutation_target"
                for item in execution_query_plan
            ) else "not_planned",
            "refutation_retrieval_stop_reason": "",
            "contrastive_query_plan": contrastive_query_plan,
            "contrastive_retry_trigger": str(contrastive_query_plan.get("trigger") or "") if contrastive_query_plan.get("state") == "ready" else "",
            "contrastive_slot_gap": (
                contrastive_query_plan.get("slot_gap")
                if isinstance(contrastive_query_plan.get("slot_gap"), list)
                else []
            ),
            "contrastive_search_result": (
                "planned" if any(
                    isinstance(item, dict) and query_variant_origin_value(item) == "contrastive_query"
                    for item in execution_query_plan
                )
                else "execution_disabled" if contrastive_query_plan.get("state") == "ready" and not ENABLE_CONTRASTIVE_RETRIEVAL
                else "not_planned"
            ),
            "contrastive_stop_reason": (
                "disabled_by_latency_guard"
                if contrastive_query_plan.get("state") == "ready" and not ENABLE_CONTRASTIVE_RETRIEVAL
                else ""
            ),
            "atomic_query_plan": atomic_query_plan,
            "atomic_retrieval_attempted": any(
                isinstance(item, dict) and bool(item.get("atomic_claim_id"))
                for item in execution_query_plan
            ),
            "atomic_query_limit": max(0, int(ATOMIC_CLAIM_QUERY_LIMIT or 0)),
            "atomic_search_results": [],
            "atomic_gate_result": (
                "not_planned"
                if not atomic_query_plan
                else "execution_disabled"
                if atomic_query_plan and not ENABLE_ATOMIC_CLAIM_RETRIEVAL
                else "planned_waiting_execution"
            ),
            "atomic_stop_reason": (
                "no_atomic_claims_attached"
                if not atomic_query_plan
                else "disabled_by_latency_guard"
                if atomic_query_plan and not ENABLE_ATOMIC_CLAIM_RETRIEVAL
                else ""
            ),
            "playwright_roles": [],
            "claim_retrieve_stop_reason": "",
            "rescue_latency_ms": 0.0,
            "family_rescue_budget_used": {"serp_count": 0, "detail_count": 0, "families": {}},
            **source_strategy_eval,
        }
        add_timing(stats, "official_discovery", discovery_elapsed)
        if source_strategy_eval.get("source_strategy_label") in {"weak", "bad"}:
            stats["source_strategy_fallback"] = "default_source_plan"
        retry_policy = retry_source_plan_policy(source_intent)
        if retry_policy:
            stats["route_retry_source_strategy"] = retry_policy
        detail_fetches = 0
        used_playwright_queries = 0
        used_playwright_detail_rescues = 0
        adaptive_fallback_used_for_claim = 0
        failed_rescue_families: set[str] = set()
        claim_evidence.extend(context_evidence(question, answer, history, claim_id))
        claim_evidence.extend(computational_evidence(question, answer, claim_text, claim_id, time_value))
        for candidate in discovery_result.get("official_domain_candidates", []) or []:
            if should_stop_querying_after_web_budget(claim_evidence, evidence_mode, source_intent, max_results_per_query):
                break
            if candidate.get("domain") not in set(discovery_result.get("discovered_domains") or []):
                continue
            item = {
                "title": candidate.get("title", ""),
                "url": candidate.get("url", ""),
                "snippet": "official discovery candidate",
                "source_type": dynamic_source_type(str(candidate.get("url", "")), "", preferred_domains, source_intent),
                "source": "official_discovery",
                "query": "official_source_discovery",
                "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "official_discovery_score": candidate.get("score", 0),
                "official_discovery_reasons": candidate.get("reasons", []),
            }
            item.update(page_intent_features(item, source_intent, f"{question} {claim_text}", stats))
            if fetch_details > 0 and item.get("url") and detail_fetches < FETCH_DETAILS_PER_CLAIM:
                stats["detail_attempts"] = int(stats.get("detail_attempts", 0) or 0) + 1
                allow_detail_rescue, detail_rescue_skip_reason = should_allow_playwright_detail_rescue(
                    item,
                    claim_item,
                    evidence_mode,
                    used_playwright_detail_rescues,
                )
                detail_trace: Dict[str, Any] = {
                    "allow_playwright_detail_rescue": allow_detail_rescue,
                    "rescue_skip_reason": detail_rescue_skip_reason,
                }
                try:
                    detail_started = time.perf_counter()
                    page_text = fetch_page_text(str(item["url"]), max_chars=5000, timeout_sec=timeout_sec, trace=detail_trace)
                    item["detail"] = extract_relevant_passage(
                        page_text,
                        passage_focus_terms(f"{question} {claim_text}", str(item.get("title") or "")),
                        max_chars=1800,
                    )
                    enrich_structured_table_evidence(item, source_intent, timeout_sec=timeout_sec, fetch_trace=detail_trace)
                    apply_detail_fetch_trace(stats, item, detail_trace, "official_discovery")
                    if detail_trace.get("playwright_rescued"):
                        used_playwright_detail_rescues += 1
                        item["_detail_rescue_playwright_used"] = True
                        stats["rescue_progress_delta"] = {
                            "raw_delta": 0,
                            "kept_delta": 0,
                            "stage": "detail_content_recovered",
                        }
                        stats["rescue_success_gate"] = "detail_content_recovered"
                        stats["rescue_target_page_type"] = str(item.get("page_utility_page_type") or "") or "detail_page"
                        stats["detail_rescue_roi_state"] = "detail_content_recovered"
                        stats["detail_rescue_target_page_type"] = str(item.get("page_utility_page_type") or "") or "detail_page"
                        record_rescue_budget_event(
                            stats,
                            "detail",
                            "official_discovery",
                            "succeeded",
                            latency_ms=(time.perf_counter() - detail_started) * 1000.0,
                        )
                    detail_fetches += 1
                    stats["detail_successes"] = int(stats.get("detail_successes", 0) or 0) + 1
                    add_timing(stats, "fetch_detail", time.perf_counter() - detail_started)
                except Exception as exc:
                    add_timing(stats, "fetch_detail", time.perf_counter() - detail_started if "detail_started" in locals() else 0.0)
                    apply_detail_fetch_trace(stats, item, detail_trace, "official_discovery")
                    if detail_trace.get("playwright_used") or detail_trace.get("playwright_rescue_skipped_by_policy"):
                        used_playwright_detail_rescues += 1 if detail_trace.get("playwright_used") else 0
                        record_rescue_budget_event(
                            stats,
                            "detail",
                            "official_discovery",
                            "failed" if detail_trace.get("playwright_used") else "skipped",
                            latency_ms=(time.perf_counter() - detail_started) * 1000.0 if "detail_started" in locals() else 0.0,
                            skip_reason=str(detail_trace.get("rescue_skip_reason") or ""),
                        )
                        if detail_trace.get("playwright_used"):
                            stats["detail_rescue_failure_reason"] = "detail_rescue_page_open_failed"
                        else:
                            stats["detail_rescue_failure_reason"] = str(detail_trace.get("rescue_skip_reason") or "detail_rescue_skipped")
                        if not detail_trace.get("playwright_used"):
                            stats["rescue_non_roi_reason"] = str(detail_trace.get("rescue_skip_reason") or "detail_rescue_skipped")
                    record_detail_fetch_failure(stats, item, exc)
            item["relevance_score"] = evidence_relevance_score(f"{question} {claim_text}", item)
            item["entity_match_count"] = entity_match_count(f"{question} {claim_text}", item)
            item["directness_score"] = evidence_directness_score(f"{question} {claim_text}", item, evidence_mode)
            item["temporal_score"] = evidence_temporal_score(f"{question} {claim_text}", item)
            item["event_window_score"] = event_window_score(f"{question} {claim_text}", item, evidence_mode)
            item["answer_candidates"] = answer_candidate_sentences(f"{question} {claim_text}", item, evidence_mode=evidence_mode)
            maybe_apply_deterministic_candidate_rescue(claim_item, item, evidence_mode, f"{question} {claim_text}")
            item["answer_candidate_quality_score"] = answer_candidate_quality_score(item)
            if item.get("direct_candidate_rescue_used"):
                stats["direct_candidate_rescue_used"] = int(stats.get("direct_candidate_rescue_used", 0) or 0) + 1
                source_field = str(item.get("direct_candidate_rescue_source") or "")
                if source_field:
                    increment_named_counter(stats, "direct_candidate_rescue_sources", source_field)
            item.update(source_quality_features(f"{question} {claim_text}", item, evidence_mode, preferred_domains))
            item.update(page_intent_features(item, source_intent, f"{question} {claim_text}", stats))
            record_page_intent_stats(stats, item)
            stats.setdefault("source_quality_scores", []).append(item.get("source_quality_score", 0))
            for reason_item in item.get("source_quality_reasons", []):
                reason_counts = stats.setdefault("source_quality_reasons", {})
                reason_counts[reason_item] = int(reason_counts.get(reason_item, 0) or 0) + 1
            if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}:
                item.update(structured_noise_features(f"{question} {claim_text}", item, evidence_mode))
            should_entry_follow, _entry_follow_reason = should_follow_entry_page(item, source_intent, evidence_mode)
            if should_entry_follow and not item.get("_bridge_expanded"):
                item["_bridge_expanded"] = True
                detail_fetches = expand_official_inner_link_candidates(
                    claim_evidence,
                    stats,
                    item,
                    f"{question} {claim_text}",
                    source_intent,
                    claim_item,
                    evidence_mode,
                    evidence_target,
                    preferred_domains,
                    fetch_details,
                    detail_fetches,
                    timeout_sec,
                    max_results_per_query,
                )
            keep_item, filter_reason = web_evidence_filter_reason(f"{question} {claim_text}", item, evidence_mode)
            task_card = claim_item.get("evidence_task_card", {}) if isinstance(claim_item.get("evidence_task_card"), dict) else {}
            if not keep_item and should_soft_keep_high_priority_item(item, filter_reason, evidence_mode, task_card):
                keep_item = True
                filter_reason = "soft_keep_high_priority_structured_candidate"
            if not keep_item and should_soft_keep_structured_metric_item(item, filter_reason, evidence_mode, task_card):
                original_filter_reason = filter_reason
                keep_item = True
                filter_reason = "soft_keep_structured_metric_table_candidate"
                annotate_soft_kept_structured_metric_item(item, f"{question} {claim_text}", evidence_mode, original_filter_reason, claim_item)
            if not keep_item and should_soft_keep_claim_aligned_fact_item(f"{question} {claim_text}", item, filter_reason, evidence_mode, claim_item):
                original_filter_reason = filter_reason
                keep_item = True
                filter_reason = "soft_keep_claim_aligned_fact_page"
                annotate_soft_kept_claim_aligned_item(item, f"{question} {claim_text}", evidence_mode, original_filter_reason, claim_item)
            if not keep_item and should_soft_keep_key_evidence_page(f"{question} {claim_text}", item, filter_reason, evidence_mode, claim_item):
                original_filter_reason = filter_reason
                keep_item = True
                filter_reason = "key_evidence_page_keep_review"
                annotate_key_evidence_page_keep(item, f"{question} {claim_text}", evidence_mode, original_filter_reason, claim_item)
            if not keep_item and should_soft_keep_route_review_item(item, filter_reason, evidence_mode):
                keep_item = True
                filter_reason = "soft_keep_route_review_candidate"
            if not keep_item:
                keep_item, filter_reason = maybe_promote_fact_page_keep_review(
                    f"{question} {claim_text}",
                    item,
                    filter_reason,
                    evidence_mode,
                    claim_item,
                )
            if not keep_item:
                keep_item, filter_reason = maybe_promote_core_second_pass_keep_review(
                    f"{question} {claim_text}",
                    item,
                    filter_reason,
                    evidence_mode,
                    claim_item,
                    int(stats.get("raw_results") or 0) + 1,
                    sum(
                        1
                        for kept_item in claim_evidence
                        if isinstance(kept_item, dict) and kept_item.get("source_type") not in {"input_context", "computed"}
                    ),
                )
            if not keep_item:
                keep_item, filter_reason = maybe_promote_prefilter_candidate_rescue(
                    f"{question} {claim_text}",
                    item,
                    filter_reason,
                    evidence_mode,
                    claim_item,
                )
            if not keep_item and should_soft_keep_key_evidence_page(f"{question} {claim_text}", item, filter_reason, evidence_mode, claim_item):
                original_filter_reason = filter_reason
                keep_item = True
                filter_reason = "key_evidence_page_keep_review"
                annotate_key_evidence_page_keep(item, f"{question} {claim_text}", evidence_mode, original_filter_reason, claim_item)
            stats["raw_results"] += 1
            if keep_item:
                record_fact_filter_diagnostic(stats, item, True, filter_reason)
                if item.get("second_pass_keep_review_used"):
                    stats["second_pass_keep_recovered_count"] = int(stats.get("second_pass_keep_recovered_count", 0) or 0) + int(item.get("second_pass_keep_recovered_count") or 1)
                    increment_named_counter(stats, "second_pass_keep_review_reason", str(item.get("second_pass_keep_review_reason") or filter_reason))
                if item.get("readiness_promotion_used"):
                    stats["readiness_promotion_used"] = int(stats.get("readiness_promotion_used", 0) or 0) + 1
                    increment_named_counter(stats, "readiness_promotion_source", normalize_text(str(item.get("readiness_promotion_source") or "fact_page_keep_review")) or "fact_page_keep_review")
                    stats.setdefault("candidate_strength_before_keep_scores", []).append(int(item.get("candidate_strength_before_keep") or 0))
                finalize_detail_rescue_effect(stats, item, keep_item)
                finalize_direct_candidate_rescue_progress(item, default_stage="post_keep")
                claim_evidence.append(item)
                if not item.get("_bridge_expanded"):
                    detail_fetches = expand_official_inner_link_candidates(
                        claim_evidence,
                        stats,
                        item,
                        f"{question} {claim_text}",
                        source_intent,
                        claim_item,
                        evidence_mode,
                        evidence_target,
                        preferred_domains,
                        fetch_details,
                        detail_fetches,
                        timeout_sec,
                        max_results_per_query,
                    )
            else:
                if item.get("core_keep_review_block_reason"):
                    increment_named_counter(stats, "core_keep_review_block_reason", str(item.get("core_keep_review_block_reason") or "blocked"))
                finalize_detail_rescue_effect(stats, item, keep_item)
                record_fact_filter_diagnostic(stats, item, False, filter_reason)
                stats["filtered_results"] += 1
                add_filter_reason(stats, filter_reason)
                add_filtered_sample(stats, filter_reason, item)
                record_filtered_rescue_pool_candidate(stats, f"{question} {claim_text}", item, filter_reason, evidence_mode, claim_item)
        if claim_query_limit <= 0:
            stats["retrieval_budget_skip"] = "query_limit_zero"
        for query_item in execution_query_plan:
            if budget_exhausted():
                stats["budget_exhausted"] = True
                break
            is_recall_probe = bool(query_item.get("probe_only_if_raw_zero"))
            if is_recall_probe and int(stats.get("raw_results", 0) or 0) > 0:
                continue
            query_goal = normalize_text(query_item.get("goal") or "general_verify") or "general_verify"
            query_family_role = normalize_text(str(query_item.get("query_family_role") or ""))
            query = normalize_text(query_item.get("q") or "")
            if not query:
                continue
            is_atomic_query = bool(query_item.get("atomic_claim_id")) or query_variant_origin_value(query_item) == "atomic_claim_query"
            stats["query_count"] += 1
            if should_stop_querying_after_web_budget(claim_evidence, evidence_mode, source_intent, max_results_per_query):
                break
            page_intent = normalize_page_intent(source_intent)
            page_probe_adaptive_fallback = (
                query_goal in {"find_route_page", "find_page_intent_page"}
                or (
                    query_goal == "verification_question"
                    and str(page_intent.get("needed_page_type") or "") not in {"", "general_page"}
                )
            )
            authority_first_query = query_needs_authority_pair(query_goal, query_family_role, source_intent)
            allow_adaptive_fallback = (ENABLE_ADAPTIVE_SOURCE_FALLBACK or page_probe_adaptive_fallback or authority_first_query) and not is_recall_probe
            source_jobs = [
                (source_name, query)
                for source_name in source_plan_for_query_goal(source_plan, query_item, query_goal, source_intent)
            ]
            planned_source_order = [str(item) for item in (query_item.get("_planned_source_order") or []) if str(item)]
            post_role_priority_order = [str(item) for item in (query_item.get("_post_role_priority_order") or []) if str(item)]
            if is_recall_probe:
                source_jobs = restrict_recall_probe_source_jobs(source_jobs, evidence_mode)
                stats["recall_probe_used"] = 1
                stats["recall_probe_query"] = query
                stats["recall_probe_source"] = [source_name for source_name, _ in source_jobs]
            if ENABLE_SOURCE_HEALTH_REORDER:
                stats["source_health_before"] = {
                    key: dict(value)
                    for key, value in list(source_health.items())[:20]
                }
                before_health_reorder = [source_name for source_name, _ in source_jobs]
                source_jobs, health_actions = reorder_sources_by_health(source_jobs, source_health, evidence_mode, query_goal)
                if health_actions:
                    stats.setdefault("source_health_reorder_actions", []).extend(health_actions[:5])
                    stats["provider_health_snapshot"] = health_actions[:5]
                note_source_order_stage(query_item, "health_reorder_order", [source_name for source_name, _ in source_jobs], before_health_reorder, "reorder_sources_by_health")
            original_source_job_count = len(source_jobs)
            if claim_source_limit > 0:
                source_jobs, source_budget_cutoff = budgeted_source_jobs(source_jobs, claim_source_limit, query_goal, source_intent, query_item)
                stats["skipped_sources_by_budget"] = int(stats.get("skipped_sources_by_budget", 0) or 0) + max(0, original_source_job_count - len(source_jobs))
                if source_budget_cutoff.get("applied"):
                    stats["source_budget_cutoff"] = source_budget_cutoff
            post_budget_selected_order = [source_name for source_name, _ in source_jobs]
            note_source_order_stage(
                query_item,
                "post_budget_selected_order",
                post_budget_selected_order,
                post_role_priority_order or planned_source_order,
                str((stats.get("source_budget_cutoff") or {}).get("final_source_selection_reason") or "budgeted_source_jobs"),
            )
            stats["effective_source_plan"] = dedupe_keep_order(
                list(stats.get("effective_source_plan", [])) + [source_name for source_name, _ in source_jobs]
            )[:10]
            use_playwright, playwright_policy_reason = should_use_playwright_fallback(
                claim_evidence,
                evidence_mode,
                centrality,
                source_intent,
            )
            query_playwright_allowed = (
                not is_recall_probe
                and ENABLE_PLAYWRIGHT
                and used_playwright_queries < PLAYWRIGHT_MAX_QUERIES_PER_CLAIM
                and use_playwright
                and playwright_rescue_mode_allowed(evidence_mode, centrality, source_intent)
                and not extract_site_constraint(query)
            )
            if not query_playwright_allowed and not is_recall_probe and ENABLE_PLAYWRIGHT:
                stats.setdefault("playwright_skipped_reasons", []).append(playwright_policy_reason)
            executed_query_row = {
                "q": query,
                "goal": query_goal,
                "origin": normalize_text(str(query_item.get("origin") or "")) or "planner",
                "query_variant_origin": query_variant_origin_value(query_item),
                "probe_only_if_raw_zero": is_recall_probe,
                "sources": post_budget_selected_order[:10],
                "source_count": len(source_jobs),
                "planned_source_order": planned_source_order[:10],
                "post_role_priority_order": post_role_priority_order[:10],
                "post_budget_selected_order": post_budget_selected_order[:10],
                "final_executed_source_order": [],
                "source_order_trace": list(query_item.get("_source_order_trace") or [])[:8],
                "priority_source_dropped_stage": str((stats.get("source_budget_cutoff") or {}).get("priority_source_dropped_stage") or ""),
                "final_source_selection_reason": str((stats.get("source_budget_cutoff") or {}).get("final_source_selection_reason") or ""),
                "authority_pair_preserved": bool((stats.get("source_budget_cutoff") or {}).get("authority_pair_preserved")),
            }
            if is_atomic_query:
                executed_query_row.update(
                    {
                        "atomic_query": True,
                        "atomic_claim_id": str(query_item.get("atomic_claim_id") or ""),
                        "atomic_risk_type": str(query_item.get("atomic_risk_type") or ""),
                    }
                )
            stats.setdefault("executed_query_source_plan", []).append(executed_query_row)
            fallback_jobs = adaptive_fallback_candidates(source_plan, source_jobs, query)
            fallback_used_for_query = 0
            source_index = 0
            query_raw_before = int(stats.get("raw_results", 0) or 0)
            query_bad_before = sum(
                int(bucket.get("bad", 0) or 0)
                for bucket in (stats.get("source_pollution_stats") if isinstance(stats.get("source_pollution_stats"), dict) else {}).values()
            )
            query_kept_before = sum(1 for ev in claim_evidence if ev.get("source_type") not in {"input_context", "computed"})
            query_high_priority_attempted = False
            query_anti_bot_blocked = False
            query_playwright_scheduled = any(source_name == "playwright_duckduckgo" for source_name, _ in source_jobs)
            executed_source_order: List[str] = []
            query_rescue_family = ""

            def maybe_schedule_query_playwright_rescue() -> None:
                nonlocal query_playwright_scheduled, used_playwright_queries
                if not query_playwright_allowed or query_playwright_scheduled:
                    return
                if used_playwright_queries >= PLAYWRIGHT_MAX_QUERIES_PER_CLAIM:
                    record_rescue_budget_event(stats, "serp", query_rescue_family or "playwright_duckduckgo", "skipped", skip_reason="serp_rescue_budget_exhausted")
                    stats["rescue_roi_state"] = "budget_exhausted_before_rescue"
                    return
                if int(stats.get("kept_web", 0) or 0) > 0 or sum(1 for ev in claim_evidence if ev.get("source_type") not in {"input_context", "computed"}) > query_kept_before:
                    record_rescue_budget_event(stats, "serp", query_rescue_family or "playwright_duckduckgo", "skipped", skip_reason="kept_web_already_positive")
                    stats["rescue_roi_state"] = "skipped_after_kept_progress"
                    return
                if query_rescue_family and query_rescue_family in failed_rescue_families:
                    record_rescue_budget_event(stats, "serp", query_rescue_family, "skipped", skip_reason="same_family_rescue_failed")
                    stats["rescue_roi_state"] = "skipped_same_family_failed"
                    return
                query_raw_now = int(stats.get("raw_results", 0) or 0) - query_raw_before
                rescue_trigger = ""
                if query_anti_bot_blocked:
                    rescue_trigger = "anti_bot_blocked"
                elif PLAYWRIGHT_AFTER_SEARCH and query_high_priority_attempted and source_index >= len(source_jobs) and query_raw_now <= 0:
                    rescue_trigger = "high_priority_sources_no_raw"
                if not rescue_trigger:
                    return
                source_jobs.append(("playwright_duckduckgo", query))
                query_playwright_scheduled = True
                used_playwright_queries += 1
                stats["playwright_rescue_trigger"] = rescue_trigger
                stats.setdefault("playwright_queries", []).append(query)
                stats.setdefault("playwright_reasons", []).append(rescue_trigger)
                role = "authority_entry_opener" if query_item.get("query_family_role") in {"closure", "distinguish", "refute"} else "serp_rescue"
                stats.setdefault("playwright_roles", []).append(role)
                stats["rescue_roi_state"] = f"scheduled_{rescue_trigger}"

            while source_index < len(source_jobs):
                source_name, source_query = source_jobs[source_index]
                source_index += 1
                if budget_exhausted():
                    stats["budget_exhausted"] = True
                    break
                if source_name != "playwright_duckduckgo":
                    stop_reason = source_family_stop_loss_triggered(stats, source_name)
                    if stop_reason:
                        stats["claim_retrieve_stop_reason"] = normalize_text(f"{source_name}:{stop_reason}") or stop_reason
                        continue
                executed_source_order.append(source_name)
                if source_name != "playwright_duckduckgo" and high_priority_search_source(source_name):
                    query_high_priority_attempted = True
                if should_precheck_source(source_name, source_query, max_results_per_query) and not source_precheck_passes(
                    stats,
                    source_name,
                    source_query,
                    evidence_mode,
                    preferred_domains,
                    timeout_sec,
                ):
                    stats["source_precheck_skipped_sources"] = int(stats.get("source_precheck_skipped_sources", 0) or 0) + 1
                    maybe_schedule_query_playwright_rescue()
                    continue
                try:
                    source_started = time.perf_counter()
                    items = search_source(source_name, source_query, max_results_per_query, timeout_sec)
                    add_timing(stats, source_name, time.perf_counter() - source_started)
                except Exception as exc:
                    add_timing(stats, source_name, time.perf_counter() - source_started if "source_started" in locals() else 0.0)
                    error_reason = "anti_bot_blocked" if exception_looks_like_anti_bot(exc) else "source_error"
                    if error_reason == "anti_bot_blocked":
                        query_anti_bot_blocked = True
                        query_rescue_family = source_name
                    record_source_call(stats, source_name, 0, error=True, error_reason=error_reason)
                    if source_name == "playwright_duckduckgo":
                        family_name = source_family_name(query_rescue_family or "playwright_duckduckgo")
                        failed_rescue_families.add(family_name)
                        record_rescue_budget_event(
                            stats,
                            "serp",
                            family_name,
                            "failed",
                            latency_ms=timing_seconds(stats, source_name) * 1000.0,
                        )
                        stats["rescue_roi_state"] = "playwright_rescue_failed"
                    all_logs.append({"claim_id": claim_id, "query": source_query, "source": source_name, "error": str(exc), "error_reason": error_reason})
                    maybe_schedule_query_playwright_rescue()
                    continue
                record_source_call(stats, source_name, len(items))
                if source_name == "playwright_duckduckgo":
                    family_name = source_family_name(query_rescue_family or "playwright_duckduckgo")
                    if items:
                        stats["playwright_rescued"] = int(stats.get("playwright_rescued", 0) or 0) + 1
                        stats["rescue_progress_delta"] = {
                            "raw_delta": len(items),
                            "kept_delta": 0,
                            "stage": "search_result_recovered",
                        }
                        stats["rescue_success_gate"] = "search_result_recovered"
                        stats["rescue_target_page_type"] = normalize_text(str(page_intent.get("needed_page_type") or "")) or "serp_result"
                        record_rescue_budget_event(
                            stats,
                            "serp",
                            family_name,
                            "succeeded",
                            latency_ms=timing_seconds(stats, source_name) * 1000.0,
                        )
                        stats["rescue_roi_state"] = "playwright_rescue_succeeded"
                    else:
                        failed_rescue_families.add(family_name)
                        record_rescue_budget_event(
                            stats,
                            "serp",
                            family_name,
                            "failed",
                            latency_ms=timing_seconds(stats, source_name) * 1000.0,
                        )
                        stats["rescue_roi_state"] = "playwright_rescue_no_raw"
                search_fallback_from_anti_bot = any(bool(item.get("search_fallback_from_anti_bot")) for item in items if isinstance(item, dict))
                if search_fallback_from_anti_bot:
                    query_anti_bot_blocked = True
                    query_rescue_family = source_name
                    stats.setdefault("playwright_queries", []).append(source_query)
                    stats.setdefault("playwright_reasons", []).append("anti_bot_blocked")
                    stats.setdefault("playwright_roles", []).append("serp_rescue")
                    if used_playwright_queries < PLAYWRIGHT_MAX_QUERIES_PER_CLAIM:
                        used_playwright_queries += 1
                    stats["playwright_rescued"] = int(stats.get("playwright_rescued", 0) or 0) + 1
                    stats["rescue_progress_delta"] = {
                        "raw_delta": len(items),
                        "kept_delta": 0,
                        "stage": "search_result_recovered",
                    }
                    stats["rescue_success_gate"] = "search_result_recovered"
                    stats["rescue_target_page_type"] = normalize_text(str(page_intent.get("needed_page_type") or "")) or "serp_result"
                    record_rescue_budget_event(stats, "serp", source_name, "succeeded", latency_ms=timing_seconds(stats, source_name) * 1000.0)
                    stats["rescue_roi_state"] = "search_source_internal_rescue_succeeded"
                stats["raw_results"] += len(items)
                for item in items:
                    if budget_exhausted():
                        stats["budget_exhausted"] = True
                        break
                    item = dict(item)
                    item["query"] = source_query
                    item["query_goal"] = query_goal
                    item["query_origin"] = normalize_text(str(query_item.get("origin") or "")) or "planner"
                    if is_atomic_query:
                        item["atomic_query"] = True
                        item["atomic_claim_id"] = str(query_item.get("atomic_claim_id") or "")
                        item["atomic_risk_type"] = str(query_item.get("atomic_risk_type") or "")
                        item["atomic_claim_text"] = str(query_item.get("atomic_claim_text") or "")
                    item["retrieved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    item["source_type"] = dynamic_source_type(str(item.get("url", "")), source_query, preferred_domains, source_intent)
                    rough_relevance = evidence_relevance_score(source_query, item)
                    rough_matches = entity_match_count(source_query, item)
                    item["relevance_score"] = rough_relevance
                    item["entity_match_count"] = rough_matches
                    item["temporal_score"] = evidence_temporal_score(source_query, item)
                    item["event_window_score"] = event_window_score(source_query, item, evidence_mode)
                    item.update(source_quality_features(source_query, item, evidence_mode, preferred_domains))
                    item.update(page_intent_features(item, source_intent, source_query, stats))
                    record_page_intent_stats(stats, item)
                    stats.setdefault("source_quality_scores", []).append(item.get("source_quality_score", 0))
                    for reason_item in item.get("source_quality_reasons", []):
                        reason_counts = stats.setdefault("source_quality_reasons", {})
                        reason_counts[reason_item] = int(reason_counts.get(reason_item, 0) or 0) + 1
                    detail_candidate = (
                        fetch_details > 0
                        and item.get("url")
                        and detail_fetches < FETCH_DETAILS_PER_CLAIM
                        and (
                            item.get("source_type") == "official"
                            or item.get("source") == "domain_sitemap"
                            or bool(extract_site_constraint(query))
                            or evidence_target in {"match_result", "withdrawal_status", "market_calendar", "census_phase", "position_distance", "current_status", "prize_amount"}
                            or (
                                query_goal == "verification_question"
                                and centrality in {"core", "supporting"}
                                and rough_relevance >= 2
                                and item.get("source_type") in {"official", "news", "encyclopedia", "unknown"}
                            )
                            or (
                                query_goal == "find_metric_source_page"
                                and evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}
                                and rough_relevance >= 2
                                and rough_matches >= 1
                                and item.get("source_type") in {"official", "news", "unknown"}
                            )
                            or (
                                evidence_mode in {"route_fact", "event_result", "policy_fact"}
                                and rough_relevance >= 8
                                and rough_matches >= 2
                                and item.get("source_type") in {"news", "encyclopedia", "unknown"}
                            )
                            or (
                                evidence_mode == "route_fact"
                                and rough_matches >= 2
                                and item.get("source_type") in {"news", "encyclopedia", "unknown"}
                                and int(item.get("page_intent_score") or 0) >= 35
                            )
                            or route_retry_should_fetch_detail(source_name, item, rough_relevance, rough_matches, source_intent)
                        )
                    )
                    should_fetch_detail = detail_candidate
                    if (
                        should_fetch_detail
                        and item.get("source_type") != "official"
                        and not bool(extract_site_constraint(query))
                        and item.get("source_quality_label") == "bad"
                    ):
                        should_fetch_detail = False
                        stats["source_quality_detail_skipped"] = int(stats.get("source_quality_detail_skipped", 0) or 0) + 1
                    if should_fetch_detail:
                        stats["detail_attempts"] = int(stats.get("detail_attempts", 0) or 0) + 1
                        allow_detail_rescue, detail_rescue_skip_reason = should_allow_playwright_detail_rescue(
                            item,
                            claim_item,
                            evidence_mode,
                            used_playwright_detail_rescues,
                        )
                        detail_trace: Dict[str, Any] = {
                            "allow_playwright_detail_rescue": allow_detail_rescue,
                            "rescue_skip_reason": detail_rescue_skip_reason,
                        }
                        try:
                            detail_started = time.perf_counter()
                            raw_chars = 5000 if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact", "route_fact"} else 1600
                            passage_chars = 1800 if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact", "route_fact"} else 900
                            page_text = fetch_page_text(item["url"], max_chars=raw_chars, timeout_sec=timeout_sec, trace=detail_trace)
                            item["detail"] = extract_relevant_passage(page_text, passage_focus_terms(source_query, str(item.get("title") or "")), max_chars=passage_chars)
                            enrich_structured_table_evidence(item, source_intent, timeout_sec=timeout_sec, fetch_trace=detail_trace)
                            apply_detail_fetch_trace(stats, item, detail_trace, source_name)
                            if detail_trace.get("playwright_rescued"):
                                used_playwright_detail_rescues += 1
                                item["_detail_rescue_playwright_used"] = True
                                stats["rescue_progress_delta"] = {
                                    "raw_delta": 0,
                                    "kept_delta": 0,
                                    "stage": "detail_content_recovered",
                                }
                                stats["rescue_success_gate"] = "detail_content_recovered"
                                stats["rescue_target_page_type"] = str(item.get("page_utility_page_type") or "") or "detail_page"
                                stats["detail_rescue_roi_state"] = "detail_content_recovered"
                                stats["detail_rescue_target_page_type"] = str(item.get("page_utility_page_type") or "") or "detail_page"
                                record_rescue_budget_event(
                                    stats,
                                    "detail",
                                    source_family_name(source_name),
                                    "succeeded",
                                    latency_ms=(time.perf_counter() - detail_started) * 1000.0,
                                )
                                stats["rescue_roi_state"] = "detail_rescue_succeeded"
                            elif detail_trace.get("playwright_rescue_skipped_by_policy"):
                                record_rescue_budget_event(
                                    stats,
                                    "detail",
                                    source_family_name(source_name),
                                    "skipped",
                                    skip_reason=str(detail_trace.get("rescue_skip_reason") or "detail_rescue_budget_exhausted"),
                                )
                            detail_fetches += 1
                            stats["detail_successes"] = int(stats.get("detail_successes", 0) or 0) + 1
                            add_timing(stats, "fetch_detail", time.perf_counter() - detail_started)
                        except Exception as exc:
                            add_timing(stats, "fetch_detail", time.perf_counter() - detail_started if "detail_started" in locals() else 0.0)
                            apply_detail_fetch_trace(stats, item, detail_trace, source_name)
                            if detail_trace.get("playwright_used") or detail_trace.get("playwright_rescue_skipped_by_policy"):
                                used_playwright_detail_rescues += 1 if detail_trace.get("playwright_used") else 0
                                record_rescue_budget_event(
                                    stats,
                                    "detail",
                                    source_family_name(source_name),
                                    "failed" if detail_trace.get("playwright_used") else "skipped",
                                    latency_ms=(time.perf_counter() - detail_started) * 1000.0 if "detail_started" in locals() else 0.0,
                                    skip_reason=str(detail_trace.get("rescue_skip_reason") or ""),
                                )
                                if detail_trace.get("playwright_used"):
                                    stats["detail_rescue_failure_reason"] = "detail_rescue_page_open_failed"
                                else:
                                    stats["detail_rescue_failure_reason"] = str(detail_trace.get("rescue_skip_reason") or "detail_rescue_skipped")
                                if detail_trace.get("playwright_used"):
                                    failed_rescue_families.add(source_family_name(source_name))
                                    stats["rescue_roi_state"] = "detail_rescue_failed"
                                else:
                                    stats["rescue_non_roi_reason"] = str(detail_trace.get("rescue_skip_reason") or "detail_rescue_skipped")
                            record_detail_fetch_failure(stats, item, exc, source_name)
                    item["relevance_score"] = evidence_relevance_score(source_query, item)
                    item["entity_match_count"] = entity_match_count(source_query, item)
                    if evidence_mode == "route_fact":
                        item["route_sentence"] = route_sentence_analysis(source_query, item)
                    item["directness_score"] = evidence_directness_score(source_query, item, evidence_mode)
                    item["temporal_score"] = evidence_temporal_score(source_query, item)
                    item["event_window_score"] = event_window_score(source_query, item, evidence_mode)
                    item["answer_candidates"] = answer_candidate_sentences(source_query, item, evidence_mode=evidence_mode)
                    maybe_apply_deterministic_candidate_rescue(claim_item, item, evidence_mode, source_query)
                    item["answer_candidate_quality_score"] = answer_candidate_quality_score(item)
                    if item.get("direct_candidate_rescue_used"):
                        stats["direct_candidate_rescue_used"] = int(stats.get("direct_candidate_rescue_used", 0) or 0) + 1
                        source_field = str(item.get("direct_candidate_rescue_source") or "")
                        if source_field:
                            increment_named_counter(stats, "direct_candidate_rescue_sources", source_field)
                    item.update(task_card_match_features(item, claim_item.get("evidence_task_card", {}) if isinstance(claim_item.get("evidence_task_card"), dict) else {}))
                    if item["answer_candidates"]:
                        stats["answer_candidate_count"] = int(stats.get("answer_candidate_count", 0) or 0) + len(item["answer_candidates"])
                        stats.setdefault("answer_candidate_examples", []).extend(item["answer_candidates"][:1])
                        field_counts = stats.setdefault("answer_candidate_fields", {})
                        for candidate in item["answer_candidates"]:
                            field = str(candidate.get("field") or "unknown")
                            field_counts[field] = int(field_counts.get(field, 0) or 0) + 1
                        stats.setdefault("answer_candidate_quality_scores", []).append(item["answer_candidate_quality_score"])
                    stats.setdefault("task_card_scores", []).append(item.get("task_card_score", 0))
                    for reason_item in item.get("task_card_reasons", []):
                        task_reason_counts = stats.setdefault("task_card_reasons", {})
                        task_reason_counts[reason_item] = int(task_reason_counts.get(reason_item, 0) or 0) + 1
                    item.update(source_quality_features(source_query, item, evidence_mode, preferred_domains))
                    item.update(page_intent_features(item, source_intent, source_query, stats))
                    record_page_intent_stats(stats, item)
                    if evidence_mode in {"numeric_fact", "date_fact", "schedule_fact"}:
                        item.update(structured_noise_features(source_query, item, evidence_mode))
                        stats.setdefault("structured_rerank_scores", []).append(item.get("structured_rerank_score", 0))
                        for noise_reason in item.get("structured_noise_reasons", []):
                            noise_counts = stats.setdefault("structured_noise_reasons", {})
                            noise_counts[noise_reason] = int(noise_counts.get(noise_reason, 0) or 0) + 1
                    if evidence_mode == "route_fact":
                        rerank = route_rerank_features(source_query, item, claim_text)
                        item.update(rerank)
                        stats.setdefault("route_keyword_profiles", []).append(rerank.get("keyword_profile", {}))
                        stats.setdefault("route_rerank_scores", []).append(rerank.get("route_rerank_score", 0))
                        for noise_reason in rerank.get("noise_reasons", []):
                            noise_counts = stats.setdefault("route_noise_reasons", {})
                            noise_counts[noise_reason] = int(noise_counts.get(noise_reason, 0) or 0) + 1
                    bridge_risks = item.get("evidence_contract_risks") if isinstance(item.get("evidence_contract_risks"), list) else []
                    if (
                        str(item.get("source_type") or "") == "official"
                        and official_homepage_like(item)
                        and "homepage_portal_not_direct_metric_record" in bridge_risks
                        and not item.get("_bridge_expanded")
                    ):
                        item["_bridge_expanded"] = True
                        detail_fetches = expand_official_inner_link_candidates(
                            claim_evidence,
                            stats,
                            item,
                            source_query,
                            source_intent,
                            claim_item,
                            evidence_mode,
                            evidence_target,
                            preferred_domains,
                            fetch_details,
                            detail_fetches,
                            timeout_sec,
                            max_results_per_query,
                        )
                    keep_item, filter_reason = web_evidence_filter_reason(source_query, item, evidence_mode)
                    task_card = claim_item.get("evidence_task_card", {}) if isinstance(claim_item.get("evidence_task_card"), dict) else {}
                    if not keep_item and should_soft_keep_high_priority_item(item, filter_reason, evidence_mode, task_card):
                        keep_item = True
                        filter_reason = "soft_keep_high_priority_structured_candidate"
                    if not keep_item and should_soft_keep_structured_metric_item(item, filter_reason, evidence_mode, task_card):
                        original_filter_reason = filter_reason
                        keep_item = True
                        filter_reason = "soft_keep_structured_metric_table_candidate"
                        annotate_soft_kept_structured_metric_item(item, source_query, evidence_mode, original_filter_reason, claim_item)
                    if not keep_item and should_soft_keep_claim_aligned_fact_item(source_query, item, filter_reason, evidence_mode, claim_item):
                        original_filter_reason = filter_reason
                        keep_item = True
                        filter_reason = "soft_keep_claim_aligned_fact_page"
                        annotate_soft_kept_claim_aligned_item(item, source_query, evidence_mode, original_filter_reason, claim_item)
                    if not keep_item and should_soft_keep_key_evidence_page(source_query, item, filter_reason, evidence_mode, claim_item):
                        original_filter_reason = filter_reason
                        keep_item = True
                        filter_reason = "key_evidence_page_keep_review"
                        annotate_key_evidence_page_keep(item, source_query, evidence_mode, original_filter_reason, claim_item)
                    if not keep_item and should_soft_keep_route_review_item(item, filter_reason, evidence_mode):
                        keep_item = True
                        filter_reason = "soft_keep_route_review_candidate"
                    if not keep_item:
                        keep_item, filter_reason = maybe_promote_fact_page_keep_review(
                            source_query,
                            item,
                            filter_reason,
                            evidence_mode,
                            claim_item,
                        )
                    if not keep_item:
                        keep_item, filter_reason = maybe_promote_core_second_pass_keep_review(
                            source_query,
                            item,
                            filter_reason,
                            evidence_mode,
                            claim_item,
                            int(stats.get("raw_results") or 0) + 1,
                            sum(
                                1
                                for kept_item in claim_evidence
                                if isinstance(kept_item, dict) and kept_item.get("source_type") not in {"input_context", "computed"}
                            ),
                        )
                    if not keep_item:
                        keep_item, filter_reason = maybe_promote_prefilter_candidate_rescue(
                            source_query,
                            item,
                            filter_reason,
                            evidence_mode,
                            claim_item,
                        )
                    if not keep_item:
                        if item.get("core_keep_review_block_reason"):
                            increment_named_counter(stats, "core_keep_review_block_reason", str(item.get("core_keep_review_block_reason") or "blocked"))
                        finalize_detail_rescue_effect(stats, item, keep_item)
                        record_fact_filter_diagnostic(stats, item, False, filter_reason)
                        add_trusted_deepen_jobs(stats, source_jobs, item, filter_reason, source_query)
                        record_source_item_quality(stats, source_name, item, kept=False, filter_reason=filter_reason)
                        stats["filtered_results"] += 1
                        add_filter_reason(stats, filter_reason)
                        add_filtered_sample(stats, filter_reason, item)
                        record_filtered_rescue_pool_candidate(stats, source_query, item, filter_reason, evidence_mode, claim_item)
                        continue
                    record_fact_filter_diagnostic(stats, item, True, filter_reason)
                    if item.get("second_pass_keep_review_used"):
                        stats["second_pass_keep_recovered_count"] = int(stats.get("second_pass_keep_recovered_count", 0) or 0) + int(item.get("second_pass_keep_recovered_count") or 1)
                        increment_named_counter(stats, "second_pass_keep_review_reason", str(item.get("second_pass_keep_review_reason") or filter_reason))
                    if item.get("readiness_promotion_used"):
                        stats["readiness_promotion_used"] = int(stats.get("readiness_promotion_used", 0) or 0) + 1
                        increment_named_counter(stats, "readiness_promotion_source", normalize_text(str(item.get("readiness_promotion_source") or "fact_page_keep_review")) or "fact_page_keep_review")
                        stats.setdefault("candidate_strength_before_keep_scores", []).append(int(item.get("candidate_strength_before_keep") or 0))
                    finalize_detail_rescue_effect(stats, item, keep_item)
                    finalize_direct_candidate_rescue_progress(item, default_stage="post_keep")
                    record_source_item_quality(stats, source_name, item, kept=True)
                    claim_evidence.append(item)
                    if not item.get("_bridge_expanded"):
                        detail_fetches = expand_official_inner_link_candidates(
                            claim_evidence,
                            stats,
                            item,
                            source_query,
                            source_intent,
                            claim_item,
                            evidence_mode,
                            evidence_target,
                            preferred_domains,
                            fetch_details,
                            detail_fetches,
                            timeout_sec,
                            max_results_per_query,
                        )
                    if should_stop_querying_after_web_budget(claim_evidence, evidence_mode, source_intent, max_results_per_query):
                        break
                if should_stop_querying_after_web_budget(claim_evidence, evidence_mode, source_intent, max_results_per_query):
                    break
                maybe_schedule_query_playwright_rescue()
                if (
                    allow_adaptive_fallback
                    and fallback_used_for_query < ADAPTIVE_SOURCE_FALLBACK_LIMIT
                    and adaptive_fallback_used_for_claim < ADAPTIVE_SOURCE_FALLBACK_LIMIT
                ):
                    source_bucket = (stats.get("source_pollution_stats") if isinstance(stats.get("source_pollution_stats"), dict) else {}).get(source_name, {})
                    source_raw = int(source_bucket.get("raw", 0) or 0)
                    source_kept = int(source_bucket.get("kept", 0) or 0)
                    source_bad = int(source_bucket.get("bad", 0) or 0)
                    if source_raw > 0 and source_kept <= 0 and source_bad >= source_raw:
                        fallback_job = next((job for job in fallback_jobs if job[0] not in {name for name, _query in source_jobs}), None)
                        if fallback_job:
                            source_jobs.append(fallback_job)
                            fallback_jobs = [job for job in fallback_jobs if job != fallback_job]
                            fallback_used_for_query += 1
                            adaptive_fallback_used_for_claim += 1
                            stats["adaptive_source_fallback_used"] = int(stats.get("adaptive_source_fallback_used", 0) or 0) + 1
                            stats.setdefault("adaptive_source_fallback_jobs", []).append(
                                {
                                    "query": query,
                                    "source": fallback_job[0],
                                    "reason": "current_source_all_bad",
                                    "raw_before": source_raw,
                                    "bad_before": source_bad,
                                }
                            )
                if (
                    allow_adaptive_fallback
                    and fallback_used_for_query < ADAPTIVE_SOURCE_FALLBACK_LIMIT
                    and adaptive_fallback_used_for_claim < ADAPTIVE_SOURCE_FALLBACK_LIMIT
                    and source_index >= len(source_jobs)
                    and fallback_jobs
                ):
                    query_raw_now = int(stats.get("raw_results", 0) or 0) - query_raw_before
                    query_bad_now = sum(
                        int(bucket.get("bad", 0) or 0)
                        for bucket in (stats.get("source_pollution_stats") if isinstance(stats.get("source_pollution_stats"), dict) else {}).values()
                    ) - query_bad_before
                    query_kept_now = sum(1 for ev in claim_evidence if ev.get("source_type") not in {"input_context", "computed"}) - query_kept_before
                    if query_kept_now <= 0 and (query_raw_now <= 0 or (query_raw_now > 0 and query_bad_now >= query_raw_now)):
                        fallback_job = fallback_jobs.pop(0)
                        source_jobs.append(fallback_job)
                        fallback_used_for_query += 1
                        adaptive_fallback_used_for_claim += 1
                        stats["adaptive_source_fallback_used"] = int(stats.get("adaptive_source_fallback_used", 0) or 0) + 1
                        stats.setdefault("adaptive_source_fallback_jobs", []).append(
                            {
                                "query": query,
                                "source": fallback_job[0],
                                "reason": "no_kept_and_no_raw_or_all_bad",
                                "raw_before": query_raw_now,
                                "bad_before": query_bad_now,
                            }
                        )
                if (
                    authority_first_query
                    and fallback_used_for_query < ADAPTIVE_SOURCE_FALLBACK_LIMIT
                    and adaptive_fallback_used_for_claim < ADAPTIVE_SOURCE_FALLBACK_LIMIT
                    and source_index >= len(source_jobs)
                ):
                    query_raw_now = int(stats.get("raw_results", 0) or 0) - query_raw_before
                    query_bad_now = sum(
                        int(bucket.get("bad", 0) or 0)
                        for bucket in (stats.get("source_pollution_stats") if isinstance(stats.get("source_pollution_stats"), dict) else {}).values()
                    ) - query_bad_before
                    query_kept_now = sum(1 for ev in claim_evidence if ev.get("source_type") not in {"input_context", "computed"}) - query_kept_before
                    used_source_names = {name for name, _query in source_jobs}
                    if query_raw_now <= 0 and query_kept_now <= 0:
                        fallback_job = None
                        for preferred_source in ["sogou_html", "bing_news_zh_rss", "bing_news_rss"]:
                            if preferred_source in used_source_names:
                                continue
                            fallback_job = (preferred_source, query)
                            break
                        if fallback_job:
                            source_jobs.append(fallback_job)
                            fallback_used_for_query += 1
                            adaptive_fallback_used_for_claim += 1
                            stats["adaptive_source_fallback_used"] = int(stats.get("adaptive_source_fallback_used", 0) or 0) + 1
                            stats.setdefault("adaptive_source_fallback_jobs", []).append(
                                {
                                    "query": query,
                                    "source": fallback_job[0],
                                    "reason": "authority_pair_no_raw_then_supplement",
                                    "raw_before": query_raw_now,
                                    "bad_before": query_bad_now,
                                }
                            )
            maybe_schedule_query_playwright_rescue()
            if promote_filtered_rescue_pool_if_needed(stats, claim_evidence, query_kept_before):
                executed_source_order.append("filtered_rescue_pool")
            executed_query_row["final_executed_source_order"] = dedupe_keep_order(executed_source_order)[:10]
            executed_query_row["source_count"] = len(executed_query_row["final_executed_source_order"] or executed_query_row.get("sources") or [])
            if should_stop_querying_after_web_budget(claim_evidence, evidence_mode, source_intent, max_results_per_query):
                break
            if is_recall_probe:
                stats["recall_probe_raw_hits"] = int(stats.get("raw_results", 0) or 0) - query_raw_before
            query_raw_now = int(stats.get("raw_results", 0) or 0) - query_raw_before
            query_kept_now = sum(1 for ev in claim_evidence if ev.get("source_type") not in {"input_context", "computed"}) - query_kept_before
            if is_atomic_query:
                stats.setdefault("atomic_search_results", []).append(
                    {
                        "atomic_claim_id": str(query_item.get("atomic_claim_id") or ""),
                        "risk_type": str(query_item.get("atomic_risk_type") or ""),
                        "query": query,
                        "raw_hits": query_raw_now,
                        "kept_hits": query_kept_now,
                        "sources": executed_query_row.get("final_executed_source_order") or executed_query_row.get("sources") or [],
                        "stop_reason": str(stats.get("claim_retrieve_stop_reason") or ""),
                    }
                )
            if (
                authority_first_query
                and bool(executed_query_row.get("authority_pair_preserved"))
                and query_raw_now <= 0
                and query_kept_now <= 0
            ):
                stats["claim_retrieve_stop_reason"] = "authority_pair_attempted_no_progress"
                if centrality != "core" and fallback_used_for_query <= 0:
                    break
            if (
                centrality != "core"
                and evidence_mode not in {"numeric_fact", "date_fact", "schedule_fact", "route_fact", "event_result"}
                and stats["query_count"] >= 2
                and query_kept_now <= 0
                and query_raw_now <= 0
            ):
                stats["claim_retrieve_stop_reason"] = "supporting_claim_stop_loss"
                break
        if stats.get("atomic_query_plan"):
            atomic_results = stats.get("atomic_search_results") if isinstance(stats.get("atomic_search_results"), list) else []
            if not stats.get("atomic_retrieval_attempted"):
                stats["atomic_gate_result"] = "planned_not_executed"
                stats["atomic_stop_reason"] = stats.get("atomic_stop_reason") or "no_atomic_query_executed"
            elif any(int(row.get("kept_hits") or 0) > 0 for row in atomic_results if isinstance(row, dict)):
                stats["atomic_gate_result"] = "retrieved_waiting_gate"
                stats["atomic_stop_reason"] = ""
            elif any(int(row.get("raw_hits") or 0) > 0 for row in atomic_results if isinstance(row, dict)):
                stats["atomic_gate_result"] = "raw_only_filtered_or_gate_pending"
                stats["atomic_stop_reason"] = "raw_without_kept_atomic_evidence"
            elif stats.get("atomic_retrieval_attempted"):
                stats["atomic_gate_result"] = "retrieval_no_result"
                stats["atomic_stop_reason"] = stats.get("claim_retrieve_stop_reason") or "atomic_query_no_result"
        claim_evidence.sort(
            key=lambda item: (
                item.get("task_card_score", 0),
                item.get("page_retention_score", 0),
                item.get("source_quality_score", 0),
                answer_candidate_quality_score(item),
                item.get("page_utility_llm_score", item.get("page_utility_score", 0)),
                item.get("structured_rerank_score", item.get("route_rerank_score", item.get("relevance_score", 0))),
                item.get("route_rerank_score", item.get("relevance_score", 0)),
                item.get("directness_score", 0),
                item.get("relevance_score", 0),
            ),
            reverse=True,
        )
        stats["detail_fetches"] = detail_fetches
        evidence_by_claim[claim_id] = apply_evidence_budget(claim_evidence, max_results_per_query)
        diagnostics_by_claim[claim_id] = diagnose_claim_retrieval(claim_item, evidence_by_claim[claim_id], stats)
        if ENABLE_SOURCE_HEALTH_REORDER:
            update_source_health_from_stats(source_health, stats, evidence_mode)
            diagnostics_by_claim[claim_id]["source_health_after"] = {
                key: dict(value)
                for key, value in list(source_health.items())[:20]
            }
    return {"evidence_by_claim": evidence_by_claim, "diagnostics_by_claim": diagnostics_by_claim, "logs": all_logs}
