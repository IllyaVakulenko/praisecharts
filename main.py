from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
import time
import requests
import os

# === Конфіг ===
START_URL = "https://www.praisecharts.com/songs/details/70645/o-holy-night-sheet-music/orchestration"  # твоє посилання
DOWNLOAD_DIR = "downloaded_images"

# === Firefox headless mode ===
options = Options()
# options.add_argument('--headless')
driver = webdriver.Firefox(service=Service(), options=options)

# === Сторінка ===
driver.get(START_URL)
time.sleep(3)

# === Папка для збереження ===
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# === Знайти перше зображення ===
preview = driver.find_element(By.CLASS_NAME, "app-product-sheet-preview")
sheet_wrappers = preview.find_elements(By.CLASS_NAME, "sheet-wrapper")

first_img = sheet_wrappers[0].find_element(By.CSS_SELECTOR, ".sheet-page img")
first_img_src = first_img.get_attribute("src")
first_img_name = os.path.basename(first_img_src)

print(f"🔸 First image: {first_img_name}")

visited = set()
current_name = ""

while True:
    time.sleep(1)
    
    preview = driver.find_element(By.CLASS_NAME, "app-product-sheet-preview")
    sheet_wrappers = preview.find_elements(By.CLASS_NAME, "sheet-wrapper")
    
    if len(sheet_wrappers) < 2:
        print("🛑 Не знайдено другого sheet-wrapper. Зупиняю.")
        break

    img = sheet_wrappers[1].find_element(By.CSS_SELECTOR, ".sheet-page img")
    img_src = img.get_attribute("src")
    current_name = os.path.basename(img_src)

    if current_name in visited:
        print("✅ Завантаження завершено.")
        break

    print(f"⬇️ Завантажую: {current_name}")
    img_data = requests.get(img_src).content
    with open(os.path.join(DOWNLOAD_DIR, current_name), 'wb') as f:
        f.write(img_data)

    visited.add(current_name)

    # натискаємо першу кнопку після картинки
    buttons = sheet_wrappers[1].find_elements(By.TAG_NAME, "button")
    if buttons:
        buttons[0].click()
        time.sleep(1.5)  # чекати оновлення DOM
    else:
        print("⚠️ Кнопки не знайдено")
        break

driver.quit()
