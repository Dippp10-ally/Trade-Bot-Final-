import asyncio
from fastapi import WebSocket
from backend.mt5_connector import mt5_connector

async def stream_candles(websocket: WebSocket):
    from backend.status_manager import bot_status
    
    await websocket.accept()
    timeframe = websocket.query_params.get("timeframe", "M5").upper()
    print(f"CANDLE WS CONNECTED: {timeframe}")
    
    while True:
        try:
            # Efficient candle fetch
            candles = mt5_connector.get_candles(timeframe, limit=20)
            tick = bot_status.last_tick
            
            await websocket.send_json(
                {
                    "type": "candles",
                    "timeframe": timeframe,
                    "candles": candles,
                    "tick": tick,
                }
            )
            await asyncio.sleep(1)
        except Exception as exc:
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
            except:
                break
            await asyncio.sleep(2)
