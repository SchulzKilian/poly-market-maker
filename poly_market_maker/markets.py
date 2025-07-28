import pickle  
import requests
import logging
from datetime import datetime, timedelta, timezone


logger = logging.getLogger(__name__)

def get_polymarket_sports_markets():






    # url = f"https://clob.polymarket.com/markets?next_cursor={next_cursor}" 
    url = f"https://gamma-api.polymarket.com/markets?limit=40&active=true&closed=false&order=liquidity"

    response = requests.get(url)
    data = response.json()

    response.raise_for_status()







    # Format each market
    formatted_markets = {}

    for market in data:
        if type(market)!= str:
            if market.get('active') and not market.get('closed') and market.get('enableOrderBook') and is_end_date_valid(market.get('end_date')):
                condition_id = market.get('id') 
                formatted_market = {
                    'question': market.get('question'),
                    'description': market.get('description'),
                    'end_date': market.get('end_date_iso'),
                    'market_slug': market.get('market_slug'),
                    'price': tuple(
                        token.get('price') 
                        for token in market.get('tokens', [])
                    )
                }
                
                formatted_markets[condition_id] = market
                if condition_id == '':
                    import sys
                    logger.error(f"Skipping market with empty condition_id: {market}")
                    sys.exit(0)
            else:
                print(f"Skipping market {market.get('id')} due to conditions: active={market.get('active')}, closed={market.get('closed')}, accepting_orders={market.get('accepting_orders')}, condition_id={market.get('condition_id')}, end_date_iso={market.get('end_date_iso')}")
                continue
        else:
            continue


    print(len(formatted_markets), "markets fetched")
    return formatted_markets

def is_end_date_valid(end_date_iso: str | None) -> bool:
    """
    Checks if a market's end date is either None or at least 7 days away.
    """
    # If there is no end date, it's valid according to the rule.
    if end_date_iso is None:
        return True

    try:
        # Parse the ISO format string into a timezone-aware datetime object.
        # The 'Z' at the end means UTC.
        end_date = datetime.fromisoformat(end_date_iso.replace('Z', '+00:00'))

        # Get the current time in UTC to ensure a correct comparison.
        now_utc = datetime.now(timezone.utc)

        # Return True if the end date is at least 7 days in the future.
        return end_date - now_utc >= timedelta(days=7)

    except (ValueError, TypeError):
        # Handle cases where the date format is invalid or not a string.
        return False

if __name__ == "__main__":
    markets = get_polymarket_sports_markets()
    
    counter = 0
    for keys in markets.keys():
        market = markets[keys]
        # logger.info(market)
        
        assert market["active"] and not market["closed"], "Market is not active or closed"
        print(market["question"])
        try:
            print(market["volume1wk"])
        except KeyError:
            counter += 1
    print(f"Total markets without volume1wk: {counter}")
    logger.info(f"Total markets fetched: {len(markets)}")