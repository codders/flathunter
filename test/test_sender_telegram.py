import requests_mock
import unittest
from flathunter.sender_telegram import SenderTelegram 

class SenderTelegramTest(unittest.TestCase):

    @requests_mock.Mocker()
    def test_send_message(self, m):
      sender = SenderTelegram({ "telegram": { "bot_token": "dummy_token", "receiver_ids": [ 123 ] }})
      mock_response = '{"ok":true,"result":{"message_id":456,"from":{"id":1,"is_bot":true,"first_name":"Wohnbot","username":"wohnung_search_bot"},"chat":{"id":5,"first_name":"Arthur","last_name":"Taylor","type":"private"},"date":1589813130,"text":"hello arthur"}}'
      m.get('https://api.telegram.org/botdummy_token/sendMessage?chat_id=123&text=result', text=mock_response)
      self.assertEqual(None, sender.send_message("result"), "Expected message to be sent")

    @requests_mock.Mocker()
    def test_send_no_message_if_no_receivers(self, m):
      sender = SenderTelegram({ "telegram": { "bot_token": "dummy_token", "receiver_ids": None }})
      self.assertEqual(None, sender.send_message("result"), "Expected no message to be sent")
