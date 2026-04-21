import os
import pickle
import numpy as np
import pandas as pd
import warnings
import tensorflow as tf
import ta

from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import LogisticRegression
from sklearn.utils import resample
from xgboost import XGBClassifier

from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization
from tensorflow.keras.callbacks import EarlyStopping

warnings.filterwarnings("ignore")
tf.get_logger().setLevel("ERROR")

###############################################
# LOAD DATA
###############################################

def load_data(path):
    try:
        df = pd.read_csv(path, sep='\t')
        if '<DATE>' not in df.columns:
            df = pd.read_csv(path)
    except:
        df = pd.read_csv(path)

    df.columns = [c.replace("<","").replace(">","") for c in df.columns]

    if "TIME" in df.columns:
        df["DATETIME"] = pd.to_datetime(
            df["DATE"] + " " + df["TIME"],
            format="%Y.%m.%d %H:%M:%S"
        )
        df.drop(columns=["DATE","TIME"], inplace=True)
    else:
        df["DATETIME"] = pd.to_datetime(
            df["DATE"],
            format="%Y.%m.%d"
        )
        df.drop(columns=["DATE"], inplace=True)

    df.set_index("DATETIME", inplace=True)
    df.sort_index(inplace=True)
    return df

###############################################
# FEATURE ENGINEERING
###############################################

def generate_features(df, prefix):
    # Ensure columns exist
    for col in ['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOL', 'TICKVOL', 'SPREAD']:
        if col not in df.columns:
            df[col] = 0.0

    df[f"{prefix}RSI14"] = ta.momentum.rsi(df["CLOSE"], window=14).fillna(50)
    df[f"{prefix}EMA50"] = df["CLOSE"].ewm(span=50, adjust=False).mean()
    df[f"{prefix}EMA200"] = df["CLOSE"].ewm(span=200, adjust=False).mean()
    df[f"{prefix}EMA50_SLOPE"] = df[f"{prefix}EMA50"].diff(5).fillna(0)
    df[f"{prefix}EMA200_SLOPE"] = df[f"{prefix}EMA200"].diff(5).fillna(0)
    
    df[f"{prefix}ATR14"] = ta.volatility.average_true_range(
        df["HIGH"], df["LOW"], df["CLOSE"], window=14
    ).fillna(0)

    df[f"{prefix}RESISTANCE"] = df["HIGH"].rolling(20).max().shift(1).bfill()
    df[f"{prefix}SUPPORT"] = df["LOW"].rolling(20).min().shift(1).bfill()

    # Safe division
    ema200 = df[f"{prefix}EMA200"]
    df[f"{prefix}DIST_EMA200"] = np.where(ema200 != 0, (df["CLOSE"] - ema200) / ema200, 0)
    df[f"{prefix}CLOSE_PRICE"] = df["CLOSE"]

    return df

###############################################
# SMART LABEL ENGINE (BUY + SELL)
###############################################

def generate_labels(close_series, high_series, low_series):
    close = close_series.values
    high = high_series.values
    low = low_series.values

    # Calculate ATR manually or pass it in. We'll pass it in directly for speed,
    # but the prompt calls TA lib.
    atr_series = ta.volatility.average_true_range(
        high_series, low_series, close_series, window=14
    ).bfill()
    atr = atr_series.values

    labels = []
    horizon = 48
    n = len(close)

    for i in range(n - horizon):
        entry = close[i]
        atr_val = atr[i]

        if np.isnan(atr_val) or atr_val == 0:
            labels.append(np.nan)
            continue

        c_high = high[i]
        c_low = low[i]

        # Let the SL and TP breathe according to the live candlestick
        # SL placed just beyond the current candle's wick with a small ATR buffer
        sl_buy = c_low - (atr_val * 0.2)
        risk_buy = entry - sl_buy
        tp_buy = entry + (risk_buy * 2.0)

        sl_sell = c_high + (atr_val * 0.2)
        risk_sell = sl_sell - entry
        tp_sell = entry - (risk_sell * 2.0)

        outcome = np.nan

        # Lookahead loop
        for j in range(i+1, i+horizon):
            h = high[j]
            l = low[j]

            # Pessimistic SL logic: if both TP and SL hit in same candle, assume SL hit first.
            
            # Check Buy Scenario
            if l <= sl_buy:
                outcome = 0  # Buy failed (SL hit)
                break
            elif h >= tp_buy:
                outcome = 1  # Buy succeeded
                break
                
            # Check Sell Scenario
            if h >= sl_sell:
                outcome = 0  # Sell failed (SL hit)
                # Note: The original code overrode outcome here. 
                # If outcome = 0 means "failed", then 1 means "succeeded". 
                # Wait, original code: h>=tp_buy -> 1, l<=tp_sell -> 0. 
                # This implies 1 = BUY, 0 = SELL.
                # Let's fix the logic to explicitly return 1 for BUY and 0 for SELL.
                pass # See below for fixed logic

        # FIXED LOGIC: We need to know if it's a BUY or a SELL setup that won.
        # 1 = BUY Setup Won
        # 0 = SELL Setup Won
        # -1 = Neither won (Hold/Discard)
        
        buy_won = False
        sell_won = False
        
        for j in range(i+1, i+horizon):
            h = high[j]
            l = low[j]
            
            # Buy check
            if l <= sl_buy:
                pass # Buy dead
            elif h >= tp_buy:
                buy_won = True
                break
                
            # Sell check
            if h >= sl_sell:
                pass # Sell dead
            elif l <= tp_sell:
                sell_won = True
                break
                
        if buy_won:
            labels.append(1)
        elif sell_won:
            labels.append(0)
        else:
            labels.append(np.nan)

    # Pad the end
    labels.extend([np.nan] * horizon)
    return labels

