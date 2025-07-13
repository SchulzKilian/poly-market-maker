import logging
import sys
import time
import requests
from py_clob_client.client import ClobClient, ApiCreds, OrderArgs
from py_clob_client.exceptions import PolyApiException
import pickle

from constants import OK
from metrics import clob_requests_latency

DEFAULT_PRICE = 0.5


class ClobApi:
    def __init__(self, host= "https://clob.polymarket.com", chain_id= 137, private_key= None):
        self.logger = logging.getLogger(self.__class__.__name__)
        if private_key:
            self.client = self._init_client_L1(
                host=host,
                chain_id=chain_id,
                private_key=private_key,
            )

            try:
                api_creds = self.client.derive_api_key()
                self.logger.debug(f"Api key found: {api_creds.api_key}")
            except PolyApiException:
                self.logger.debug("Api key not found. Creating a new one...")
                api_creds = self.client.create_api_key()
                self.logger.debug(f"Api key created: {api_creds.api_key}.")

            self.client = self._init_client_L2(
                host=host,
                chain_id=chain_id,
                private_key=private_key,
                creds=api_creds,
            )
        else:
            self.client = None

    def get_address(self):
        return self.client.get_address()

    def get_collateral_address(self):
        return self.client.get_collateral_address()

    def get_conditional_address(self):
        return self.client.get_conditional_address()

    def get_exchange(self, neg_risk = False):
        return self.client.get_exchange_address(neg_risk)

    def get_price(self, token_id: int, side: str = None) -> float:
        """
        Get the current price on the orderbook
        """
        self.logger.debug(f"Fetching price for token {token_id} with side {side}...")
        start_time = time.time()
        try:
            if side:
                resp = self.client.get_price(token_id, side)
                price = resp.get("price")
            else:
                resp = self.client.get_midpoint(token_id)
                price = resp.get("mid")

            clob_requests_latency.labels(method="get_price", status="ok").observe(
                (time.time() - start_time)
            )
            if price is not None:
                return float(price)
        except Exception as e:
            self.logger.error(f"Error fetching current price from the CLOB API: {e}")
            clob_requests_latency.labels(method="get_price", status="error").observe(
                (time.time() - start_time)
            )
        # TODO Return None and handle it in the caller
        return None

    def get_book(self, token_id: int):
        """
        Get the order book for a given token
        """
        self.logger.debug(f"Fetching order book for token {token_id}...")
        start_time = time.time()
        try:
            api_url = "https://clob.polymarket.com/book"
            parameters = {"token_id": token_id}
            response = requests.get(api_url, params=parameters)
            logging.debug(f"Response: {response.text}")
            clob_requests_latency.labels(method="get_orderbook", status="ok").observe(
                (time.time() - start_time)
            )
            return response.json()
        except Exception as e:
            self.logger.error(f"Error fetching order book from the CLOB API: {e}")
            clob_requests_latency.labels(method="get_orderbook", status="error").observe(
                (time.time() - start_time)
            )
        return None

    def get_price_history(self, token_id: int):
        """
        Get the price history for a given token
        """
        self.logger.debug(f"Fetching price history for token {token_id}...")
        start_time = time.time()
        try:
            api_url = "https://clob.polymarket.com/prices-history"
            parameters = {"market": token_id, "interval": "max"}# "startTs": start_ts, "endTs": end_ts}
            response = requests.get(api_url, params=parameters)

            clob_requests_latency.labels(method="get_price_history", status="ok").observe(
                (time.time() - start_time)
            )
            return response.json().get("history", [])
        except Exception as e:
            self.logger.error(f"Error fetching price history from the CLOB API: {e}")
            clob_requests_latency.labels(method="get_price_history", status="error").observe(
                (time.time() - start_time)
            )
        return None

    def get_token_trades(self, token_id: int):
        """
        Get recent trades for a given token
        """
        self.logger.debug(f"Fetching trades for token {token_id}...")
        start_time = time.time()
        try:
            # Assuming the client has a get_trades method that can filter by token_id
            resp = self.client.get_trades(FilterParams(token_id=token_id))
            clob_requests_latency.labels(method="get_trades", status="ok").observe(
                (time.time() - start_time)
            )
            return resp
        except Exception as e:
            self.logger.error(f"Error fetching trades from the CLOB API: {e}")
            clob_requests_latency.labels(method="get_trades", status="error").observe(
                (time.time() - start_time)
            )
        return None


 

    def get_orders(self, condition_id: str):
        """
        Get open keeper orders on the orderbook
        """
        self.logger.debug("Fetching open keeper orders from the API...")
        start_time = time.time()
        try:
            resp = self.client.get_orders(FilterParams(market=condition_id))
            clob_requests_latency.labels(method="get_orders", status="ok").observe(
                (time.time() - start_time)
            )

            return [self._get_order(order) for order in resp]
        except Exception as e:
            self.logger.error(
                f"Error fetching keeper open orders from the CLOB API: {e}"
            )
            clob_requests_latency.labels(method="get_orders", status="error").observe(
                (time.time() - start_time)
            )
        return []

    def place_order(self, price: float, size: float, side: str, token_id: int) -> str:
        """
        Places a new order
        """
        self.logger.debug(
            f"Attempting to place a {side} order for token {token_id} of size {size} at price {price}"
        )
        start_time = time.time()
        try:
            resp = self.client.create_and_post_order(
                OrderArgs(price=price, size=size, side=side, token_id=token_id)
            )
            clob_requests_latency.labels(
                method="create_and_post_order", status="ok"
            ).observe((time.time() - start_time))
            order_id = None
            if resp and resp.get("success") and resp.get("orderID"):
                order_id = resp.get("orderID")
                self.logger.debug(
                    f"Successfully placed {side} order for token {token_id}. Order ID: {order_id}"
                )
                return order_id

            err_msg = resp.get("errorMsg")
            self.logger.error(
                f"Could not place new order! CLOB returned error: {err_msg}"
            )
        except Exception as e:
            self.logger.error(f"Request exception: failed placing new order: {e}")
            clob_requests_latency.labels(
                method="create_and_post_order", status="error"
            ).observe((time.time() - start_time))
        return None

    def cancel_order(self, order_id) -> bool:
        self.logger.debug(f"Attempting to cancel order {order_id}...")
        if order_id is None:
            self.logger.debug("Invalid order_id, skipping cancellation.")
            return True

        start_time = time.time()
        try:
            resp = self.client.cancel(order_id)
            clob_requests_latency.labels(method="cancel", status="ok").observe(
                (time.time() - start_time)
            )
            if resp == OK:
                self.logger.debug(f"Successfully cancelled order {order_id}.")
                return True
            else:
                self.logger.error(f"Failed to cancel order {order_id}.")
                return False
        except Exception as e:
            self.logger.error(f"Error cancelling order: {order_id}: {e}")
            clob_requests_latency.labels(method="cancel", status="error").observe(
                (time.time() - start_time)
            )
        return False

    def cancel_all_orders(self) -> bool:
        self.logger.debug("Attempting to cancel all open keeper orders...")
        start_time = time.time()
        try:
            resp = self.client.cancel_all()
            clob_requests_latency.labels(method="cancel_all", status="ok").observe(
                (time.time() - start_time)
            )
            if resp == OK:
                self.logger.debug("Successfully cancelled all orders.")
                return True
            else:
                self.logger.error("Failed to cancel all orders.")
                return False
        except Exception as e:
            self.logger.error(f"Error cancelling all orders: {e}")
            clob_requests_latency.labels(method="cancel_all", status="error").observe(
                (time.time() - start_time)
            )
        return False
    
    def get_volume_and_liquidity(self, condition_ids: list[str]):
        if not condition_ids:
            return {}, {}

        import urllib.parse
        gamma_url = "https://gamma-api.polymarket.com/markets"
        volume_data = {}
        liquidity_data = {}

        all_chunks = []
        current_chunk = []
        for cid in condition_ids:
            test_chunk = current_chunk + [cid]
            query_string = urllib.parse.urlencode({"condition_ids": test_chunk}, doseq=True)

            if len(gamma_url) + 1 + len(query_string) > 2000:
                if current_chunk:
                    all_chunks.append(current_chunk)
                current_chunk = [cid]
            else:
                current_chunk.append(cid)

        if current_chunk:
            all_chunks.append(current_chunk)

        for chunk in all_chunks:
            parameters = {
                "condition_ids": chunk
            }

            try:
                response = requests.get(gamma_url, params=parameters)
                if response.status_code != 200:
                    self.logger.error(f"Error fetching volume from Gamma API {response.status_code} with {response.text}   ")
                    continue

                data = response.json()

                for market in data:
                    condition_id = market.get("condition_id")
                    if condition_id in chunk:
                        volume_data[condition_id] = market.get("volumeNum", 0)
                        liquidity_data[condition_id] = market.get("liquidityNum", 0)
            except Exception as e:
                self.logger.error(f"Exception fetching volume from Gamma API: {e}")

        if len(volume_data) != len(condition_ids) or len(liquidity_data) != len(condition_ids):
            self.logger.warning(f"Not all condition IDs found, expected {len(condition_ids)}, got {len(volume_data)} for the volume and {len(liquidity_data)} for the liquidity")

        return volume_data, liquidity_data

    def get_to_delete(self, condition_ids: list[str]) -> set:
        """
        Get the volume scores for a list of condition IDs.
        """
        if not condition_ids:
            return set()

        import urllib.parse
        gamma_url = "https://gamma-api.polymarket.com/markets"
        to_delete = set()

        all_chunks = []
        current_chunk = []
        # longest extra param is "accepting_orders=False"
        extra_param_len = len("&accepting_orders=False")

        for cid in condition_ids:
            test_chunk = current_chunk + [cid]
            query_string = urllib.parse.urlencode({"condition_ids": test_chunk}, doseq=True)

            if len(gamma_url) + 1 + len(query_string) + extra_param_len > 2000:
                if current_chunk:
                    all_chunks.append(current_chunk)
                current_chunk = [cid]
            else:
                current_chunk.append(cid)

        if current_chunk:
            all_chunks.append(current_chunk)

        for chunk in all_chunks:
            # Request 1: active=False
            params1 = {"condition_ids": chunk, "active": False}
            try:
                response1 = requests.get(gamma_url, params=params1)
                if response1.status_code == 200:
                    for market in response1.json():
                        if market.get("condition_id"):
                            to_delete.add(market.get("condition_id"))
                else:
                    self.logger.error(f"Error fetching activity from Gamma API (active=False): {response1.status_code} {response1.text}")
            except Exception as e:
                self.logger.error(f"Exception fetching activity from Gamma API (active=False): {e}")

            # Request 2: closed=True
            params2 = {"condition_ids": chunk, "closed": True}
            try:
                response2 = requests.get(gamma_url, params=params2)
                if response2.status_code == 200:
                    for market in response2.json():
                        if market.get("condition_id"):
                            to_delete.add(market.get("condition_id"))
                else:
                    self.logger.error(f"Error fetching activity from Gamma API (closed=True): {response2.status_code} {response2.text}")
            except Exception as e:
                self.logger.error(f"Exception fetching activity from Gamma API (closed=True): {e}")

            # Request 3: accepting_orders=False
            params3 = {"condition_ids": chunk, "accepting_orders": False}
            try:
                response3 = requests.get(gamma_url, params=params3)
                if response3.status_code == 200:
                    for market in response3.json():
                        if market.get("condition_id"):
                            to_delete.add(market.get("condition_id"))
                else:
                    self.logger.error(f"Error fetching activity from Gamma API (accepting_orders=False): {response3.status_code} {response3.text}")
            except Exception as e:
                self.logger.error(f"Exception fetching activity from Gamma API (accepting_orders=False): {e}")

        return to_delete
        
    def _init_client_L1(
        self,
        host,
        chain_id,
        private_key,
    ) -> ClobClient:
        assert private_key is not None, "Private key must be provided for CLOB API client initialization"
        assert host is not None, "Host must be provided for CLOB API client initialization"
        print(f"Connecting to CLOB API at {host} with chain ID {chain_id}...")
        print(f"Using private key: {private_key[:6]}...{private_key[-6:]}")
        clob_client = ClobClient(host, chain_id, private_key)
        try:
            if clob_client.get_ok() == OK:
                self.logger.info("Connected to CLOB API!")
                self.logger.info(
                    "CLOB Keeper address: {}".format(clob_client.get_address())
                )
                return clob_client
        except Exception as e  :
            self.logger.error(f"Error connecting to CLOB API: {e}")
            self.logger.error("Unable to connect to CLOB API L1, shutting down!")
            sys.exit(1)

    def _init_client_L2(
        self, host, chain_id, private_key, creds: ApiCreds
    ) -> ClobClient:
        assert private_key is not None, "Private key must be provided for CLOB API client initialization"
        assert host is not None, "Host must be provided for CLOB API client initialization"
        assert creds is not None, "API credentials must be provided for CLOB API client initialization"
        clob_client = ClobClient(host, chain_id, private_key, creds)
        try:
            if clob_client.get_ok() == OK:
                self.logger.info("Connected to CLOB API!")
                self.logger.info(
                    "CLOB Keeper address: {}".format(clob_client.get_address())
                )
                return clob_client
        except:
            self.logger.error("Unable to connect to CLOB API on L2, shutting down!")
            sys.exit(1)

    def _get_order(self, order_dict: dict) -> dict:
        size = float(order_dict.get("original_size")) - float(
            order_dict.get("size_matched")
        )
        price = float(order_dict.get("price"))
        side = order_dict.get("side")
        order_id = order_dict.get("id")
        token_id = int(order_dict.get("asset_id"))

        return {
            "size": size,
            "price": price,
            "side": side,
            "token_id": token_id,
            "id": order_id,
        }

