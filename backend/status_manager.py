class BotStatus:
    def __init__(self):
        self.current_message = "Initializing AI Engine..."
        self.last_signal = "NO_TRADE"
        self.last_conf = 0
        self.last_full_signal = {
            "signal": "NO_TRADE",
            "confidence": 0,
            "trend": "syncing",
            "volatility": "syncing",
            "liquidity": "syncing",
            "atr": 0,
            "atr_ma": 0,
            "trend_pct": 50,
            "momentum_pct": 50,
            "volume_pct": 50
        }
        self.last_tick = {"last": 0, "bid": 0, "ask": 0}

bot_status = BotStatus()
