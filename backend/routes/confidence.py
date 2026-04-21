from fastapi import APIRouter, HTTPException

from backend.mt5_connector import mt5_connector
from backend.signal_engine import generate_signal

router = APIRouter(tags=["confidence"])


@router.get("/confidence")
def confidence():
    try:
        candles = mt5_connector.get_candles("M5")
        return generate_signal(candles)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"confidence error: {exc}") from exc
