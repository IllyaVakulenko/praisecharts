import os
import sys
import re
import argparse
import shutil
import logging
import atexit
from urllib.parse import urlparse
from typing import List

try:
    import requests
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        WebDriverException,
        SessionNotCreatedException,
    )
    from PIL import Image
    from colorama import init, Fore, Style
except ImportError:
    print("Error: Required libraries are not installed.")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)

# --- UI/UX Helper Class ---
class ConsoleUI:
    def __init__(self):
        init(autoreset=True)

    def header(self, text):
        print(f"\n{Style.BRIGHT}{Fore.MAGENTA}--- {text} ---")

    def info(self, message):
        print(f"{Fore.CYAN}>> {message}")

    def success(self, message):
        print(f"{Fore.GREEN}✔ {message}")

    def warning(self, message):
        print(f"{Fore.YELLOW}⚠ {message}")

    def error(self, message):
        print(f"{Fore.RED}✖ {message}")

    def prompt(self, question):
        return input(f"{Fore.YELLOW}? {question} ")

    def item(self, index, text):
        print(f"  {Style.BRIGHT}{index}. {text}")

ui = ConsoleUI()

# --- Configuration Defaults (production‑ready constants) ---
DEFAULT_DOWNLOAD_DIR = 'charts'
HTTP_TIMEOUT_SECONDS = 20
HTTP_HEAD_TIMEOUT_SECONDS = 10
REQUEST_CHUNK_BYTES = 8192
SELENIUM_WAIT_SECONDS = 10
PAGE_CHANGE_WAIT_SECONDS = 3

# These are set from CLI at runtime
DOWNLOAD_DIR = DEFAULT_DOWNLOAD_DIR
# Controls browser headless mode; set from CLI (default: headless)
BROWSER_HEADLESS = True

# Shared HTTP session and headers
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36 PraiseChartsDownloader/1.0'
}
REQUESTS_SESSION = requests.Session()
atexit.register(lambda: REQUESTS_SESSION.close())

def setup_logging(debug_mode: bool) -> None:
    """Initialize logging with a consistent, production‑friendly format."""
    log_level = logging.DEBUG if debug_mode else logging.WARNING
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s')

def normalize_url(raw: str) -> str | None:
    """Return a normalized URL. Accepts inputs without scheme like 'praisecharts.com/x'.
    Returns None if cannot form a valid http(s) URL.
    """
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

def redirects_to_domain_root(url: str) -> bool:
    """Return True if URL ultimately resolves to domain root '/'; otherwise False.

    Used as a heuristic to skip likely invalid PraiseCharts links that collapse to the homepage.
    """
    try:
        original = urlparse(url)
        original_path = original.path or "/"
        # Only meaningful if original path is deeper than '/'
        if original_path in ("", "/"):
            return False
        try:
            # Prefer HEAD; fall back to GET when HEAD is not allowed.
            with REQUESTS_SESSION.head(
                url,
                headers=REQUEST_HEADERS,
                allow_redirects=True,
                timeout=HTTP_HEAD_TIMEOUT_SECONDS,
            ) as head_resp:
                if head_resp.status_code == 405:
                    # Use non-streaming GET and ensure connection is closed
                    with REQUESTS_SESSION.get(
                        url,
                        headers=REQUEST_HEADERS,
                        allow_redirects=True,
                        timeout=HTTP_HEAD_TIMEOUT_SECONDS,
                    ) as get_resp:
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
            # If we cannot check, do not block; let downstream handling proceed
            return False
    except Exception:
        return False

def is_praisecharts_song_details_url(url: str) -> bool:
    """Accept only PraiseCharts song details URLs, e.g.,
    https://www.praisecharts.com/songs/details/<id>/<slug>/..."""
    try:
        normalized = normalize_url(url)
        if not normalized:
            return False
        parsed = urlparse(normalized)
        # accept subdomains (e.g., www)
        if not parsed.netloc.endswith("praisecharts.com"):
            return False
        # require '/songs/details/' in the path
        return "/songs/details/" in (parsed.path or "")
    except Exception:
        return False

def safe_prompt(question: str, default: str = "") -> str:
    try:
        return ui.prompt(question)
    except (EOFError, KeyboardInterrupt):
        ui.warning("No input available; using default response.")
        return default

