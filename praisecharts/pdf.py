from __future__ import annotations

import os
import re
from PIL import Image

from .ui import ConsoleUI


def create_pdfs_from_images(ui: ConsoleUI, arrangement_dir_path: str) -> None:
    if not os.path.isdir(arrangement_dir_path):
        ui.warning(f"Arrangement path is not a directory or does not exist: {arrangement_dir_path}")
        return
    ui.header(f"Creating PDFs for {arrangement_dir_path}")
    try:
        instrument_dirs = [
            d for d in os.listdir(arrangement_dir_path)
            if os.path.isdir(os.path.join(arrangement_dir_path, d))
        ]
    except OSError as e:
        ui.error(f"Failed to list directory {arrangement_dir_path}: {e}")
        return
    for instrument in instrument_dirs:
        instrument_path = os.path.join(arrangement_dir_path, instrument)
        try:
            images = [
                f for f in os.listdir(instrument_path)
                if os.path.isfile(os.path.join(instrument_path, f)) and f.lower().endswith('.png')
            ]
        except OSError as e:
            ui.error(f"Failed to list images in {instrument_path}: {e}")
            continue
        if not images:
            continue

        def sort_key(filename: str):
            match = re.search(r'_(\d{3})\.png$', filename, re.IGNORECASE)
            return (match is None, int(match.group(1)) if match else 0, filename)

        images.sort(key=sort_key)
        pdf_path = os.path.join(arrangement_dir_path, f"{instrument}.pdf")
        if os.path.exists(pdf_path):
            continue

        image_objects: list[Image.Image] = []
        try:
            for i, image_name in enumerate(images):
                img_path = os.path.join(instrument_path, image_name)
                img = Image.open(img_path).convert('RGB')
                if i == 0:
                    first_image = img
                else:
                    image_objects.append(img)
            first_image.save(pdf_path, save_all=True, append_images=image_objects)  # type: ignore[name-defined]
            ui.success(f"Created {os.path.basename(pdf_path)}")
        except Exception as e:
            ui.error(f"Failed to create PDF for {instrument}: {e}")
        finally:
            try:
                for img in image_objects:
                    img.close()
                if 'first_image' in locals():
                    first_image.close()  # type: ignore[name-defined]
            except Exception:
                pass


