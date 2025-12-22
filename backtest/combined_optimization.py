import pandas as pd
import numpy as np
import json
import os
import random
from datetime import datetime

# ============ Configuration ============
ETF_CODE = "512890"
INITIAL_CAPITAL = 100000
ITERATIONS = 3000  # Increased iterations

def load_data():
    """Load data from JSON (Price Only)"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, 'backtest_result.json')
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Convert to DataFrame
    daily = data['daily_values']['strategy']
    df = pd.DataFrame([{
        'date': pd.to_datetime(d['date']), 
        'close': d['close']
    } for d in daily])
    df = df.sort_values('date').reset_index(drop=True)
    return df

# ============ Indicator Functions ============

def calculate_rsi_ema(series, period):
    """RSI with EMA smoothing"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    
    alpha = 1 / period
    avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_volatility(series, window):
    """Historical Volatility (Annualized %)"""
    log_ret = np.log(series / series.shift(1))
    vol = log_ret.rolling(window=window).std() * np.sqrt(252) * 100
    return vol

# ============ Backtest Engine ============

def run_combined_backtest(df, params):
    close = df['close']
    
    # Calculate Indicators
    rsi = calculate_rsi_ema(close, params['rsi_period'])
    vol = calculate_volatility(close, params['vol_window'])
    
    # Dynamic Thresholds
    # Logic: High Vol -> Lower Buy Threshold (Wait for deeper crash)
    #        Low Vol -> Higher Buy Threshold (Buy shallow dip)
    
    # We use a simple linear adjustment:
    # threshold = base - k * (vol - 15)  (Assuming 15 is avg vol)
    
    adj_buy = params['rsi_buy_base'] - params['k_vol'] * (vol - 15)
    adj_sell = params['rsi_sell_base'] + params['k_vol'] * (vol - 15)
    
    # Clip to reasonable range
    adj_buy = adj_buy.clip(20, 50)
    adj_sell = adj_sell.clip(60, 90)
    
    buy_signal = rsi < adj_buy
    sell_signal = rsi > adj_sell
        
    # Simulation
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    start_val = INITIAL_CAPITAL
    
    price_arr = close.values
    buy_arr = buy_signal.values
    sell_arr = sell_signal.values
    
    for i in range(len(price_arr)):
        if i < 50: continue
        
        if position == 0:
            if buy_arr[i]:
                shares = cash / price_arr[i]
                cash = 0
                position = 1
        elif position == 1:
            if sell_arr[i]:
                cash = shares * price_arr[i]
                shares = 0
                position = 0
                
    final_value = cash + shares * price_arr[-1]
    ret = (final_value - start_val) / start_val * 100
    return ret

def generate_random_params():
    return {
        'rsi_period': 15,
        'rsi_buy_base': random.randint(25, 45),
        'rsi_sell_base': random.randint(65, 85),
        'vol_window': random.randint(10, 60),
        'k_vol': random.uniform(-0.5, 1.0) # Can be positive or negative
    }

def main():
    print(f"Loading data (Price Only) and optimizing RSI + Volatility ({ITERATIONS} iterations)...")
    df = load_data()
    
    best_return = -999
    best_params = None
    
    # Baseline
    base_params = {
        'rsi_period': 15, 'rsi_buy_base': 32, 'rsi_sell_base': 77,
        'vol_window': 20, 'k_vol': 0 # Disable dynamic
    }
    base_return = run_combined_backtest(df, base_params)
    print(f"Baseline RSI(15) 32/77 Return: {base_return:.2f}%")
    
    for i in range(ITERATIONS):
        params = generate_random_params()
        
        ret = run_combined_backtest(df, params)
        
        if ret > best_return:
            best_return = ret
            best_params = params
            print(f"New Best [{i}]: {ret:.2f}% | Params: {json.dumps(params)}")
            
    print("\nOptimization Complete.")
    print(f"Top Return: {best_return:.2f}% (Baseline: {base_return:.2f}%)")
    print("Best Parameters:")
    print(json.dumps(best_params, indent=2))
    
    with open('backtest/best_combined_params.json', 'w') as f:
        json.dump(best_params, f, indent=2)

if __name__ == "__main__":
    main()