def classify_user_input(raw: str) -> tuple[str | None, str | None]:
    """Classify user input prioritizing files first (simpler):
    - If ends with .txt (case-insensitive) OR an existing regular file -> treat as file
    - Else if starts with http(s):// -> URL
    - Else if starts with www.praisecharts.com/songs/details/ or praisecharts.com/songs/details/ -> URL
    - Else if existing directory -> error (expecting a file, not a folder)
    - Else -> error (cannot determine)

    Returns ("url", normalized_url) or ("file", path) or (None, error_message)
    """
    s = (raw or "").strip()
    if not s:
        return None, "Empty input."
    low = s.lower()

    # Prefer file classification first
    if low.endswith('.txt') or os.path.isfile(s):
        return "file", s
    if os.path.isdir(s):
        return None, f"Provided path is a directory, not a file: {s}"

    # URLs
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

def download_image(url: str, filepath: str) -> None:
    """Download an image to filepath, validating content type and ensuring directories exist."""
    try:
        if os.path.exists(filepath):
            return
        ui.info(f"Downloading {os.path.basename(filepath)}")
        with REQUESTS_SESSION.get(
            url,
            headers=REQUEST_HEADERS,
            stream=True,
            timeout=HTTP_TIMEOUT_SECONDS,
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '')
            if 'image' not in content_type.lower():
                ui.warning(f"Unexpected content type for {url}: {content_type}")
                return
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=REQUEST_CHUNK_BYTES):
                    f.write(chunk)
    except requests.exceptions.RequestException as e:
        ui.error(f"Failed to download {url}: {e}")
    except OSError as e:
        ui.error(f"Filesystem error while saving {filepath}: {e}")

def create_pdfs_from_images(arrangement_dir_path: str) -> None:
    if not os.path.isdir(arrangement_dir_path):
        ui.warning(f"Arrangement path is not a directory or does not exist: {arrangement_dir_path}")
        return
    ui.header(f"Creating PDFs for {os.path.relpath(arrangement_dir_path, DOWNLOAD_DIR)}")
    try:
        instrument_dirs = [d for d in os.listdir(arrangement_dir_path) if os.path.isdir(os.path.join(arrangement_dir_path, d))]
    except OSError as e:
        ui.error(f"Failed to list directory {arrangement_dir_path}: {e}")
        return
    for instrument in instrument_dirs:
        instrument_path = os.path.join(arrangement_dir_path, instrument)
        try:
            images = [f for f in os.listdir(instrument_path) if os.path.isfile(os.path.join(instrument_path, f)) and f.lower().endswith('.png')]
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
        
        image_objects = []
        try:
            for i, image_name in enumerate(images):
                img_path = os.path.join(instrument_path, image_name)
                img = Image.open(img_path).convert('RGB')
                if i == 0:
                    first_image = img
                else:
                    image_objects.append(img)
            first_image.save(pdf_path, save_all=True, append_images=image_objects)
            ui.success(f"Created {os.path.basename(pdf_path)}")
        except Exception as e:
            ui.error(f"Failed to create PDF for {instrument}: {e}")
        finally:
            try:
                for img in image_objects:
                    img.close()
                if 'first_image' in locals():
                    first_image.close()
            except Exception:
                pass

def get_path_components(url: str) -> tuple[str, str]:
    try:
        path_parts = urlparse(url).path.strip('/').split('/')
        id_index = next((i for i, part in enumerate(path_parts) if part.isdigit()), -1)
        if id_index != -1 and id_index + 1 < len(path_parts):
            song_slug = path_parts[id_index + 1].removesuffix('-sheet-music')
            arrangement_slug = path_parts[id_index + 2] if id_index + 2 < len(path_parts) else "default"
            return song_slug, arrangement_slug
    except Exception: pass
    return "unknown-song", "unknown-arrangement"

def get_arrangement_path(url: str) -> str:
    song_slug, arrangement_slug = get_path_components(url)
    return os.path.join(DOWNLOAD_DIR, song_slug, arrangement_slug)

def find_next_available_dir(base_path: str) -> str:
    counter = 1
    while True:
        new_path = f"{base_path}_{counter}"
        if not os.path.exists(new_path): return new_path
        counter += 1

def get_instrument_from_filename(filename: str) -> str:
    match = re.search(r'_([a-zA-Z0-9-]+)_(?:[A-Z]|All)_', filename)
    return match.group(1) if match else "unknown-instrument"

