class DynamicRiskManager:
    def __init__(self):
        self.manual_reset_required = False
        self.trading_disabled_until = None

    def evaluate_trade(
        self,
        equity,
        confidence_score,
        atr,
        rolling_atr_mean,
        spread,
        rolling_mean_spread,
        session,
        news_flag,
        last_5_trade_results,
        current_drawdown_pct,
        open_trade_profit,
        trades_today,
        trades_this_hour,
        daily_equity_drop_pct,
        total_equity_drop_pct,
        current_time
    ):
        """
        Evaluates trading conditions and returns risk management parameters.
        """
        # Default outputs
        trade_permission = True
        lot_size = 0.0
        sl_distance = 0.0
        tp_distance = 0.0
        trailing_stop_distance = None
        move_to_break_even = False

        # Check manual reset / time-based bans first
        if self.manual_reset_required:
            return {"trade_permission": False, "reason": "Manual reset required due to max total drawdown."}

        if self.trading_disabled_until and current_time < self.trading_disabled_until:
            return {"trade_permission": False, "reason": f"Trading disabled until {self.trading_disabled_until}"}
        else:
            self.trading_disabled_until = None

        # ----------------------------------------------------
        # STEP 1: BLOCK BAD CONDITIONS
        # ----------------------------------------------------
        if news_flag == "HIGH_IMPACT":
            trade_permission = False

        if spread > rolling_mean_spread * 1.8:
            trade_permission = False

        if session not in ("London", "NewYork", "Sydney"):
            trade_permission = False

        if confidence_score < 0.90:
            trade_permission = False

        # ----------------------------------------------------
        # STEP 2: VOLATILITY-AWARE STOP LOSS
        # ----------------------------------------------------
        sl_distance = atr * 1.4

        if atr <= rolling_atr_mean:
            trade_permission = False

        # ----------------------------------------------------
        # STEP 3: ADAPTIVE TAKE PROFIT
        # ----------------------------------------------------
        if confidence_score > 0.96:
            tp_distance = sl_distance * 2.4
        else:
            tp_distance = sl_distance * 1.8

        # ----------------------------------------------------
        # STEP 4: EQUITY-PROTECTION LOT SIZING
        # ----------------------------------------------------
        base_lot = (equity / 100.0) * 0.01

        if confidence_score >= 0.98:
            confidence_multiplier = 1.25
        elif confidence_score >= 0.95:
            confidence_multiplier = 1.10
        else:
            confidence_multiplier = 1.00

        if current_drawdown_pct > 6.0:
            drawdown_penalty = 0.60
        elif current_drawdown_pct > 3.0:
            drawdown_penalty = 0.80
        else:
            drawdown_penalty = 1.00

        lot_size = base_lot * confidence_multiplier * drawdown_penalty

        # ----------------------------------------------------
        # STEP 5: LOSS-STREAK PROTECTION
        # ----------------------------------------------------
        # Assuming last_5_trade_results is a list of 'W' (win) and 'L' (loss), e.g. ['W', 'L', 'L', 'W', 'L']
        losses_in_last_5 = last_5_trade_results.count('L')
        
        if losses_in_last_5 >= 3:
            lot_size = lot_size * 0.5

        if losses_in_last_5 >= 4:
            trade_permission = False

        # ----------------------------------------------------
        # STEP 6: TRADE BREATHING LOGIC
        # ----------------------------------------------------
        if open_trade_profit >= atr * 1.2:
            trailing_stop_distance = atr * 0.9

        # ----------------------------------------------------
        # STEP 7: SMART BREAK-EVEN SHIFT
        # ----------------------------------------------------
        if open_trade_profit >= atr * 1.6:
            move_to_break_even = True

        # ----------------------------------------------------
        # STEP 8: OVERTRADING PROTECTION
        # ----------------------------------------------------
        if trades_today >= 6:
            trade_permission = False

        if trades_this_hour >= 2:
            trade_permission = False

        # ----------------------------------------------------
        # STEP 9: EQUITY CURVE PROTECTION
        # ----------------------------------------------------
        if daily_equity_drop_pct >= 4.0:
            # Disable for 24 hours
            import datetime
            self.trading_disabled_until = current_time + datetime.timedelta(hours=24)
            trade_permission = False

        if total_equity_drop_pct >= 8.0:
            self.manual_reset_required = True
            trade_permission = False

        return {
            "lot_size": round(lot_size, 2) if trade_permission else 0.0,
            "sl_distance": sl_distance,
            "tp_distance": tp_distance,
            "trade_permission": trade_permission,
            "trailing_stop_distance": trailing_stop_distance,
            "move_to_break_even": move_to_break_even,
            "reason": "Conditions met" if trade_permission else "Blocked by filters"
        }

if __name__ == "__main__":
    import datetime
    
    manager = DynamicRiskManager()
    
    # Example Usage
    result = manager.evaluate_trade(
        equity=1000.0,
        confidence_score=0.97,
        atr=2.5,
        rolling_atr_mean=2.0,
        spread=0.5,
        rolling_mean_spread=0.4,
        session="London",
        news_flag="LOW_IMPACT",
        last_5_trade_results=['W', 'L', 'W', 'W', 'W'],
        current_drawdown_pct=2.0,
        open_trade_profit=3.5,
        trades_today=2,
        trades_this_hour=0,
        daily_equity_drop_pct=1.0,
        total_equity_drop_pct=2.0,
        current_time=datetime.datetime.now()
    )
    
    print("Risk Manager Output:")
    for k, v in result.items():
        print(f"{k}: {v}")
