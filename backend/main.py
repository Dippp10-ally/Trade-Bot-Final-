import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.database.connection import engine, SessionLocal
from backend.database.models import Base
from backend.mt5_connector import mt5_connector
from backend.trade_executor import trade_executor
from backend.signal_engine import generate_signal
from backend.status_manager import bot_status
from backend.routes.candles import router as candles_router
from backend.routes.confidence import router as confidence_router
from backend.routes.status import router as status_router
from backend.routes.trades import router as trades_router
from backend.websocket.candle_stream import stream_candles
from backend.websocket.trade_stream import stream_trade_updates

app = FastAPI(title="AI XAUUSD Trading Backend", version="1.0.0")
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(candles_router)
app.include_router(confidence_router)
app.include_router(status_router)
app.include_router(trades_router)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

async def trading_engine_loop():
    """Background task to drive trading logic independently of web/socket traffic."""
    while True:
        try:
            with SessionLocal() as db:
                bot_status.current_message = "Collecting real-time MT5 price data..."
                tick = mt5_connector.get_tick()
                bot_status.last_tick = tick
                
                bot_status.current_message = "Analyzing momentum structure..."
                trade_executor.update_trade(tick["last"], db)
                
                # Always update the signal data so UI stays fresh
                candles_m15 = mt5_connector.get_candles("M15")
                candles_h1 = mt5_connector.get_candles("H1")
                candles_h4 = mt5_connector.get_candles("H4")
                
                bot_status.current_message = "Running 39-feature ensemble..."
                signal = generate_signal(candles_m15, candles_h1, candles_h4)
                bot_status.last_full_signal = signal
                bot_status.last_signal = signal["signal"]
                bot_status.last_conf = signal["confidence"]
                
                print(f"[AI ENGINE] Signal Loop Active. Confidence: {signal['confidence']}%")
                
                if trade_executor.active_trade is None and trade_executor.auto_trade_enabled:
                    bot_status.current_message = "Trade confidence ready"
                    print(f"[AI ENGINE] Evaluated signal: {signal['signal']} (Confidence: {signal['confidence']}%) - Threshold: {settings.confidence_threshold}%")
                    trade_executor.maybe_open_trade(signal, tick["last"], db)
                else:
                    bot_status.current_message = "Trade confidence ready"
                    await asyncio.sleep(1) # Slow down if no trade needed
        except Exception as e:
            bot_status.current_message = f"Engine Error: {str(e)[:30]}..."
            await asyncio.sleep(2)
        await asyncio.sleep(1)


@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
    mt5_connector.connect()
    with SessionLocal() as db:
        trade_executor.sync_active_trade(db)
    asyncio.create_task(trading_engine_loop())


@app.get("/")
def root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"service": "ai-xauusd-trading-backend", "symbol": settings.symbol})


@app.get("/mt5-login")
def mt5_login_page():
    login_file = FRONTEND_DIR / "mt5-login.html"
    if login_file.exists():
        return FileResponse(login_file)
    return JSONResponse({"error": "mt5-login.html not found in frontend/"}, status_code=404)


@app.websocket("/ws/candles")
async def ws_candles(websocket: WebSocket):
    await stream_candles(websocket)


@app.websocket("/ws/trade-updates")
async def ws_trade_updates(websocket: WebSocket):
    await stream_trade_updates(websocket)


@app.websocket("/ws/status")
async def ws_status(websocket: WebSocket):
    from backend.session_detector import detect_market_session
    from backend.status_manager import bot_status
    await websocket.accept()
    while True:
        try:
            acc = mt5_connector.get_account_info()
            await websocket.send_json(
                {
                    "type": "status",
                    "mt5": mt5_connector.status,
                    "balance": acc.get("balance"),
                    "equity": acc.get("equity"),
                    "message": bot_status.current_message,
                    "session": detect_market_session()
                }
            )
            await asyncio.sleep(1)
        except Exception:
            break


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host=settings.uvicorn_host, port=settings.uvicorn_port, reload=True)
