from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.models import TradeHistory
from backend.mt5_connector import mt5_connector

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

logger = logging.getLogger(__name__)

class TradeExecutor:
    def __init__(self):
        self.settings = get_settings()
        self.active_trade: dict | None = None
        self.auto_trade_enabled = False

    def toggle_auto_trade(self) -> bool:
        self.auto_trade_enabled = not self.auto_trade_enabled
        return self.auto_trade_enabled

    def sync_active_trade(self, db: Session):
        """Recover running trades from DB on startup."""
        row = (
            db.query(TradeHistory)
            .filter(TradeHistory.status == "running")
            .order_by(TradeHistory.timestamp.desc())
            .first()
        )
        if row:
            self.active_trade = {
                "db_id": row.id,
                "symbol": row.symbol,
                "signal": row.signal,
                "entry_price": row.entry_price,
                "current_price": row.entry_price,
                "tp": row.entry_price + 5 if row.signal == "BUY" else row.entry_price - 5,
                "sl": row.entry_price - 3 if row.signal == "BUY" else row.entry_price + 3,
                "opened_at": row.timestamp,
                "trade_state": "running",
                "profit_loss": 0.0,
                "confidence": row.confidence,
                "volume": 0.01 
            }

    def calculate_lot_size(self, equity: float) -> float:
        """
        WINNING LOGIC: Linear Compounding.
        0.01 lot per $100 equity.
        """
        return max(0.01, round((equity // 100) * 0.01, 2))

    def maybe_open_trade(self, signal_payload: dict, current_price: float, db: Session):
        if self.active_trade is not None:
            return self.active_trade

        # --- SAFETY LAYER: 3 CONSECUTIVE LOSS PAUSE ---
        recent_trades = (
            db.query(TradeHistory)
            .filter(TradeHistory.status != "running")
            .order_by(TradeHistory.timestamp.desc())
            .limit(3)
            .all()
        )
        
        if len(recent_trades) >= 3:
            # Check if all 3 were losses
            if all(t.status == "closed_sl" for t in recent_trades):
                last_loss_time = recent_trades[0].timestamp
                if last_loss_time.tzinfo is None:
                    last_loss_time = last_loss_time.replace(tzinfo=timezone.utc)
                
                diff = datetime.now(tz=timezone.utc) - last_loss_time
                if diff.total_seconds() < 3600:
                    wait_min = int((3600 - diff.total_seconds()) / 60)
                    from backend.status_manager import bot_status
                    bot_status.current_message = f"PAUSED: 3 Streak Losses ({wait_min}m left)"
                    return None

        signal = signal_payload.get("signal")
        confidence = signal_payload.get("confidence", 0)
        sl_dist = signal_payload.get("sl_dist", 3.0)
        tp_dist = signal_payload.get("tp_dist", 5.0)
        
        if signal not in {"BUY", "SELL"}:
            return None

        # ATTEMPT LIVE MT5 ORDER
        order_ticket = None
        if mt5 and mt5.terminal_info() is not None:
            trade_type = mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL
            tick = mt5.symbol_info_tick(self.settings.symbol)
            price = tick.ask if signal == "BUY" else tick.bid
            
            acc_info = mt5_connector.get_account_info()
            equity = acc_info.get("equity", 100.0)
            lot_size = self.calculate_lot_size(equity)
            
            tp_price = price + tp_dist if signal == "BUY" else price - tp_dist
            sl_price = price - sl_dist if signal == "BUY" else price + sl_dist

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.settings.symbol,
                "volume": lot_size,
                "type": trade_type,
                "price": price,
                "sl": round(sl_price, 2),
                "tp": round(tp_price, 2),
                "deviation": 20,
                "magic": 123456,
                "comment": f"HIGH-WIN GROW BOT {lot_size} lot",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                order_ticket = result.order
                logger.info(f"WINNING LOGIC TRADE OPENED: {signal} ticket={order_ticket} lot={lot_size}")
            else:
                error_msg = result.comment if result else mt5.last_error()
                logger.error(f"MT5 Order Failed: {error_msg}")
                raise ValueError(f"Broker rejected order: {error_msg}")
        else:
            raise ValueError("MT5 terminal is not connected.")
        
        self.active_trade = {
            "db_id": None,
            "symbol": self.settings.symbol,
            "signal": signal,
            "entry_price": price,
            "current_price": price,
            "tp": tp_price,
            "sl": sl_price,
            "opened_at": datetime.now(tz=timezone.utc),
            "trade_state": "running",
            "profit_loss": 0.0,
            "confidence": confidence,
            "mt5_ticket": order_ticket,
            "volume": lot_size
        }

        row = TradeHistory(
            symbol=self.settings.symbol,
            signal=signal,
            entry_price=price,
            exit_price=None,
            profit_loss=None,
            confidence=confidence,
            status="running",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        self.active_trade["db_id"] = row.id
        return self.active_trade

    def manual_open_trade(self, signal: str, current_price: float, db: Session):
        if self.active_trade is not None:
            return None
        payload = {"signal": signal.upper(), "confidence": 100, "sl_dist": 3.0, "tp_dist": 5.0}
        return self.maybe_open_trade(payload, current_price, db)

    def manual_close_trade(self, current_price: float, db: Session):
        if self.active_trade is None:
            return None
            
        trade = self.active_trade
        ticket = trade.get("mt5_ticket")
        
        if mt5 and mt5.terminal_info() is not None and ticket:
            close_type = mt5.ORDER_TYPE_SELL if trade["signal"] == "BUY" else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(self.settings.symbol)
            price = tick.bid if trade["signal"] == "BUY" else tick.ask
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.settings.symbol,
                "volume": trade.get("volume", 0.01),
                "type": close_type,
                "position": ticket,
                "price": price,
                "deviation": 20,
                "magic": 123456,
                "comment": "Manual Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Live MT5 trade manually closed: ticket={ticket}")

        trade["trade_state"] = "closed_manual"
        if trade["signal"] == "BUY":
            trade["profit_loss"] = round((current_price - trade["entry_price"]) * 100 * trade["volume"], 2)
        else:
            trade["profit_loss"] = round((trade["entry_price"] - current_price) * 100 * trade["volume"], 2)

        row = db.query(TradeHistory).filter(TradeHistory.id == trade["db_id"]).first()
        if row:
            row.exit_price = current_price
            row.profit_loss = trade["profit_loss"]
            row.status = trade["trade_state"]
            db.commit()
            
        closed_copy = trade.copy()
        self.active_trade = None
        return closed_copy

    def update_trade(self, current_price: float, db: Session) -> dict:
        if self.active_trade is None:
            return {"trade_state": "waiting"}

        trade = self.active_trade
        trade["current_price"] = current_price
        
        multiplier = 100 * trade["volume"]
        if trade["signal"] == "BUY":
            trade["profit_loss"] = round((current_price - trade["entry_price"]) * multiplier, 2)
            if current_price >= trade["tp"]: trade["trade_state"] = "closed_tp"
            elif current_price <= trade["sl"]: trade["trade_state"] = "closed_sl"
        else:
            trade["profit_loss"] = round((trade["entry_price"] - current_price) * multiplier, 2)
            if current_price <= trade["tp"]: trade["trade_state"] = "closed_tp"
            elif current_price >= trade["sl"]: trade["trade_state"] = "closed_sl"

        if trade["trade_state"] in {"closed_tp", "closed_sl"}:
            row = db.query(TradeHistory).filter(TradeHistory.id == trade["db_id"]).first()
            if row:
                row.exit_price = current_price
                row.profit_loss = trade["profit_loss"]
                row.status = trade["trade_state"]
                db.commit()
            
            closed_copy = trade.copy()
            self.active_trade = None
            return closed_copy

        return trade

trade_executor = TradeExecutor()
