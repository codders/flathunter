"""Interface for webcrawlers. Crawler implementations should subclass this"""
import re
import logging
import random
import requests
import selenium
from time import sleep as sleep
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium import webdriver
from bs4 import BeautifulSoup


class Crawler:
    """Defines the Crawler interface"""

    __log__ = logging.getLogger('flathunt')
    URL_PATTERN = None

    USER_AGENTS = [
        # Chrome
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
         "AppleWebKit/537.36 (KHTML, like Gecko)"
         "Chrome/74.0.3729.169 Safari/537.36"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
         "AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/80.0.3987.149 Safari/537.36"),
        # Edge
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
         "AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/51.0.2704.79 Safari/537.36 Edge/14.14393"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
         "AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/70.0.3538.102 Safari/537.36 Edge/18.18363"),
        # Firefox
        ("Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) "
         "Gecko/20100101 Firefox/40.1"),
        ("Mozilla/5.0 (Windows NT 6.1; WOW64; rv:54.0) "
         "Gecko/20100101 Firefox/54.0"),
        # Safari
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) "
         "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/11.1.2 "
         "Safari/605.1.15"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) "
         "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.5 "
         "Safari/605.1.15")
    ]

    HEADERS = {
        'Connection': 'keep-alive',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': f'{random.choice(USER_AGENTS)}',
        'Accept': 'text/html,application/xhtml+xml,application/xml;'
                  'q=0.9,image/webp,image/apng,*/*;q=0.8,'
                  'application/signed-exchange;v=b3;q=0.9',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-User': '?1',
        'Sec-Fetch-Dest': 'document',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    def configure_driver(self, driver_path, driver_arguments):
        chrome_options = Options()
        if driver_arguments is not None:
            for driver_argument in driver_arguments:
                chrome_options.add_argument(driver_argument)
        driver = webdriver.Chrome(executable_path=driver_path, options=chrome_options)
        return driver

    def rotate_user_agent(self):
        """Choose a new random user agent"""
        self.HEADERS['User-Agent'] = random.choice(self.USER_AGENTS)

    # pylint: disable=unused-argument
    def get_page(self, search_url, driver=None, page_no=None):
        """Applies a page number to a formatted search URL and fetches the exposes at that page"""
        return self.get_soup_from_url(search_url)

    def get_soup_from_url(self, url, driver=None, captcha_api_key=None, checkbox=None, afterlogin_string=None):
        """Creates a Soup object from the HTML at the provided URL"""
        self.rotate_user_agent()
        resp = requests.get(url, headers=self.HEADERS)
        if resp.status_code != 200:
            self.__log__.error("Got response (%i): %s", resp.status_code, resp.content)
        if driver is not None and re.search("g-recaptcha", resp.text):
            driver.get(url)
            if re.search("g-recaptcha", driver.page_source):
                self.resolvecaptcha(driver, checkbox, afterlogin_string, captcha_api_key)
            return BeautifulSoup(driver.page_source, 'html.parser')
        return BeautifulSoup(resp.content, 'html.parser')

    # pylint: disable=no-self-use
    def extract_data(self, soup):
        """Should be implemented in subclass"""
        raise Exception("Method not implemented")

    # pylint: disable=unused-argument
    def get_results(self, search_url, max_pages=None):
        """Loads the exposes from the site, starting at the provided URL"""
        self.__log__.debug("Got search URL %s", search_url)

        # load first page
        soup = self.get_page(search_url)

        # get data from first page
        entries = self.extract_data(soup)
        self.__log__.debug('Number of found entries: %d', len(entries))

        return entries

    def crawl(self, url, max_pages=None):
        """Load as many exposes as possible from the provided URL"""
        if re.search(self.URL_PATTERN, url):
            try:
                return self.get_results(url, max_pages)
            except requests.exceptions.ConnectionError:
                self.__log__.warning("Connection to %s failed. Retrying.", url.split('/')[2])
                return []
        return []

    def get_name(self):
        """Returns the name of this crawler"""
        return type(self).__name__

    def get_expose_details(self, expose):
        """Loads additional detalis for an expose. Should be implemented in the subclass"""
        return expose

    def resolvecaptcha(self, driver, checkbox: bool, afterlogin_string: str = "", api_key: str = None):
        iframe_present = self._check_if_iframe_visible(driver)
        if checkbox is False and afterlogin_string == "" and iframe_present:
            self._solve(driver, api_key)
        else:
            if checkbox:
                self._clickcaptcha(driver, checkbox)
            else:
                self._wait_for_captcha_resolution(driver, checkbox, afterlogin_string)

    def _solve(self, driver, api_key):
        src_iframe = driver.find_element_by_tag_name("iframe").get_attribute("src")
        google_site_key_temp = re.search("&k=(.*?)&", src_iframe)
        self.__log__.debug("Google site key: %s", google_site_key_temp)
        google_site_key = google_site_key_temp.group(1)
        url = driver.current_url
        session = requests.Session()
        postrequest = (
            f"http://2captcha.com/in.php?key={api_key}&method=userrecaptcha&googlekey={google_site_key}&pageurl={url}"
        )
        captcha_id = session.post(postrequest).text.split("|")[1]
        recaptcha_answer = session.get(f"http://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}").text
        while "CAPCHA_NOT_READY" in recaptcha_answer:
            sleep(5)
            self.__log__.debug("Captcha status: %s", recaptcha_answer)
            recaptcha_answer = session.get(f"http://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}").text
        self.__log__.debug("Captcha promise: %s", recaptcha_answer)
        recaptcha_answer = recaptcha_answer.split("|")[1]
        driver.execute_script(f'document.getElementById("g-recaptcha-response").innerHTML="{recaptcha_answer}";')
        driver.execute_script(f'solvedCaptcha("{recaptcha_answer}")')
        self._check_if_iframe_not_visible(driver)

    def _clickcaptcha(self, driver, checkbox: bool):
        driver.switch_to.frame(driver.find_element_by_tag_name("iframe"))
        recaptcha_checkbox = driver.find_element_by_class_name("recaptcha-checkbox-checkmark")
        recaptcha_checkbox.click()
        self._wait_for_captcha_resolution(driver, checkbox)
        driver.switch_to.default_content()

    def _wait_for_captcha_resolution(self, driver, checkbox: bool, afterlogin_string=""):
        if checkbox:
            try:
                element = WebDriverWait(driver, 120).until(
                    EC.visibility_of_element_located((By.CLASS_NAME, "recaptcha-checkbox-checked"))
                )
            except selenium.common.exceptions.TimeoutException:
                print("Selenium.Timeoutexception")
        else:
            xpath_string = f"//*[contains(text(), '{afterlogin_string}')]"
            try:
                element = WebDriverWait(driver, 120).until(EC.visibility_of_element_located((By.XPATH, xpath_string)))
            except selenium.common.exceptions.TimeoutException:
                print("Selenium.Timeoutexception")

    def _check_if_iframe_visible(self, driver: selenium.webdriver.Chrome):
        try:
            iframe = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "iframe[src^='https://www.google.com/recaptcha/api2/anchor?']")))
            return iframe
        except NoSuchElementException:
            print("No iframe found, therefore no chaptcha verification necessary")

    def _check_if_iframe_not_visible(self, driver: selenium.webdriver.Chrome):
        try:
            iframe = WebDriverWait(driver, 10).until(EC.invisibility_of_element(
                (By.CSS_SELECTOR, "iframe[src^='https://www.google.com/recaptcha/api2/anchor?']")))
            return iframe
        except NoSuchElementException:
            print("Element not found")
