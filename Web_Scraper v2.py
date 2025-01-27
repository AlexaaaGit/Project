from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    WebDriverException
)
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import logging
import requests
import os
import re
import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# --- Конфигурационные данные ---
HIGHLIGHTS_URL = "https://www.nga.gov/collection/highlights.html"
ARTIST_NAME = "dali"  # Имя художника для создания папки и файла
IMAGE_FOLDER = ARTIST_NAME  # Папка с именем художника
MAX_PAGES = 3
JSON_OUTPUT_FILE = f"{ARTIST_NAME}.json"
DRIVER_TIMEOUT = 60  # Увеличен таймаут
SLEEP_TIME = 5  # Увеличено время ожидания между страницами

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# --- Вывод основных данных в начале ---
logging.info(f"Стартовый URL: {HIGHLIGHTS_URL}")
logging.info(f"Папка для сохранения изображений: {IMAGE_FOLDER}")
logging.info(f"Максимальное количество страниц: {MAX_PAGES}")
logging.info(f"Файл для сохранения данных: {JSON_OUTPUT_FILE}")
logging.info(f"Таймаут драйвера: {DRIVER_TIMEOUT}")
logging.info(f"Время ожидания между страницами: {SLEEP_TIME}")

def get_file_extension(url):
    """Определяет расширение файла по URL."""
    parsed_url = urlparse(url)
    path = parsed_url.path
    ext = os.path.splitext(path)[1]
    if ext.lower() in {".jpg", ".jpeg", ".png", ".gif", ".bmp"}:
        return ext
    else:
        return ".jpg" # Дефолтное значение, если не определилось

