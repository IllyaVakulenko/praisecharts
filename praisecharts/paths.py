from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from .config import DEFAULT_DOWNLOAD_DIR


def get_path_components(url: str) -> tuple[str, str]:
    try:
        path_parts = urlparse(url).path.strip("/").split("/")
        id_index = next((i for i, part in enumerate(path_parts) if part.isdigit()), -1)
        if id_index != -1 and id_index + 1 < len(path_parts):
            song_slug = path_parts[id_index + 1].removesuffix("-sheet-music")
            arrangement_slug = path_parts[id_index + 2] if id_index + 2 < len(path_parts) else "default"
            return song_slug, arrangement_slug
    except Exception:
        pass
    return "unknown-song", "unknown-arrangement"


def get_arrangement_path(url: str, download_dir: str = DEFAULT_DOWNLOAD_DIR) -> str:
    song_slug, arrangement_slug = get_path_components(url)
    return os.path.join(download_dir, song_slug, arrangement_slug)


def find_next_available_dir(base_path: str) -> str:
    counter = 1
    while True:
        new_path = f"{base_path}_{counter}"
        if not os.path.exists(new_path):
            return new_path
        counter += 1


def get_instrument_from_filename(filename: str) -> str:
    match = re.search(r"_([a-zA-Z0-9-]+)_(?:[A-Z]|All)_", filename)
    return match.group(1) if match else "unknown-instrument"


