from abc import ABC


class Notifier(ABC):

    def notify(self, message: str):
        """Notify users with the given message"""
