"""Wrap configuration options as an object"""
import os
import logging
import yaml

from flathunter.crawl_ebaykleinanzeigen import CrawlEbayKleinanzeigen
from flathunter.crawl_immobilienscout import CrawlImmobilienscout
from flathunter.crawl_wggesucht import CrawlWgGesucht
from flathunter.crawl_immowelt import CrawlImmowelt
from flathunter.filter import Filter


class Config:
    """Class to represent flathunter configuration"""

    __log__ = logging.getLogger('flathunt')

    def __init__(self, filename=None, string=None):
        if string is not None:
            self.config = yaml.safe_load(string)
        else:
            if filename is None:
                filename = os.path.dirname(os.path.abspath(__file__)) + "/../config.yaml"
            self.__log__.info("Using config %s", filename)
            with open(filename) as file:
                self.config = yaml.safe_load(file)
        self.__searchers__ = [CrawlImmobilienscout(self),
                              CrawlWgGesucht(),
                              CrawlEbayKleinanzeigen(),
                              CrawlImmowelt()]

    def __iter__(self):
        """Emulate dictionary"""
        return self.config.__iter__()

    def __getitem__(self, value):
        """Emulate dictionary"""
        return self.config[value]

    def get(self, key, value=None):
        """Emulate dictionary"""
        return self.config.get(key, value)

    def database_location(self):
        """Return the location of the database folder"""
        if "database_location" in self.config:
            return self.config["database_location"]
        return os.path.abspath(os.path.dirname(os.path.abspath(__file__)) + "/..")

    def set_searchers(self, searchers):
        """Update the active search plugins"""
        self.__searchers__ = searchers

    def searchers(self):
        """Get the list of search plugins"""
        return self.__searchers__

    def get_filter(self):
        """Read the configured filter"""
        builder = Filter.builder()
        builder.read_config(self.config)
        return builder.build()

    def captcha_enabled(self):
        return ("captcha" in self.config)
