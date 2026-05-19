class BotState:
    def __init__(self):
        self.monitoring = True
        self.min_profit_pct = None
        self.symbol_filter = set()
        self.last_signals = {}
        self.awaiting_profit_input = False

state = BotState()