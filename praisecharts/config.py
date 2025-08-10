from __future__ import annotations

import logging
from dataclasses import dataclass


DEFAULT_DOWNLOAD_DIR = "charts"
HTTP_TIMEOUT_SECONDS = 20
HTTP_HEAD_TIMEOUT_SECONDS = 10
REQUEST_CHUNK_BYTES = 8192
SELENIUM_WAIT_SECONDS = 10
PAGE_CHANGE_WAIT_SECONDS = 3


@dataclass(slots=True)
class AppConfig:
    download_dir: str = DEFAULT_DOWNLOAD_DIR
    browser_headless: bool = True
    http_timeout_seconds: int = HTTP_TIMEOUT_SECONDS
    http_head_timeout_seconds: int = HTTP_HEAD_TIMEOUT_SECONDS
    request_chunk_bytes: int = REQUEST_CHUNK_BYTES
    selenium_wait_seconds: int = SELENIUM_WAIT_SECONDS
    page_change_wait_seconds: int = PAGE_CHANGE_WAIT_SECONDS


def setup_logging(debug_mode: bool) -> None:
    log_level = logging.DEBUG if debug_mode else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
    )


