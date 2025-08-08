import os
import sys
import re
import time
import requests
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
    print("Помилка: бібліотека Pillow не встановлена.")
    print("Будь ласка, встановіть її, виконавши команду: pip install Pillow")
    sys.exit(1)

DOWNLOAD_DIR = 'downloaded_images'

def download_image(url, filepath):
    """Завантажує зображення та зберігає його за вказаним шляхом."""
    try:
        if os.path.exists(filepath):
            print(f"Зображення {os.path.basename(filepath)} вже існує. Пропускаємо.")
            return
        
        print(f"Завантаження {url}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Збережено як {filepath}")
    except requests.exceptions.RequestException as e:
        print(f"Помилка завантаження {url}: {e}")

def create_pdfs_from_images(arrangement_dir_path):
    """Створює PDF-файли з зображень у піддиректоріях інструментів."""
    print("\nСтворення PDF-файлів...")
    instrument_dirs = [d for d in os.listdir(arrangement_dir_path) if os.path.isdir(os.path.join(arrangement_dir_path, d))]

    for instrument in instrument_dirs:
        instrument_path = os.path.join(arrangement_dir_path, instrument)
        images = [f for f in os.listdir(instrument_path) if f.endswith('.png')]
        
        if not images:
            continue

        images.sort(key=lambda f: int(re.search(r'_(\d{3})\.png$', f).group(1)))
        
        pdf_path = os.path.join(arrangement_dir_path, f"{instrument}.pdf")
        if os.path.exists(pdf_path):
            print(f"PDF {os.path.basename(pdf_path)} вже існує. Пропускаємо.")
            continue

        print(f"Створення {os.path.basename(pdf_path)}...")
        
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
        except Exception as e:
            print(f"Не вдалося створити PDF для {instrument}: {e}")

def get_path_components(url):
    """Витягує назву пісні та аранжування з URL, видаляючи зайві частини."""
    try:
        path_parts = urlparse(url).path.strip('/').split('/')
        id_index = -1
        for i, part in enumerate(path_parts):
            if part.isdigit():
                id_index = i
                break
        
        if id_index != -1 and id_index + 1 < len(path_parts):
            song_slug = path_parts[id_index + 1]
            song_slug = song_slug.removesuffix('-sheet-music')
            
            arrangement_slug = None
            if id_index + 2 < len(path_parts):
                arrangement_slug = path_parts[id_index + 2]
            return song_slug, arrangement_slug
    except Exception:
        pass
    
    try:
        path_parts = urlparse(url).path.strip('/').split('/')
        song_slug = path_parts[-1] if path_parts else "unknown-song"
        song_slug = song_slug.removesuffix('-sheet-music')
        return song_slug, None
    except:
        return "unknown-song", None

def get_instrument_from_filename(filename):
    """Визначає назву інструменту з імені файлу."""
    match = re.search(r'_([a-zA-Z0-9-]+)_(?:[A-Z]|All)_', filename)
    if match:
        return match.group(1)
    return "unknown-instrument"

def main():
    if len(sys.argv) < 2:
        print("Будь ласка, вкажіть URL як аргумент."); sys.exit(1)
    url = sys.argv[1]

    song_slug, arrangement_slug = get_path_components(url)
    
    song_dir = os.path.join(DOWNLOAD_DIR, song_slug)
    session_dir = os.path.join(song_dir, arrangement_slug) if arrangement_slug else song_dir

    print(f"Назва пісні: {song_slug}")
    if arrangement_slug:
        print(f"Аранжування: {arrangement_slug}")

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    options = FirefoxOptions()
    # options.add_argument("--headless")
    driver = webdriver.Firefox(options=options)
    wait = WebDriverWait(driver, 20)

    try:
        print(f"Переходимо на сторінку: {url}")
        driver.get(url)

        try:
            cookie_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'Agree')] ")))
            print("Знайдено кнопку згоди на cookie. Натискаємо..."); cookie_button.click(); time.sleep(2)
        except TimeoutException:
            print("Кнопку згоди на cookie не знайдено. Продовжуємо.")

        print("Очікування контейнера...");
        preview_container = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'app-product-sheet-preview')))
        print("Контейнер знайдено.")

        first_image_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.sheet-wrapper:nth-child(1) img')))
        first_image_url = first_image_element.get_attribute('src')
        if not first_image_url:
            print("Не вдалося отримати URL першого зображення."); return
            
        first_image_filename = os.path.basename(first_image_url.split('?')[0])
        instrument = get_instrument_from_filename(first_image_filename)
        instrument_dir = os.path.join(session_dir, instrument)
        download_image(first_image_url, os.path.join(instrument_dir, first_image_filename))

        while True:
            sheet_wrappers = preview_container.find_elements(By.CSS_SELECTOR, '.sheet-wrapper')
            if len(sheet_wrappers) < 2:
                print("Другий .sheet-wrapper не знайдено. Завантаження завершено."); break
            
            try:
                second_wrapper = sheet_wrappers[1]
                second_image_element = second_wrapper.find_element(By.TAG_NAME, 'img')
                current_image_url = second_image_element.get_attribute('src')

                if not current_image_url:
                    print("Не вдалося отримати URL поточного зображення. Завершуємо."); break

                current_image_filename = os.path.basename(current_image_url.split('?')[0])
                if current_image_filename == first_image_filename:
                    print("Повернулися до першого зображення. Завантаження завершено."); break

                instrument = get_instrument_from_filename(current_image_filename)
                instrument_dir = os.path.join(session_dir, instrument)
                download_image(current_image_url, os.path.join(instrument_dir, current_image_filename))

                next_button = second_wrapper.find_element(By.TAG_NAME, 'button')
                driver.execute_script("arguments[0].click();", next_button)
                print(f"Натиснуто 'Next Page' для інструменту: {instrument}")

                wait.until(lambda d: d.find_element(By.CSS_SELECTOR, '.sheet-wrapper:nth-child(2) img').get_attribute('src') != current_image_url)
                print("Зображення оновилося.")

            except TimeoutException:
                print("Не вдалося дочекатися оновлення зображення. Завершуємо."); break
            except NoSuchElementException:
                print("Наступний елемент не знайдено. Завантаження завершено."); break
            except Exception as e:
                print(f"Виникла неочікувана помилка: {e}"); break
                
    except TimeoutException:
        print("Час очікування елемента вийшов. Перевірте селектори, URL або CAPTCHA.")
    except Exception as e:
        print(f"Виникла неочікувана помилка: {e}")
    finally:
        print("Закриваємо браузер.")
        driver.quit()
        if 'session_dir' in locals() and os.path.exists(session_dir):
            create_pdfs_from_images(session_dir)
        print("\nРоботу завершено.")

if __name__ == '__main__':
    main()
