import logging
from prometheus_client import start_http_server
import time
import os
# from args import get_args
from price_feed import PriceFeedClob
from gas import GasStation, GasStrategy
from utils import setup_logging, setup_web3
from order import Order, Side
from market import Market
from token_class import Token, Collateral
from clob_api import ClobApi
from lifecycle import Lifecycle
from orderbook import OrderBookManager
from contracts import Contracts
from metrics import keeper_balance_amount
from strategy import StrategyManager
import types

class App:
    """Market maker keeper on Polymarket CLOB"""

    def __init__(self, config, condition_id: str = None):
        self.logger = logging.getLogger(__name__)

        self.sync_interval = 5

        # self.min_tick = args.min_tick
        # self.min_size = args.min_size
        args = config
        # server to expose the metrics.
        self.metrics_server_port = args.metrics_server_port
        start_http_server(self.metrics_server_port)

        self.web3 = setup_web3(args.rpc_url, args.private_key)
        self.address = self.web3.eth.account.from_key(args.private_key).address

        self.clob_api = ClobApi(
            host=args.clob_api_url,
            chain_id=self.web3.eth.chain_id,
            private_key=args.private_key,
        )

        self.gas_station = GasStation(
            strat=GasStrategy(args.gas_strategy),
            w3=self.web3,
            url=args.gas_station_url,
            fixed=args.fixed_gas_price,
        )
        self.contracts = Contracts(self.web3, self.gas_station)

        self.market = Market(
            condition_id,
            self.clob_api.get_collateral_address(),
        )

        self.price_feed = PriceFeedClob(self.market, self.clob_api)

        self.order_book_manager = OrderBookManager(
            args.refresh_frequency, max_workers=1
        )
        self.order_book_manager.get_orders_with(self.get_orders)
        self.order_book_manager.get_balances_with(self.get_balances)
        self.order_book_manager.cancel_orders_with(
            lambda order: self.clob_api.cancel_order(order.id)
        )
        self.order_book_manager.place_orders_with(self.place_order)
        self.order_book_manager.cancel_all_orders_with(
            lambda _: self.clob_api.cancel_all_orders()
        )
        self.order_book_manager.start()

        self.strategy_manager = StrategyManager(
            args.strategy,
            args.strategy_config,
            self.price_feed,
            self.order_book_manager,
        )

    """
    main
    """

    def main(self):
        self.logger.debug(self.sync_interval)
        with Lifecycle() as lifecycle:
            lifecycle.on_startup(self.startup)
            lifecycle.every(self.sync_interval, self.synchronize)  # Sync every 5s
            lifecycle.on_shutdown(self.shutdown)

    """
    lifecycle
    """

    def startup(self):
        self.logger.info("Running startup callback...")
        self.approve()
        time.sleep(5)  # 5 second initial delay so that bg threads fetch the orderbook
        self.logger.info("Startup complete!")

    def synchronize(self):
        """
        Synchronize the orderbook by cancelling orders out of bands and placing new orders if necessary
        """
        self.logger.debug("Synchronizing orderbook...")
        self.strategy_manager.synchronize()
        self.logger.debug("Synchronized orderbook!")

    def shutdown(self):
        """
        Shut down the keeper
        """
        self.logger.info("Keeper shutting down...")
        self.order_book_manager.cancel_all_orders()
        self.logger.info("Keeper is shut down!")

    """
    handlers
    """

    def get_balances(self) -> dict:
        """
        Fetch the onchain balances of collateral and conditional tokens for the keeper
        """
        self.logger.debug(f"Getting balances for address: {self.address}")

        collateral_balance = self.contracts.token_balance_of(
            self.clob_api.get_collateral_address(), self.address
        )
        token_A_balance = self.contracts.token_balance_of(
            self.clob_api.get_conditional_address(),
            self.address,
            self.market.token_id(Token.A),
        )
        token_B_balance = self.contracts.token_balance_of(
            self.clob_api.get_conditional_address(),
            self.address,
            self.market.token_id(Token.B),
        )
        gas_balance = self.contracts.gas_balance(self.address)

        keeper_balance_amount.labels(
            accountaddress=self.address,
            assetaddress=self.clob_api.get_collateral_address(),
            tokenid="-1",
        ).set(collateral_balance)
        keeper_balance_amount.labels(
            accountaddress=self.address,
            assetaddress=self.clob_api.get_conditional_address(),
            tokenid=self.market.token_id(Token.A),
        ).set(token_A_balance)
        keeper_balance_amount.labels(
            accountaddress=self.address,
            assetaddress=self.clob_api.get_conditional_address(),
            tokenid=self.market.token_id(Token.B),
        ).set(token_B_balance)
        keeper_balance_amount.labels(
            accountaddress=self.address,
            assetaddress="0x0",
            tokenid="-1",
        ).set(gas_balance)

        return {
            Collateral: collateral_balance,
            Token.A: token_A_balance,
            Token.B: token_B_balance,
        }

    def get_orders(self) -> list[Order]:
        orders = self.clob_api.get_orders(self.market.condition_id)
        return [
            Order(
                size=order_dict["size"],
                price=order_dict["price"],
                side=Side(order_dict["side"]),
                token=self.market.token(order_dict["token_id"]),
                id=order_dict["id"],
            )
            for order_dict in orders
        ]

    def place_order(self, new_order: Order) -> Order:
        order_id = self.clob_api.place_order(
            price=new_order.price,
            size=new_order.size,
            side=new_order.side.value,
            token_id=self.market.token_id(new_order.token),
        )
        return Order(
            price=new_order.price,
            size=new_order.size,
            side=new_order.side,
            id=order_id,
            token=new_order.token,
        )

    def approve(self):
        """
        Approve the keeper on the collateral and conditional tokens
        """
        collateral = self.clob_api.get_collateral_address()
        conditional = self.clob_api.get_conditional_address()
        exchange = self.clob_api.get_exchange()

        self.contracts.max_approve_erc20(collateral, self.address, exchange)
        self.contracts.max_approve_erc1155(conditional, self.address, exchange)
