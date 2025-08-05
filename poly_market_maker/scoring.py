import logging
import numpy as np
from datetime import datetime, timedelta
from clob_api import ClobApi



def get_token_score(token_id: int):
    """
    Scores a token based on its spread, depth, and volume.
    Returns a score from 0 to 100.
    """
    logger = logging.getLogger(__name__)
    logger.level = logging.INFO
    clob_api = ClobApi()

    # 1. Get data from the order book endpoint
    order_book = clob_api.get_book(token_id)
    
    # If essential data is missing, we can't score it.
    if not order_book or not order_book.get('bids') or not order_book.get('asks') or len(order_book['bids']) == 0 or len(order_book['asks']) == 0:
        logger.debug(f"Could not score token {token_id} due to empty or invalid order book.")
        if not order_book:
            explanation = 0
        elif not order_book.get('bids'):
            explanation = 1
        elif not order_book.get('asks'):
            explanation = 2
        # logger.warning(f"The exact conditions were {order_book}")
        return explanation,0, float('inf'), 0

    # 2. Calculate Spread from Order Book
    best_bid = float(order_book['bids'][0]['price'])
    best_ask = float(order_book['asks'][0]['price'])
    spread_score = best_ask - best_bid
    price = (best_bid + best_ask) / 2


    # 3. Calculate Depth from Order Book
    top_bids_size = sum(float(b['size']) for b in order_book['bids'][:5])
    top_asks_size = sum(float(a['size']) for a in order_book['asks'][:5])
    depth_score = top_bids_size + top_asks_size


    price_history = clob_api.get_price_history(token_id)
    logger.debug(f"Fetched Price history {price_history}")
    
    volatility_score = float('inf')
    if price_history:
        prices = [item['p'] for item in price_history]
        prices_array = np.array(prices)
        log_returns = np.log(prices_array[1:] / prices_array[:-1])
        volatility_score = np.std(log_returns)




    logger.debug(f"Scored token {token_id}:  (Spread={spread_score:.2f}, Depth={depth_score:.2f},  Volatility={volatility_score:.2f})")

    return  spread_score, depth_score, volatility_score, price


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    token_id_to_test = 115110300459694805744035858549696192321864942474801224215254976811205215560373
    score = get_token_score(token_id_to_test)
    print(f"The score for token {token_id_to_test} is {score}")






