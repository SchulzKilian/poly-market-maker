import requests
import time
import sys
import json
import os
import logging
import os
os.environ['SSL_CERT_FILE'] = '/home/kilianschulz/Applications/anaconda3/ssl/cacert.pem'

from datetime import datetime, timedelta, timezone
from markets import get_polymarket_sports_markets
from scoring import get_token_score
from clob_api import ClobApi
import traceback
from metrics import active_markets_gauge
# --- Configuration ---

# How often to perform actions (in seconds)
MARKET_UPDATE_INTERVAL = 60 * 60 # Update the list of markets every 10 minutes
SCORING_INTERVAL = 60 * 60     # Rescore all markets every 5 minutes
CLEANUP_INTERVAL = 60 * 60 * 2    # Clean up inactive markets every hour
LOOP_SLEEP_INTERVAL = 60 * 60        # Sleep time for the main loop to prevent high CPU usage

# The file to write the top market condition_ids to
MARKET_FILE = "markets_to_trade.json"
# The number of top markets to select for market making
TOP_N_MARKETS = 5

# Scoring weights: Adjust these to prioritize what you find most important
# For example, if you are very risk-averse, increase the VOLATILITY_WEIGHT.
# If you need high volume, increase the VOLUME_WEIGHT.
WEIGHTS = {
    "SPREAD_SCORE": 0.35,
    "DEPTH_SCORE": 0.25,
    "VOLUME_SCORE": 0.25,
    "VOLATILITY_SCORE": -0.15,
}

logger = logging.getLogger(__name__)

