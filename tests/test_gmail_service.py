import unittest
from unittest.mock import patch

from gmail_service import test_smtp_credentials


class DummyServer:
    def __init__(self, *, auth_error=False):
        self.auth_error = auth_error
        self.started_tls = False
        self.closed = False

    def ehlo(self):
        return None

    def starttls(self):
        self.started_tls = True
        return None

    def login(self, email, password):
        if self.auth_error:
            raise Exception("Authentication failed")
        return None

    def quit(self):
        self.closed = True
        return None

    def close(self):
        self.closed = True
        return None


class TestGmailService(unittest.TestCase):
    @patch("gmail_service.smtplib.SMTP_SSL")
    def test_returns_true_when_ssl_login_succeeds(self, smtp_ssl_cls):
        smtp_ssl_cls.return_value = DummyServer()

        self.assertTrue(test_smtp_credentials("user@gmail.com", "abcdefghijkl"))

    @patch("gmail_service.smtplib.SMTP_SSL")
    @patch("gmail_service.smtplib.SMTP")
    def test_falls_back_to_starttls_when_ssl_is_unavailable(self, smtp_cls, smtp_ssl_cls):
        smtp_ssl_cls.side_effect = Exception("ssl not available")
        smtp_cls.return_value = DummyServer()

        self.assertTrue(test_smtp_credentials("user@gmail.com", "abcdefghijkl"))

    @patch("gmail_service.smtplib.SMTP_SSL")
    @patch("gmail_service.smtplib.SMTP")
    def test_returns_false_when_authentication_fails(self, smtp_cls, smtp_ssl_cls):
        smtp_ssl_cls.side_effect = Exception("ssl not available")
        smtp_cls.return_value = DummyServer(auth_error=True)

        self.assertFalse(test_smtp_credentials("user@gmail.com", "abcdefghijkl"))


if __name__ == "__main__":
    unittest.main()
