
import os
import sys
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Директорія для збереження зображень
DOWNLOAD_DIR = 'downloaded_images'

def download_image(url, filename):
    """Завантажує зображення за URL і зберігає його."""
    try:
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.exists(filepath):
            print(f"Зображення {filename} вже існує. Пропускаємо.")
            return
            
        print(f"Завантаження {url}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Збережено як {filename}")
    except requests.exceptions.RequestException as e:
        print(f"Помилка завантаження {url}: {e}")

def main():
    """
    Головна функція для завантаження зображень зі сторінки PraiseCharts.
    """
    if len(sys.argv) < 2:
        print("Будь ласка, вкажіть URL як аргумент.")
        print(f"Приклад: python {sys.argv[0]} <URL>")
        sys.exit(1)
    url = sys.argv[1]

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    options = FirefoxOptions()
    # options.add_argument("--headless")
    driver = webdriver.Firefox(options=options)

    try:
        print(f"Переходимо на сторінку: {url}")
        driver.get(url)

        # Спроба закрити банер cookie, якщо він є
        try:
            cookie_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'Agree')]"))
            )
            print("Знайдено кнопку згоди на cookie. Натискаємо...")
            cookie_button.click()
            time.sleep(2) # Даємо час банеру зникнути
        except TimeoutException:
            print("Кнопку згоди на cookie не знайдено. Продовжуємо.")

        print("Очікування завантаження контейнера попереднього перегляду...")
        wait = WebDriverWait(driver, 20)
        
        # ВИПРАВЛЕНО: Використовуємо ваш селектор, який спрацював
        preview_container = wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'app-product-sheet-preview'))
        )
        print("Контейнер знайдено.")

        wait.until(EC.visibility_of_all_elements_located((By.CSS_SELECTOR, '.sheet-wrapper')))
        
        first_image_element = wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, '.sheet-wrapper:nth-child(1) img'))
        )
        first_image_url = first_image_element.get_attribute('src')
        if not first_image_url:
            print("Не вдалося отримати URL першого зображення.")
            return
            
        first_image_filename = os.path.basename(first_image_url.split('?')[0])
        download_image(first_image_url, first_image_filename)

        sheet_wrappers = preview_container.find_elements(By.CSS_SELECTOR, '.sheet-wrapper')
        if len(sheet_wrappers) < 2:
            print("Знайдено тільки один аркуш, завантаження завершено.")
            return
        
        # Головний цикл
        while True:
            # Знаходимо другий wrapper і зображення в ньому
            second_image_element = wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, '.sheet-wrapper:nth-child(2) img'))
            )
            current_image_url = second_image_element.get_attribute('src')
            if not current_image_url:
                print("Не вдалося отримати URL поточного зображення. Завершуємо.")
                break

            current_image_filename = os.path.basename(current_image_url.split('?')[0])

            if current_image_filename == first_image_filename:
                print("Повернулися до першого зображення. Завантаження завершено.")
                break

            download_image(current_image_url, current_image_filename)

            # ВИПРАВЛЕНО: Шукаємо кнопки всередині другого sheet-wrapper
            try:
                sheet_wrappers = preview_container.find_elements(By.CSS_SELECTOR, '.sheet-wrapper')
                second_wrapper = sheet_wrappers[1]
                
                # Знаходимо першу кнопку всередині цього блоку
                next_button = second_wrapper.find_element(By.TAG_NAME, 'button')
                
                driver.execute_script("arguments[0].click();", next_button)
                print("Натиснуто кнопку 'Next Page'.")

                # Очікуємо оновлення src зображення
                wait.until(
                    lambda d: d.find_element(By.CSS_SELECTOR, '.sheet-wrapper:nth-child(2) img').get_attribute('src') != current_image_url
                )
                print("Зображення оновилося.")

            except TimeoutException:
                print("Не вдалося дочекатися оновлення зображення після кліку. Можливо, це кінець.")
                break
            except NoSuchElementException:
                print("Кнопку 'Next Page' більше не знайдено у другому блоці. Завершуємо.")
                break
            except Exception as e:
                print(f"Виникла помилка під час кліку або очікування: {e}")
                break
                
    except TimeoutException:
        print("Час очікування елемента вийшов. Перевірте селектори, URL або наявність CAPTCHA.")
    except Exception as e:
        print(f"Виникла неочікувана помилка: {e}")
    finally:
        print("Закриваємо браузер.")
        driver.quit()

if __name__ == '__main__':
    main()
