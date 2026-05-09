from __future__ import annotations

import re
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, unquote, urlparse

import requests

SearchResult = Dict[str, Any]

_HTTP = requests.Session()
_HTTP.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    }
)

SOURCE_TYPES = {
    "official": {
        ".gov",
        "gov.cn",
        ".edu",
        "who.int",
        "nih.gov",
        "wto.org",
        "imf.org",
        "worldbank.org",
        "sec.gov",
        "fda.gov",
        "ec.europa.eu",
        "europa.eu",
    },
    "encyclopedia": {"wikipedia.org", "baike.baidu.com"},
    "news": {
        "news.",
        "reuters.com",
        "apnews.com",
        "bbc.com",
        "cnn.com",
        "nytimes.com",
        "washingtonpost.com",
        "theguardian.com",
        "ap.org",
        "pbs.org",
        "yahoo.com",
        "msn.com",
        "bloomberg.com",
        "ft.com",
        "wsj.com",
        "cnbc.com",
    },
    "forum": {"reddit.com", "zhihu.com", "tieba.baidu.com", "x.com"},
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def decode_response_text(response: requests.Response) -> str:
    encoding = response.encoding
    if not encoding or encoding.lower() in {"iso-8859-1", "latin-1"}:
        encoding = response.apparent_encoding or "utf-8"
    try:
        return response.content.decode(encoding, errors="ignore")
    except Exception:
        return response.text


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


def search_duckduckgo_html(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[SearchResult]:
    response = _HTTP.get(build_duckduckgo_url(query), timeout=timeout_sec)
    response.raise_for_status()
    blocks = re.findall(
        r'<a rel="nofollow" class="result__a" href="(.*?)"[^>]*>(.*?)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>',
        response.text,
        flags=re.S,
    )
    items: List[SearchResult] = []
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


def search_bing_rss(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[SearchResult]:
    response = _HTTP.get(build_bing_rss_url(query), timeout=timeout_sec)
    response.raise_for_status()
    text = decode_response_text(response)
    items: List[SearchResult] = []
    for match in re.finditer(
        r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<description>(.*?)</description>.*?</item>",
        text,
        flags=re.S,
    ):
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


def search_bing_html(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[SearchResult]:
    response = _HTTP.get(build_bing_html_url(query), timeout=timeout_sec)
    response.raise_for_status()
    blocks = re.findall(r'<li class="b_algo".*?</li>', response.text, flags=re.S)
    items: List[SearchResult] = []
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


def search_sogou_html(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[SearchResult]:
    response = _HTTP.get(build_sogou_url(query), timeout=timeout_sec)
    response.raise_for_status()
    blocks = re.findall(r"<h3[^>]*>(.*?)</h3>.*?<p[^>]*class=\"(?:str_info|txt-info)\"[^>]*>(.*?)</p>", response.text, flags=re.S)
    if not blocks:
        blocks = [(match, "") for match in re.findall(r"<h3[^>]*>(.*?)</h3>", response.text, flags=re.S)]
    items: List[SearchResult] = []
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


def parse_bing_news_rss(text: str, source_name: str, max_results: int = 5) -> List[SearchResult]:
    items: List[SearchResult] = []
    for match in re.finditer(
        r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<description>(.*?)</description>.*?</item>",
        text,
        flags=re.S,
    ):
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


def search_bing_news_rss(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[SearchResult]:
    response = _HTTP.get(
        build_bing_news_rss_url(query),
        timeout=timeout_sec,
        headers={"Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"},
    )
    response.raise_for_status()
    return parse_bing_news_rss(response.text, "bing_news_rss", max_results=max_results)


def search_bing_news_zh_rss(query: str, max_results: int = 5, timeout_sec: int = 10) -> List[SearchResult]:
    response = _HTTP.get(
        build_bing_news_zh_rss_url(query),
        timeout=timeout_sec,
        headers={"Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"},
    )
    response.raise_for_status()
    return parse_bing_news_rss(decode_response_text(response), "bing_news_zh_rss", max_results=max_results)


def search_wikipedia(query: str, max_results: int = 3, timeout_sec: int = 10) -> List[SearchResult]:
    url = f"https://zh.wikipedia.org/w/api.php?action=opensearch&search={quote_plus(query)}&limit={max_results}&namespace=0&format=json"
    response = _HTTP.get(url, timeout=timeout_sec)
    response.raise_for_status()
    data = response.json()
    results: List[SearchResult] = []
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


PROVIDERS = {
    "duckduckgo_html": search_duckduckgo_html,
    "bing_rss": search_bing_rss,
    "bing_html": search_bing_html,
    "sogou_html": search_sogou_html,
    "bing_news_rss": search_bing_news_rss,
    "bing_news_zh_rss": search_bing_news_zh_rss,
    "wikipedia": search_wikipedia,
}


def supports_provider(source_name: str) -> bool:
    return source_name in PROVIDERS


def search_with_provider(
    source_name: str,
    query: str,
    max_results: int,
    timeout_sec: int,
) -> Optional[List[SearchResult]]:
    provider = PROVIDERS.get(source_name)
    if provider is None:
        return None
    return provider(query, max_results=max_results, timeout_sec=timeout_sec)
