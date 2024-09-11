from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as WDW
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential, wait_random_exponential
from ratelimit import limits, sleep_and_retry 
import time
from dotenv import load_dotenv
import os
import json
import logging
import tqdm
import random

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

fh = logging.FileHandler('log.txt')
fh.setLevel(logging.INFO)

fh.setFormatter(formatter)
ch.setFormatter(formatter)

logger.addHandler(ch)
logger.addHandler(fh)

load_dotenv()

DEBUGGING = os.getenv('DEBUGGING', 'True').lower() == 'true'
TRANSLATE_URL = os.getenv('TRANSLATE_URL', 'https://translate.google.com/?sl=en&tl=sn&op=translate')
TIMEOUT = int(os.getenv('TIMEOUT', 8))

chrome_options = Options()

custom_options = webdriver.ChromeOptions()
prefs = {
  "translate_whitelists": {"en":"sn"},
  "translate":{"enabled":"true"}
}
chrome_options.add_experimental_option("prefs", prefs)

if DEBUGGING:
    chrome_options.add_experimental_option('detach', True)
else:
    chrome_options.add_argument('--headless')

class NoTranslationResult(Exception):
    ...


@retry(
        retry=retry_if_exception((TimeoutException, ConnectionError, WebDriverException)),
        stop=stop_after_attempt(7),
        wait=wait_random_exponential(multiplier=1, min=3, max=60),
        before_sleep=lambda retry_state: time.sleep(random.uniform(1, 5))
)
def wait_for_element(browser, by, element_id, timeout=5):
    try:
        element = EC.presence_of_element_located((by, element_id))
        WDW(browser, timeout).until(element)
    except TimeoutException as e:
        logger.error(f'Element with {by} = {element_id} not found within {timeout} seconds: {e}')
        return None
    except ConnectionError as e:
        logger.error(f'Connection error: {e}')
        return None
    return browser.find_element(by, element_id)

@sleep_and_retry
@limits(calls=1, period=random.uniform(2, 4))
def rate_limited_translate(text: str, in_browser: webdriver.Chrome) -> str:
    return translate(text, in_browser)

def translate(text: str, in_browser: webdriver.Chrome) -> str:
    text_area = wait_for_element(in_browser, By.CSS_SELECTOR, 'textarea[aria-label="Source text"]', timeout=random.uniform(2, 5))

    if text_area:
        text_area.clear()
        text_area.send_keys(text)

        result = wait_for_element(in_browser, By.CSS_SELECTOR, 'span.ryNqvb', timeout=random.uniform(2, 5))
        time.sleep(random.uniform(2, 3))
        
        if result and result.text:
            return result.text
    return ''

def translate_item(e, browser):
    e['sh_instruction'] = rate_limited_translate(e['instruction'], browser)
    e['sh_context'] = rate_limited_translate(e['context'], browser)
    e['sh_response'] = rate_limited_translate(e['response'], browser)
    return e

def main():
    browser_path = Path(__file__).resolve().parent / 'cd' / 'chromedriver.exe'
    service = Service(browser_path)
    browser = webdriver.Chrome(service=service, options=chrome_options)
    browser.get(TRANSLATE_URL)

    try:
        with open('data.json', 'r') as f:
            data = json.load(f)

        try:
            with open('checkpoint.json', 'r') as f:
                checkpoint = json.load(f)
                start_index = checkpoint['last_processed_index'] + 1
        except FileNotFoundError:
            start_index = 0

        batch = []
        for i, e in enumerate(tqdm.tqdm(data[start_index:], initial=start_index, total=len(data))):
            translated_item = translate_item(e, browser)
            batch.append(translated_item)
            
            if len(batch) >= 10 or i == len(data) - 1:
                with open('trans.json', 'a') as f:
                    json.dump(batch, f, indent=4)
                
                with open('checkpoint.json', 'w') as f:
                    json.dump({'last_processed_index': start_index + i}, f)

                batch = []

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if not DEBUGGING:
            browser.quit()
            logger.info('Browser quit.')

if __name__ == '__main__':
    logger.debug('Program started.')
    main()
    logger.debug('Program execution complete.')
