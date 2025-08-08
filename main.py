import os
import sys
import re
import argparse
import requests
import shutil
import logging
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

try:
    from PIL import Image
    from colorama import init, Fore, Style
except ImportError:
    print("Error: Required libraries are not installed.")
    print("Please run: pip install Pillow colorama")
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
DOWNLOAD_DIR = 'downloaded_images'

def setup_logging(debug_mode):
    log_level = logging.DEBUG if debug_mode else logging.WARNING
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s')

def download_image(url, filepath):
    try:
        if os.path.exists(filepath): return
        ui.info(f"Downloading {os.path.basename(filepath)}")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    except requests.exceptions.RequestException as e:
        ui.error(f"Failed to download {url}: {e}")

def create_pdfs_from_images(arrangement_dir_path):
    ui.header(f"Creating PDFs for {os.path.relpath(arrangement_dir_path, DOWNLOAD_DIR)}")
    instrument_dirs = [d for d in os.listdir(arrangement_dir_path) if os.path.isdir(os.path.join(arrangement_dir_path, d))]
    for instrument in instrument_dirs:
        instrument_path = os.path.join(arrangement_dir_path, instrument)
        images = [f for f in os.listdir(instrument_path) if f.endswith('.png')]
        if not images: continue
        images.sort(key=lambda f: int(re.search(r'_(\d{3})\.png$', f).group(1)))
        pdf_path = os.path.join(arrangement_dir_path, f"{instrument}.pdf")
        if os.path.exists(pdf_path): continue
        
        image_objects = []
        try:
            for i, image_name in enumerate(images):
                img_path = os.path.join(instrument_path, image_name)
                img = Image.open(img_path).convert('RGB')
                if i == 0: first_image = img
                else: image_objects.append(img)
            first_image.save(pdf_path, save_all=True, append_images=image_objects)
            ui.success(f"Created {os.path.basename(pdf_path)}")
        except Exception as e:
            ui.error(f"Failed to create PDF for {instrument}: {e}")

def get_path_components(url):
    try:
        path_parts = urlparse(url).path.strip('/').split('/')
        id_index = next((i for i, part in enumerate(path_parts) if part.isdigit()), -1)
        if id_index != -1 and id_index + 1 < len(path_parts):
            song_slug = path_parts[id_index + 1].removesuffix('-sheet-music')
            arrangement_slug = path_parts[id_index + 2] if id_index + 2 < len(path_parts) else "default"
            return song_slug, arrangement_slug
    except Exception: pass
    return "unknown-song", "unknown-arrangement"

def get_arrangement_path(url):
    song_slug, arrangement_slug = get_path_components(url)
    return os.path.join(DOWNLOAD_DIR, song_slug, arrangement_slug)

def find_next_available_dir(base_path):
    counter = 1
    while True:
        new_path = f"{base_path}_{counter}"
        if not os.path.exists(new_path): return new_path
        counter += 1

def get_instrument_from_filename(filename):
    match = re.search(r'_([a-zA-Z0-9-]+)_(?:[A-Z]|All)_', filename)
    return match.group(1) if match else "unknown-instrument"

