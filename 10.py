from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains
import json
import time
import os
import re

# Настройки браузера
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=options)

base_url = "https://www.vangoghmuseum.nl/nl/collectie"
image_data = []
image_id = 1
max_images = 5036
download_folder = "vangogh_images_test"

# Создание папки для загрузки изображений
if not os.path.exists(download_folder):
    os.makedirs(download_folder)

def click_with_retry(driver, element, timeout=20):
    """
    Пытается кликнуть по элементу, обрабатывая ElementClickInterceptedException.
    Использует ActionChains для прокрутки и клика, а также JavaScript как запасной вариант.
    """
    try:
        # Ожидаем, пока элемент станет видимым
        WebDriverWait(driver, timeout).until(
            EC.visibility_of(element)
        )
        # Прокручиваем до элемента
        ActionChains(driver).move_to_element(element).perform()

        # Ожидаем, пока элемент станет кликабельным
        clickable_element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(element)
        )
        # Пытаемся кликнуть по элементу
        clickable_element.click()
    except ElementClickInterceptedException:
        # Если клик был перехвачен, ждем немного и пробуем снова
        print("Клик по элементу перехвачен, ждем и пробуем еще раз...")
        time.sleep(2)
        # Используем JavaScript для клика
        driver.execute_script("arguments[0].click();", element)
    except TimeoutException:
        print(f"Элемент не стал кликабельным после {timeout} секунд")

