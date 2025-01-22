import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
    TimeoutException,
)
from bs4 import BeautifulSoup
import json
import requests
import os
import re
import logging
import time
import signal
from selenium.webdriver.common.action_chains import ActionChains
from concurrent.futures import ThreadPoolExecutor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def show_help():
    """Отображает справочное сообщение."""
    print("Użycie: python Alexa_v2.py [polecenie]")
    print("Polecenia:")
    print("  run     - Uruchomienie skryptu do scrapowania danych.")
    print("  help    - Wyświetlenie tego komunikatu pomocy.")

def download_image(url, folder, filename):
    """Скачивает изображение из URL и сохраняет его в указанной папке."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(os.path.join(folder, filename), "wb") as file:
            for chunk in response.iter_content(8192):
                file.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при скачивании изображения {url}: {e}")
        return False

def scrape_nga_highlights(driver):
    """Скрапит страницу National Gallery of Art Highlights."""
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")

    ul_element = soup.find("ul", class_="returns")
    if ul_element is None:
        logging.error("Не удалось найти элемент ul с классом 'returns'.")
        return None

    li_items = ul_element.find_all("li")
    if not li_items:
        logging.error("Элементы li не найдены в ul.")
        return None

    image_data = []
    for li in li_items:
        img_tag = li.find("img")
        if not img_tag:
            logging.warning("Не удалось найти тег img в li.")
            continue

        image_url = img_tag.get("src")
        if not image_url:
            logging.warning("Отсутствует атрибут src в img.")
            continue

        a_tag = li.find("a")
        href = a_tag.get("href") if a_tag else None
        art_object_url = f"https://www.nga.gov{href}" if href else None

        image_data.append(
            {
                "link_to_the_page_of_the_work": art_object_url,
                "image_url": image_url,
            }
        )

    return image_data

def scrape_artwork_details(art_object_url):
    """Извлекает детальную информацию о произведении искусства из HTML-кода,
    включая открытие скрытых вкладок."""
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--headless") # Добавляем headless режим
    
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5) # Уменьшаем время ожидания

    driver.get(art_object_url)
    wait = WebDriverWait(driver, 10) # Уменьшаем время ожидания
    soup = BeautifulSoup(driver.page_source, "html.parser")

    artwork_data = {}

    def extract_text_or_none(element):
        """Вспомогательная функция: возвращает текст из элемента или None, если элемента нет."""
        return element.get_text(strip=True) if element else None

    title_element = soup.select_one("h1.object-title")
    if title_element:
        title_text = title_element.get_text(strip=True).replace("\n", " ").replace(
            "\r", ""
        )
        artwork_data["title"] = re.sub(
            r",\s*\d{4}(-\d{4})?$", "", title_text
        )

    artwork_data["name_of_artist"] = extract_text_or_none(soup.select_one("p.attribution"))
    artwork_data["date:"] = extract_text_or_none(soup.select_one("h1.object-title .date"))
    artwork_data["on_view"] = extract_text_or_none(soup.select_one("p.onview"))
    artwork_data["technique:"] = extract_text_or_none(soup.select_one(".object-attr.medium .object-attr-value"))
    artwork_data["dimensions:"] = extract_text_or_none(soup.select_one(".object-attr.dimensions .object-attr-value"))
    artwork_data["credit_line"] = extract_text_or_none(soup.select_one(".object-attr.credit .object-attr-value"))
    artwork_data["accession_number"] = extract_text_or_none(soup.select_one(".object-attr.accession .object-attr-value"))
    artwork_data["artist_nationality"] = extract_text_or_none(soup.select_one(".object-attr.artists-makers .nationality"))
    artwork_data["image_use"] = extract_text_or_none(soup.select_one(".object-attr.image-use .object-attr-value"))
    custom_prints_element = soup.select_one(".object-attr.prints .object-attr-value a")
    artwork_data["custom_prints_link"] = custom_prints_element["href"] if custom_prints_element else None
    artwork_data["copyright"] = extract_text_or_none(soup.select_one(".object-attr.copyright .object-attr-value"))
    artwork_data["signature:"] = None # Добавляем поле "signature:" со значением None

    # Кликаем по кнопкам, чтобы открыть вкладки
    buttons_to_click = [
        "accordion-provenance",
        "accordion-inscription",
        "accordion-exhibition-history",
        "accordion-bibliography",
        "accordion-related-content",
        "accordion-marks",
        "accordion-technical"
    ]

    for button_id in buttons_to_click:
        try:
            button = wait.until(EC.presence_of_element_located((By.ID, button_id)))
            driver.execute_script("arguments[0].click();", button)

        except (NoSuchElementException, TimeoutException, ElementClickInterceptedException) as e:
            logging.debug(f"Не удалось кликнуть на кнопку {button_id}: {e}")

    # Обновляем soup после кликов по кнопкам
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Извлекаем провенанс (Provenance)
    provenance_text = []
    provenance_div = soup.find('div', id='provenance')
    if provenance_div:
        h3_tag = provenance_div.find('h3', class_='heading-mimic-h6')
        if h3_tag and h3_tag.get_text(strip=True) == 'Provenance':
            p_tags = provenance_div.find_all('p')
            for p in p_tags:
                provenance_text.append(p.get_text(strip=True))

    # Извлекаем "Associated Names" из раздела "Provenance"
    associated_names_data = []
    if provenance_div:
        # Ищем все теги <a> внутри раздела "Provenance"
        a_tags = provenance_div.find_all("a", href=True)
        for a in a_tags:
            name = a.get_text(strip=True)
            link = a["href"]
            if name and link:
                associated_names_data.append(
                    {"name": name, "link": f"https://www.nga.gov{link}"}
                )

    artwork_data["provenance"] = provenance_text
    artwork_data["associated_names"] = associated_names_data

    # Извлекаем подпись (Inscription)
    inscription_list = []
    inscription_div = soup.find('div', id='inscription')
    if inscription_div:
        h3_tag = inscription_div.find('h3', class_='heading-mimic-h6')
        if h3_tag and h3_tag.get_text(strip=True) == 'Inscription':
            p_tags = inscription_div.find_all('p')
            for p in p_tags:
                inscription_list.append(p.get_text(strip=True))
    artwork_data["inscription"] = inscription_list

    # Извлекаем историю выставок (Exhibition History)
    exhibitions_text = []
    history_div = soup.find('div', id='history')
    if history_div:
        h3_tag = history_div.find('h3', class_='heading-mimic-h6')
        if h3_tag and h3_tag.get_text(strip=True) == 'Exhibition History':
            dl_tags = history_div.find_all('dl', class_='year-list')
            for dl in dl_tags:
                exhibitions_text.append(re.sub(r'(\d{4})', r'\n\1 ', dl.get_text(strip=True)).strip())
    artwork_data["exhibitions"] = exhibitions_text

    # Извлекаем библиографию (Bibliography)
    bibliography_text = []
    bibliography_div = soup.find('div', id='bibliography')
    if bibliography_div:
        h3_tag = bibliography_div.find('h3', class_='heading-mimic-h6')
        if h3_tag and h3_tag.get_text(strip=True) == 'Bibliography':
            dl_tags = bibliography_div.find_all('dl', class_='year-list')
            for dl in dl_tags:
                bibliography_text.append(re.sub(r'(\d{4})', r'\n\1 ', dl.get_text(strip=True)).strip())
    artwork_data["bibliography"] = bibliography_text

    # Извлекаем related content
    related_content_data = []
    related_content_div = soup.find('div', id='relatedpages')
    if related_content_div:
        h3_tag = related_content_div.find('h3', class_='heading-mimic-h6')
        if h3_tag and h3_tag.get_text(strip=True) == 'Related Content':
            content_div = related_content_div.find('div', id='tmsRelatedContent')
            if content_div:
                links = content_div.find_all('a')
                for link in links:
                    related_content_data.append({
                        "title": link.get_text(strip=True),
                        "url": f"https://www.nga.gov{link.get('href')}"
                    })
    artwork_data["related_content"] = related_content_data

    # Извлекаем описание изображения (image_description)
    image_description_div = soup.find('div', class_='drawer-alttext')
    if image_description_div:
        # Открываем вкладку с описанием изображения, если она есть
        try:
            button = wait.until(EC.presence_of_element_located((By.ID, "drawer-control-0")))
            driver.execute_script("arguments[0].click();", button)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            image_description_div = soup.find('div', class_='drawer-alttext')  # Ищем заново после обновления
        except (NoSuchElementException, TimeoutException, ElementClickInterceptedException) as e:
            logging.debug(f"Не удалось кликнуть на кнопку описания изображения: {e}")

        content_div = image_description_div.find('div', id='drawer-content-0')
        if content_div:
            p_tag = content_div.find('p')
            if p_tag:
                artwork_data["image_description"] = p_tag.get_text(strip=True)
            else:
                artwork_data["image_description"] = None
        else:
            artwork_data["image_description"] = None
    else:
        artwork_data["image_description"] = None

    # Извлекаем местоположение
    on_view_text = artwork_data["on_view"]
    if on_view_text and "Gallery" in on_view_text:
        match = re.search(r"Gallery (\w+)", on_view_text)
        if match:
            artwork_data["location:"] = f"National Gallery of Art, {match.group(0)}"
        else:
            artwork_data["location:"] = on_view_text
    else:
      artwork_data["location:"] = None

    # Извлекаем информацию об артисте
    artist_info_div = soup.find('div', id='accordion-artists-makers')
    if artist_info_div:
        artist_name_element = artist_info_div.find('h3', class_='heading-mimic-h6')
        artist_name = artist_name_element.get_text(strip=True) if artist_name_element else None
        if artist_name:
            artwork_data['artist_name'] = artist_name

        # Извлекаем даты рождения и смерти артиста
        birth_date_element = artist_info_div.find('span', class_='birth')
        death_date_element = artist_info_div.find('span', class_='death')
        artwork_data['artist_birth_date'] = birth_date_element.get_text(strip=True) if birth_date_element else None
        artwork_data['artist_death_date'] = death_date_element.get_text(strip=True) if death_date_element else None

    # Извлекаем дату приобретения
    acquisition_div = soup.find('div', id='accordion-acquisition')
    if acquisition_div:
        acquisition_date_element = acquisition_div.find('span', class_='acquisition-date')
        artwork_data['acquisition_date'] = acquisition_date_element.get_text(strip=True) if acquisition_date_element else None

    # Извлекаем "Marks and Labels"
    marks_and_labels_list = []
    marks_and_labels_div = soup.find('div', id='marks')
    if marks_and_labels_div:
        h3_tag = marks_and_labels_div.find('h3', class_='heading-mimic-h6')
        if h3_tag and h3_tag.get_text(strip=True) == 'Marks and Labels':
            p_tags = marks_and_labels_div.find_all('p')
            for p in p_tags:
                marks_and_labels_list.append(p.get_text(strip=True))
    artwork_data["marks_and_labels"] = marks_and_labels_list
    
    # Извлекаем "Technical Summary"
    technical_summary_list = []
    technical_summary_div = soup.find('div', id='technical')
    if technical_summary_div:
        h3_tag = technical_summary_div.find('h3', class_='heading-mimic-h6')
        if h3_tag and h3_tag.get_text(strip=True) == 'Technical Summary':
            p_tags = technical_summary_div.find_all('p')
            for p in p_tags:
                technical_summary_list.append(p.get_text(strip=True))
    artwork_data["technical_summary"] = technical_summary_list

    driver.quit()
    return artwork_data

def scrape_page(driver, page_num, artwork_counter, image_folder, max_workers=5):
    """Скрапит отдельную страницу и возвращает список произведений искусства."""
    logging.info(f"Обработка страницы {page_num}...")
    wait = WebDriverWait(driver, 40)

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.returns")))
        scraped_data = scrape_nga_highlights(driver)

        if not scraped_data:
            logging.warning("Не удалось получить данные со страницы.")
            return [], artwork_counter

        page_artworks = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for item in scraped_data:
                artwork_info = {
                    "id": artwork_counter,
                    "link_to_the_page_of_the_work": item.get("link_to_the_page_of_the_work"),
                    "image_url": item.get("image_url"),
                }

                if item["link_to_the_page_of_the_work"]:
                    future = executor.submit(scrape_artwork_details, item["link_to_the_page_of_the_work"])
                    futures.append((future, artwork_info, item.get("image_url")))

                artwork_counter += 1

            for future, artwork_info, image_url in futures:
                try:
                    artwork_details = future.result()
                    artwork_info.update(artwork_details)

                    # Заменяем пустые значения на None, а пустые списки на []
                    for key, value in artwork_info.items():
                        if value == '':
                            artwork_info[key] = None

                except requests.exceptions.RequestException as e:
                    logging.error(
                        f"Ошибка при запросе страницы {artwork_info['link_to_the_page_of_the_work']}: {e}"
                    )

                page_artworks.append(artwork_info)

                if image_url:
                    image_filename = f"{artwork_info['id']}.jpg"
                    if download_image(image_url, image_folder, image_filename):
                        logging.info(
                            f"Скачано изображение {image_filename} со страницы {page_num}"
                        )
                    else:
                        logging.error(f"Не удалось скачать изображение для произведения с ID {artwork_info['id']}")

        return page_artworks, artwork_counter

    except Exception as e:
        logging.error(f"Произошла ошибка на странице {page_num}: {e}")
        return [], artwork_counter

def signal_handler(signum, frame):
    """Обработчик сигнала для прерывания цикла."""
    global running
    running = False
    logging.info("Прерывание выполнения по сигналу (Ctrl+C). Завершение...")

def run_scraper():
    """Основная функция для запуска скрапинга."""
    global running
    running = True
    signal.signal(signal.SIGINT, signal_handler)

    highlights_url = "https://www.nga.gov/collection/highlights.html"
    max_pages = 10  # Указываем максимальное количество страниц

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    # options.add_argument("--headless") # Раскомментируйте, если нужен headless режим для основного драйвера

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(10)
    driver.get(highlights_url)
    time.sleep(2)  # Уменьшаем начальную паузу
    wait = WebDriverWait(driver, 20)

    all_artworks = []
    page_num = 1
    artwork_counter = 1
    image_folder = "masterpieces"

    if not os.path.exists(image_folder):
        os.makedirs(image_folder)

    while running and page_num <= max_pages:
        page_artworks, artwork_counter = scrape_page(
            driver, page_num, artwork_counter, image_folder
        )
        all_artworks.extend(page_artworks)

        with open("masterpieces_data_test.json", "w", encoding="utf-8") as json_file:
            json.dump(all_artworks, json_file, indent=4, ensure_ascii=False)
        logging.info(f"Данные со страницы {page_num} добавлены в masterpieces_data.json")

        # Переход на следующую страницу
        if page_num < max_pages:
            try:
                # Ожидание появления списка
                wait = WebDriverWait(driver, 10)
                wait.until(
                    EC.presence_of_element_located((By.XPATH, "/html/body/div[2]/div[1]/div[2]/div/div/div/div[3]/div/div/div[5]/div/ul"))
                )
                # Находим кнопку "Next" *после* загрузки страницы
                next_button_xpath = "/html/body/div[2]/div[1]/div[2]/div/div/div/div[3]/div/div/div[5]/div/ul/li[4]/a/span"  # poprawiony xpath
                next_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, next_button_xpath))
                )

                # Запоминаем текущий URL перед кликом, чтобы потом сравнить
                current_url = driver.current_url

                # Клик по кнопке "Next" с помощью JavaScript
                driver.execute_script("arguments[0].click();", next_button)
                # Ожидание обновления URL (zmiany strony)
                wait.until(lambda driver: driver.current_url != current_url) 

            except TimeoutException:
                print(f"Не удалось найти кнопку 'Next' на странице {page_num + 1} или не произошло переключение страницы.")
                break

                # Ожидание обновления списка результатов
                def list_updated(driver):
                    new_list = driver.find_elements(By.CSS_SELECTOR, "ul.returns li")
                    return len(new_list) > 0 and len(new_list) != initial_list_count

                initial_list_count = len(driver.find_elements(By.CSS_SELECTOR, "ul.returns li"))
                wait.until(list_updated)

                page_num += 1
                time.sleep(1)

            except NoSuchElementException:
                logging.info("Кнопка 'next' не найдена. Завершение.")
                break
            except TimeoutException:
                logging.error(
                    "Превышено время ожидания загрузки следующей страницы."
                )
                break
        else:
            logging.info("Достигнута последняя страница.")
            break

    driver.quit()
    logging.info("Завершено.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "help":
            show_help()
        elif command == "run":
            run_scraper()
        else:
            print("Неизвестная команда.")
            show_help()
    else:
        run_scraper()