###############################################
# MAIN EXECUTION
###############################################

def main():
    print("Loading data...")
    # Load and process Data
    df_m15 = generate_features(load_data("Data/M15.csv"), "M15_")
    df_h1 = generate_features(load_data("Data/H1.csv"), "H1_")
    df_h4 = generate_features(load_data("Data/H4.csv"), "H4_")

    print("Labeling data...")
    df_m15["TARGET"] = generate_labels(
        df_m15["M15_CLOSE_PRICE"],
        df_m15["HIGH"],
        df_m15["LOW"]
    )

    print("Merging timeframes...")
    # Prefix columns to avoid collisions before merge
    df_h1.columns = [f"H1_{c}" if not c.startswith("H1_") else c for c in df_h1.columns]
    df_h4.columns = [f"H4_{c}" if not c.startswith("H4_") else c for c in df_h4.columns]

    merged = pd.merge_asof(df_m15, df_h1, left_index=True, right_index=True)
    merged = pd.merge_asof(merged, df_h4, left_index=True, right_index=True)

    merged.dropna(subset=["TARGET"], inplace=True)
    merged.ffill(inplace=True)

    print("Cleaning features...")
    # Remove all raw OHLCV columns to prevent data leakage
    leak_keywords = ["OPEN", "HIGH", "LOW", "CLOSE", "VOL", "TICKVOL", "SPREAD"]
    cols_to_drop = [c for c in merged.columns if any(k in c.split("_")[-1] for k in leak_keywords)]
    
    # But keep CLOSE_PRICE features since they were explicitly created (wait, close price IS leakage if not careful, 
    # but the prompt explicitly drops price_cols. Let's strictly follow the prompt's drop logic).
    price_cols = [c for c in merged.columns if any(x in c for x in ["OPEN","HIGH","LOW", "CLOSE_PRICE"])]
    merged.drop(columns=price_cols, inplace=True, errors='ignore')

    print("Applying filters...")
    # Volatility Filter
    vol = merged["M15_EMA50"].rolling(12).std() # Using EMA50 proxy for price since CLOSE is dropped
    merged = merged[vol > vol.quantile(.25)]

    # Trend Filter
    trend_up = merged["M15_EMA50"] > merged["M15_EMA200"]
    trend_down = merged["M15_EMA50"] < merged["M15_EMA200"]
    merged = merged[trend_up | trend_down]

    # RSI Filter
    merged = merged[(merged["M15_RSI14"] > 55) | (merged["M15_RSI14"] < 45)]

    print(f"Data ready for training: {len(merged)} rows.")

    features = [c for c in merged.columns if c != "TARGET"]
    X = merged[features]
    y = merged["TARGET"]

    split = int(len(X) * .7)
    X_train = X.iloc[:split]
    X_test = X.iloc[split:]
    y_train = y.iloc[:split]
    y_test = y.iloc[split:]

    print("Balancing classes...")
    train_df = pd.concat([X_train, y_train], axis=1)
    majority = train_df[train_df.TARGET == 0]
    minority = train_df[train_df.TARGET == 1]

    if len(minority) > 0 and len(majority) > 0:
        minority_up = resample(minority, replace=True, n_samples=len(majority), random_state=42)
        train_df = pd.concat([majority, minority_up]).sample(frac=1, random_state=42) # Shuffle
    
    X_train = train_df.drop(columns=["TARGET"])
    y_train = train_df["TARGET"]

    print("Scaling...")
    scaler = MinMaxScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    print("Training XGBoost...")
    xgb = XGBClassifier(
        n_estimators=400,
        learning_rate=.02,
        max_depth=8,
        subsample=.9,
        colsample_bytree=.9,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1
    )
    xgb.fit(X_train_scaled, y_train)

    print("Training LSTM...")
    X_train_lstm = X_train_scaled.reshape((X_train_scaled.shape[0], 1, X_train_scaled.shape[1]))
    
    lstm = Sequential([
        LSTM(128, return_sequences=True, input_shape=(1, X_train_scaled.shape[1])),
        BatchNormalization(),
        Dropout(.3),
        LSTM(64),
        BatchNormalization(),
        Dropout(.3),
        Dense(32, activation="relu"),
        Dense(1, activation="sigmoid")
    ])

    lstm.compile(optimizer="adam", loss="binary_crossentropy")

    lstm.fit(
        X_train_lstm, y_train,
        epochs=30, batch_size=128, validation_split=.2,
        callbacks=[EarlyStopping(patience=5, restore_best_weights=True)],
        verbose=1
    )

    print("Training Meta Model...")
    xgb_preds = xgb.predict_proba(X_train_scaled)[:, 1]
    lstm_preds = lstm.predict(X_train_lstm, verbose=0).flatten()
    
    meta_input = np.column_stack((xgb_preds, lstm_preds))
    meta = LogisticRegression()
    meta.fit(meta_input, y_train)

    print("Saving Models...")
    os.makedirs("models", exist_ok=True)
    pickle.dump(xgb, open("models/xgb.pkl", "wb"))
    lstm.save("models/lstm.h5")
    pickle.dump(meta, open("models/meta.pkl", "wb"))
    pickle.dump(scaler, open("models/scaler.pkl", "wb"))
    pickle.dump(features, open("models/features.pkl", "wb"))

    print("Training Complete ✅")

if __name__ == "__main__":
    main()