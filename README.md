# 🏆 AI XAU Trader Pro
### *Next-Gen Gold (XAUUSD) Trading with 39-Feature AI Ensemble*

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)](https://www.python.org/)
[![XGBoost](https://img.shields.io/badge/XGBoost-1b5e20?style=for-the-badge)](https://xgboost.readthedocs.io/)
[![TensorFlow](https://img.shields.io/badge/TensorFlow-%23FF6F00.svg?style=for-the-badge&logo=TensorFlow&logoColor=white)](https://www.tensorflow.org/)
[![MetaTrader 5](https://img.shields.io/badge/MT5-005EB8?style=for-the-badge)](https://www.mql5.com/en/docs/python_metatrader5)

AI XAU Trader Pro is a high-performance, automated trading system specifically engineered for **XAUUSD (Gold)**. By combining **XGBoost**, **LSTM Neural Networks**, and a **Logistic Regression Meta-Model**, the bot filters market noise with extreme precision, only executing trades when confidence exceeds 95%.

---

## ✨ Key Features

| Feature | Description |
| :--- | :--- |
| **🧠 Triple-Model Ensemble** | XGBoost (Patterns) + LSTM (Momentum) + Meta-Model (Decision). |
| **⚡ Real-time Dashboard** | Live TradingView charting & AI thought-process visualization. |
| **🛡️ Pro Risk Management** | 3-Loss Pause mechanism, ATR Volatility Gates, and 95% Confidence Threshold. |
| **📊 39-Feature Engine** | Advanced technical analysis including RSI, EMA Slopes, and custom volatility metrics. |
| **🔌 MT5 Integration** | Seamless bridge between AI logic and MetaTrader 5 execution. |

---

## 🏗️ System Architecture

The bot operates on a **modular microservice-inspired architecture**:

1.  **Signal Engine:** Processes 39 technical features across M15, H1, and H4 timeframes.
2.  **AI Ensemble:**
    *   **XGBoost:** Identifies complex non-linear price patterns.
    *   **LSTM:** Analyzes temporal dependencies and sequential price action.
    *   **Meta-Model:** The "Judge" that weighs model outputs to produce a final % confidence.
3.  **Trade Executor:** Manages entries, SL/TP levels, and real-time trade tracking.
4.  **MT5 Connector:** Low-latency bridge for price data and order routing.

---

## 🚀 Getting Started

### 1. Prerequisites
*   Python 3.9+
*   MetaTrader 5 Terminal installed & logged in.
*   [Enable Algo Trading] in MT5 settings.

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/your-repo/trade-bot-final.git
cd trade-bot-final

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Rename `.env.example` to `.env` (if applicable) and configure your MT5 credentials:
```env
MT5_LOGIN=your_login
MT5_PASSWORD=your_password
MT5_SERVER=your_server
```

### 4. Running the Bot
```bash
# Start the FastAPI Backend & Trading Engine
python -m backend.main
```
Navigate to `http://localhost:8000` to view the **Live AI Dashboard**.

---

## 🧠 Model Retraining Guide

To adapt to new market conditions, follow the "Smart Training" pipeline:

1.  **Data Export:** Export `M15.csv`, `H1.csv`, and `H4.csv` from MT5 to the `Data/` folder.
2.  **Run Pipeline:**
    ```bash
    python train_advanced.py
    ```
3.  **Auto-Deploy:** The bot will automatically detect the new `.pkl` and `.h5` files in the `models/` directory upon restart.

---

## 📂 Project Structure

```text
├── 📂 backend           # FastAPI App & Trading Logic
│   ├── 🛰️ mt5_connector.py   # MT5 API Bridge
│   ├── 🧠 signal_engine.py   # Feature Engineering & AI Logic
│   └── ⚡ trade_executor.py  # Order Management
├── 📂 frontend          # Web Dashboard (HTML/JS)
├── 📂 models            # Trained AI Weights & Scalers
├── 🧪 train_advanced.py # The 39-Feature Training Pipeline
└── 🛡️ risk_manager.py   # Global Risk Parameters
```

---

## ⚠️ Risk Warning
Automated trading carries substantial risk. This software is provided for **educational and research purposes only**. Past performance of AI models is not indicative of future results. **Always start on a Demo Account.**

---
*Developed with ❤️ for Quantitative Trading.*

## ✨ README Improvement Notes

### 📌 Formatting Enhancements Needed
- Improve heading hierarchy for better readability
- Ensure consistent spacing between sections
- Use proper Markdown formatting for code blocks and lists
- Align all installation and usage steps properly

### 🚀 Suggested Structure Upgrade
- Introduction
- Features
- Tech Stack
- Installation
- Usage
- Project Structure
- Contribution Guidelines
- License

### 🛠️ Documentation Improvements
- Add badges (optional): build, license, contributors
- Add screenshots for better UI understanding
- Standardize code blocks for commands

### 🎯 Goal
Improve onboarding experience for new contributors and users by making README more structured, readable, and professional.


