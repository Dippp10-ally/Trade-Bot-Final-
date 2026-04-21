import re

def check():
    min_equity = 1000.0
    initial_equity = 1000.0
    
    with open('trade_simulation_results.txt', 'r') as f:
        lines = f.readlines()
    
    found = False
    for line in lines:
        # Match equity values like $10200.00
        match = re.search(r'\$(\d+\.\d+)', line)
        if match:
            equity = float(match.group(1))
            if not found: # The first equity found is actually the first trade
                min_equity = equity
                found = True
            else:
                if equity < min_equity:
                    min_equity = equity
                    
    print(f"Initial Equity: ${initial_equity:.2f}")
    print(f"Minimum Equity Reached: ${min_equity:.2f}")
    if min_equity < initial_equity:
        drawdown = ((initial_equity - min_equity) / initial_equity) * 100
        print(f"Max Drawdown from Initial: {drawdown:.2f}%")
    else:
        print("Equity never dropped below initial.")

if __name__ == "__main__":
    check()
