from unittest import TestCase

from price_feed import PriceFeedClob
from token_class import Token
from market import Market
from clob_api import ClobApi


class MockClobApi(ClobApi):
    def __init__(self):
        pass

    def get_price(self, token: Token):
        return 0.4


class TestPriceFeed(TestCase):
    def test_price_feed(self):
        market = Market("0x045A", "0x0456")
        price_feed = PriceFeedClob(market, MockClobApi())

        self.assertEqual(price_feed.get_price(Token.A), 0.4)
