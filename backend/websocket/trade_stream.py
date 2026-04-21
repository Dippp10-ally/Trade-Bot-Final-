import asyncio
import logging
from fastapi import WebSocket

from backend.trade_executor import trade_executor

logger = logging.getLogger('TradeStream')

async def stream_trade_updates(websocket: WebSocket):
    from backend.status_manager import bot_status
    
    await websocket.accept()
    print("TRADE WS: ACCEPTED") # VERIFY IN TERMINAL
    
    # Send immediate initial data
    try:
        await websocket.send_json({
            "type": "trade_update",
            "signal": bot_status.last_full_signal,
            "trade": trade_executor.active_trade.copy() if trade_executor.active_trade else {"trade_state": "waiting"},
            "price": bot_status.last_tick.get("last", 0)
        })
    except: pass

    while True:
        try:
            # USE PRE-CALCULATED SIGNAL FROM MAIN LOOP (39-FEATURE MODE)
            signal = bot_status.last_full_signal
            tick = bot_status.last_tick
            
            # debug log every 10 seconds
            # if int(time.time()) % 10 == 0:
            #    logger.info(f"Pushing trade update: {signal.get('confidence')}%")
            
            if not signal:
                signal = {"signal": "NO_TRADE", "confidence": 0, "trend": "syncing"}

            trade_data = trade_executor.active_trade.copy() if trade_executor.active_trade else {"trade_state": "waiting"}
            if "opened_at" in trade_data and hasattr(trade_data["opened_at"], "isoformat"):
                trade_data["opened_at"] = trade_data["opened_at"].isoformat()

            await websocket.send_json(
                {
                    "type": "trade_update",
                    "signal": signal,
                    "trade": trade_data,
                    "price": tick.get("last", 0),
                }
            )
            await asyncio.sleep(1)
        except Exception as exc:
            logger.error(f"Trade stream error: {exc}")
            break
