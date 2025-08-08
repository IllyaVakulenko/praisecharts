import os
import sys
import re
import time
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
except ImportError:
    print("Error: Pillow library is not installed.")
    print("Please install it by running: pip install Pillow")
    sys.exit(1)

DOWNLOAD_DIR = 'downloaded_images'

def setup_logging(debug_mode):
    """Налаштовує логування залежно від режиму відладки."""
    log_level = logging.DEBUG if debug_mode else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def download_image(url, filepath):
    try:
        if os.path.exists(filepath):
            return
        logging.info(f"Downloading {url}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logging.debug(f"Saved as {filepath}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading {url}: {e}")

def create_pdfs_from_images(arrangement_dir_path):
    logging.info(f"Creating PDFs for arrangement: {os.path.basename(arrangement_dir_path)}...")
    instrument_dirs = [d for d in os.listdir(arrangement_dir_path) if os.path.isdir(os.path.join(arrangement_dir_path, d))]
    for instrument in instrument_dirs:
        instrument_path = os.path.join(arrangement_dir_path, instrument)
        images = [f for f in os.listdir(instrument_path) if f.endswith('.png')]
        if not images: continue
        images.sort(key=lambda f: int(re.search(r'_(\d{3})\.png$', f).group(1)))
        pdf_path = os.path.join(arrangement_dir_path, f"{instrument}.pdf")
        if os.path.exists(pdf_path): continue
        logging.info(f"Creating {os.path.basename(pdf_path)}...")
        image_objects = []
        try:
            for i, image_name in enumerate(images):
                img_path = os.path.join(instrument_path, image_name)
                img = Image.open(img_path).convert('RGB')
                if i == 0: first_image = img
                else: image_objects.append(img)
            first_image.save(pdf_path, save_all=True, append_images=image_objects)
        except Exception as e:
            logging.error(f"Failed to create PDF for {instrument}: {e}")

def get_path_components(url):
    try:
        path_parts = urlparse(url).path.strip('/').split('/')
        id_index = next((i for i, part in enumerate(path_parts) if part.isdigit()), -1)
        if id_index != -1 and id_index + 1 < len(path_parts):
            song_slug = path_parts[id_index + 1].removesuffix('-sheet-music')
            arrangement_slug = path_parts[id_index + 2] if id_index + 2 < len(path_parts) else None
            return song_slug, arrangement_slug
    except Exception: pass
    return "unknown-song", None

def get_arrangement_path(url):
    song_slug, arrangement_slug = get_path_components(url)
    path = os.path.join(DOWNLOAD_DIR, song_slug)
    return os.path.join(path, arrangement_slug) if arrangement_slug else path

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
    logging.info(f"Processing: {url}")
    logging.info(f"Target directory: {target_path}")
    
    if os.path.exists(target_path):
        logging.warning("Target directory exists. Deleting for overwrite.")
        shutil.rmtree(target_path)

    options = FirefoxOptions()
    # options.add_argument("--headless")
    driver = webdriver.Firefox(options=options)
    wait = WebDriverWait(driver, 10)

    try:
        driver.get(url)

        spinner_selector = (By.CSS_SELECTOR, '.spinner, .loading, .overlay, .app-spinner')
        logging.info("Waiting for loading spinner to disappear...")
        start_time = time.time()
        try:
            wait.until(EC.invisibility_of_element_located(spinner_selector))
            logging.info(f"Spinner disappeared. (Took {time.time() - start_time:.2f}s)")
        except TimeoutException:
            logging.warning("Spinner did not disappear in time, but continuing anyway.")

        logging.info("Waiting for preview container...")
        preview_container = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'app-product-sheet-preview')))
        
        first_image_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.sheet-wrapper:nth-child(1) img')))
        first_image_url = first_image_element.get_attribute('src')
        first_image_filename = os.path.basename(first_image_url.split('?')[0])
        
        instrument = get_instrument_from_filename(first_image_filename)
        download_image(first_image_url, os.path.join(target_path, instrument, first_image_filename))

        while True:
            sheet_wrappers = preview_container.find_elements(By.CSS_SELECTOR, '.sheet-wrapper')
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
                logging.debug("Next button clicked.")

                # **ВИПРАВЛЕНО: Зменшено час очікування**
                WebDriverWait(driver, 2).until(lambda d: d.find_element(By.CSS_SELECTOR, '.sheet-wrapper:nth-child(2) img').get_attribute('src') != current_image_url)
                logging.debug("Image source has been updated.")

            except (TimeoutException, NoSuchElementException):
                logging.info("Next element not found or timed out. Assuming end of sequence.")
                break
            except Exception as e: 
                logging.error(f"Error in loop: {e}"); break
    finally:
        logging.info("Closing browser.")
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

    if args.url:
        target_path = get_arrangement_path(args.url)
        if os.path.exists(target_path):
            choice = input(f"Directory '{os.path.relpath(target_path)}' already exists. Your action: [O]verwrite, [N]umber, [S]kip, [Q]uit? ").lower()
            if choice == 'o': process_url(args.url, target_path)
            elif choice == 'n': process_url(args.url, find_next_available_dir(target_path))
            elif choice == 'q': sys.exit("Operation cancelled by user.")
            else: logging.info("Skipping.")
        else:
            process_url(args.url, target_path)
    elif args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        except FileNotFoundError:
            sys.exit(f"Error: File not found at {args.file}")

        conflicts = {i: (url, get_arrangement_path(url)) for i, url in enumerate(urls) if os.path.exists(get_arrangement_path(url))}
        non_conflicts = [(url, get_arrangement_path(url)) for i, url in enumerate(urls) if i not in conflicts]
        to_overwrite, to_rename = [], []

        if conflicts:
            logging.info("Found existing arrangements:")
            for i, (_, path) in conflicts.items():
                print(f"  {i+1}. {os.path.relpath(path)}")
            
            actions = {'o': ('Overwrite', to_overwrite), 'n': ('Add number', to_rename)}
            for action_key, (action_text, target_list) in actions.items():
                if not conflicts: break
                user_input = input(f"\nEnter numbers for '{action_text}' (space-separated, 'all', or Enter to skip): ")
                if not user_input: continue
                selected_indices = list(conflicts.keys()) if user_input.lower() == 'all' else [int(n) - 1 for n in user_input.split()]
                
                moved_indices = [i for i in selected_indices if i in conflicts]
                for i in moved_indices:
                    target_list.append(conflicts.pop(i))

        all_tasks = [('overwrite', to_overwrite), ('rename', to_rename), ('new', non_conflicts)]
        for task_type, tasks in all_tasks:
            if not tasks: continue
            logging.info(f"--- Starting processing: {task_type.upper()} ---")
            for url, path in tasks:
                final_path = find_next_available_dir(path) if task_type == 'rename' else path
                try:
                    process_url(url, final_path)
                except Exception as e:
                    logging.error(f"!! Failed to process {url}: {e}")

    logging.info("Work complete.")

if __name__ == '__main__':
    main()
