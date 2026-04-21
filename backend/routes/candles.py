from fastapi import APIRouter, HTTPException

from backend.mt5_connector import mt5_connector

router = APIRouter(tags=["candles"])


@router.get("/candles/{timeframe}")
def get_candles(timeframe: str, limit: int = 50000):
    try:
        candles = mt5_connector.get_candles(timeframe, limit=limit)
        return candles
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
