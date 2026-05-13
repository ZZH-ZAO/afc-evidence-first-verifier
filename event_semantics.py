from __future__ import annotations

import re
from typing import List


EVENT_SCORE_PATTERN = re.compile(r"(?<![\d.])\d{1,3}\s*[-:：比]\s*\d{1,3}(?![\d.])")
EVENT_PAIR_PATTERN = re.compile(r"(vs|VS|对阵|迎战)")
EVENT_LEXICON_HINTS_ENABLED = False

# Event-result related phrase lists are kept in one place for auditability,
# but the runtime path intentionally does not rely on them right now.
EVENT_LEXICON_BANK = {
    "withdrawal_terms": [
        "退赛",
        "弃权",
        "不战而胜",
        "walkover",
        "withdrawal",
        "withdrawn",
        "retire",
        "retired",
    ],
    "result_terms": [
        "战胜",
        "击败",
        "获胜",
        "赛果",
        "结果",
        "完赛",
        "晋级",
        "win",
        "beat",
        "defeat",
        "lose",
        "result",
    ],
    "query_terms": {
        "score_detail": ["赛果", "结果", "比赛", "是否完赛"],
        "withdrawal_like": ["赛果", "结果", "比赛", "是否完赛"],
        "result_like": ["赛果", "结果", "比赛"],
        "default": ["赛果", "结果", "比赛", "比分"],
    },
}

EVENT_WITHDRAWAL_PATTERN = re.compile(
    r"(退赛|弃权|不战而胜|walkover|withdraw(?:al|n)?|retir(?:e|ed))",
    re.I,
)
EVENT_RESULT_PATTERN = re.compile(
    r"(战胜|击败|获胜|不敌|负于|赛果|结果|完赛|晋级|出局|win|beat|defeat|lose|lost|result)",
    re.I,
)


def normalize_event_text(text: str) -> str:
    clean = str(text or "")
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def event_status_family(text: str) -> str:
    clean = normalize_event_text(text)
    if not clean:
        return "none"
    if EVENT_SCORE_PATTERN.search(clean):
        return "score_detail"
    if not EVENT_LEXICON_HINTS_ENABLED:
        return "none"
    if EVENT_WITHDRAWAL_PATTERN.search(clean):
        return "withdrawal_like"
    if EVENT_RESULT_PATTERN.search(clean):
        return "result_like"
    return "none"


def event_has_result_signal(text: str) -> bool:
    clean = normalize_event_text(text)
    if not clean:
        return False
    if EVENT_SCORE_PATTERN.search(clean):
        return True
    if not EVENT_LEXICON_HINTS_ENABLED:
        return False
    return bool(EVENT_WITHDRAWAL_PATTERN.search(clean) or EVENT_RESULT_PATTERN.search(clean))


def event_result_query_terms(text: str) -> List[str]:
    if not EVENT_LEXICON_HINTS_ENABLED:
        return []
    family = event_status_family(text)
    if family in {"score_detail", "withdrawal_like"}:
        return list(EVENT_LEXICON_BANK["query_terms"]["score_detail"])
    if family == "result_like":
        return list(EVENT_LEXICON_BANK["query_terms"]["result_like"])
    return list(EVENT_LEXICON_BANK["query_terms"]["default"])
