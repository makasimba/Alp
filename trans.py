from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as WDW
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
import time
from dotenv import load_dotenv
import os
import json
import logging

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
if DEBUGGING:
    chrome_options.add_experimental_option('detach', True)
else:
    chrome_options.add_argument('--headless')

class NoTranslationResult(Exception):
    ...


@retry(
        retry=retry_if_exception((TimeoutException, ConnectionError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60)
)
def wait_for_element(browser, by, element_id, timeout=TIMEOUT):
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

def translate(text: str, in_browser: webdriver.Chrome) -> str:
    text_area = wait_for_element(in_browser, By.CSS_SELECTOR, 'textarea[aria-label="Source text"]')

    if text_area:
        text_area.clear()
        text_area.send_keys(text)
        time.sleep(5)

        result = wait_for_element(in_browser, By.CSS_SELECTOR, 'span.ryNqvb')
        if result and result.text:
            return result.text
    return ''

def main():
    browser_path =  Path(__file__).resolve().parent / 'cd' / 'chromedriver.exe'

    service = Service(browser_path)

    browser = webdriver.Chrome(service=service, options=chrome_options)
    browser.get(TRANSLATE_URL)

    examples = json.load(open('data.json'))
    c = 0
    batch = []
    try:
        for e in examples:
            sh_inst = translate(e['instruction'], browser)
            sh_cxt = translate(e['context'], browser)
            sh_rp = translate(e['response'], browser)

            e['sh_instruction'] = sh_inst
            e['sh_context'] = sh_cxt
            e['sh_response'] = sh_rp

            batch.append(e)
            if c % 10 == 0:
                with open('trans.json', 'a') as f:
                    json.dump(batch, f, indent=4)
                logger.debug(f'Batch {c//10} saved.')
                batch = []

            logger.debug(f'Example  {c} translated.')
            c += 1
            time.sleep(2)
        
    except NoTranslationResult as e:
        logger.error(f'Unable to retrieve translation')
    except NoSuchElementException as e:
        logger.error(f'Unable to retrieve translation result element: {e}')
    except WebDriverException as e:
        logger.error(f'General webdriver error: {e}')
    finally:
        if not DEBUGGING:
            browser.quit()

if __name__ == '__main__':
    main()
