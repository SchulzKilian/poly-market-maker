import requests
from prometheus_client import Counter, Gauge, Histogram

chain_requests_counter = Counter(
    "chain_requests_counter",
    "Counts the chain executions",
    labelnames=["method", "status"],
    namespace="market_maker",
)
keeper_balance_amount = Gauge(
    "balance_amount",
    "Balance of the bot",
    labelnames=["accountaddress", "assetaddress", "tokenid"],
    namespace="market_maker",
)
clob_requests_latency = Histogram(
    "clob_requests_latency",
    "Latency of the clob requests",
    labelnames=["method", "status"],
    namespace="market_maker",
)
gas_station_latency = Histogram(
    "gas_station_latency",
    "Latency of the gas station",
    labelnames=["strategy", "status"],
    namespace="market_maker",
)
active_markets_gauge = Gauge(
    "active_markets",
    "Number of active markets",
    namespace="market_maker",
)
orders_placed_counter = Counter(
    "orders_placed",
    "Number of orders placed",
    labelnames=["side"],
    namespace="market_maker",
)
profit_and_loss_gauge = Gauge(
    "profit_and_loss",
    "Profit and loss",
    namespace="market_maker",
)
market_info_gauge = Gauge(
    "market_info",
    "Extra market info",
    labelnames=["market", "condition_id", "question_id"],
    namespace="market_maker",
)
position_gauge = Gauge(
    "position",
    "Current position of the bot",
    labelnames=["market", "token"],
    namespace="market_maker",
)
