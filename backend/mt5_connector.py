from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from backend.config import get_settings

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

# Correct MT5 timeframe constants fallbacks
TF_MAP = {
    "M1": getattr(mt5, "TIMEFRAME_M1", 1),
    "M5": getattr(mt5, "TIMEFRAME_M5", 5),
    "M15": getattr(mt5, "TIMEFRAME_M15", 15),
    "M30": getattr(mt5, "TIMEFRAME_M30", 30),
    "H1": getattr(mt5, "TIMEFRAME_H1", 16385),
    "H4": getattr(mt5, "TIMEFRAME_H4", 16388),
    "D1": getattr(mt5, "TIMEFRAME_D1", 16408),
}

class MT5Connector:
    def __init__(self):
        self.settings = get_settings()
        self.status = "disconnected"
        self.last_error = None
        self._lock = threading.Lock()
        self.broker_utc_offset = 0
        
        self._monitor_thread = threading.Thread(target=self._connection_monitor, daemon=True)
        self._monitor_thread.start()

    def connect(self) -> bool:
        with self._lock:
            if mt5 is None:
                self.last_error = "MetaTrader5 package unavailable"
                self.status = "disconnected"
                return False

            self.status = "reconnecting"
            if not mt5.initialize():
                self.last_error = f"initialize failed: {mt5.last_error()}"
                self.status = "disconnected"
                return False

            if self.settings.mt5_login and self.settings.mt5_password and self.settings.mt5_server:
                login_ok = mt5.login(
                    self.settings.mt5_login,
                    password=self.settings.mt5_password,
                    server=self.settings.mt5_server,
                )
                if not login_ok:
                    self.last_error = f"login failed: {mt5.last_error()}"
                    self.status = "disconnected"
                    return False

            # Detect broker timezone offset relative to UTC
            tick = mt5.symbol_info_tick(self.settings.symbol)
            if tick:
                now_utc = datetime.now(timezone.utc).timestamp()
                # Round to nearest hour
                self.broker_utc_offset = round((tick.time - now_utc) / 3600) * 3600

            info = mt5.symbol_info(self.settings.symbol)
            if info is None:
                self.last_error = f"symbol {self.settings.symbol} unavailable"
                self.status = "disconnected"
                return False

            if not info.visible:
                mt5.symbol_select(self.settings.symbol, True)

            self.status = "connected"
            self.last_error = None
            return True

    def get_account_info(self) -> dict:
        """Retrieves real-time account info (equity, balance, etc)."""
        if self.status != "connected" or mt5 is None:
            return {"equity": 1000.0, "balance": 1000.0, "leverage": 100, "currency": "USD"}
        
        acc = mt5.account_info()
        if acc is None:
            return {"equity": 1000.0, "balance": 1000.0, "leverage": 100, "currency": "USD"}
            
        return {
            "equity": float(acc.equity),
            "balance": float(acc.balance),
            "leverage": int(acc.leverage),
            "currency": str(acc.currency),
        }

    def _connection_monitor(self):
        """Monitors MT5 connection."""
        while True:
            try:
                if self.status != "connected":
                    self.connect()
                else:
                    if mt5 is None or mt5.terminal_info() is None:
                        self.status = "disconnected"
                time.sleep(5)
            except Exception:
                time.sleep(5)

    def get_tick(self) -> dict:
        if self.status != "connected" or mt5 is None:
            raise RuntimeError(f"MT5 is not connected. Status: {self.status}, Error: {self.last_error}")
            
        tick = mt5.symbol_info_tick(self.settings.symbol)
        if tick is None:
            raise RuntimeError(f"Failed to get live tick for {self.settings.symbol} from MT5.")
            
        return {
            "symbol": self.settings.symbol,
            "bid": round(float(tick.bid), 5),
            "ask": round(float(tick.ask), 5),
            "last": round(float(tick.last or tick.bid), 5),
            "time": int(tick.time) - self.broker_utc_offset,
        }

    def get_candles(self, timeframe: str, limit: int | None = None) -> list[dict]:
        timeframe = timeframe.upper()
        limit = limit or self.settings.candle_limit
        
        if self.status != "connected" or mt5 is None:
            raise RuntimeError(f"MT5 is not connected. Status: {self.status}, Error: {self.last_error}")

        rates = mt5.copy_rates_from_pos(self.settings.symbol, TF_MAP.get(timeframe, 5), 0, limit)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"No candle data received from MT5 for {self.settings.symbol}.")
            
        # Adjust timestamps to UTC for universal accuracy
        return [
            {
                "time": int(rates[i]["time"]) - self.broker_utc_offset,
                "open": round(float(rates[i]["open"]), 5),
                "high": round(float(rates[i]["high"]), 5),
                "low": round(float(rates[i]["low"]), 5),
                "close": round(float(rates[i]["close"]), 5),
                "tickvol": int(rates[i]["tick_volume"]),
                "vol": int(rates[i]["real_volume"]),
                "spread": int(rates[i]["spread"]),
            }
            for i in range(len(rates))
        ]

mt5_connector = MT5Connector()