# AI XAUUSD Trading Platform (Backend)

## Project overview
Production-oriented FastAPI backend for an AI-assisted **XAUUSD-only** trading platform. It provides:
- MT5 connectivity and health status
- 500-candle OHLC endpoints in TradingView Lightweight Charts format
- Multi-timeframe support: `M1 M5 M15 M30 H1 H4 D1`
- Indicator-based signal/confidence engine (EMA/RSI/MACD/momentum)
- WebSocket feeds for candles, trade updates, model status
- Auto-trade execution with TP `+5` and SL `-10`
- PostgreSQL trade history persistence
- Session detection (Asia/London/New York)

## Folder structure
```
backend/
├── main.py
├── config.py
├── mt5_connector.py
├── signal_engine.py
├── trade_executor.py
├── session_detector.py
├── routes/
│   ├── candles.py
│   ├── trades.py
│   ├── confidence.py
│   ├── status.py
├── websocket/
│   ├── candle_stream.py
│   ├── trade_stream.py
├── database/
│   ├── models.py
│   ├── connection.py
├── requirements.txt
├── Dockerfile
└── README.md
```

## MT5 installation steps
### Windows (recommended for live MT5)
1. Install MetaTrader 5 desktop terminal.
2. Log in to your broker account in MT5.
3. Ensure `XAUUSD` exists in *Market Watch*.
4. Install Python 3.11 and then backend requirements.
5. Run backend from same Windows machine where terminal is installed/open.

### Linux/macOS note
`MetaTrader5` Python package may not initialize without a compatible MT5 terminal runtime.
Backend keeps readable JSON errors and reconnect logic when unavailable.

## Environment variables setup
Copy `.env.example` to `.env` in project root:
```bash
cp .env.example .env
```
Set:
```env
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/trading_bot
SYMBOL=XAUUSD
```

## Setup instructions
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```

## Backend start command
From repo root:
```bash
python -m backend.main
```

## Frontend start command
Simple static run:
```bash
python -m http.server 5173 --directory frontend
```
Open:
- `http://localhost:5173/index.html`
- `http://localhost:5173/mt5-login.html`

Alternatively, if backend is running, frontend is also served directly by FastAPI at:
- `http://localhost:8000/`
- `http://localhost:8000/mt5-login`

If your existing frontend is Vite/React, use:
```bash
npm install
npm run dev
```
and point API base URL to `http://localhost:8000`.

## API documentation
- `GET /mt5-status` → `connected | disconnected | reconnecting`
- `GET /candles/{timeframe}` → 500 OHLC candles:
  ```json
  [{"time": 1710000000, "open": 2641.2, "high": 2642.1, "low": 2640.8, "close": 2641.8}]
  ```
- `GET /confidence` → signal + confidence + trend + volatility + liquidity
- `GET /model-status` → rotating model messages
- `GET /trade-status` → entry/current/PNL/TP/SL/duration/state
- `GET /trade-history` → last 20 persisted trades
- `GET /market-session` → `Asia|London|New York`

Interactive Swagger: `http://localhost:8000/docs`

## WebSocket documentation
- `ws://localhost:8000/ws/candles?timeframe=M5`
  - Streams candles/tick payload
- `ws://localhost:8000/ws/trade-updates`
  - Streams signal/trade lifecycle/confidence updates
- `ws://localhost:8000/ws/status`
  - Streams MT5 status + rotating model processing message

## Docker setup
Build and run backend:
```bash
docker build -f backend/Dockerfile -t xau-backend .
docker run --env-file .env -p 8000:8000 xau-backend
```

## PostgreSQL table
`trade_history`:
- `id`
- `symbol`
- `signal`
- `entry_price`
- `exit_price`
- `profit_loss`
- `confidence`
- `timestamp`
- `status`

## Error handling
Readable JSON errors for:
- MT5 disconnected
- invalid timeframe
- symbol unavailable
- database failure
- trade rejected/blocked by threshold

## Troubleshooting
- **`ModuleNotFoundError: No module named 'psycopg2'`**
  - Install dependencies again: `pip install -r backend/requirements.txt`
  - If PostgreSQL driver is still unavailable, backend now auto-falls back to local SQLite (`trading_bot_fallback.db`) so you can continue development while fixing PostgreSQL setup.

## Notes for your custom CSV model training
This backend does **not** train a model. To plug your own CSV-trained model:
1. Add your inference loader in `signal_engine.py`.
2. Keep output keys unchanged: `signal, confidence, trend, volatility, liquidity`.
3. Keep confidence scale 0–100 so trade threshold logic remains valid.
