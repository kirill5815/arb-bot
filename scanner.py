import ccxt
from config import EX1_NAME, EX2_NAME, QUOTE, FEE1, FEE2, MIN_NOTIONAL_QUOTE, OB_LIMIT

def get_exchange(name):
    ex_class = getattr(ccxt, name)
    return ex_class({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })

def load_spot_symbols(ex):
    markets = ex.load_markets()
    return sorted([
        s for s, m in markets.items()
        if m.get("spot") and m.get("active") and m.get("quote") == QUOTE
    ])

def top_bid_ask(order_book):
    bid = order_book["bids"][0][0] if order_book.get("bids") else None
    ask = order_book["asks"][0][0] if order_book.get("asks") else None
    return bid, ask

def notional_from_levels(levels, min_notional):
    total = 0.0
    for price, amount in levels:
        total += price * amount
        if total >= min_notional:
            return True
    return False

def profit_pct(buy_price, sell_price, buy_fee, sell_fee):
    buy_cost = buy_price * (1 + buy_fee)
    sell_rev = sell_price * (1 - sell_fee)
    return (sell_rev - buy_cost) / buy_cost * 100.0

class Scanner:
    def __init__(self):
        self.ex1 = get_exchange(EX1_NAME)
        self.ex2 = get_exchange(EX2_NAME)
        self.symbols1 = set(load_spot_symbols(self.ex1))
        self.symbols2 = set(load_spot_symbols(self.ex2))
        self.common_symbols = sorted(self.symbols1.intersection(self.symbols2))

    def scan(self, min_profit_pct, symbol_filter=None):
        results = []
        symbol_filter = symbol_filter or set()

        for sym in self.common_symbols:
            if symbol_filter and sym not in symbol_filter:
                continue

            try:
                ob1 = self.ex1.fetch_order_book(sym, limit=OB_LIMIT)
                ob2 = self.ex2.fetch_order_book(sym, limit=OB_LIMIT)

                if not ob1.get("bids") or not ob1.get("asks") or not ob2.get("bids") or not ob2.get("asks"):
                    continue

                bid1, ask1 = top_bid_ask(ob1)
                bid2, ask2 = top_bid_ask(ob2)

                if notional_from_levels(ob1["asks"], MIN_NOTIONAL_QUOTE) and notional_from_levels(ob2["bids"], MIN_NOTIONAL_QUOTE):
                    p1 = profit_pct(ask1, bid2, FEE1, FEE2)
                    if p1 >= min_profit_pct:
                        results.append({
                            "symbol": sym,
                            "buy_ex": EX1_NAME,
                            "sell_ex": EX2_NAME,
                            "buy_price": ask1,
                            "sell_price": bid2,
                            "profit": p1,
                        })

                if notional_from_levels(ob2["asks"], MIN_NOTIONAL_QUOTE) and notional_from_levels(ob1["bids"], MIN_NOTIONAL_QUOTE):
                    p2 = profit_pct(ask2, bid1, FEE2, FEE1)
                    if p2 >= min_profit_pct:
                        results.append({
                            "symbol": sym,
                            "buy_ex": EX2_NAME,
                            "sell_ex": EX1_NAME,
                            "buy_price": ask2,
                            "sell_price": bid1,
                            "profit": p2,
                        })

            except Exception:
                continue

        return sorted(results, key=lambda x: x["profit"], reverse=True)