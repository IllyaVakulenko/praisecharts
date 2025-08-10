from __future__ import annotations

from urllib.parse import urlparse
import requests

from .config import HTTP_HEAD_TIMEOUT_SECONDS


def normalize_url(raw: str) -> str | None:
    try:
        if not raw:
            return None
        s = raw.strip()
        if not s:
            return None
        if not s.lower().startswith(("http://", "https://")):
            s = "https://" + s
        parsed = urlparse(s)
        if not parsed.netloc:
            return None
        if any(ch.isspace() for ch in s):
            return None
        return s
    except Exception:
        return None


def redirects_to_domain_root(url: str, session: requests.Session) -> bool:
    try:
        original = urlparse(url)
        original_path = original.path or "/"
        if original_path in ("", "/"):
            return False
        try:
            with session.head(url, allow_redirects=True, timeout=HTTP_HEAD_TIMEOUT_SECONDS) as head_resp:
                if head_resp.status_code == 405:
                    with session.get(url, allow_redirects=True, timeout=HTTP_HEAD_TIMEOUT_SECONDS) as get_resp:
                        final = urlparse(get_resp.url)
                        final_path = final.path or "/"
                        if final_path == "/" and original_path != "/":
                            return True
                        if getattr(get_resp, "status_code", 200) == 404:
                            return True
                        return False
                final = urlparse(head_resp.url)
                final_path = final.path or "/"
                if final_path == "/" and original_path != "/":
                    return True
                if getattr(head_resp, "status_code", 200) == 404:
                    return True
                return False
        except requests.exceptions.RequestException:
            return False
    except Exception:
        return False


def is_praisecharts_song_details_url(url: str) -> bool:
    try:
        normalized = normalize_url(url)
        if not normalized:
            return False
        parsed = urlparse(normalized)
        if not parsed.netloc.endswith("praisecharts.com"):
            return False
        return "/songs/details/" in (parsed.path or "")
    except Exception:
        return False


