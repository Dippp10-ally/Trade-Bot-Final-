import os
import pickle
import numpy as np
import pandas as pd
import warnings
import tensorflow as tf
import ta
from sklearn.metrics import accuracy_score, precision_score, confusion_matrix

warnings.filterwarnings("ignore")
tf.get_logger().setLevel("ERROR")

def load_data(path):
    df = pd.read_csv(path, sep='\t')
    if '<DATE>' not in df.columns: df = pd.read_csv(path)
    df.columns = [c.replace("<","").replace(">","") for c in df.columns]
    if "TIME" in df.columns:
        df["DATETIME"] = pd.to_datetime(df["DATE"] + " " + df["TIME"], format="%Y.%m.%d %H:%M:%S")
    else:
        df["DATETIME"] = pd.to_datetime(df["DATE"], format="%Y.%m.%d")
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

def generate_labels(close_series, high_series, low_series):
    close = close_series.values
    high = high_series.values
    low = low_series.values
    atr = ta.volatility.average_true_range(high_series, low_series, close_series, window=14).bfill().values
    labels = []
    horizon = 48
    for i in range(len(close) - horizon):
        entry = close[i]
        atr_val = atr[i]
        sl_buy = low[i] - (atr_val * 0.2)
        tp_buy = entry + ((entry - sl_buy) * 2.0)
        sl_sell = high[i] + (atr_val * 0.2)
        tp_sell = entry - ((sl_sell - entry) * 2.0)
        
        buy_won = False
        sell_won = False
        for j in range(i+1, i+horizon):
            if low[j] <= sl_buy: break
            if high[j] >= tp_buy: buy_won = True; break
        for j in range(i+1, i+horizon):
            if high[j] >= sl_sell: break
            if low[j] <= tp_sell: sell_won = True; break
        if buy_won: labels.append(1)
        elif sell_won: labels.append(0)
        else: labels.append(np.nan)
    labels.extend([np.nan] * horizon)
    return labels

def main():
    print("--- ENSEMBLE PERFORMANCE VERIFICATION (2026 DATA) ---")
    print("Loading models...")
    xgb = pickle.load(open("models/xgb.pkl", "rb"))
    lstm = tf.keras.models.load_model("models/lstm.h5")
    meta = pickle.load(open("models/meta.pkl", "rb"))
    scaler = pickle.load(open("models/scaler.pkl", "rb"))
    features = pickle.load(open("models/features.pkl", "rb"))

    print("Processing 2026 data...")
    df_m15 = generate_features(load_data("Data/M15.csv"), "M15_")
    df_h1 = generate_features(load_data("Data/H1.csv"), "H1_")
    df_h4 = generate_features(load_data("Data/H4.csv"), "H4_")
    
    df_m15["TARGET"] = generate_labels(df_m15["M15_CLOSE_PRICE"], df_m15["HIGH"], df_m15["LOW"])
    
    df_h1.columns = [f"H1_{c}" if not c.startswith("H1_") else c for c in df_h1.columns]
    df_h4.columns = [f"H4_{c}" if not c.startswith("H4_") else c for c in df_h4.columns]
    merged = pd.merge_asof(df_m15, df_h1, left_index=True, right_index=True)
    merged = pd.merge_asof(merged, df_h4, left_index=True, right_index=True)
    
    # Filter for 2026
    df_2026 = merged[merged.index >= '2026-01-01'].dropna(subset=["TARGET"]).ffill()
    
    if df_2026.empty:
        print("Error: No 2026 data found.")
        return

    X = df_2026[features]
    y = df_2026["TARGET"]
    X_scaled = scaler.transform(X)
    X_lstm = X_scaled.reshape((X_scaled.shape[0], 1, X_scaled.shape[1]))

    print("Generating ensemble predictions...")
    xgb_probs = xgb.predict_proba(X_scaled)[:, 1]
    lstm_probs = lstm.predict(X_lstm, verbose=0).flatten()
    meta_input = np.column_stack((xgb_probs, lstm_probs))
    
    final_probs = meta.predict_proba(meta_input)[:, 1]
    
    # High Confidence Filter (95% threshold + Volatility Filter)
    threshold = 0.95
    atr_vals = df_2026["M15_ATR14"].values
    atr_ma_vals = df_2026["M15_ATR14_MA"].values
    
    mask = ((final_probs >= threshold) | (final_probs <= (1 - threshold))) & (atr_vals > atr_ma_vals)
    
    y_test = y[mask]
    preds = (final_probs[mask] >= 0.5).astype(int)

    if len(y_test) > 0:
        acc = accuracy_score(y_test, preds)
        prec = precision_score(y_test, preds)
        cm = confusion_matrix(y_test, preds)
        
        print("\n" + "="*40)
        print(f"RESULTS FOR 2026 (Threshold: {int(threshold*100)}%)")
        print("="*40)
        print(f"Total 2026 Samples: {len(df_2026)}")
        print(f"Trades Detected:    {len(y_test)}")
        print(f"Accuracy:           {acc*100:.2f}%")
        print(f"Precision:          {prec*100:.2f}%")
        print("\nConfusion Matrix:")
        print(cm)
        print("="*40)
    else:
        print(f"\nNo trades met the {int(threshold*100)}% threshold in the 2026 data.")

if __name__ == "__main__":
    main()