# --- Main Application Loop ---
def main_loop():
    markets = {}
    last_market_update = 0
    last_scoring_update = 0
    last_cleanup = 0
    clobapi = ClobApi(private_key=os.getenv("PRIVATE_KEY", None))

    logger.info("🚀 Starting market maker scoring engine...")

    while True:
        current_time = time.time()

        # --- Task 1: Update the list of markets ---
        if current_time - last_market_update > MARKET_UPDATE_INTERVAL:
            logger.info("\n---")
            logger.info(f"[{datetime.now()}] 🔄 Updating market list...")
            try:
                # This call adds new markets and updates data for existing ones
                new_markets = get_polymarket_sports_markets()
                print(f"New markets fetched: {len(new_markets)}")

                markets.update(new_markets)
                active_markets_gauge.set(len(markets))
                logger.info(f"Found {len(new_markets)} new/updated markets. Total markets being tracked: {len(markets)}")
                last_market_update = current_time
            except Exception as e:
                logger.error(f"❌ Failed to update markets: {e}")
            logger.info("---\n")


        # --- Task 2: Update the scoring for each token ---
        if current_time - last_scoring_update > SCORING_INTERVAL:
            logger.info("\n---")
            all_tokens = []

            for condition_id, market_obj in markets.items():

                if condition_id == "":
                    continue

                for token_id in json.loads(market_obj.get('clobTokenIds', [])):
                    # print(token_id)
                    token = {}
                    token['token_id'] = token_id
                    # Add market slug and condition_id to each token for easier identification
                    token['market'] = market_obj
                    token['condition_id'] = condition_id

                    all_tokens.append(token)
            logger.setLevel(logging.INFO)
            logger.info(f"[{datetime.now()}] 📊 Scoring all {len(all_tokens)} tracked tokens...")

            logger.info(f"Found {len(all_tokens)} tokens to score.")
            if all_tokens:
                # 1. Get raw scores for all tokens
                raw_scores = []


                for ind, token in enumerate(all_tokens):
                    token_id = token.get('token_id')
                    if token_id:
                        spread_score, depth_score, volatility_score = get_token_score(token_id)
                        raw_scores.append({
                            'token': token,
                            'spread': spread_score,
                            'depth': depth_score,
                            'volume': float(token['market'].get('volume', 0)),
                            'liquidity': float(token['market'].get('liquidity', 0)),
                            'volatility': float(volatility_score)

                        })

                # 2. Normalize scores
                if raw_scores:
                    # Find min and max for each score type
                    min_spread = min(s['spread'] for s in raw_scores)
                    max_spread = max(s['spread'] for s in raw_scores)
                    min_depth = min(s['depth'] for s in raw_scores)
                    max_depth = max(s['depth'] for s in raw_scores)
                    min_volume = min(s['volume'] for s in raw_scores)
                    max_volume = max(s['volume'] for s in raw_scores)
                    min_volatility = min(s['volatility'] for s in raw_scores)
                    if min_volatility == 0:
                        min_volatility = 1e-10
                    max_volatility = max(s['volatility'] for s in raw_scores)

                    for score_data in raw_scores:
                        # Normalize spread (lower is better)
                        if max_spread > min_spread:
                            norm_spread = 1 - ((score_data['spread'] - min_spread) / (max_spread - min_spread))
                        else:
                            norm_spread = 1.0

                        # Normalize depth (higher is better)
                        if max_depth > min_depth:
                            norm_depth = (score_data['depth'] - min_depth) / (max_depth - min_depth)
                        else:
                            norm_depth = 1.0

                        # Normalize volume (higher is better)
                        if max_volume > min_volume:
                            norm_volume = (score_data['volume'] - min_volume) / (max_volume - min_volume)
                        else:
                            norm_volume = 1.0

                        # Normalize volatility (lower is better)
                        if max_volatility > min_volatility:
                            norm_volatility = 1 - ((score_data['volatility'] - min_volatility) / (max_volatility - min_volatility))
                        else:
                            norm_volatility = 1.0
                        
                        # 3. Calculate final weighted score
                        final_score = 100 * (
                            (norm_spread * WEIGHTS["SPREAD_SCORE"]) +
                            (norm_depth * WEIGHTS["DEPTH_SCORE"]) +
                            (norm_volume * WEIGHTS["VOLUME_SCORE"]) + 
                            (norm_volatility * WEIGHTS["VOLATILITY_SCORE"])
                        )
                        score_data['token']['score'] = final_score
                        print(f"The final score for token {score_data['token']['token_id']} is {final_score:.2f}")

                else:
                    logger.warning("⚠️ No tokens found to score. Skipping scoring step.")
                    continue

            else:
                logger.warning("⚠️ No markets found to score. Skipping scoring step.")
                continue
            # Sort and get the top N tokens
            sorted_tokens = sorted(all_tokens, key=lambda t: t.get('score', 0), reverse=True)
            top_tokens = sorted_tokens[:TOP_N_MARKETS]
            
            logger.info(f"\n🏆 Top {TOP_N_MARKETS} Tokens for Market Making:")
            for token in top_tokens:
                logger.info(f"  - {token.get('score', 0):.2f} | {token.get('market_slug')} | CID: {token.get('condition_id')}")

            # Extract the condition_ids from the top tokens
            top_condition_ids = list(set([token['condition_id'] for token in top_tokens]))

            # Write the condition_ids to the file atomically
            temp_file_path = f"{MARKET_FILE}.tmp"
            with open(temp_file_path, 'w') as f:
                json.dump(top_condition_ids, f)
            os.rename(temp_file_path, MARKET_FILE)
            
            logger.info(f"\n✅ Wrote {len(top_condition_ids)} market(s) to {MARKET_FILE}")
            last_scoring_update = current_time
            logger.info("---\n")


        # --- Task 3: Delete inactive/closed markets ---
        if current_time - last_cleanup > CLEANUP_INTERVAL:
            logger.info("\n---")

            logger.info(f"[{datetime.now()}] 🧹 Cleaning up inactive markets...")
            initial_count = len(markets)
            keys_to_delete = clobapi.get_to_delete(markets.keys())
            
            if keys_to_delete:
                for cid in keys_to_delete:
                    del markets[cid]
                logger.info(f"Removed {len(keys_to_delete)} inactive/closed markets.")
            else:
                logger.info("No inactive markets to remove.")
            
            logger.info(f"Markets being tracked: {len(markets)}")
            last_cleanup = current_time
            logger.info("---\n")
        
        # Prevent the loop from running too fast
        time.sleep(LOOP_SLEEP_INTERVAL)
        logger.info(f"[{datetime.now()}] 💤 Sleeping for {LOOP_SLEEP_INTERVAL} seconds...\n")



if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("\n🛑 Stopping market maker scoring engine...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ An error occurred: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


    