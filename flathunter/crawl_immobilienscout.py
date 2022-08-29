"""Expose crawler for ImmobilienScout"""
import datetime
import re

from jsonpath_ng import parse
from selenium.common.exceptions import JavascriptException

from flathunter.abstract_crawler import Crawler
from flathunter.logging import logger


class CrawlImmobilienscout(Crawler):
    """Implementation of Crawler interface for ImmobilienScout"""

    URL_PATTERN = re.compile(r'https://www\.immobilienscout24\.de')

    JSON_PATH_PARSER_ENTRIES = parse("$..['resultlist.realEstate']")
    JSON_PATH_PARSER_IMAGES = parse("$..galleryAttachments..['@href']")

    RESULT_LIMIT = 50

    FALLBACK_IMAGE_URL = "https://www.static-immobilienscout24.de/statpic/placeholder_house/" + \
                         "496c95154de31a357afa978cdb7f15f0_placeholder_medium.png"

    def __init__(self, config):
        super().__init__(config)

        self.config = config
        self.driver = None
        self.checkbox = None
        self.afterlogin_string = None

        if config.captcha_enabled():
            driver_arguments = config.captcha_driver_arguments()

            self.checkbox = config.get_captcha_checkbox()
            self.afterlogin_string = config.get_captcha_afterlogin_string()
            if self.captcha_solver:
                self.driver = self.configure_driver(driver_arguments)

    def get_results(self, search_url, max_pages=None):
        """Loads the exposes from the ImmoScout site, starting at the provided URL"""
        # convert to paged URL
        # if '/P-' in search_url:
        #     search_url = re.sub(r"/Suche/(.+?)/P-\d+", "/Suche/\1/P-{0}", search_url)
        # else:
        #     search_url = re.sub(r"/Suche/(.+?)/", r"/Suche/\1/P-{0}/", search_url)
        if '&pagenumber' in search_url:
            search_url = re.sub(r"&pagenumber=[0-9]", "&pagenumber={0}", search_url)
        else:
            search_url = search_url + '&pagenumber={0}'
        logger.debug("Got search URL %s", search_url)

        # load first page to get number of entries
        page_no = 1
        soup = self.get_page(search_url, self.driver, page_no)

        # If we are using Selenium, just parse the results from the JSON in the page response
        if self.driver is not None:
            return self.get_entries_from_javascript()

        try:
            no_of_results = int(
                soup.find_all(lambda e: e.has_attr('data-is24-qa') and \
                                        e['data-is24-qa'] == 'resultlist-resultCount')[0] \
                    .text.replace('.', ''))
        except IndexError:
            logger.error('Index error occurred')
            no_of_results = 0

        # get data from first page
        entries = self.extract_data(soup)

        # iterate over all remaining pages
        while len(entries) < min(no_of_results, self.RESULT_LIMIT) and \
                (max_pages is None or page_no < max_pages):
            logger.debug(
                '(Next page) Number of entries: %d / Number of results: %d',
                len(entries), no_of_results)
            page_no += 1
            soup = self.get_page(search_url, self.driver, page_no)
            cur_entry = self.extract_data(soup)
            if isinstance(cur_entry, list):
                break
            entries.extend(cur_entry)
        return entries

    def get_entries_from_javascript(self):
        """Get entries from JavaScript"""
        try:
            result_json = self.driver.execute_script('return window.IS24.resultList;')
        except JavascriptException:
            logger.warning("Unable to find IS24 variable in window")
            return []
        return self.get_entries_from_json(result_json)

    def get_entries_from_json(self, json):
        """Get entries from JSON"""
        return [
            self.extract_entry_from_javascript(entry.value) for entry in self.JSON_PATH_PARSER_ENTRIES.find(json)
        ]

    def extract_entry_from_javascript(self, entry):
        """Get single entry from JavaScript"""

        # the url that is being returned to the frontend has a placeholder for screen size. (%WIDTH% and %HEIGHT%)
        # The website's frontend fills these variables based on the user's screen size.
        # If we remove this part, the API will return the original size of the image.
        #
        # Before:
        # https://pictures.immobilienscout24.de/listings/$$IMAGE_ID$$.jpg/ORIG/legacy_thumbnail/%WIDTH%x%HEIGHT%3E/format/webp/quality/50
        #
        # After: https://pictures.immobilienscout24.de/listings/$$IMAGE_ID$$.jpg

        images = [
            '/'.join(image.value.split('/')[:5]) for image in self.JSON_PATH_PARSER_IMAGES.find(entry)
        ]

        return {
            'id': int(entry.get("@id", 0)),
            'url': ("https://www.immobilienscout24.de/expose/" + str(entry.get("@id", 0))),
            'image': images[0] if len(images) else self.FALLBACK_IMAGE_URL,
            'images': images,
            'title': entry.get("title", ''),
            'address': entry.get("address", {}).get("description", {}).get("text", ''),
            'crawler': self.get_name(),
            'price': str(entry.get("price", {}).get("value", '')),
            'total_price': str(entry.get('calculatedTotalRent', {}).get("totalRent", {}).get('value', '')),
            'size': str(entry.get("livingSpace", '')),
            'rooms': str(entry.get("numberOfRooms", ''))
        }

    def get_page(self, search_url, driver=None, page_no=None):
        """Applies a page number to a formatted search URL and fetches the exposes at that page"""
        return self.get_soup_from_url(
            search_url.format(page_no),
            driver=driver,
            checkbox=self.checkbox,
            afterlogin_string=self.afterlogin_string
        )

    def get_expose_details(self, expose):
        """Loads additional details for an expose by processing the expose detail URL"""
        soup = self.get_soup_from_url(expose['url'])
        date = soup.find('dd', {"class": "is24qa-bezugsfrei-ab"})
        expose['from'] = datetime.datetime.now().strftime("%2d.%2m.%Y")
        if date is not None:
            if not re.match(r'.*sofort.*', date.text):
                expose['from'] = date.text.strip()
        return expose

    # pylint: disable=too-many-locals
    # pylint: disable=too-many-branches
    def extract_data(self, soup):
        """Extracts all exposes from a provided Soup object"""
        entries = []

        results_list = soup.find(id="resultListItems")
        title_elements = results_list.find_all(
            lambda e: e.name == 'a' and e.has_attr('class') and \
                      'result-list-entry__brand-title-container' in e['class']
        ) if results_list else []
        expose_ids = []
        expose_urls = []
        for link in title_elements:
            expose_id = int(link.get('href').split('/')[-1].replace('.html', ''))
            expose_ids.append(expose_id)
            if len(str(expose_id)) > 5:
                expose_urls.append('https://www.immobilienscout24.de/expose/' + str(expose_id))
            else:
                expose_urls.append(link.get('href'))

        attr_container_els = soup.find_all(
            lambda e: e.has_attr('data-is24-qa') and e['data-is24-qa'] == "attributes"
        )
        address_fields = soup.find_all(
            lambda e: e.has_attr('class') and 'result-list-entry__address' in e['class']
        )
        gallery_elements = soup.find_all(
            lambda e: e.has_attr('class') and 'result-list-entry__gallery-container' in e['class']
        )
        for idx, title_el in enumerate(title_elements):
            attr_els = attr_container_els[idx].find_all('dd')
            try:
                address = address_fields[idx].text.strip()
            except AttributeError:
                address = "No address given"

            gallery_tag = gallery_elements[idx].find("div", {"class": "gallery-container"})
            if gallery_tag is not None:
                image_tag = gallery_tag.find("img")
                try:
                    image = image_tag["src"]
                except KeyError:
                    image = image_tag["data-lazy-src"]
            else:
                image = None

            details = {
                'id': expose_ids[idx],
                'url': expose_urls[idx],
                'image': image,
                'title': title_el.text.strip().replace('NEU', ''),
                'address': address,
                'crawler': self.get_name()
            }
            if len(attr_els) > 2:
                details['price'] = attr_els[0].text.strip().split(' ')[0].strip()
                details['size'] = attr_els[1].text.strip().split(' ')[0].strip() + " qm"
                details['rooms'] = attr_els[2].text.strip().split(' ')[0].strip()
            else:
                # If there are less than three elements, it is unclear which is what.
                details['price'] = ''
                details['size'] = ''
                details['rooms'] = ''
            # print entries
            exist = False
            for expose in entries:
                if expose_id == expose["id"]:
                    exist = True
                    break
            if not exist:
                entries.append(details)

        logger.debug('Number of entries found: %d', len(entries))
        return entries