try:
    driver.get(base_url)
    print(f"Обрабатывается страница: {base_url}")

    last_height = driver.execute_script("return document.body.scrollHeight")
    processed_links = set()
    new_links_found = True
    page_load_attempts = 0

    while image_id <= max_images and new_links_found:
        page_load_attempts += 1
        print(f'Попытка загрузки страницы: {page_load_attempts}')

        # Ожидание загрузки страницы - изменено время ожидания на 30 секунд
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CLASS_NAME, "collection-art-object-item-image"))
            )
        except TimeoutException:
            print(
                f"Превышено время ожидания загрузки элементов на странице {base_url}. Попытка перезагрузки страницы."
            )
            driver.refresh() # Перезагружаем страницу
            continue

        # Поиск всех элементов с изображениями
        image_elements = driver.find_elements(
            By.CLASS_NAME, "collection-art-object-item-image"
        )
        print(f"Найдено {len(image_elements)} элементов с изображениями.")

        links = []
        for image_element in image_elements:
            link = (
                image_element.get_attribute("data-src")
                or image_element.get_attribute("src")
            )
            if (
                link
                and link
                != "https://www.vangoghmuseum.nl/nl/collectie/default.jpg"
                and link not in processed_links
            ):
                links.append(link)

        # Проверка, были ли найдены новые ссылки
        new_links_found = len(links) > 0
        print(f"Найдено {len(links)} новых ссылок.")

        i = 0
        while i < len(links):
            if image_id > max_images:
                print(
                    f"Достигнут лимит в {max_images} изображений. Завершаем обработку."
                )
                break

            link = links[i]
            processed_links.add(link)
            print(f"Обрабатывается изображение {image_id} из {max_images}: {link}")

            try:
                # Получаем ссылку на страницу с картиной
                all_links = driver.find_elements(By.TAG_NAME, "a")
                detail_page_link = None
                for a_link in all_links:
                    try:
                        img = a_link.find_element(By.TAG_NAME, "img")
                        img_src = (
                            img.get_attribute("data-src")
                            or img.get_attribute("src")
                        )
                        if img_src == link:
                            detail_page_link = a_link.get_attribute("href")
                            break
                    except NoSuchElementException:
                        continue

                if not detail_page_link:
                    print(
                        f"Не найдена ссылка на страницу с деталями для изображения {link}"
                    )
                    i += 1
                    continue

                driver.get(detail_page_link)

                # Ожидание загрузки нужных элементов
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            ".art-object-page-content-title, .art-object-page-content-creator-info, .inline-list__item, .art-object-page-content-details, .definition-list-item-value",
                        )
                    )
                )

                # Получение заголовка
                title = driver.find_element(
                    By.CLASS_NAME, "art-object-page-content-title"
                ).text

                # Поиск элемента с информацией об авторе и дате
                try:
                    creator_info_element = driver.find_element(
                        By.CLASS_NAME, "art-object-page-content-creator-info"
                    )
                except TimeoutException:
                    try:
                        creator_info_element = driver.find_element(
                            By.CSS_SELECTOR, ".inline-list__item:nth-child(2)"
                        )
                    except TimeoutException:
                        print(
                            f"Не удалось найти информацию об авторе для изображения {link}"
                        )
                        driver.get(base_url)
                        i += 1
                        continue

                # Получение и обработка информации об авторе
                creator_info_text = creator_info_element.text
                artist_name = creator_info_text.split(",")[0].strip()
                # Получение и обработка даты
                date_text = creator_info_element.text
                date_parts = date_text.split(",")
                if len(date_parts) > 1:
                    date = date_parts[-1].strip()
                else:
                    date = ""

                # Раздел "Objectgegevens"
                # details = {}  <-- Удаляем эту строку
                technique = None
                dimensions = None
                provenance = None

                try:
                    # Находим кнопку для открытия раздела "Objectgegevens"
                    objectgegevens_button = driver.find_element(
                        By.XPATH,
                        "//h4[contains(@class, 'accordion-item-button') and contains(., 'Objectgegevens')]/button",
                    )

                    click_with_retry(driver, objectgegevens_button)

                    # Ожидание загрузки содержимого раздела "Objectgegevens"
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                "//h5[contains(text(), 'Herkomst')]/following-sibling::p",
                            )
                        )
                    )

                    # Извлекаем technique
                    try:
                        # Ищем элемент с техникой в разделе "Objectgegevens"
                        technique_element = driver.find_element(
                            By.XPATH,
                            "//dt[contains(., 'Technique') or contains(., 'technique')]/following-sibling::dd[1]"
                        )
                        technique = technique_element.text.strip()

                    except NoSuchElementException:
                        print(
                            f"Не удалось найти информацию о технике для изображения {link}"
                        )

                    # Извлекаем dimensions
                    try:
                        # Ищем элемент с размерами в разделе "Objectgegevens"
                        dimensions_element = driver.find_element(
                            By.XPATH,
                            "//dt[contains(., 'Dimensions') or contains(., 'dimensions')]/following-sibling::dd[1]"
                        )

                        dimensions_text = dimensions_element.text.strip()

                        # Ищем только числа и "cm"
                        dimensions_match = re.search(
                            r"(\d+(?:\.\d+)?\s*cm\s*×\s*\d+(?:\.\d+)?\s*cm)",
                           dimensions_text
                        )

                        if dimensions_match:
                            dimensions = dimensions_match.group(1).strip()

                    except NoSuchElementException:
                        print(
                            f"Не удалось найти информацию о размерах для изображения {link}"
                        )
                    # Извлекаем provenance
                    try:
                        provenance_element = driver.find_element(
                            By.XPATH,
                            "//h5[contains(text(), 'Herkomst') or contains(text(), 'Provenance')]/following-sibling::p",
                        )
                        provenance = provenance_element.text.strip()

                    except NoSuchElementException:
                        print(
                            f"Не удалось найти информацию о провенансе для изображения {link}"
                        )

                except (
                    NoSuchElementException,
                    TimeoutException,
                    StaleElementReferenceException,
                ) as e:
                    print(
                        f"Ошибка при обработке раздела 'Objectgegevens' для изображения {link}: {e}"
                    )

               # Обработка информации о выставках (exhibitions)
                exhibitions = []
                try:
                    # Поиск кнопки для открытия раздела "Tentoonstellingen"
                    exhibitions_button = driver.find_element(
                        By.XPATH,
                        "//h4[contains(@class, 'accordion-item-button') and contains(., 'Tentoonstellingen')]/button",
                    )

                    click_with_retry(driver, exhibitions_button)

                    # Ожидание загрузки содержимого раздела "Tentoonstellingen"
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, ".accordion-item-content-expanded")
                        )
                    )

                    # Поиск всех элементов с информацией о выставках в .accordion-item-content
                    exhibition_items = driver.find_elements(
                        By.CSS_SELECTOR, ".accordion-item-content-expanded .markdown"
                    )

                    # Извлечение и форматирование информации о выставках
                    for item in exhibition_items:
                        exhibitions.append(item.text.strip())

                except (
                    NoSuchElementException,
                    TimeoutException,
                    StaleElementReferenceException,
                ) as e:
                    print(
                        f"Ошибка при обработке раздела 'Tentoonstellingen' для изображения {link}: {e}"
                    )

                # Обработка информации о литературе (literature)
                literature = []
                try:
                    # Поиск кнопки для открытия раздела "Literatuur"
                    literature_button = driver.find_element(
                        By.XPATH,
                        "//h4[contains(@class, 'accordion-item-button') and contains(., 'Literatuur')]/button",
                    )
                    click_with_retry(driver, literature_button)

                    # Ожидание загрузки содержимого раздела "Literatuur"
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, ".accordion-item-content-expanded")
                        )
                    )

                    # Находим родительский div раздела "Literatuur"
                    literature_parent_div = driver.find_element(
                        By.XPATH,
                        "//h4[contains(@class, 'accordion-item-button') and contains(., 'Literatuur')]/ancestor::div[contains(@class, 'accordion-item')]",
                    )

                    # Извлечение информации о литературе
                    literature_content = literature_parent_div.find_element(
                        By.CSS_SELECTOR, ".accordion-item-content-expanded"
                    )

                    if literature_content:
                        # Находим все <p> теги в содержимом раздела "Literatuur"
                        p_tags = literature_content.find_elements(By.TAG_NAME, "p")
                        for p in p_tags:
                            literature.append(p.text.strip())

                except (
                    NoSuchElementException,
                    TimeoutException,
                    StaleElementReferenceException,
                ) as e:
                    print(
                        f"Ошибка при обработке раздела 'Literatuur' для изображения {link}: {e}"
                    )

                image_data.append(
                    {
                        "id": image_id,
                        "image_url": link,
                        "title": title,
                        "date": date,
                        "name_of_artist": artist_name,
                        "technique": technique, # Изменено
                        "dimensions": dimensions, # Изменено
                        "signature": None,
                        "location": "Van Gogh Museum, Amsterdam",
                        "exhibitions": exhibitions,
                        "provenance": provenance, # Изменено
                        "literature": literature
                    }
                )
                print(
                    f"Собран заголовок: {title}, изображение: {link}, дата: {date}, художник: {artist_name}, техника: {technique}, размеры: {dimensions}, подпись: {None}, местонахождение: Van Gogh Museum, Amsterdam, выставки: {exhibitions}, провенанс: {provenance}, литература: {literature}"
                )

                image_id += 1
                i += 1

            except Exception as e:
                print(f"Непредвиденная ошибка: {e}")
            finally:
                # Возвращаемся к базовому URL после обработки каждой картины
                driver.get(base_url)

                # Ожидаем загрузку элементов на главной странице
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, "collection-art-object-item-image")
                    )
                )

                # Обновляем список ссылок после возвращения на главную страницу
                image_elements = driver.find_elements(
                    By.CLASS_NAME, "collection-art-object-item-image"
                )
                print(
                    f"После возврата на главную страницу найдено {len(image_elements)} элементов с изображениями."
                )
                links = []
                for image_element in image_elements:
                    link = (
                        image_element.get_attribute("data-src")
                        or image_element.get_attribute("src")
                    )
                    if (
                        link
                        and link
                        != "https://www.vangoghmuseum.nl/nl/collectie/default.jpg"
                        and link not in processed_links
                    ):
                        links.append(link)
                print(
                    f"После возврата на главную страницу найдено {len(links)} новых ссылок."
                )

        # Прокрутка вниз для загрузки новых элементов
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(5)  # Увеличил паузу до 5 секунд
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            print("Достигнут конец страницы, выходим из цикла.")
            break
        last_height = new_height

        if image_id > max_images:
            print(f"Достигнут лимит в {max_images} изображений (заголовков).")
            break

        if not new_links_found:
            print("Новых ссылок не найдено, выходим из цикла.")
            break

except Exception as e:
    print(f"Произошла ошибка: {e}")

finally:
    driver.quit()

# Сохранение данных в JSON файл
with open("vangogh_images_test.json", "w", encoding="utf-8") as f:
    json.dump(image_data, f, indent=4, ensure_ascii=False)
print(f"Собрано данных: {len(image_data)}")
print("Данные сохранены в файл vangogh_images_test.json")