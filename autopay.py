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
        print(f'Element with {by} = {element_id} not found within {timeout} seconds: {e}')
        return None
    except ConnectionError as e:
        print(f'Connection error: {e}')
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

    texts = [
        'Hello World',
        'How are you?',
        'What is your name?',
        'I am fine',
        'What is the time?',
        'Good morning',
        'Good afternoon',
        'Good evening',
        'Good night',
        'Goodbye',
        'Thank you',
        'Please',
    ]

    try:
        for text in texts:
            result = translate(text, browser)
            print(f'Translation result:\n{text} >_ {result}\n\n')
            time.sleep(2)
    except NoTranslationResult as e:
        print(f'Unable to retrieve translation')
    except NoSuchElementException as e:
        print(f'Unable to retrieve translation result element: {e}')
    except WebDriverException as e:
        print(f'General webdriver error: {e}')
    finally:
        if not DEBUGGING:
            browser.quit()

if __name__ == '__main__':
    main()
