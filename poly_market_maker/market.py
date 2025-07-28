import logging

from ct_helpers import CTHelpers
from token_class import Token


class Market:
    def __init__(self, condition_id: str, collateral_address: str):
        self.logger = logging.getLogger(self.__class__.__name__)

        assert isinstance(condition_id, str)
        assert isinstance(collateral_address, str)

        self.condition_id = condition_id
        token_ids_list = CTHelpers.get_token_ids(condition_id)

        self.token_ids = {
            Token.A: token_ids_list[0] if token_ids_list else None,
            Token.B: token_ids_list[1] if token_ids_list and len(token_ids_list) > 1 else None
        }

        self.logger.debug(f"Initialized Market: {self}")

    def __repr__(self):
        return f"Market[condition_id={self.condition_id}, token_id_a={self.token_ids[Token.A]}, token_id_b={self.token_ids[Token.B]}]"

    def token_id(self, token: Token) -> int:
        token_id = self.token_ids.get(token)
        return int(token_id) if token_id is not None else None

    def token(self, token_id: int) -> Token:
        if token_id is None:
            return None
        for token in Token:
            if token_id == self.token_ids[token]:
                return token
        raise ValueError("Unrecognized token ID")
