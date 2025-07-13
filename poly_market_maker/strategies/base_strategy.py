import logging
from typing import Tuple

from orderbook import OrderBook
from order import Order


class BaseStrategy:
    """Base market making strategy"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.place_orders = None
        self.cancel_orders = None

    def get_orders(
        self, orderbook: OrderBook, token_prices
    ) -> Tuple[list[Order], list[Order]]:
        pass
