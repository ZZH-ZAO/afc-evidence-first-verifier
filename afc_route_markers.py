# -*- coding: utf-8 -*-
from __future__ import annotations

# Shared lexical anchors for route-related retrieval and evidence diagnosis.
# They are weak signals only, not final verdict rules.

ROUTE_RELATION_MARKERS = [
    "airspace", "route", "via", "through", "transit", "cross", "crossed", "corridor",
    "flight path", "trajectory", "overfly", "overflight", "flew over", "passed through",
    "toward", "towards", "headed to", "bound for", "entered", "enter", "reached",
    "bypass", "bypassed", "avoid", "avoided",
    "经过", "经由", "通过", "穿越", "领空", "路线", "通道", "飞越", "飞向", "进入", "到达", "抵达", "前往", "驶向",
]

ROUTE_OBJECT_MARKERS = [
    "missile", "missiles", "drone", "drones", "uav", "rocket", "rockets", "projectile",
    "ballistic", "flight", "airspace", "trajectory", "overfly", "launch", "launched",
    "导弹", "无人机", "火箭弹", "弹道", "飞行", "飞越", "领空", "空域", "航迹", "轨迹", "发射",
]

ROUTE_STRICT_OBJECT_MARKERS = [
    marker
    for marker in ROUTE_OBJECT_MARKERS
    if marker not in {
        "ballistic",
        "flight",
        "airspace",
        "trajectory",
        "overfly",
        "launch",
        "launched",
        "飞行",
        "飞越",
        "领空",
        "空域",
        "航迹",
        "轨迹",
        "发射",
    }
]

ROUTE_DIRECTIONAL_MARKERS = [
    "toward", "towards", "headed to", "bound for", "entered", "enter", "reached", "into",
    "向", "朝", "往", "赴", "前往", "飞向", "驶向", "进入", "到达", "抵达", "直达", "运往", "射向", "指向",
]

ROUTE_QUERY_STOPWORDS = {
    "route", "airspace", "via", "through", "transit", "cross", "crossed", "corridor",
    "flight", "path", "trajectory", "overfly", "overflight", "bypass", "avoid",
    "toward", "towards", "entered", "enter", "reached",
    "analysis", "map", "pass", "passed", "flew", "over",
    "经过", "经由", "通过", "穿越", "领空", "路线", "通道", "飞越", "飞向", "进入", "到达", "抵达", "前往", "驶向",
}

ROUTE_QUERY_FOCUS_STOPWORDS = {
    "准备", "协助", "支持", "推动", "武力", "利用", "允许", "愿意", "可能", "正在", "直接", "间接",
    "方面", "美国", "盟友", "军事", "打通", "提供", "及其", "并", "和", "与", "对", "把",
}

ROUTE_ENTITY_QUERY_STOPWORDS = {
    "support", "supported", "supporting",
    "assist", "assisted", "assistance",
    "prepare", "prepared", "preparing",
    "willing", "plan", "planned", "planning",
    "latest", "update", "updates",
    "genuine", "technical", "billing", "email",
    "question", "questions", "chat", "community",
    "service", "services", "help", "determine",
    "article", "report", "analysis",
}

ROUTE_MEDIUM_HINTS = {
    "air": {
        "terms": [
            "airspace", "flight", "fly", "flight path", "trajectory", "overfly", "aircraft",
            "missile", "drone", "uav", "领空", "空域", "飞行", "飞越", "航线", "航迹", "轨迹",
        ],
        "suffix_zh": "飞行路线 轨迹 经过 领空",
        "suffix_en": "flight route trajectory airspace",
    },
    "maritime": {
        "terms": [
            "sea", "strait", "shipping", "passage", "port", "naval", "vessel", "waterway",
            "海峡", "海运", "航运", "通航", "航道", "港口", "海上", "扫雷", "后勤", "过境", "通道",
        ],
        "suffix_zh": "海峡 航运 通航 过境",
        "suffix_en": "strait shipping passage maritime route",
    },
    "land": {
        "terms": [
            "land", "border", "crossing", "corridor", "road", "rail",
            "边境", "过境", "口岸", "通道", "走廊", "陆路", "公路", "铁路",
        ],
        "suffix_zh": "过境 通道 走廊 边境",
        "suffix_en": "border crossing corridor land route",
    },
    "generic": {
        "terms": [
            "route", "path", "through", "via", "经过", "经由", "路线", "通道",
        ],
        "suffix_zh": "路线 轨迹 经过 通道",
        "suffix_en": "route trajectory passage",
    },
}
