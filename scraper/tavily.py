"""Bounded Tavily discovery. Returned sources are not verified CPD events."""
import ipaddress
import json
import os
import secrets
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen



class ProviderError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def tavily_post(endpoint, payload, key):
    request = Request(
        "https://api.tavily.com/" + endpoint,
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError("Invalid provider response")
        return data
    except HTTPError as error:
        # Never expose provider response bodies, request headers, or API keys.
        if error.code in (401, 403):
            raise ProviderError(503, "Tavily rejected the server API key.") from None
        if error.code in (429, 432, 433):
            raise ProviderError(429, "Tavily rate or credit limit reached. Try again later.") from None
        raise ProviderError(502, "Tavily request failed.") from None
    except (TimeoutError, URLError):
        raise ProviderError(504, "Tavily is unavailable or timed out.") from None
    except (ValueError, UnicodeError):
        raise ProviderError(502, "Tavily returned an invalid response.") from None


def reported_credits(payload):
    """Keep provider-reported credit counts; never invent a spend figure."""
    usage = payload.get('usage') if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return None
    raw = usage.get('credits')
    # Reject bools: float(True)==1.0 / float(False)==0.0 would invent spend from junk JSON.
    if raw is None or raw == '' or isinstance(raw, bool):
        return None
    try:
        credits = float(raw)
    except (TypeError, ValueError):
        return None
    if credits != credits or credits in (float('inf'), float('-inf')) or credits < 0:
        return None
    return credits


def source_url(value):
    """Reject local/literal IP and non-web links; remove fragments for deduplication."""
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if (parts.scheme not in ("https", "http") or "." not in host
                or host.endswith((".localhost", ".local", ".internal"))
                or parts.username or parts.password or parts.port not in (None, 80, 443)):
            return None
        try:
            ipaddress.ip_address(host)
            return None
        except ValueError:
            pass
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, parts.query, ""))
    except ValueError:
        return None


def discover(query, max_results=5):
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        raise ProviderError(503, "Tavily is not configured. Run python scripts/setup_integrations.py locally.")
    search = tavily_post("search", {
        "query": "Malaysia medical CPD courses conferences webinars " + query,
        "topic": "general", "search_depth": "basic", "max_results": max_results,
        "include_answer": False, "include_raw_content": False,
    }, key)
    credits = [reported_credits(search)]
    sources = {}
    for item in search["results"]:
        if not isinstance(item, dict):
            continue
        url = source_url(item.get("url"))
        if url and url not in sources and len(sources) < max_results:
            sources[url] = {
                "url": url, "title": str(item.get("title") or "Untitled source"),
                "snippet": str(item.get("content") or ""), "raw_content": None,
                "extraction_status": "failed", "verification_status": "unverified",
            }
    warnings = []
    if sources:
        try:
            extracted = tavily_post("extract", {
                "urls": list(sources), "extract_depth": "basic", "format": "text",
            }, key)
            credits.append(reported_credits(extracted))
            for item in extracted["results"]:
                if not isinstance(item, dict):
                    continue
                url = source_url(item.get("url"))
                content = item.get("raw_content")
                if url in sources and isinstance(content, str) and content.strip():
                    sources[url]["raw_content"] = content
                    sources[url]["extraction_status"] = "success"
            if any(item["extraction_status"] == "failed" for item in sources.values()):
                warnings.append("Some pages could not be extracted; their search snippets are retained.")
        except ProviderError as error:
            warnings.append(error.detail + " Search snippets are retained; extraction is incomplete.")
    known = [value for value in credits if value is not None]
    retrieved_at = datetime.now(timezone.utc).isoformat()
    # Stamp each source so job-complete can persist scraper ISO (not only complete-time).
    for item in sources.values():
        item.setdefault("retrieved_at", retrieved_at)
    return {
        "provider": "tavily", "query": query,
        "retrieved_at": retrieved_at,
        "sources": list(sources.values()), "warnings": warnings,
        "usage": {"tavily_credits": sum(known) if known else None},
    }


