from __future__ import annotations

import argparse
import os
import sys
from typing import List

from .config import AppConfig, setup_logging
from .ui import ConsoleUI, safe_prompt, is_tty
from .urls import normalize_url, is_praisecharts_song_details_url
from .paths import get_arrangement_path, get_path_components, find_next_available_dir
from .scraper import process_url


def _checkbox_select_indices(index_to_label: dict[int, str]) -> list[int] | None:
    try:
        import questionary
    except Exception:
        return None
    if not (is_tty() and index_to_label):
        return None
    items = sorted(index_to_label.items(), key=lambda kv: kv[0])
    choices = [questionary.Choice(f"{idx+1}. {label}", idx) for idx, label in items]
    selected = questionary.checkbox("Select:", choices=choices).ask()
    return list(selected or [])


def interactive_flags_prompt(ui: ConsoleUI, args) -> None:
    try:
        import questionary
    except Exception:
        questionary = None

    if questionary and is_tty():
        choices = [
            questionary.Choice("Show browser window (disable headless)", "headed", checked=bool(getattr(args, 'headed', False))),
            questionary.Choice("Enable debug logging", "debug", checked=bool(getattr(args, 'debug', False))),
            questionary.Choice("Change output directory", "outdir", checked=False),
        ]
        selected = questionary.checkbox("Quick settings:", choices=choices).ask() or []
        if "debug" in selected:
            args.debug = True
        if "headed" in selected:
            args.headed = True
        if "outdir" in selected:
            new_outdir = questionary.text("Output directory:", default=(args.outdir or "charts")).ask()
            if new_outdir:
                args.outdir = new_outdir
        return

    ui.info("Quick settings (enter numbers separated by space, or press Enter to skip):")
    ui.item(1, "Show browser window (disable headless)")
    ui.item(2, "Enable debug logging")
    ui.item(3, f"Change output directory (current: {getattr(args, 'outdir', 'charts')})")
    raw = safe_prompt(ui, "Your choice:").strip()
    try:
        nums = {int(t) for t in raw.split() if t.isdigit()}
    except Exception:
        nums = set()
    if 1 in nums:
        args.headed = True
    if 2 in nums:
        args.debug = True
    if 3 in nums:
        new_outdir = safe_prompt(ui, "Output directory:").strip()
        if new_outdir:
            args.outdir = new_outdir


def classify_user_input(raw: str) -> tuple[str | None, str | None]:
    s = (raw or "").strip()
    if not s:
        return None, "Empty input."
    low = s.lower()
    if low.endswith('.txt') or os.path.isfile(s):
        return "file", s
    if os.path.isdir(s):
        return None, f"Provided path is a directory, not a file: {s}"
    if low.startswith("https://") or low.startswith("http://"):
        url = normalize_url(s)
        if url:
            return "url", url
        return None, f"Invalid URL: {s}"
    if low.startswith("www.praisecharts.com/songs/details/") or low.startswith("praisecharts.com/songs/details/"):
        url = normalize_url(s)
        if url:
            return "url", url
        return None, f"Invalid PraiseCharts URL: {s}"
    return None, "Could not determine if input is a URL or a path to a .txt file."


