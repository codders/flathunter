"""Expose crawler for ImmobilienScout"""
import logging
import re
import datetime

from flathunter.abstract_crawler import Crawler


class CrawlImmobilienscout(Crawler):
    """Implementation of Crawler interface for ImmobilienScout"""

    __log__ = logging.getLogger('flathunt')
    URL_PATTERN = re.compile(r'https://www\.immobilienscout24\.de')
    RESULT_LIMIT = 50

    def __init__(self, config):
        logging.getLogger("requests").setLevel(logging.WARNING)
        self.config = config
        self.driver = None
        self.captcha_api_key = None
        self.checkbox = None
        self.afterlogin_string = None
        if "captcha" in config:
            self.captcha_api_key = self.config.get('captcha', dict()).get('api_key', '')
            self.driver_executable_path = self.config.get('captcha', dict()).get('driver_path', '')
            self.driver_arguments = self.config.get('captcha', dict()).get('driver_arguments', list())
            if self.config.get('captcha', dict()).get('checkbox', '') == "":
                self.checkbox = False
            else:
                self.checkbox = self.config.get('captcha', dict()).get('checkbox', '')
            if self.config.get('captcha', dict()).get('afterlogin_string', '') == "":
                self.afterlogin_string = ""
            else:
                self.afterlogin_string = self.config.get('captcha', dict()).get('afterlogin_string', '')
            if self.captcha_api_key is not None or self.driver_executable_path is not None:
                self.driver = self.configure_driver(self.driver_executable_path, self.driver_arguments)

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
        self.__log__.debug("Got search URL %s", search_url)

        # load first page to get number of entries
        page_no = 1
        soup = self.get_page(search_url, self.driver, page_no)
        try:
            no_of_results = int(
                soup.find_all(lambda e: e.has_attr('data-is24-qa') and \
                                        e['data-is24-qa'] == 'resultlist-resultCount')[0] \
                    .text.replace('.', ''))
        except IndexError:
            self.__log__.debug('Index Error occurred')
            no_of_results = 0

        # get data from first page
        entries = self.extract_data(soup)

        # iterate over all remaining pages
        while len(entries) < min(no_of_results, self.RESULT_LIMIT) and \
                (max_pages is None or page_no < max_pages):
            self.__log__.debug(
                'Next Page, Number of entries : %d, no of results: %d',
                len(entries), no_of_results)
            page_no += 1
            soup = self.get_page(search_url, self.driver, page_no)
            cur_entry = self.extract_data(soup)
            if cur_entry is list():
                break
            entries.extend(cur_entry)
        return entries

    def get_page(self, search_url, driver, page_no=None):
        """Applies a page number to a formatted search URL and fetches the exposes at that page"""
        return self.get_soup_from_url(search_url.format(page_no), driver, self.captcha_api_key, self.checkbox,
                                      self.afterlogin_string)

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
        entries = list()

        results_list = soup.find(id="resultListItems")
        title_elements = results_list.find_all(
            lambda e: e.name == 'a' and e.has_attr('class') and \
                      'result-list-entry__brand-title-container' in e['class']
        ) if results_list else []
        expose_ids = list()
        expose_urls = list()
        for link in title_elements:
            expose_id = int(link.get('href').split('/')[-1].replace('.html', ''))
            expose_ids.append(expose_id)
            if len(str(expose_id)) > 5:
                expose_urls.append('https://www.immobilienscout24.de/expose/' + str(expose_id))
            else:
                expose_urls.append(link.get('href'))
        self.__log__.debug(expose_ids)

        attr_container_els = soup.find_all(lambda e: e.has_attr('data-is24-qa') and \
                                                     e['data-is24-qa'] == "attributes")
        address_fields = soup.find_all(lambda e: e.has_attr('class') and \
                                                 'result-list-entry__address' in e['class'])
        gallery_elements = soup.find_all(lambda e: e.has_attr('class') and \
                                                   'result-list-entry__gallery-container' in e['class'])
        for idx, title_el in enumerate(title_elements):
            attr_els = attr_container_els[idx].find_all('dd')
            try:
                address = address_fields[idx].text.strip()
            except AttributeError:
                address = "No address given"

            #            gallery_tag = gallery_elements[idx].find("div", {"class": "gallery-container"})
            #            if gallery_tag is not None:
            #                image_tag = gallery_tag.find("img")
            #                try:
            #                    image = image_tag["src"]
            #                except KeyError:
            #                    image = image_tag["data-lazy-src"]
            #            else:
            #                image = None

            details = {
                'id': expose_ids[idx],
                'url': expose_urls[idx],
                #               'image': image,
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

        self.__log__.debug('extracted: %d', len(entries))
        return entries
