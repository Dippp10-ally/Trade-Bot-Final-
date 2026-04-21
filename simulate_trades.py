import os
import pickle
import numpy as np
import pandas as pd
import warnings
import tensorflow as tf
import ta
from datetime import datetime

warnings.filterwarnings("ignore")
tf.get_logger().setLevel("ERROR")

# Configuration
INITIAL_EQUITY = 1000.0
RISK_PER_TRADE_PERCENT = 0.01  # Risk 1% per trade
THRESHOLD = 0.95
DATA_START_YEAR = '2024-01-01'
OUTPUT_FILE = "trade_simulation_results.txt"

def load_data(path):
    # Detect separator (tab vs comma)
    with open(path, 'r') as f:
        line = f.readline()
        sep = '\t' if '\t' in line else ','
    
    df = pd.read_csv(path, sep=sep)
    df.columns = [c.replace("<","").replace(">","") for c in df.columns]
    
    if "TIME" in df.columns:
        df["DATETIME"] = pd.to_datetime(df["DATE"] + " " + df["TIME"], format="%Y.%m.%d %H:%M:%S")
        df.drop(columns=["DATE", "TIME"], inplace=True)
    else:
        df["DATETIME"] = pd.to_datetime(df["DATE"], format="%Y.%m.%d")
        df.drop(columns=["DATE"], inplace=True)
        
    df.set_index("DATETIME", inplace=True)
    df.sort_index(inplace=True)
    return df

def generate_features(df, prefix):
    df = df.copy()
    for col in ['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOL', 'TICKVOL', 'SPREAD']:
        if col not in df.columns: df[col] = 0.0
    df[f"{prefix}RSI14"] = ta.momentum.rsi(df["CLOSE"], window=14).fillna(50)
    df[f"{prefix}EMA50"] = df["CLOSE"].ewm(span=50, adjust=False).mean()
    df[f"{prefix}EMA200"] = df["CLOSE"].ewm(span=200, adjust=False).mean()
    df[f"{prefix}EMA50_SLOPE"] = df[f"{prefix}EMA50"].diff(5).fillna(0)
    df[f"{prefix}EMA200_SLOPE"] = df[f"{prefix}EMA200"].diff(5).fillna(0)
    df[f"{prefix}ATR14"] = ta.volatility.average_true_range(df["HIGH"], df["LOW"], df["CLOSE"], window=14).fillna(0)
    df[f"{prefix}ATR14_MA"] = df[f"{prefix}ATR14"].rolling(20).mean().fillna(0)
    df[f"{prefix}RESISTANCE"] = df["HIGH"].rolling(20).max().shift(1).bfill()
    df[f"{prefix}SUPPORT"] = df["LOW"].rolling(20).min().shift(1).bfill()
    ema200 = df[f"{prefix}EMA200"]
    df[f"{prefix}DIST_EMA200"] = np.where(ema200 != 0, (df["CLOSE"] - ema200) / ema200, 0)
    df[f"{prefix}CLOSE_PRICE"] = df["CLOSE"]
    return df

