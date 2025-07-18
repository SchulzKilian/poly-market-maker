import multiprocessing
import sys
import copy
import time
from strategy import Strategy
import json
import os
import logging
import types
from enum import Enum
from app import App
from dotenv import load_dotenv
from utils import setup_logging

# 1. Load environment variables from a .env file into the OS environment.
# This should be done at the very top of the script.
load_dotenv()

# 3. Define all default configuration values in a single dictionary.

DEFAULT_CONFIG = {
    "private_key": None,
    "rpc_url": None,
    "clob_api_url": None,
    "sync_interval": 30,
    "min_size": 15.0,
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
    It receives a ready-to-use configuration object.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Starting market maker bot for condition_id: {condition_id}")
    try:
        # The config object is passed directly to the App.
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