def process_url(url: str, target_path: str) -> None:
    normalized = normalize_url(url)
    if not normalized:
        ui.error(f"Invalid URL: {url}")
        return
    if not is_praisecharts_song_details_url(normalized):
        ui.error("Unsupported URL. Expected something like 'praisecharts.com/songs/details/...'")
        return
    # Redirect heuristic: skip if it collapses to domain root
    if redirects_to_domain_root(normalized):
        ui.error(f"URL appears invalid (redirects to domain root): {url}")
        return

    if os.path.exists(target_path):
        try:
            if os.path.isdir(target_path):
                ui.warning(f"Overwriting directory: {os.path.relpath(target_path)}")
                shutil.rmtree(target_path)
            else:
                ui.warning(f"A file exists at target path; removing file: {os.path.relpath(target_path)}")
                os.remove(target_path)
        except OSError as e:
            ui.error(f"Failed to clear target path '{target_path}': {e}")
            return

    driver = None
    try:
        options = FirefoxOptions()
        if BROWSER_HEADLESS:
            options.add_argument("--headless")
        driver = webdriver.Firefox(options=options)
        wait = WebDriverWait(driver, SELENIUM_WAIT_SECONDS)

        driver.get(normalized)
        spinner_selector = (By.CSS_SELECTOR, '.spinner, .loading, .overlay, .app-spinner')
        try:
            wait.until(EC.invisibility_of_element_located(spinner_selector))
        except TimeoutException:
            ui.warning("Spinner did not disappear in time, continuing anyway.")

        _ = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'app-product-sheet-preview')))
        first_image_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.sheet-wrapper:nth-child(1) img')))
        first_image_url = first_image_element.get_attribute('src')
        if not first_image_url:
            ui.error("Could not locate first preview image URL.")
            return
        first_image_filename = os.path.basename(first_image_url.split('?')[0])
        
        instrument = get_instrument_from_filename(first_image_filename)
        download_image(first_image_url, os.path.join(target_path, instrument, first_image_filename))

        while True:
            sheet_wrappers = driver.find_elements(By.CSS_SELECTOR, '.sheet-wrapper')
            if len(sheet_wrappers) < 2:
                break
            try:
                second_wrapper = sheet_wrappers[1]
                second_image_element = second_wrapper.find_element(By.TAG_NAME, 'img')
                current_image_url = second_image_element.get_attribute('src')
                if not current_image_url:
                    break
                current_image_filename = os.path.basename(current_image_url.split('?')[0])

                if current_image_filename == first_image_filename:
                    break

                instrument = get_instrument_from_filename(current_image_filename)
                download_image(current_image_url, os.path.join(target_path, instrument, current_image_filename))

                next_button = second_wrapper.find_element(By.TAG_NAME, 'button')
                driver.execute_script("arguments[0].click();", next_button)

                WebDriverWait(driver, PAGE_CHANGE_WAIT_SECONDS).until(
                    lambda d: d.find_element(By.CSS_SELECTOR, '.sheet-wrapper:nth-child(2) img').get_attribute('src') != current_image_url
                )
            except (TimeoutException, NoSuchElementException):
                break
            except Exception as e:
                ui.error(f"Error in loop: {e}")
                break
    except (WebDriverException, SessionNotCreatedException) as e:
        ui.error(f"Browser automation failed: {e}")
        ui.info("Ensure Firefox and geckodriver are installed and compatible with your Selenium version.")
    except Exception as e:
        ui.error(f"Unexpected error during processing: {e}")
    finally:
        try:
            if driver is not None:
                driver.quit()
        except Exception:
            pass
        if os.path.isdir(target_path):
            create_pdfs_from_images(target_path)