def main() -> None:
    ui = ConsoleUI()
    parser = argparse.ArgumentParser(description="Downloads sheet music from PraiseCharts.")
    parser.add_argument('--debug', action='store_true', help="Enable detailed debug logging.")
    parser.add_argument('--headed', action='store_true', help="Run browser with a visible window (disable headless).")
    parser.add_argument('--outdir', default='charts', help="Output directory for downloads (default: charts)")
    parser.add_argument('url', nargs='?', help="A single URL or a .txt file path (default mode).")
    parser.add_argument('--url', dest='url_flag', help="A single URL to download (same as positional).")
    parser.add_argument('--file', help="A file containing a list of URLs.")
    args = parser.parse_args()

    if args.url and not args.file:
        kind, value = classify_user_input(args.url)
        if kind == "file":
            args.file = value
            args.url = None
        elif kind == "url":
            args.url = value

    if not args.file and not (args.url or args.url_flag):
        ui.header("Interactive Mode")
        interactive_flags_prompt(ui, args)
        user_inp = safe_prompt(ui, "Enter PraiseCharts URL or path to a file with URLs:").strip()
        kind, value = classify_user_input(user_inp)
        if kind == "url":
            args.url = value
        elif kind == "file":
            args.file = value
        else:
            ui.error(value or "Unable to determine input type.")
            parser.print_help()
            sys.exit(2)

    setup_logging(bool(args.debug))
    cfg = AppConfig(
        download_dir=args.outdir or AppConfig.download_dir,
        browser_headless=not bool(args.headed),
    )
    stats = {'new': 0, 'overwritten': 0, 'renamed': 0, 'skipped': 0, 'errors': 0}

    if args.file and (args.url or args.url_flag):
        ui.warning("Both --file and --url provided. The --file list will be processed; the single URL will be ignored.")

    if args.file:
        try:
            if not os.path.exists(args.file):
                ui.error(f"File not found at {args.file}")
                sys.exit(1)
            if os.path.isdir(args.file):
                ui.error(f"Provided --file is a directory, not a file: {args.file}")
                sys.exit(1)
            if not args.file.lower().endswith('.txt'):
                ui.error(f"Provided --file is not a .txt file: {args.file}")
                sys.exit(1)
            with open(args.file, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        except UnicodeDecodeError as e:
            ui.error(f"Failed to read file (encoding issue) {args.file}: {e}")
            sys.exit(1)
        except OSError as e:
            ui.error(f"Failed to open file {args.file}: {e}")
            sys.exit(1)

        normalized_urls: List[str] = []
        invalid_urls: List[str] = []
        for u in urls:
            nu = normalize_url(u)
            if nu and is_praisecharts_song_details_url(nu):
                normalized_urls.append(nu)
            else:
                invalid_urls.append(u)
        if invalid_urls:
            ui.warning("Some entries are not valid PraiseCharts song URLs and will be skipped:")
            for bad in invalid_urls[:10]:
                ui.item('-', bad)
            if len(invalid_urls) > 10:
                ui.info(f"... and {len(invalid_urls) - 10} more")
            stats['skipped'] += len(invalid_urls)
        if not normalized_urls:
            ui.warning("No valid URLs to process.")
            sys.exit(0)
        urls = normalized_urls

        conflicts = {i: (url, get_arrangement_path(url, cfg.download_dir)) for i, url in enumerate(urls) if os.path.exists(get_arrangement_path(url, cfg.download_dir))}
        non_conflicts = [(url, get_arrangement_path(url, cfg.download_dir)) for i, url in enumerate(urls) if i not in conflicts]
        tasks: list[tuple[str, str]] = []

        if conflicts:
            ui.header("Conflict Resolution")
            ui.warning("Found existing arrangements:")
            for i, (_, path) in conflicts.items():
                ui.item(i + 1, os.path.relpath(path))

            selected = _checkbox_select_indices({i: os.path.relpath(p) for i, (_, p) in conflicts.items()})
            if selected:
                for i in selected:
                    if i in conflicts:
                        url, path = conflicts.pop(i)
                        tasks.append((url, path))
                        stats['overwritten'] += 1
            elif selected is None:
                user_input = safe_prompt(ui, "Enter numbers to 'Overwrite' (e.g., '1 2', 'all', or Enter to skip):")
                if user_input:
                    if user_input.lower() == 'all':
                        indices = list(conflicts.keys())
                    else:
                        indices = []
                        for token in user_input.split():
                            try:
                                idx = int(token) - 1
                                if idx in conflicts:
                                    indices.append(idx)
                                else:
                                    ui.warning(f"Index out of range: {token}")
                            except ValueError:
                                ui.warning(f"Invalid number: {token}")
                    for i in indices:
                        if i in conflicts:
                            url, path = conflicts.pop(i)
                            tasks.append((url, path))
                            stats['overwritten'] += 1

            if conflicts:
                selected_n = _checkbox_select_indices({i: os.path.relpath(p) for i, (_, p) in conflicts.items()})
                if selected_n:
                    for i in selected_n:
                        if i in conflicts:
                            url, path = conflicts.pop(i)
                            final_path = find_next_available_dir(path)
                            tasks.append((url, final_path))
                            stats['renamed'] += 1
                elif selected_n is None:
                    user_input = safe_prompt(ui, "Enter numbers to 'Add number' (e.g., '1 2', 'all', or Enter to skip):")
                    if user_input:
                        if user_input.lower() == 'all':
                            indices = list(conflicts.keys())
                        else:
                            indices = []
                            for token in user_input.split():
                                try:
                                    idx = int(token) - 1
                                    if idx in conflicts:
                                        indices.append(idx)
                                    else:
                                        ui.warning(f"Index out of range: {token}")
                                except ValueError:
                                    ui.warning(f"Invalid number: {token}")
                        for i in indices:
                            if i in conflicts:
                                url, path = conflicts.pop(i)
                                final_path = find_next_available_dir(path)
                                tasks.append((url, final_path))
                                stats['renamed'] += 1

        stats['skipped'] = len(conflicts)
        tasks.extend(non_conflicts)
        stats['new'] += len(non_conflicts)

        ui.header("Processing Queue")
        for i, (url, path) in enumerate(tasks):
            ui.info(f"[{i+1}/{len(tasks)}] Queued: {get_path_components(url)[0]} -> {os.path.relpath(path)}")
            try:
                process_url(ui, cfg, url, path)
            except Exception as e:
                ui.error(f"Failed to process {url}: {e}")
                stats['errors'] += 1

    elif args.url or args.url_flag:
        single = args.url or args.url_flag
        normalized_single = normalize_url(single)
        if not normalized_single:
            ui.error(f"Invalid URL: {single}")
            sys.exit(2)
        if not is_praisecharts_song_details_url(normalized_single):
            ui.error("Unsupported URL. Expected something like 'praisecharts.com/songs/details/...'")
            sys.exit(2)
        target_path = get_arrangement_path(normalized_single, cfg.download_dir)
        if os.path.exists(target_path):
            choice = safe_prompt(ui, f"Path '{os.path.relpath(target_path)}' exists. [O]verwrite, [N]umber, [S]kip, [Q]uit?").lower()
            if choice == 'o':
                process_url(ui, cfg, normalized_single, target_path)
                stats['overwritten'] += 1
            elif choice == 'n':
                process_url(ui, cfg, normalized_single, find_next_available_dir(target_path))
                stats['renamed'] += 1
            elif choice == 'q':
                sys.exit("Operation cancelled.")
            else:
                ui.info("Skipping.")
                stats['skipped'] += 1
        else:
            process_url(ui, cfg, normalized_single, target_path)
            stats['new'] += 1

    ui.header("Summary")
    ui.success(f"New downloads: {stats['new']}")
    ui.info(f"Overwritten: {stats['overwritten']}")
    ui.info(f"Renamed: {stats['renamed']}")
    ui.warning(f"Skipped: {stats['skipped']}")
    if stats['errors']:
        ui.error(f"Errors: {stats['errors']}")
    print("\nWork complete.")


