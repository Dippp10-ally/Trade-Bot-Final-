from itertools import cycle

from fastapi import APIRouter

from backend.mt5_connector import mt5_connector
from backend.session_detector import detect_market_session

router = APIRouter(tags=["status"])

_MESSAGES = cycle(
    [
        "Collecting real-time MT5 price data...",
        "Analyzing momentum structure...",
        "Running prediction engine...",
        "Trade confidence generated successfully",
    ]
)


@router.get("/mt5-status")
def mt5_status():
    acc = mt5_connector.get_account_info()
    return {
        "status": mt5_connector.status, 
        "error": mt5_connector.last_error,
        "balance": acc.get("balance"),
        "equity": acc.get("equity")
    }


@router.get("/model-status")
def model_status():
    from backend.status_manager import bot_status
    return {"message": bot_status.current_message}


@router.get("/market-session")
def market_session():
    return {"session": detect_market_session()}


@router.get("/price")
def get_price():
    try:
        return mt5_connector.get_tick()
    except Exception as e:
        return {"error": str(e)}