def main():
    global DOWNLOAD_DIR, BROWSER_HEADLESS
    parser = argparse.ArgumentParser(description="Downloads sheet music from PraiseCharts.")
    parser.add_argument('--debug', action='store_true', help="Enable detailed debug logging.")
    parser.add_argument('--headed', action='store_true', help="Run browser with a visible window (disable headless).")
    parser.add_argument('--outdir', default='charts', help="Output directory for downloads (default: charts)")
    parser.add_argument('url', nargs='?', help="A single URL or a .txt file path (default mode).")
    parser.add_argument('--url', dest='url', help="A single URL to download (same as positional).")
    parser.add_argument('--file', help="A file containing a list of URLs.")
    args = parser.parse_args()

    setup_logging(args.debug)
    stats = {'new': 0, 'overwritten': 0, 'renamed': 0, 'skipped': 0, 'errors': 0}

    # Apply CLI configuration
    DOWNLOAD_DIR = args.outdir or DOWNLOAD_DIR
    BROWSER_HEADLESS = not bool(args.headed)

    # Reclassify positional input: prefer file if it's a .txt or existing file
    if args.url and not args.file:
        kind, value = classify_user_input(args.url)
        if kind == "file":
            args.file = value
            args.url = None
        elif kind == "url":
            args.url = value
        else:
            # keep original; will fall through to interactive/help if needed
            pass

    if not args.file and not args.url:
        ui.header("Interactive Mode")
        user_inp = safe_prompt("Enter PraiseCharts URL or path to a file with URLs:").strip()
        kind, value = classify_user_input(user_inp)
        if kind == "url":
            args.url = value
        elif kind == "file":
            args.file = value
        else:
            ui.error(value or "Unable to determine input type.")
            parser.print_help()
            sys.exit(2)

    if args.file and args.url:
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

        # Normalize and keep only praisecharts song details URLs
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

        conflicts = {i: (url, get_arrangement_path(url)) for i, url in enumerate(urls) if os.path.exists(get_arrangement_path(url))}
        non_conflicts = [(url, get_arrangement_path(url)) for i, url in enumerate(urls) if i not in conflicts]
        tasks = []

        if conflicts:
            ui.header("Conflict Resolution")
            ui.warning("Found existing arrangements:")
            for i, (_, path) in conflicts.items():
                ui.item(i + 1, os.path.relpath(path))
            
            actions = {'o': ('Overwrite', 'overwritten'), 'n': ('Add number', 'renamed')}
            for key, (text, stat_key) in actions.items():
                if not conflicts:
                    break
                user_input = safe_prompt(f"Enter numbers to '{text}' (e.g., '1 2', 'all', or Enter to skip):")
                if not user_input:
                    continue
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
                        final_path = find_next_available_dir(path) if key == 'n' else path
                        tasks.append((url, final_path))
                        stats[stat_key] += 1

        stats['skipped'] = len(conflicts)
        tasks.extend(non_conflicts); stats['new'] += len(non_conflicts)

        ui.header("Processing Queue")
        for i, (url, path) in enumerate(tasks):
            ui.info(f"[{i+1}/{len(tasks)}] Queued: {get_path_components(url)[0]} -> {os.path.relpath(path)}")
            try:
                process_url(url, path)
            except Exception as e:
                ui.error(f"Failed to process {url}: {e}"); stats['errors'] += 1

    elif args.url:
        normalized_single = normalize_url(args.url)
        if not normalized_single:
            ui.error(f"Invalid URL: {args.url}")
            sys.exit(2)
        if not is_praisecharts_song_details_url(normalized_single):
            ui.error("Unsupported URL. Expected something like 'praisecharts.com/songs/details/...'")
            sys.exit(2)
        target_path = get_arrangement_path(normalized_single)
        if os.path.exists(target_path):
            choice = safe_prompt(f"Path '{os.path.relpath(target_path)}' exists. [O]verwrite, [N]umber, [S]kip, [Q]uit?").lower()
            if choice == 'o':
                process_url(normalized_single, target_path); stats['overwritten'] += 1
            elif choice == 'n':
                process_url(normalized_single, find_next_available_dir(target_path)); stats['renamed'] += 1
            elif choice == 'q':
                sys.exit("Operation cancelled.")
            else:
                ui.info("Skipping."); stats['skipped'] += 1
        else:
            process_url(normalized_single, target_path); stats['new'] += 1

    ui.header("Summary")
    ui.success(f"New downloads: {stats['new']}")
    ui.info(f"Overwritten: {stats['overwritten']}")
    ui.info(f"Renamed: {stats['renamed']}")
    ui.warning(f"Skipped: {stats['skipped']}")
    if stats['errors']: ui.error(f"Errors: {stats['errors']}")
    print(f"\n{Style.BRIGHT}Work complete.")

if __name__ == '__main__':
    main()