import requests
import time
import sys
from datetime import datetime, timedelta, timezone
from markets import get_polymarket_sports_markets
from scoring import get_token_score
import traceback
# --- Configuration ---



# How often to perform actions (in seconds)
MARKET_UPDATE_INTERVAL = 60 * 10  # Update the list of markets every 10 minutes
SCORING_INTERVAL = 60 * 5       # Rescore all markets every 5 minutes
CLEANUP_INTERVAL = 60 * 60      # Clean up inactive markets every hour
LOOP_SLEEP_INTERVAL = 5         # Sleep time for the main loop to prevent high CPU usage

# Scoring weights: Adjust these to prioritize what you find most important
# For example, if you are very risk-averse, increase the VOLATILITY_WEIGHT.
# If you need high volume, increase the VOLUME_WEIGHT.
WEIGHTS = {
    "SPREAD_SCORE": 0.35,
    "DEPTH_SCORE": 0.25,
    "VOLUME_SCORE": 0.25,
    "VOLATILITY_SCORE": 0.15,
}





# --- Main Application Loop ---
def main_loop():
    markets = {}
    last_market_update = 0
    last_scoring_update = 0
    last_cleanup = 0

    print("🚀 Starting market maker scoring engine...")

    while True:
        current_time = time.time()

        # --- Task 1: Update the list of markets ---
        if current_time - last_market_update > MARKET_UPDATE_INTERVAL:
            print("\n---")
            print(f"[{datetime.now()}] 🔄 Updating market list...")
            try:
                # This call adds new markets and updates data for existing ones
                new_markets = get_polymarket_sports_markets()
                markets.update(new_markets)
                print(f"Found {len(new_markets)} new/updated markets. Total markets being tracked: {len(markets)}")
                last_market_update = current_time
            except Exception as e:
                print(f"❌ Failed to update markets: {e}")
            print("---\n")


        # --- Task 2: Update the scoring for each token ---
        if current_time - last_scoring_update > SCORING_INTERVAL:
            print("\n---")
            all_tokens = []
            for market_obj in markets.values():
                for token in market_obj.get('tokens', []):
                    # Add market slug to each token for easier identification
                    token['market_slug'] = market_obj.get('market_slug')
                    all_tokens.append(token)

            print(f"[{datetime.now()}] 📊 Scoring all {len(all_tokens)} tracked tokens...")

            # 1. Get raw scores for all tokens
            raw_scores = []
            for token in all_tokens[0:100]:
                token_id = token.get('token_id')
                if token_id:
                    spread_score, depth_score, volume_score, volatility_score = get_token_score(token_id)
                    raw_scores.append({
                        'token': token,
                        'spread': spread_score,
                        'depth': depth_score,
                        'volume': volume_score,
                        'volatility': volatility_score

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
                    
                    # 3. Calculate final weighted score
                    final_score = 100 * (
                        (norm_spread * WEIGHTS["SPREAD_SCORE"]) +
                        (norm_depth * WEIGHTS["DEPTH_SCORE"]) +
                        (norm_volume * WEIGHTS["VOLUME_SCORE"])
                    )
                    score_data['token']['score'] = final_score

            # Sort and print the top 10 tokens
            sorted_tokens = sorted(all_tokens, key=lambda t: t.get('score', 0), reverse=True)
            
            print("\n🏆 Top 10 Tokens for Market Making (Normalized Scores):")
            for token in sorted_tokens[:10]:
                print(f"  - {token.get('score', 0):.2f} | {token.get('market_slug')} | Token ID: {token.get('token_id')}")

            print("\n- Printing ten random tokens for verification:")
            for token in all_tokens[:10]:
                print(f"  - {token.get('score', 0):.2f} | {token.get('market_slug')} | Token ID: {token.get('token_id')}")
            last_scoring_update = current_time
            print("---\n")


        # --- Task 3: Delete inactive/closed markets ---
        if current_time - last_cleanup > CLEANUP_INTERVAL:
            print("\n---")

            print(f"[{datetime.now()}] 🧹 Cleaning up inactive markets...")
            initial_count = len(markets)
            keys_to_delete = [
                cid for cid, m in markets.items() if not m.get('active') or m.get('closed')
            ]
            
            if keys_to_delete:
                for cid in keys_to_delete:
                    del markets[cid]
                print(f"Removed {len(keys_to_delete)} inactive/closed markets.")
            else:
                print("No inactive markets to remove.")
            
            print(f"Markets being tracked: {len(markets)}")
            last_cleanup = current_time
            print("---\n")
        
        # Prevent the loop from running too fast
        return
        time.sleep(LOOP_SLEEP_INTERVAL)



if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n🛑 Stopping market maker scoring engine...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        print(traceback.format_exc())
        sys.exit(1)


    