def process_url(url, target_path):
    if os.path.exists(target_path):
        ui.warning(f"Overwriting directory: {os.path.relpath(target_path)}")
        shutil.rmtree(target_path)

    options = FirefoxOptions()
    options.add_argument("--headless")
    driver = webdriver.Firefox(options=options)
    wait = WebDriverWait(driver, 10)

    try:
        driver.get(url)
        spinner_selector = (By.CSS_SELECTOR, '.spinner, .loading, .overlay, .app-spinner')
        try:
            wait.until(EC.invisibility_of_element_located(spinner_selector))
        except TimeoutException:
            ui.warning("Spinner did not disappear in time, continuing anyway.")

        preview_container = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'app-product-sheet-preview')))
        first_image_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.sheet-wrapper:nth-child(1) img')))
        first_image_url = first_image_element.get_attribute('src')
        first_image_filename = os.path.basename(first_image_url.split('?')[0])
        
        instrument = get_instrument_from_filename(first_image_filename)
        download_image(first_image_url, os.path.join(target_path, instrument, first_image_filename))

        while True:
            sheet_wrappers = driver.find_elements(By.CSS_SELECTOR, '.sheet-wrapper')
            if len(sheet_wrappers) < 2: break
            
            try:
                second_wrapper = sheet_wrappers[1]
                second_image_element = second_wrapper.find_element(By.TAG_NAME, 'img')
                current_image_url = second_image_element.get_attribute('src')
                current_image_filename = os.path.basename(current_image_url.split('?')[0])

                if current_image_filename == first_image_filename: break

                instrument = get_instrument_from_filename(current_image_filename)
                download_image(current_image_url, os.path.join(target_path, instrument, current_image_filename))

                next_button = second_wrapper.find_element(By.TAG_NAME, 'button')
                driver.execute_script("arguments[0].click();", next_button)

                WebDriverWait(driver, 2).until(lambda d: d.find_element(By.CSS_SELECTOR, '.sheet-wrapper:nth-child(2) img').get_attribute('src') != current_image_url)
            except (TimeoutException, NoSuchElementException): break
            except Exception as e: ui.error(f"Error in loop: {e}"); break
    finally:
        driver.quit()
        if os.path.exists(target_path):
            create_pdfs_from_images(target_path)

def main():
    parser = argparse.ArgumentParser(description="Downloads sheet music from PraiseCharts.")
    parser.add_argument('--debug', action='store_true', help="Enable detailed debug logging.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--url', help="A single URL to download.")
    group.add_argument('--file', help="A file containing a list of URLs.")
    args = parser.parse_args()

    setup_logging(args.debug)
    stats = {'new': 0, 'overwritten': 0, 'renamed': 0, 'skipped': 0, 'errors': 0}

    if args.url:
        target_path = get_arrangement_path(args.url)
        if os.path.exists(target_path):
            choice = ui.prompt(f"Directory '{os.path.relpath(target_path)}' exists. [O]verwrite, [N]umber, [S]kip, [Q]uit?").lower()
            if choice == 'o':
                process_url(args.url, target_path); stats['overwritten'] += 1
            elif choice == 'n':
                process_url(args.url, find_next_available_dir(target_path)); stats['renamed'] += 1
            elif choice == 'q':
                sys.exit("Operation cancelled.")
            else:
                ui.info("Skipping."); stats['skipped'] += 1
        else:
            process_url(args.url, target_path); stats['new'] += 1
    elif args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        except FileNotFoundError:
            ui.error(f"File not found at {args.file}"); sys.exit(1)

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
                if not conflicts: break
                user_input = ui.prompt(f"Enter numbers to '{text}' (e.g., '1 2', 'all', or Enter to skip):")
                if not user_input: continue
                
                indices = list(conflicts.keys()) if user_input.lower() == 'all' else [int(n) - 1 for n in user_input.split()]
                
                moved = []
                for i in indices:
                    if i in conflicts:
                        url, path = conflicts.pop(i)
                        final_path = find_next_available_dir(path) if key == 'n' else path
                        tasks.append((url, final_path)); stats[stat_key] += 1
                        moved.append(i)

        stats['skipped'] = len(conflicts)
        tasks.extend(non_conflicts); stats['new'] += len(non_conflicts)

        ui.header("Processing Queue")
        for i, (url, path) in enumerate(tasks):
            ui.info(f"[{i+1}/{len(tasks)}] Queued: {get_path_components(url)[0]} -> {os.path.relpath(path)}")
            try:
                process_url(url, path)
            except Exception as e:
                ui.error(f"Failed to process {url}: {e}"); stats['errors'] += 1
    
    ui.header("Summary")
    ui.success(f"New downloads: {stats['new']}")
    ui.info(f"Overwritten: {stats['overwritten']}")
    ui.info(f"Renamed: {stats['renamed']}")
    ui.warning(f"Skipped: {stats['skipped']}")
    if stats['errors']: ui.error(f"Errors: {stats['errors']}")
    print(f"\n{Style.BRIGHT}Work complete.")

if __name__ == '__main__':
    main()