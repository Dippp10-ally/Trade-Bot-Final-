from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import TradeHistory
from backend.mt5_connector import mt5_connector
from backend.trade_executor import trade_executor

from pydantic import BaseModel

class ManualTradeRequest(BaseModel):
    signal: str

router = APIRouter(tags=["trades"])

@router.post("/trade/manual-open")
def manual_open(req: ManualTradeRequest, db: Session = Depends(get_db)):
    try:
        tick = mt5_connector.get_tick()
        price = tick["last"]
    except Exception:
        raise HTTPException(status_code=503, detail="MT5 not connected")
    
    try:
        trade = trade_executor.manual_open_trade(req.signal, price, db)
        if trade is None:
            raise HTTPException(status_code=400, detail="Trade already active")
        return trade
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.post("/trade/manual-close")
def manual_close(db: Session = Depends(get_db)):
    try:
        tick = mt5_connector.get_tick()
        price = tick["last"]
    except Exception:
        raise HTTPException(status_code=503, detail="MT5 not connected")
    
    trade = trade_executor.manual_close_trade(price, db)
    if trade is None:
        raise HTTPException(status_code=400, detail="No active trade")
    return trade

@router.get("/auto-trade/status")
def get_auto_trade_status():
    return {"active": trade_executor.auto_trade_enabled}

@router.post("/auto-trade/toggle")
def toggle_auto_trade():
    active = trade_executor.toggle_auto_trade()
    return {"active": active}

@router.get("/trade-status")
def trade_status(db: Session = Depends(get_db)):
    try:
        maybe = trade_executor.active_trade
        if maybe is None:
            return {"trade_state": "waiting"}

        # Use mt5 to get latest price if possible
        current_price = maybe.get("current_price")
        try:
            tick = mt5_connector.get_tick()
            current_price = tick["last"]
        except:
            pass

        opened = maybe["opened_at"]
        # Ensure 'opened' has timezone info for subtraction
        if opened and opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
            
        duration = int((datetime.now(tz=timezone.utc) - opened).total_seconds()) if opened else 0
        
        return {
            "entry_price": maybe.get("entry_price"),
            "current_price": current_price,
            "profit_loss": maybe.get("profit_loss"),
            "tp": maybe.get("tp"),
            "sl": maybe.get("sl"),
            "trade_duration": duration,
            "trade_state": maybe.get("trade_state"),
            "signal": maybe.get("signal"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/trade-history")
def trade_history(db: Session = Depends(get_db)):
    try:
        # Use explicit descending order on timestamp
        rows = db.query(TradeHistory).order_by(TradeHistory.timestamp.desc()).limit(100).all()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "signal": r.signal,
                "entry_price": r.entry_price,
                "exit_price": r.exit_price,
                "profit_loss": r.profit_loss,
                "confidence": r.confidence,
                "timestamp": r.timestamp.isoformat(),
                "status": r.status,
            }
            for r in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"database failure: {exc}") from exc
