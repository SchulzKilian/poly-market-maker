import multiprocessing
import sys
import copy
import time
from strategy import Strategy
from prometheus_client import start_http_server
import json
import os
import logging
import types
from enum import Enum
from app import App
from dotenv import load_dotenv
from utils import setup_logging
from clob_api import ClobApi
from market import Market, Token

# 1. Load environment variables from a .env file into the OS environment.
# This should be done at the very top of the script.
load_dotenv()

# 3. Define all default configuration values in a single dictionary.

DEFAULT_CONFIG = {
    "private_key": None,
    "rpc_url": None,
    "clob_api_url": None,
    "sync_interval": 30,
    "min_size": 5,
    "min_tick": 0.01,
    "refresh_frequency": 5,
    "gas_strategy": "web3",
    "gas_station_url": None,
    "fixed_gas_price": None,
    "metrics_server_port": 9008,
    "strategy": Strategy.AMM,
    "strategy_config": f"../config/amm.json",
}

# --- Main Application Logic ---

MARKET_FILE = "markets_to_trade.json"
CHECK_INTERVAL = 10  # seconds

def run_market_maker(config_obj, condition_id: str):
    """
    Runs the market maker for a single condition_id.
    This function is the target for the multiprocessing.Process.

    FIX: This function now accepts a 'config_obj' which is the already-parsed
    configuration. It does NOT call get_args() again. It passes the config
    directly to the App.
    """
    # A new process needs to have logging configured again.
    setup_logging()
    from prometheus_client import start_http_server
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)
    logger.info(f"Starting market maker bot for condition_id: {condition_id}")
    try:
        from prometheus_client import start_http_server
        assert config_obj.metrics_server_port is not None, "Metrics server port must be set in the config object."
        logger.info(f"Attempting to start metrics server on url http://localhost:{config_obj.metrics_server_port} for condition id {condition_id}...")
        start_http_server(config_obj.metrics_server_port)
        time.sleep(5)
        logger.info(f"Metrics server started successfully for {condition_id}.")
    except Exception as e:

        print("Failed to start metrics server:", e)
        logger.error(f"CRITICAL: Failed to start metrics server for {condition_id} on port {config_obj.metrics_server_port}", exc_info=True)

    try:
        # The config_obj is passed directly to the App. No re-parsing!
        app = App(config_obj, condition_id)
        app.main()
    except KeyboardInterrupt:
        logger.info(f"Process for {condition_id} received KeyboardInterrupt.")
    except Exception:
        logger.exception(f"An error occurred in the market maker bot for {condition_id}")

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)

    # 4. Create the base configuration object from defaults and environment variables.
    config_dict = DEFAULT_CONFIG.copy()
    for key in config_dict:
        env_value = os.environ.get(key.upper())
        if env_value is not None:
            config_dict[key] = env_value
            
    # Convert the final dictionary into a SimpleNamespace object for dot notation access (e.g., config.private_key)
    base_config = types.SimpleNamespace(**config_dict)

    # Create a single ClobApi instance for pre-flight checks
    try:
        clob_api_for_checks = ClobApi(host=base_config.clob_api_url, chain_id=137, private_key=base_config.private_key)
        collateral_address = clob_api_for_checks.get_collateral_address()
    except Exception as e:
        logger.error(f"Failed to initialize ClobApi for pre-flight checks. Cannot start bots. Error: {e}")
        sys.exit(1)


    running_bots = {}  # {condition_id: Process}

    try:
        logger.info("🚀 Starting Bot Runner...")
        while True:
            target_condition_ids = []
            if os.path.exists(MARKET_FILE):
                try:
                    with open(MARKET_FILE, 'r') as f:
                        target_condition_ids = json.load(f)
                except json.JSONDecodeError:
                    logger.warning(f"Could not decode JSON from {MARKET_FILE}. Skipping check.")
                    time.sleep(CHECK_INTERVAL)
                    continue
            else:
                # For testing, if the file doesn't exist, let's create it with dummy data.
                logger.info(f"{MARKET_FILE} not found. Creating a dummy file for demonstration.")
                with open(MARKET_FILE, 'w') as f:
                    json.dump(["market_a", "market_b", "market_c"], f)
                continue # Loop again to read the new file

            target_set = set(target_condition_ids)
            running_set = set(running_bots.keys())

            # --- Stop bots that are no longer in the target list ---
            bots_to_stop = running_set - target_set
            for cid in bots_to_stop:
                logger.info(f"Stopping bot for {cid}...")
                process = running_bots.pop(cid)
                process.terminate()
                process.join(timeout=10)
                if process.is_alive():
                    logger.warning(f"Process for {cid} did not terminate gracefully. Killing.")
                    process.kill()
                logger.info(f"Bot for {cid} stopped.")

            # --- Start new bots ---
            bots_to_start = target_set - running_set
            for cid in bots_to_start:
                # --- PRE-FLIGHT CHECK ---
                try:
                    logger.info(f"Performing pre-flight check for market {cid}...")
                    market = Market(cid, collateral_address)
                    token_a_id = market.token_id(Token.A)
                    price = clob_api_for_checks.get_price(token_a_id)

                    if price is None or price <= 0.001 or price >= 0.999:
                        logger.warning(f"SKIPPING bot for market {cid} due to illiquidity or invalid price ({price}).")
                        continue # Skip starting this bot
                    
                    logger.info(f"Pre-flight check PASSED for market {cid} with price {price}.")

                except Exception as e:
                    logger.error(f"Pre-flight check FAILED for market {cid}. Skipping bot. Error: {e}")
                    continue
                # --- END PRE-FLIGHT CHECK ---

                # Create a deep copy of the config for the new process
                process_config = copy.deepcopy(base_config)

                # Assign a unique metrics port
                if cid in target_condition_ids:
                    port_offset = target_condition_ids.index(cid)
                    base_port = int(process_config.metrics_server_port)
                    process_config.metrics_server_port = base_port + port_offset
                
                logger.info(f"Starting bot for {cid} on metrics port {process_config.metrics_server_port}")

                p = multiprocessing.Process(
                    target=run_market_maker,
                    args=(process_config, cid) # Pass the final config object
                )
                p.start()
                running_bots[cid] = p

            logger.debug(f"Active bots: {len(running_bots)}. Target markets: {len(target_set)}.")
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.info("\n🛑 Shutting down Bot Runner and all active bots...")
        for cid, process in running_bots.items():
            logger.info(f"Stopping bot for {cid}...")
            process.terminate()
            process.join(timeout=10)
        logger.info("All bots have been shut down.")
    except Exception:
        logger.exception("An unexpected error occurred in the Bot Runner main loop.")
