import pickle  
import requests
from datetime import datetime, timedelta, timezone
GET_NEW_CURSOR = True


def get_polymarket_sports_markets():
    global GET_NEW_CURSOR
    try:
        with open('next_cursor.pkl', 'rb') as file:
            # Deserialize the string from the file
            next_cursor = pickle.load(file)
    except:
        next_cursor = ""




    all_markets = []

    while True:
        url = f"https://clob.polymarket.com/markets?next_cursor={next_cursor}" 

        response = requests.get(url)
        data = response.json()

        if response.status_code != 200 or 'data' not in data:
            print("Error fetching markets")
            break


        if GET_NEW_CURSOR:
            for item in data["data"]:
                if item.get('active') and not item.get('closed'):
                    GET_NEW_CURSOR = False
                    with open('next_cursor.pkl', 'wb') as file:
                        pickle.dump(next_cursor, file)
                    break

        next_cursor = data.get('next_cursor', '')


        

        all_markets.extend(data['data'])
        if next_cursor == '' or next_cursor == 'LTE=':
            break
        
        





    # Format each market
    formatted_markets = {}
    for market in all_markets:
        if type(market)!= str:
            if market.get('active') and not market.get('closed') and market.get('accepting_orders') and market.get('condition_id') and is_end_date_valid(market.get('end_date_iso')):
                condition_id = market.get('condition_id') 
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
                    print(f"Skipping market with empty condition_id: {market}")
                    sys.exit(0)
            else:
                continue
        else:
            continue


            

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
    for keys in markets.keys():
        market = markets[keys]
        print(market)
        assert market["active"] and not market["closed"], "Market is not active or closed"
    print(f"Total markets fetched: {len(markets)}")