from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as WDW
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential, wait_random_exponential, wait_random
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
BATCH_SIZE = int(os.getenv('BATCH_SIZE'))
NUMBER_OF_ITEMS = int(os.getenv('NUMBER_OF_ITEMS'))
FILENAME = os.getenv('FILENAME')
DEBUGGING = os.getenv('DEBUGGING', 'True') == 'True'
TRANSLATE_URL = os.getenv('TRANSLATE_URL', 'https://translate.google.com/?sl=en&tl=sn&op=translate')
TIMEOUT = int(os.getenv('TIMEOUT', 3))

chrome_options = Options()
if DEBUGGING:
    logger.info(f'Running in debug mode')
    chrome_options.add_experimental_option('detach', True)
else:
    logger.info(f'Running in --headless mode')
    chrome_options.add_argument('--headless')

class NoTranslationResult(Exception):
    ...


@retry(
        retry=retry_if_exception((TimeoutException, ConnectionError, WebDriverException)),
        stop=stop_after_attempt(5),
        wait=wait_random_exponential(multiplier=1, min=3, max=10) + wait_random(0, 2),
        before_sleep=lambda retry_state: logger.warning(f'Retrying in {retry_state.next_action.sleep} seconds')
)
def wait_for_element(browser, by, element_id, timeout=5, check_visibility=False):
    try:
        condition = EC.visibility_of_element_located if check_visibility else EC.presence_of_element_located
        element = condition((by, element_id))
        WDW(browser, timeout).until(element)
        return browser.find_element(by, element_id)
    except (ConnectionError, TimeoutException, WebDriverException) as e:
        logger.error(f'Error encountered: {e}')
        return False

@sleep_and_retry
@limits(calls=1, period=random.uniform(2, 5))
def rate_limited_translate(text: str, in_browser: webdriver.Chrome, max_retries: int=3) -> str:
    for attempt in range(max_retries):
        try:
            result = translate(text, in_browser)
            logger.debug(f'Translation successful on attempt {attempt + 1}')
            return result
        except Exception as e:
            logger.warning (f"Translation failed on attempt {attempt + 1}: {e}")
            if attempt == max_retries-1:
                logger.error(f"All {max_retries} translation attempt failed")
                raise
    return translate(text, in_browser)

def translate(text: str, in_browser: webdriver.Chrome) -> str:
    time.sleep(random.uniform(5, 8))
    text_area = wait_for_element(in_browser, By.CSS_SELECTOR, 'textarea.er8xn', timeout=random.uniform(1, 10))
    if text_area:
        text_area.clear()
        text_area.send_keys(text)

        time.sleep(random.uniform(5, 8))
        result = wait_for_element(in_browser, By.CSS_SELECTOR, 'span.ryNqvb', timeout=random.uniform(1, 10))
        if result and result.text:
            return result.text
    return 'Text area not found'

def chunk(text: str, max_length: int = 5_000):
    chunks = []
    current_chunk = ""
    for sentence in text.split(". "):
        if len(current_chunk) + len(sentence) < max_length-1:
            current_chunk += sentence + ". "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + ". "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

def translate_chunked(text: str, browser):
    if len(text) < 5_000:
        return rate_limited_translate(text, browser)
    else:
        logger.info(f'Text, {len(text)} too long. Chunking...')
        translated_chunks = [rate_limited_translate(chunk, browser) for chunk in chunk(text)]
        return " ". join(translated_chunks)

def translate_item(e, browser):
    e['sh_instruction'] = translate_chunked(e['instruction'], browser)
    e['sh_context'] = translate_chunked(e['context'], browser)
    e['sh_response'] = translate_chunked(e['response'], browser)
    return e

def save_data(batch, n):
    if len(batch) == int(BATCH_SIZE) or n == int(NUMBER_OF_ITEMS):
        try:
            with open('data.json', 'r') as f:
                existing_data = json.load(f)
        except FileNotFoundError:
            existing_data = []
        existing_data.extend(batch)

        with open('data.json', 'w') as f:
            json.dump(existing_data, f, indent=4)
        
        batch = []
    return batch

def load_checkpoint():
    try:
        with open('checkpoint.json', 'r') as f:
            return json.load(f)['last_checkpoint']
    except FileNotFoundError:
        return 0

def translate_data_in(browser):
    ckpt = load_checkpoint()
    batch = []
    for n, line in enumerate(open(FILENAME, 'r'), ckpt):
        logger.info(f'Translating item: {n}')
        batch.append(translate_item(json.loads(line), browser))
        logger.info(f'Translating item: {n}. Complete')
        batch = save_data(batch, n)

def initialize():
    logger.debug('Initializing browser')
    browser_path = Path(__file__).resolve().parent / 'cd' / 'chromedriver.exe'
    service = Service(browser_path)
    browser = webdriver.Chrome(service=service, options=chrome_options)
    browser.get(TRANSLATE_URL)
    time.sleep(random.uniform(5, 10))
    return browser

def main():
    browser = initialize()
    try:
        translate_data_in(browser)
    except Exception as e:
        logger.error(f'An error occurred: {e}')


if __name__ == '__main__':
    logger.debug('Dolly15K translation has commenenced.')
    main()
    logger.debug('Dolly15K translation is complete.')