def main():
    print(f"--- SIMULATING TRADE ENVIRONMENT ({DATA_START_YEAR} to Present) ---")
    
    # 1. Load models
    print("Loading models...")
    xgb = pickle.load(open("models/xgb.pkl", "rb"))
    lstm = tf.keras.models.load_model("models/lstm.h5")
    meta = pickle.load(open("models/meta.pkl", "rb"))
    scaler = pickle.load(open("models/scaler.pkl", "rb"))
    features = pickle.load(open("models/features.pkl", "rb"))

    # 2. Process data
    print("Processing M15, H1, H4 data...")
    df_m15_raw = load_data("Data/M15.csv")
    df_h1 = generate_features(load_data("Data/H1.csv"), "H1_")
    df_h4 = generate_features(load_data("Data/H4.csv"), "H4_")
    
    # Feature engineering for M15 (signals)
    df_m15_feat = generate_features(df_m15_raw, "M15_")
    
    # Merge for signal generation
    df_h1.columns = [f"H1_{c}" if not c.startswith("H1_") else c for c in df_h1.columns]
    df_h4.columns = [f"H4_{c}" if not c.startswith("H4_") else c for c in df_h4.columns]
    merged = pd.merge_asof(df_m15_feat, df_h1, left_index=True, right_index=True)
    merged = pd.merge_asof(merged, df_h4, left_index=True, right_index=True)
    
    # Filter for simulation period (unseen data)
    sim_data = merged[merged.index >= DATA_START_YEAR].copy()
    if sim_data.empty:
        print(f"Error: No data found after {DATA_START_YEAR}.")
        return

    # Load M1 data for exit checking
    print("Loading M1 data (this may take a moment)...")
    df_m1 = load_data("Data/M1.csv")
    m1_index = df_m1.index
    m1_highs = df_m1["HIGH"].values
    m1_lows = df_m1["LOW"].values

    # 3. Predict Probabilities
    print("Generating signals...")
    X = sim_data[features]
    X_scaled = scaler.transform(X)
    X_lstm = X_scaled.reshape((X_scaled.shape[0], 1, X_scaled.shape[1]))
    
    xgb_probs = xgb.predict_proba(X_scaled)[:, 1]
    lstm_probs = lstm.predict(X_lstm, verbose=0).flatten()
    meta_input = np.column_stack((xgb_probs, lstm_probs))
    final_probs = meta.predict_proba(meta_input)[:, 1]
    
    sim_data["PROB"] = final_probs

    # 4. Simulation Loop
    print("Simulating trades with M1 exit checking...")
    equity = INITIAL_EQUITY
    trades = []
    
    # Signal data
    index_m15 = sim_data.index
    closes_m15 = sim_data["M15_CLOSE_PRICE"].values
    atrs_m15 = sim_data["M15_ATR14"].values
    atr_mas_m15 = sim_data["M15_ATR14_MA"].values
    probs_m15 = sim_data["PROB"].values
    
    # Keep track of when we're in a trade to avoid overlap (simplified)
    last_exit_time = pd.Timestamp.min

    for i in range(len(sim_data)):
        current_time = index_m15[i]
        
        # Avoid overlapping trades for simplicity
        if current_time <= last_exit_time:
            continue

        prob = probs_m15[i]
        atr_val = atrs_m15[i]
        atr_ma_val = atr_mas_m15[i]
        
        trade_type = None
        # High Volatility Filter: ATR > MA
        if atr_val > atr_ma_val:
            if prob >= THRESHOLD:
                trade_type = "BUY"
            elif prob <= (1 - THRESHOLD):
                trade_type = "SELL"
            
        if trade_type:
            entry_price = closes_m15[i]
            atr_val = atrs_m15[i]
            if atr_val <= 0: continue
            
            # SL and TP calculation (matches training logic)
            # Use M15 candle's low/high for SL placement
            if trade_type == "BUY":
                sl = sim_data["LOW"].iloc[i] - (atr_val * 0.2)
                risk = entry_price - sl
                if risk <= 0: continue
                tp = entry_price + (risk * 2.0)
            else: # SELL
                sl = sim_data["HIGH"].iloc[i] + (atr_val * 0.2)
                risk = sl - entry_price
                if risk <= 0: continue
                tp = entry_price - (risk * 2.0)
            
            # Find entry index in M1
            # We start looking from the next M1 candle AFTER the signal timestamp
            start_m1_idx = m1_index.get_indexer([current_time], method='pad')[0]
            if start_m1_idx == -1: continue
            
            # Exit loop using M1 data
            outcome = None # "TP" or "SL"
            exit_time = None
            
            # Search limit: 48 M15 candles = 720 M1 candles
            search_limit = min(start_m1_idx + 720, len(m1_index))
            
            for j in range(start_m1_idx + 1, search_limit):
                h = m1_highs[j]
                l = m1_lows[j]
                
                if trade_type == "BUY":
                    # Check SL first (pessimistic)
                    if l <= sl:
                        outcome = "SL"
                        exit_time = m1_index[j]
                        break
                    elif h >= tp:
                        outcome = "TP"
                        exit_time = m1_index[j]
                        break
                else: # SELL
                    if h >= sl:
                        outcome = "SL"
                        exit_time = m1_index[j]
                        break
                    elif l <= tp:
                        outcome = "TP"
                        exit_time = m1_index[j]
                        break
            
            if outcome:
                # Calculate PnL
                if outcome == "TP":
                    equity += equity * RISK_PER_TRADE_PERCENT * 2.0
                else:
                    equity -= equity * RISK_PER_TRADE_PERCENT
                
                trades.append({
                    "entry_time": current_time,
                    "exit_time": exit_time,
                    "type": trade_type,
                    "status": outcome,
                    "equity": equity
                })
                last_exit_time = exit_time
            else:
                # Time out (neither hit)
                # For this simulation, we consider it a wash/exit at current price?
                # Actually, let's stick to the prompt's focus on SL/TP hits.
                # If neither hit after 12 hours, we exit at current price.
                exit_price = m1_lows[search_limit-1] if trade_type == "BUY" else m1_highs[search_limit-1]
                # If exit_price is better than entry, it's profit, else loss.
                # But to be safe and conservative, if it's "confused" or timed out, let's treat it as a SL/Flat.
                # User said: "if confused, consider loss".
                equity -= equity * RISK_PER_TRADE_PERCENT
                trades.append({
                    "entry_time": current_time,
                    "exit_time": m1_index[search_limit-1],
                    "type": trade_type,
                    "status": "TIMEOUT_SL",
                    "equity": equity
                })
                last_exit_time = m1_index[search_limit-1]

    # 5. Save Results
    print(f"Simulation complete. Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w") as f:
        f.write("--- TRADE SIMULATION RESULTS (M1 VERIFIED) ---\n")
        f.write(f"Period: {DATA_START_YEAR} to Present\n")
        f.write(f"Initial Equity: ${INITIAL_EQUITY:.2f}\n")
        f.write(f"Threshold: {THRESHOLD*100}%\n")
        f.write(f"Risk per trade: {RISK_PER_TRADE_PERCENT*100}%\n")
        f.write("-" * 85 + "\n")
        f.write(f"{'Entry Time':<25} {'Exit Time':<25} {'Type':<8} {'Status':<12} {'Equity':<15}\n")
        f.write("-" * 85 + "\n")
        
        for t in trades:
            f.write(f"{str(t['entry_time']):<25} {str(t['exit_time']):<25} {t['type']:<8} {t['status']:<12} ${t['equity']:<14.2f}\n")
        
        f.write("-" * 85 + "\n")
        f.write(f"Final Equity: ${equity:.2f}\n")
        f.write(f"Total Trades: {len(trades)}\n")
        
        if trades:
            wins = sum(1 for t in trades if t["status"] == "TP")
            losses = sum(1 for t in trades if t["status"] in ["SL", "TIMEOUT_SL"])
            win_rate = (wins / len(trades)) * 100
            f.write(f"Wins: {wins}, Losses: {losses}, Win Rate: {win_rate:.2f}%\n")

    print(f"Final Equity: ${equity:.2f}")
    print("Done! Check trade_simulation_results.txt ✅")

if __name__ == "__main__":
    main()
