from __future__ import annotations

import atexit
import os
from typing import Final

import requests

from .config import REQUEST_CHUNK_BYTES, HTTP_TIMEOUT_SECONDS
from .ui import ConsoleUI


REQUEST_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36 PraiseChartsDownloader/1.0"
    )
}

SESSION = requests.Session()
atexit.register(lambda: SESSION.close())


def download_image(ui: ConsoleUI, url: str, filepath: str) -> None:
    try:
        if os.path.exists(filepath):
            return
        ui.info(f"Downloading {os.path.basename(filepath)}")
        with SESSION.get(url, headers=REQUEST_HEADERS, stream=True, timeout=HTTP_TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "image" not in content_type.lower():
                ui.warning(f"Unexpected content type for {url}: {content_type}")
                return
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=REQUEST_CHUNK_BYTES):
                    f.write(chunk)
    except requests.exceptions.RequestException as e:
        ui.error(f"Failed to download {url}: {e}")
    except OSError as e:
        ui.error(f"Filesystem error while saving {filepath}: {e}")


