"""Functions and classes related to sending Telegram messages"""
import json

import requests

from flathunter.abstract_notifier import Notifier
from flathunter.abstract_processor import Processor
from flathunter.logging import logger


class SenderMattermost(Processor, Notifier):
    """Expose processor that sends Mattermost messages"""

    def __init__(self, config):
        self.config = config
        self.webhook_url = self.config.mattermost_webhook_url()

    def process_expose(self, expose):
        """Send a message to a user describing the expose"""
        message = self.config.message_format().format(
            title=expose['title'],
            rooms=expose['rooms'],
            size=expose['size'],
            price=expose['price'],
            url=expose['url'],
            address=expose['address'],
            durations="" if 'durations' not in expose else expose[
                'durations']).strip()
        self.notify(message)
        return expose

    def notify(self, message):
        """Send message to the mattermost webhook"""
        self.__send_text(message)

    def __send_text(self, message: str):
        """Send messages to the mattermost webhook"""
        logger.debug(('webhook_url:', self.webhook_url))
        logger.debug(('message', message))
        resp = requests.post(
            self.webhook_url,
            data=json.dumps({"text": message})
        )
        logger.debug("Got response (%i): %s", resp.status_code, resp.content)

        # handle error
        if resp.status_code != 200:
            logger.error(
                "When sending mattermost bot message, we got status %i with message: %s",
                resp.status_code,
                resp.text
            )
