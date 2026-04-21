import os
import pickle
import numpy as np
import pandas as pd
import logging
import ta
import tensorflow as tf
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('SignalEngine')

# Disable TF warnings for cleaner logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
tf.get_logger().setLevel('ERROR')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, 'models')

# Load the 39-Feature Ensemble
try:
    XGB_MODEL = pickle.load(open(os.path.join(MODELS_DIR, 'xgb.pkl'), 'rb'))
    LSTM_MODEL = tf.keras.models.load_model(os.path.join(MODELS_DIR, 'lstm.h5'))
    META_MODEL = pickle.load(open(os.path.join(MODELS_DIR, 'meta.pkl'), 'rb'))
    SCALER = pickle.load(open(os.path.join(MODELS_DIR, 'scaler.pkl'), 'rb'))
    FEATURE_NAMES = pickle.load(open(os.path.join(MODELS_DIR, 'features.pkl'), 'rb'))
    MODELS_LOADED = True
    logger.info("39-FEATURE ENSEMBLE LOADED SUCCESSFULLY.")
except Exception as e:
    logger.error(f"Error loading ensemble models: {e}")
    MODELS_LOADED = False

def generate_features(df, prefix):
    """Original feature engineering logic for the ensemble."""
    df = df.copy()
    # Ensure all columns are uppercase
    df.columns = [c.upper() for c in df.columns]
    
    # Map volume columns if they exist in alternate formats
    if 'TICK_VOLUME' in df.columns: df['TICKVOL'] = df['TICK_VOLUME']
    if 'REAL_VOLUME' in df.columns: df['VOL'] = df['REAL_VOLUME']
    
    # Required indicators
    df[f"{prefix}RSI14"] = ta.momentum.rsi(df["CLOSE"], window=14).fillna(50)
    df[f"{prefix}EMA50"] = df["CLOSE"].ewm(span=50, adjust=False).mean()
    df[f"{prefix}EMA200"] = df["CLOSE"].ewm(span=200, adjust=False).mean()
    df[f"{prefix}EMA50_SLOPE"] = df[f"{prefix}EMA50"].diff(5).fillna(0)
    df[f"{prefix}EMA200_SLOPE"] = df[f"{prefix}EMA200"].diff(5).fillna(0)
    
    df[f"{prefix}ATR14"] = ta.volatility.average_true_range(df["HIGH"], df["LOW"], df["CLOSE"], window=14).fillna(0)
    df[f"{prefix}RESISTANCE"] = df["HIGH"].rolling(20).max().shift(1).bfill()
    df[f"{prefix}SUPPORT"] = df["LOW"].rolling(20).min().shift(1).bfill()
    
    ema200 = df[f"{prefix}EMA200"]
    df[f"{prefix}DIST_EMA200"] = np.where(ema200 != 0, (df["CLOSE"] - ema200) / ema200, 0)
    return df

def generate_signal(candles_m15, candles_h1, candles_h4) -> dict:
    """The main entry point used by the live loop."""
    try:
        if not MODELS_LOADED:
            return {"signal": "NO_TRADE", "confidence": 0}

        # 1. Process Timeframes
        def to_df(candles):
            df = pd.DataFrame(candles)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            df.columns = [c.upper() for c in df.columns]
            return df

        df_m15 = generate_features(to_df(candles_m15), "M15_")
        df_h1 = generate_features(to_df(candles_h1), "H1_")
        df_h4 = generate_features(to_df(candles_h4), "H4_")

        # 2. Merge (Sync to M15)
        df_h1.columns = [f"H1_{c}" if not c.startswith("H1_") else c for c in df_h1.columns]
        df_h4.columns = [f"H4_{c}" if not c.startswith("H4_") else c for c in df_h4.columns]
        
        merged = pd.merge_asof(df_m15, df_h1, left_index=True, right_index=True)
        merged = pd.merge_asof(merged, df_h4, left_index=True, right_index=True)
        
        # 3. Final Feature Prep
        latest_row = merged.iloc[[-1]]
        X = latest_row[FEATURE_NAMES].ffill().fillna(0)
        X_scaled = SCALER.transform(X)

        # 4. Model Predictions
        xgb_prob = XGB_MODEL.predict_proba(X_scaled)[:, 1][0]
        X_lstm = X_scaled.reshape((1, 1, X_scaled.shape[1]))
        lstm_prob = LSTM_MODEL.predict(X_lstm, verbose=0)[0][0]
        
        # 5. Meta-Model "Judge"
        meta_input = np.column_stack((xgb_prob, lstm_prob))
        prob = META_MODEL.predict_proba(meta_input)[:, 1][0]
        
        # logger.info(f"AI PROB: {prob:.4f}")
        confidence = int(max(prob, 1 - prob) * 100)
        
        # 6. Dashboard Metrics
        atr = latest_row['M15_ATR14'].iloc[0]
        atr_ma = df_m15['M15_ATR14'].rolling(20).mean().iloc[-1]
        
        info = {
            "signal": "NO_TRADE",
            "confidence": confidence,
            "trend": "bullish" if latest_row['M15_EMA50'].iloc[0] > latest_row['M15_EMA200'].iloc[0] else "bearish",
            "volatility": "high" if atr > atr_ma else "low",
            "liquidity": "normal", # Placeholder for session logic
            "atr": float(round(atr, 4)),
            "atr_ma": float(round(atr_ma, 4)),
            "trend_pct": 80 if latest_row['M15_EMA50'].iloc[0] > latest_row['M15_EMA200'].iloc[0] else 20,
            "momentum_pct": int(latest_row['M15_RSI14'].iloc[0]),
            "volume_pct": 90 if atr > atr_ma else 30,
            "sl_dist": 3.0,
            "tp_dist": 5.0
        }

        # 7. EXECUTION GATE (95% Threshold + Volatility Filter)
        if confidence >= 95 and atr > atr_ma:
            if prob >= 0.95: info["signal"] = "BUY"
            elif prob <= 0.05: info["signal"] = "SELL"
            
        return info

    except Exception as e:
        logger.error(f"Signal Engine Error: {e}")
        return {"signal": "NO_TRADE", "confidence": 0, "error": str(e)}
