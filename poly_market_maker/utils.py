import logging
import math
import os
import random
import yaml
from logging import config
from web3 import Web3
from web3.middleware import (
    ExtraDataToPOAMiddleware,
)
from web3.middleware.signing import SignAndSendRawMiddlewareBuilder # New import for signing middleware
from web3.gas_strategies.time_based import fast_gas_price_strategy
from constants import MAX_DECIMALS


def setup_logging(
    log_path="logging.yaml",
    log_level=logging.DEBUG,
    env_key="LOGGING_CONFIG_FILE",
):
    """
    :param default_path:
    :param default_level:
    :param env_key:
    :return:
    """
    log_value = os.getenv(env_key, None)
    if log_value:
        log_path = log_value
    if os.path.exists(log_path):
        with open(log_path) as fh:
            config.dictConfig(yaml.safe_load(fh.read()))
        logging.getLogger(__name__).info("Logging configured with config file!")
    else:
        logging.basicConfig(
            format="%(asctime)-15s %(levelname)-4s %(threadName)s %(message)s",
            level=log_level,
        )
        logging.getLogger(__name__).info("Logging configured with default attributes!")
    # Suppress requests and web3 verbose logs
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("web3").setLevel(logging.WARNING)


def setup_web3(rpc_url, private_key):
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60}))

    # Middleware to sign transactions from a private key
    # ExtraDataToPOAMiddleware should be injected at layer 0 as it modifies extraData field
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    # Updated: Use SignAndSendRawMiddlewareBuilder to construct the signing middleware
    w3.middleware_onion.add(SignAndSendRawMiddlewareBuilder.build(private_key))
    
    w3.eth.default_account = w3.eth.account.from_key(private_key).address

    # Gas Middleware
    w3.eth.set_gas_price_strategy(fast_gas_price_strategy)

    # Caching middleware - these have been removed in web3.py v7.0.0+
    # w3.middleware_onion.add(time_based_cache_middleware)
    # w3.middleware_onion.add(latest_block_based_cache_middleware)
    # w3.middleware_onion.add(simple_cache_middleware)

    return w3


def math_round_down(f: float, sig_digits: int) -> float:
    str_f = str(f).split(".")
    if len(str_f) > 1 and len(str_f[1]) == sig_digits:
        # don't round values which are already the number of sig_digits
        return f
    return math.floor((f * (10**sig_digits))) / (10**sig_digits)


def math_round_up(f: float, sig_digits: int) -> float:
    str_f = str(f).split(".")
    if len(str_f) > 1 and len(str_f[1]) == sig_digits:
        # don't round values which are already the number of sig_digits
        return f
    return math.ceil((f * (10**sig_digits))) / (10**sig_digits)


def add_randomness(price: float, lower: float, upper: float) -> float:
    return math_round_down(price + random.uniform(lower, upper), MAX_DECIMALS)


def randomize_default_price(price: float) -> float:
    return add_randomness(price, -0.1, 0.1)