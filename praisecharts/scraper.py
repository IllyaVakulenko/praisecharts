from __future__ import annotations

import os
import shutil
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

from .config import AppConfig
from .http import download_image, SESSION
from .ui import ConsoleUI
from .paths import get_instrument_from_filename
from .pdf import create_pdfs_from_images
from .urls import normalize_url, is_praisecharts_song_details_url, redirects_to_domain_root


def process_url(ui: ConsoleUI, cfg: AppConfig, url: str, target_path: str) -> None:
    normalized = normalize_url(url)
    if not normalized:
        ui.error(f"Invalid URL: {url}")
        return
    if not is_praisecharts_song_details_url(normalized):
        ui.error("Unsupported URL. Expected something like 'praisecharts.com/songs/details/...'")
        return
    if redirects_to_domain_root(normalized, SESSION):
        ui.error(f"URL appears invalid (redirects to domain root): {url}")
        return

    if os.path.exists(target_path):
        try:
            if os.path.isdir(target_path):
                ui.warning(f"Overwriting directory: {target_path}")
                shutil.rmtree(target_path)
            else:
                ui.warning(f"A file exists at target path; removing file: {target_path}")
                os.remove(target_path)
        except OSError as e:
            ui.error(f"Failed to clear target path '{target_path}': {e}")
            return

    driver = None
    try:
        options = FirefoxOptions()
        if cfg.browser_headless:
            options.add_argument("--headless")
        driver = webdriver.Firefox(options=options)
        wait = WebDriverWait(driver, cfg.selenium_wait_seconds)

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
        download_image(ui, first_image_url, os.path.join(target_path, instrument, first_image_filename))

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
                download_image(ui, current_image_url, os.path.join(target_path, instrument, current_image_filename))

                next_button = second_wrapper.find_element(By.TAG_NAME, 'button')
                driver.execute_script("arguments[0].click();", next_button)

                WebDriverWait(driver, cfg.page_change_wait_seconds).until(
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
            create_pdfs_from_images(ui, target_path)