def download_image(url, folder, filename):
    """Скачивает изображение из URL и сохраняет его в указанной папке."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        os.makedirs(folder, exist_ok=True)

        with open(os.path.join(folder, filename), "wb") as file:
            for chunk in response.iter_content(8192):
                file.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при скачивании изображения {url}: {e}")
        return False

def get_image_urls(driver):
    """Собирает URL-адреса изображений с текущей страницы."""
    image_urls = []
    image_containers = driver.find_elements(By.CSS_SELECTOR, "ul.returns li .return-image.nga-grid-image")
    for container in image_containers:
        try:
            img_tag = container.find_element(By.TAG_NAME, "img")
            src = img_tag.get_attribute("src")
            if src:
                image_urls.append(src)
        except NoSuchElementException:
            logging.warning(f"Не найден тег img в контейнере: {container.get_attribute('outerHTML')}")
    return image_urls

def extract_artwork_data(driver, link, image_id):
    """
    Extracts artwork data from a given link using Selenium.

    Args:
        driver: The Selenium WebDriver instance.
        link: The URL of the artwork page.
        image_id: ID изображения

    Returns:
        A dictionary containing the extracted artwork data, or None if an error occurs.
    """
    try:
        driver.get(link)
        driver.implicitly_wait(20)

        # Wait for a specific element that indicates the page has loaded
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1.object-title"))
        )

        # Get the page source after it's fully loaded
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")

        artwork_data = {}
        artwork_data["id"] = image_id

        def extract_text_or_none(element):
            """Вспомогательная функция: возвращает текст из элемента или None, если элемента нет."""
            return element.get_text(strip=True) if element else None

        def extract_list_or_empty(element, selector):
            """Вспомогательная функция: возвращает список текста из элементов или пустой список, если элементов нет."""
            items = element.select(selector)
            return [item.get_text(strip=True) for item in items] if items else []

        title_element = soup.select_one("h1.object-title")
        if title_element:
            title_text = title_element.get_text(strip=True).replace("\n", " ").replace(
                "\r", ""
            )
            artwork_data["title"] = re.sub(
                r",\s*\d{4}(-\d{4})?$", "", title_text
            )
        else:
            artwork_data["title"] = None
        
        artwork_data["name_of_artist"] = extract_text_or_none(soup.select_one("p.attribution"))
        artwork_data["date:"] = extract_text_or_none(soup.select_one("h1.object-title .date"))
        artwork_data["technique:"] = extract_text_or_none(soup.select_one(".object-attr.medium .object-attr-value"))
        artwork_data["dimensions:"] = extract_text_or_none(soup.select_one(".object-attr.dimensions .object-attr-value"))
        artwork_data["signature:"] = None

        provenance_text = []
        provenance_div = soup.find('div', id='provenance')
        if provenance_div:
            h3_tag = provenance_div.find('h3', class_='heading-mimic-h6')
            if h3_tag and h3_tag.get_text(strip=True) == 'Provenance':
                p_tags = provenance_div.find_all('p')
                for p in p_tags:
                    provenance_text.append(p.get_text(strip=True))

        artwork_data["provenance"] = provenance_text if provenance_text else []

        exhibitions_text = []
        history_div = soup.find('div', id='history')
        if history_div:
            h3_tag = history_div.find('h3', class_='heading-mimic-h6')
            if h3_tag and h3_tag.get_text(strip=True) == 'Exhibition History':
                dl_tags = history_div.find_all('dl', class_='year-list')
                for dl in dl_tags:
                    exhibitions_text.append(
                        re.sub(r'(\d{4})', r'\n\1 ', dl.get_text(strip=True)).replace("\n", " ").strip())
        artwork_data["exhibitions"] = exhibitions_text if exhibitions_text else []

        bibliography_text = []
        bibliography_div = soup.find('div', id='bibliography')
        if bibliography_div:
            h3_tag = bibliography_div.find('h3', class_='heading-mimic-h6')
            if h3_tag and h3_tag.get_text(strip=True) == 'Bibliography':
                dl_tags = bibliography_div.find_all('dl', class_='year-list')
                for dl in dl_tags:
                    bibliography_text.append(
                        re.sub(r'(\d{4})', r'\n\1 ', dl.get_text(strip=True)).replace("\n", " ").strip())

        artwork_data["bibliography"] = bibliography_text if bibliography_text else []

        on_view_text = extract_text_or_none(soup.select_one("p.onview"))

        if on_view_text and "Gallery" in on_view_text:
            match = re.search(r"Gallery (\w+)", on_view_text)
            if match:
                artwork_data["location:"] = f"National Gallery of Art, {match.group(0)}"
            else:
                artwork_data["location:"] = on_view_text
        else:
            artwork_data["location:"] = None

        artwork_data["image_url"] = None

        return artwork_data
    except Exception as e:
        logging.error(f"Error extracting data from {link}: {e}")
        return None

def go_to_page(driver, page_num):
    """
    Переходит на указанную страницу, используя кнопку 'Next' и JavaScript.
    """
    if page_num == 1:
        driver.get(HIGHLIGHTS_URL)
        WebDriverWait(driver, DRIVER_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.returns li"))
        )
        logging.info(f"Переход на страницу {page_num} выполнен.")
        return

    for attempt in range(3):  # Повторяем попытки сброса в исходное состояния
        try:
            # Возврат на первую страницу
            driver.get(HIGHLIGHTS_URL)
            WebDriverWait(driver, DRIVER_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.returns li"))
            )
            logging.info("Возврат на первую страницу выполнен.")

            # Переход на нужную страницу
            for _ in range(1, page_num):
                # Находим кнопку "Next"
                next_button = WebDriverWait(driver, DRIVER_TIMEOUT).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".pagination .results-next"))
                )

                # Прокрутка к кнопке
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)

                # Ожидание кликабельности кнопки
                WebDriverWait(driver, DRIVER_TIMEOUT).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".pagination .results-next"))
                )

                # Клик по кнопке "Next" с помощью JavaScript
                driver.execute_script("arguments[0].click();", next_button)

                # Ожидание обновления списка результатов
                def list_updated(driver):
                    new_list_count = len(driver.find_elements(By.CSS_SELECTOR, "ul.returns li"))
                    return new_list_count > 0 and new_list_count != initial_list_count

                initial_list_count = len(driver.find_elements(By.CSS_SELECTOR, "ul.returns li"))
                WebDriverWait(driver, DRIVER_TIMEOUT).until(list_updated)

                logging.info(f"Переход на страницу {page_num} попытка {_ + 1}  выполнен.")
                time.sleep(SLEEP_TIME)

            logging.info(f"Переход на страницу {page_num} выполнен после {attempt + 1} попыток.")
            return  # Успешный переход, выходим из функции

        except (TimeoutException, StaleElementReferenceException, ElementClickInterceptedException, ElementNotInteractableException) as e:
            logging.warning(f"Попытка {attempt + 1} перехода на страницу {page_num} не удалась: {e}")
            if attempt == 2:  # Если это была последняя попытка
                logging.error(f"Не удалось перейти на страницу {page_num} после нескольких попыток.")
                raise  # Пробрасываем исключение, чтобы остановить выполнение
            time.sleep(SLEEP_TIME * 2)  # Увеличиваем время ожидания
        except WebDriverException as e:
            logging.error(f"Веб-драйвер столкнулся с ошибкой при попытке {attempt + 1} перехода на страницу {page_num}: {e}")
            if attempt == 2:  # Если это была последняя попытка
                logging.error(f"Не удалось перейти на страницу {page_num} из-за ошибки веб-драйвера.")
                raise  # Пробрасываем исключение, чтобы остановить выполнение
            time.sleep(SLEEP_TIME * 2)  # Увеличиваем время ожидания

if __name__ == "__main__":
    # Chrome options
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # options.add_argument("--headless")

    # Use Service object with ChromeDriverManager
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    artwork_data_list = []
    image_id_counter = 1
    processed_links = set()

    for page_num in range(1, MAX_PAGES + 1):
        logging.info(f"Обработка страницы: {page_num}")
        
        try:
            go_to_page(driver, page_num)
        except Exception as e:
            logging.error(f"Ошибка при обработке страницы {page_num}: {e}")
            break  # Прерываем цикл, если не удалось перейти на страницу

        # Ожидание загрузки списка результатов
        WebDriverWait(driver, DRIVER_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.returns li"))
        )
        
        # Collect artwork links on the current page
        artwork_links = []
        link_elements = driver.find_elements(By.CSS_SELECTOR, "ul.returns li .return-image.nga-grid-image a")
        for link_element in link_elements:
            href = link_element.get_attribute("href")
            if href:
                artwork_links.append(href)

        # Сбор URL-адресов изображений
        image_urls = get_image_urls(driver)
        for i, image_url in enumerate(image_urls):
            
            # Проверяем чтобы у нас не было одинаковых ссылок
            if artwork_links[i] not in processed_links:
                file_ext = get_file_extension(image_url)
                image_filename = f"{image_id_counter}{file_ext}"

                if download_image(image_url, IMAGE_FOLDER, image_filename):
                    logging.info(f"Изображение {image_filename} сохранено.")
                else:
                    logging.warning(f"Не удалось сохранить изображение {image_filename}.")

                # Extract data from each artwork page
                artwork_info = extract_artwork_data(driver, artwork_links[i], image_id_counter)
                if artwork_info:
                    artwork_data_list.append(artwork_info)
            
                image_id_counter += 1
                processed_links.add(artwork_links[i])

    driver.quit()
    logging.info("Завершено.")

    with open(JSON_OUTPUT_FILE, "w", encoding="utf-8") as json_file:
        json.dump(artwork_data_list, json_file, indent=4, ensure_ascii=False)
    logging.info(f"Данные добавлены в {JSON_OUTPUT_FILE}")