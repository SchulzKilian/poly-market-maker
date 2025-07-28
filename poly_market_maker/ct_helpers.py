from web3 import Web3
import json
from constants import TOKEN_ID_FILE


class CTHelpers:

    @classmethod
    def get_token_ids(cls, condition_id: str) -> int:
        with open(TOKEN_ID_FILE, 'r') as f:
            token_ids = json.load(f)
        return token_ids.get(condition_id)

    
