"""
生成多组RSI策略参数的回测数据
包含 66/81, 68/71, 72/81 三组策略曲线

注意：512890是累积型ETF，分红已自动再投资体现在价格中，无需额外处理分红
"""

import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

# ============ 配置参数 ============
ETF_CODE = "512890"
ETF_NAME = "红利低波ETF"
RSI_PERIOD = 14
INITIAL_CAPITAL = 100000

# 多组策略参数（按回测收益率排序）
STRATEGIES = [
    {'buy': 34, 'sell': 78, 'name': 'strategy_34_78', 'label': 'RSI(14) 34/78', 'primary': True},
    {'buy': 36, 'sell': 78, 'name': 'strategy_36_78', 'label': 'RSI(14) 36/78'},
    {'buy': 66, 'sell': 81, 'name': 'strategy_66_81', 'label': 'RSI(14) 66/81'},
]

# 理想化策略参数（EMA平滑，小数份额 - 等同ETF联结基金交易）
IDEAL_STRATEGY = {
    'rsi_period': 15,
    'buy': 32, 
    'sell': 77, 
    'name': 'strategy_ideal_15_32_77', 
    'label': 'RSI(15) 32/77 联结基金'
}


def calculate_rsi(prices, period=14):
    """计算RSI指标"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    
    for i in range(period, len(prices)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_rsi_ema(prices, period):
    """计算RSI指标（使用EMA平滑，更敏感）"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    
    # 使用EMA而非SMA
    alpha = 1 / period
    avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def add_moving_averages(df, short_window=20, long_window=60):
    """计算短期/长期均线并返回副本"""
    ma_df = df.copy()
    ma_df['ma_short'] = ma_df['close'].rolling(window=short_window, min_periods=short_window).mean()
    ma_df['ma_long'] = ma_df['close'].rolling(window=long_window, min_periods=long_window).mean()
    return ma_df


def add_macd(df, fast=12, slow=26, signal=9):
    """计算 MACD 指标并返回副本"""
    macd_df = df.copy()
    macd_df['ema_fast'] = macd_df['close'].ewm(span=fast, adjust=False).mean()
    macd_df['ema_slow'] = macd_df['close'].ewm(span=slow, adjust=False).mean()
    macd_df['macd'] = macd_df['ema_fast'] - macd_df['ema_slow']
    macd_df['macd_signal'] = macd_df['macd'].ewm(span=signal, adjust=False).mean()
    return macd_df


def add_bollinger(df, window=20, num_std=2):
    """计算布林带"""
    b_df = df.copy()
    b_df['bb_mid'] = b_df['close'].rolling(window=window, min_periods=window).mean()
    b_df['bb_std'] = b_df['close'].rolling(window=window, min_periods=window).std()
    b_df['bb_upper'] = b_df['bb_mid'] + num_std * b_df['bb_std']
    b_df['bb_lower'] = b_df['bb_mid'] - num_std * b_df['bb_std']
    return b_df


def add_donchian(df, window=20):
    """计算唐奇安通道"""
    d_df = df.copy()
    d_df['don_high'] = d_df['close'].rolling(window=window, min_periods=window).max()
    d_df['don_low'] = d_df['close'].rolling(window=window, min_periods=window).min()
    return d_df


def add_atr(df, window=14):
    """计算ATR用于移动止损"""
    a_df = df.copy()
    # 如果缺少高低价列，用收盘价代替，避免KeyError
    if 'high' not in a_df.columns:
        a_df['high'] = a_df['close']
    if 'low' not in a_df.columns:
        a_df['low'] = a_df['close']
    a_df['prev_close'] = a_df['close'].shift(1)
    a_df['tr'] = np.max([
        (a_df['high'] - a_df['low']).abs(),
        (a_df['high'] - a_df['prev_close']).abs(),
        (a_df['low'] - a_df['prev_close']).abs()
    ], axis=0)
    a_df['atr'] = a_df['tr'].rolling(window=window, min_periods=window).mean()
    return a_df


def add_kdj(df, n=9, k_smooth=3, d_smooth=3):
    """计算 KDJ 指标"""
    kdj_df = df.copy()
    # 如果缺少高低价列，用收盘价代替，避免KeyError
    if 'high' not in kdj_df.columns:
        kdj_df['high'] = kdj_df['close']
    if 'low' not in kdj_df.columns:
        kdj_df['low'] = kdj_df['close']
    low_list = kdj_df['low'].rolling(window=n, min_periods=n).min()
    high_list = kdj_df['high'].rolling(window=n, min_periods=n).max()
    rsv = (kdj_df['close'] - low_list) / (high_list - low_list) * 100
    kdj_df['K'] = rsv.ewm(alpha=1 / k_smooth, adjust=False, min_periods=n).mean()
    kdj_df['D'] = kdj_df['K'].ewm(alpha=1 / d_smooth, adjust=False, min_periods=n).mean()
    kdj_df['J'] = 3 * kdj_df['K'] - 2 * kdj_df['D']
    return kdj_df


def run_backtest_ideal(df, rsi_period, buy_threshold, sell_threshold):
    """执行理想化RSI策略回测（允许小数份额，EMA平滑）"""
    df = df.copy()
    df['rsi'] = calculate_rsi_ema(df['close'], rsi_period)
    
    cash = float(INITIAL_CAPITAL)
    shares = 0.0
    position = 0
    
    trades = []
    daily_values = []
    
    for i, row in df.iterrows():
        date = row['date']
        price = row['close']
        rsi = row['rsi']
        date_str = date.strftime('%Y-%m-%d')
        
        if pd.notna(rsi):
            if rsi < buy_threshold and position == 0:
                # 全仓买入（允许小数份额）
                shares = cash / price
                cost = cash
                cash = 0.0
                position = 1
                trades.append({
                    'date': date_str,
                    'action': '买入',
                    'price': price,
                    'shares': shares,
                    'amount': cost,
                    'rsi': rsi,
                    'total_shares': shares,
                    'cash': cash
                })
                    
            elif rsi > sell_threshold and position == 1:
                # 全仓卖出
                revenue = shares * price
                cash = revenue
                sell_shares = shares
                shares = 0.0
                position = 0
                trades.append({
                    'date': date_str,
                    'action': '卖出',
                    'price': price,
                    'shares': sell_shares,
                    'amount': revenue,
                    'rsi': rsi,
                    'total_shares': shares,
                    'cash': cash
                })
        
        total_value = cash + shares * price
        daily_values.append({
            'date': date_str,
            'close': price,
            'rsi': rsi if pd.notna(rsi) else None,
            'cash': cash,
            'shares': shares,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })
    
    return trades, daily_values


def get_data_from_json():
    """从本地JSON文件获取数据"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, "backtest_result.json")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 提取每日价格数据
    strategy_values = data['daily_values']['strategy']
    
    df = pd.DataFrame([{
        'date': pd.to_datetime(d['date']),
        'close': d['close']
    } for d in strategy_values])
    
    df = df.sort_values('date').reset_index(drop=True)
    
    # 提取其他基准数据
    benchmarks = {}
    for key in ['buyhold', 'buyhold_no_div', 'hs300', 'gold', 'nasdaq', 'sp500']:
        if key in data['daily_values'] and data['daily_values'][key]:
            benchmarks[key] = data['daily_values'][key]
    
    return df, benchmarks, data


def run_backtest(df, buy_threshold, sell_threshold):
    """执行RSI策略回测
    
    注意：512890是累积型ETF，分红已体现在价格中，无需处理分红
    """
    df = df.copy()
    df['rsi'] = calculate_rsi(df['close'], RSI_PERIOD)
    
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    
    trades = []
    daily_values = []
    
    for i, row in df.iterrows():
        date = row['date']
        price = row['close']
        rsi = row['rsi']
        date_str = date.strftime('%Y-%m-%d')
        
        # RSI信号判断
        if pd.notna(rsi):
            if rsi < buy_threshold and position == 0:
                shares_to_buy = int(cash / price / 100) * 100
                if shares_to_buy > 0:
                    cost = shares_to_buy * price
                    cash -= cost
                    shares += shares_to_buy
                    position = 1
                    trades.append({
                        'date': date_str,
                        'action': '买入',
                        'price': price,
                        'shares': shares_to_buy,
                        'amount': cost,
                        'rsi': rsi,
                        'total_shares': shares,
                        'cash': cash
                    })
                    
            elif rsi > sell_threshold and position == 1:
                if shares > 0:
                    sell_shares = int(shares / 100) * 100
                    if sell_shares > 0:
                        revenue = sell_shares * price
                        cash += revenue
                        shares -= sell_shares
                        if shares < 100:
                            cash += shares * price
                            shares = 0
                        position = 0
                        trades.append({
                            'date': date_str,
                            'action': '卖出',
                            'price': price,
                            'shares': sell_shares,
                            'amount': revenue,
                            'rsi': rsi,
                            'total_shares': shares,
                            'cash': cash
                        })
        
        total_value = cash + shares * price
        daily_values.append({
            'date': date_str,
            'close': price,
            'rsi': rsi if pd.notna(rsi) else None,
            'cash': cash,
            'shares': shares,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })
    
    return trades, daily_values


def run_backtest_ma_cross(df, short_window=20, long_window=60):
    """均线金叉/死叉策略（场内整手）"""
    ma_df = add_moving_averages(df, short_window, long_window)
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []

    for i, row in ma_df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        ma_s, ma_l = row['ma_short'], row['ma_long']
        prev = ma_df.iloc[i-1] if i > 0 else None

        golden_cross = prev is not None and prev['ma_short'] <= prev['ma_long'] and ma_s > ma_l
        dead_cross = prev is not None and prev['ma_short'] >= prev['ma_long'] and ma_s < ma_l

        if pd.notna(ma_s) and pd.notna(ma_l):
            if golden_cross and position == 0:
                shares_to_buy = int(cash / price / 100) * 100
                if shares_to_buy > 0:
                    cost = shares_to_buy * price
                    cash -= cost
                    shares += shares_to_buy
                    position = 1
                    trades.append({
                        'date': date_str,
                        'action': '买入',
                        'price': price,
                        'shares': shares_to_buy,
                        'amount': cost,
                        'signal': '金叉'
                    })
            elif dead_cross and position == 1:
                sell_shares = int(shares / 100) * 100
                if sell_shares > 0:
                    revenue = sell_shares * price
                    cash += revenue
                    shares -= sell_shares
                    if shares < 100:
                        cash += shares * price
                        shares = 0
                    position = 0
                    trades.append({
                        'date': date_str,
                        'action': '卖出',
                        'price': price,
                        'shares': sell_shares,
                        'amount': revenue,
                        'signal': '死叉'
                    })

        total_value = cash + shares * price
        daily_values.append({
            'date': date_str,
            'close': price,
            'ma_short': ma_s if pd.notna(ma_s) else None,
            'ma_long': ma_l if pd.notna(ma_l) else None,
            'cash': cash,
            'shares': shares,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })

    return trades, daily_values


def run_backtest_macd(df, fast=12, slow=26, signal=9):
    """MACD 金叉/死叉策略（场内整手）"""
    macd_df = add_macd(df, fast, slow, signal)
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []

    for i, row in macd_df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        macd_val = row['macd']
        sig_val = row['macd_signal']
        prev = macd_df.iloc[i-1] if i > 0 else None

        golden = prev is not None and prev['macd'] <= prev['macd_signal'] and macd_val > sig_val
        dead = prev is not None and prev['macd'] >= prev['macd_signal'] and macd_val < sig_val

        if pd.notna(macd_val) and pd.notna(sig_val):
            if golden and position == 0:
                shares_to_buy = int(cash / price / 100) * 100
                if shares_to_buy > 0:
                    cost = shares_to_buy * price
                    cash -= cost
                    shares += shares_to_buy
                    position = 1
                    trades.append({
                        'date': date_str,
                        'action': '买入',
                        'price': price,
                        'shares': shares_to_buy,
                        'amount': cost,
                        'signal': 'MACD金叉'
                    })
            elif dead and position == 1:
                sell_shares = int(shares / 100) * 100
                if sell_shares > 0:
                    revenue = sell_shares * price
                    cash += revenue
                    shares -= sell_shares
                    if shares < 100:
                        cash += shares * price
                        shares = 0
                    position = 0
                    trades.append({
                        'date': date_str,
                        'action': '卖出',
                        'price': price,
                        'shares': sell_shares,
                        'amount': revenue,
                        'signal': 'MACD死叉'
                    })

        total_value = cash + shares * price
        daily_values.append({
            'date': date_str,
            'close': price,
            'macd': macd_val if pd.notna(macd_val) else None,
            'macd_signal': sig_val if pd.notna(sig_val) else None,
            'cash': cash,
            'shares': shares,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })

    return trades, daily_values


def run_backtest_rsi_ma_filter(df, rsi_buy=34, rsi_sell=78, ma_window=60):
    """RSI + 均线过滤策略：低位买，高位或跌破均线卖（场内整手）"""
    ma_df = add_moving_averages(df, ma_window // 3, ma_window)  # 提供一个中期均线
    ma_df['rsi'] = calculate_rsi(ma_df['close'], RSI_PERIOD)
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []

    for i, row in ma_df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        rsi_val = row['rsi']
        ma_l = row['ma_long']

        buy_signal = pd.notna(rsi_val) and pd.notna(ma_l) and rsi_val < rsi_buy and price > ma_l and position == 0
        sell_signal = pd.notna(rsi_val) and ((rsi_val > rsi_sell and position == 1) or (pd.notna(ma_l) and price < ma_l and position == 1))

        if buy_signal:
            shares_to_buy = int(cash / price / 100) * 100
            if shares_to_buy > 0:
                cost = shares_to_buy * price
                cash -= cost
                shares += shares_to_buy
                position = 1
                trades.append({
                    'date': date_str,
                    'action': '买入',
                    'price': price,
                    'shares': shares_to_buy,
                    'amount': cost,
                    'rsi': rsi_val,
                    'signal': 'RSI+MA'
                })
        elif sell_signal:
            sell_shares = int(shares / 100) * 100
            if sell_shares > 0:
                revenue = sell_shares * price
                cash += revenue
                shares -= sell_shares
                if shares < 100:
                    cash += shares * price
                    shares = 0
                position = 0
                trades.append({
                    'date': date_str,
                    'action': '卖出',
                    'price': price,
                    'shares': sell_shares,
                    'amount': revenue,
                    'rsi': rsi_val,
                    'signal': 'RSI+MA 卖出'
                })

        total_value = cash + shares * price
        daily_values.append({
            'date': date_str,
            'close': price,
            'rsi': rsi_val if pd.notna(rsi_val) else None,
            'ma_long': ma_l if pd.notna(ma_l) else None,
            'cash': cash,
            'shares': shares,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })

    return trades, daily_values


def run_backtest_bollinger(df, window=20, num_std=2):
    """布林带突破/回落策略（场内整手）"""
    b_df = add_bollinger(df, window, num_std)
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []

    for _, row in b_df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        upper, lower = row['bb_upper'], row['bb_lower']

        breakout = pd.notna(upper) and price > upper and position == 0
        breakdown = pd.notna(lower) and price < lower and position == 1

        if breakout:
            shares_to_buy = int(cash / price / 100) * 100
            if shares_to_buy > 0:
                cost = shares_to_buy * price
                cash -= cost
                shares += shares_to_buy
                position = 1
                trades.append({
                    'date': date_str,
                    'action': '买入',
                    'price': price,
                    'shares': shares_to_buy,
                    'amount': cost,
                    'signal': '突破上轨'
                })
        elif breakdown:
            sell_shares = int(shares / 100) * 100
            if sell_shares > 0:
                revenue = sell_shares * price
                cash += revenue
                shares -= sell_shares
                if shares < 100:
                    cash += shares * price
                    shares = 0
                position = 0
                trades.append({
                    'date': date_str,
                    'action': '卖出',
                    'price': price,
                    'shares': sell_shares,
                    'amount': revenue,
                    'signal': '跌破下轨'
                })

        total_value = cash + shares * price
        daily_values.append({
            'date': date_str,
            'close': price,
            'bb_upper': upper if pd.notna(upper) else None,
            'bb_lower': lower if pd.notna(lower) else None,
            'cash': cash,
            'shares': shares,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })

    return trades, daily_values


def run_backtest_donchian(df, window=20):
    """唐奇安通道突破/回落策略（场内整手）"""
    d_df = add_donchian(df, window)
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []

    for _, row in d_df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        high, low = row['don_high'], row['don_low']

        breakout = pd.notna(high) and price > high and position == 0
        breakdown = pd.notna(low) and price < low and position == 1

        if breakout:
            shares_to_buy = int(cash / price / 100) * 100
            if shares_to_buy > 0:
                cost = shares_to_buy * price
                cash -= cost
                shares += shares_to_buy
                position = 1
                trades.append({
                    'date': date_str,
                    'action': '买入',
                    'price': price,
                    'shares': shares_to_buy,
                    'amount': cost,
                    'signal': '突破高点'
                })
        elif breakdown:
            sell_shares = int(shares / 100) * 100
            if sell_shares > 0:
                revenue = sell_shares * price
                cash += revenue
                shares -= sell_shares
                if shares < 100:
                    cash += shares * price
                    shares = 0
                position = 0
                trades.append({
                    'date': date_str,
                    'action': '卖出',
                    'price': price,
                    'shares': sell_shares,
                    'amount': revenue,
                    'signal': '跌破低点'
                })

        total_value = cash + shares * price
        daily_values.append({
            'date': date_str,
            'close': price,
            'don_high': high if pd.notna(high) else None,
            'don_low': low if pd.notna(low) else None,
            'cash': cash,
            'shares': shares,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })

    return trades, daily_values


def run_backtest_atr_trailing(df, ma_window=60, atr_window=14, atr_mult=2):
    """价格站上均线买入，跌破 MA - k*ATR 卖出（场内整手）"""
    a_df = add_atr(df, atr_window)
    a_df = add_moving_averages(a_df, ma_window // 3, ma_window)
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []

    for _, row in a_df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        ma_l = row['ma_long']
        atr = row['atr']

        buy_signal = pd.notna(ma_l) and price > ma_l and position == 0
        stop_line = ma_l - atr_mult * atr if pd.notna(ma_l) and pd.notna(atr) else None
        sell_signal = stop_line is not None and price < stop_line and position == 1

        if buy_signal:
            shares_to_buy = int(cash / price / 100) * 100
            if shares_to_buy > 0:
                cost = shares_to_buy * price
                cash -= cost
                shares += shares_to_buy
                position = 1
                trades.append({
                    'date': date_str,
                    'action': '买入',
                    'price': price,
                    'shares': shares_to_buy,
                    'amount': cost,
                    'signal': 'MA+ATR 入场'
                })
        elif sell_signal:
            sell_shares = int(shares / 100) * 100
            if sell_shares > 0:
                revenue = sell_shares * price
                cash += revenue
                shares -= sell_shares
                if shares < 100:
                    cash += shares * price
                    shares = 0
                position = 0
                trades.append({
                    'date': date_str,
                    'action': '卖出',
                    'price': price,
                    'shares': sell_shares,
                    'amount': revenue,
                    'signal': '跌破ATR止损'
                })

        total_value = cash + shares * price
        daily_values.append({
            'date': date_str,
            'close': price,
            'ma_long': ma_l if pd.notna(ma_l) else None,
            'atr': atr if pd.notna(atr) else None,
            'cash': cash,
            'shares': shares,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })

    return trades, daily_values


def calculate_historical_volatility(prices, window=20):
    """计算历史波动率（年化百分比）"""
    log_returns = np.log(prices / prices.shift(1))
    hv = log_returns.rolling(window=window, min_periods=window).std() * np.sqrt(252) * 100
    return hv


def run_backtest_volatility(df, buy_thr, sell_thr):
    """执行波动率策略回测"""
    df = df.copy()
    df['hv'] = calculate_historical_volatility(df['close'], 20)
    
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []
    
    for _, row in df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        hv = row['hv']
        
        # 波动率信号
        buy_signal = pd.notna(hv) and hv > buy_thr and position == 0
        sell_signal = pd.notna(hv) and hv < sell_thr and position == 1
        
        if buy_signal:
            shares_to_buy = cash / price
            if shares_to_buy > 0:
                shares += shares_to_buy
                cash = 0
                position = 1
                trades.append({
                    'date': date_str, 'action': '买入', 'price': price, 
                    'shares': shares_to_buy, 'amount': shares_to_buy * price, 'hv': hv
                })
        elif sell_signal:
            if shares > 0:
                cash += shares * price
                trades.append({
                    'date': date_str, 'action': '卖出', 'price': price, 
                    'shares': shares, 'amount': shares * price, 'hv': hv
                })
                shares = 0
                position = 0
        
        total_value = cash + shares * price
        daily_values.append({
            'date': date_str, 'close': price, 'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })
        
    return trades, daily_values


def run_backtest_volume(df, buy_mult, sell_mult):
    """执行量能策略回测 (模拟成交量 - 与 volume_optimization.py 保持一致)"""
    df = df.copy()
    # 模拟成交量：基于价格波动率
    df['return_pct'] = df['close'].pct_change().fillna(0)
    df['volatility'] = df['return_pct'].abs()
    
    # 成交量 = 基础量 * (1 + 波动率影响) + 随机噪声
    np.random.seed(42)
    base_volume = 1000000
    df['volume'] = (
        base_volume * (1 + df['volatility'] * 50) +
        np.random.normal(0, base_volume * 0.2, len(df))
    )
    df['volume'] = df['volume'].clip(lower=base_volume * 0.5)
    
    df['vol_ma250'] = df['volume'].rolling(window=250, min_periods=250).mean()
    
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []
    
    for _, row in df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        vol = row['volume']
        vol_ma = row['vol_ma250']
        
        buy_signal = pd.notna(vol_ma) and vol > vol_ma * buy_mult and position == 0
        sell_signal = pd.notna(vol_ma) and vol < vol_ma * sell_mult and position == 1
        
        if buy_signal:
            shares_to_buy = cash / price
            if shares_to_buy > 0:
                shares += shares_to_buy
                cash = 0
                position = 1
                trades.append({
                    'date': date_str, 'action': '买入', 'price': price, 
                    'shares': shares_to_buy, 'amount': shares_to_buy * price, 'vol_ratio': vol/vol_ma
                })
        elif sell_signal:
            if shares > 0:
                cash += shares * price
                trades.append({
                    'date': date_str, 'action': '卖出', 'price': price, 
                    'shares': shares, 'amount': shares * price, 'vol_ratio': vol/vol_ma
                })
                shares = 0
                position = 0
        
        total_value = cash + shares * price
        daily_values.append({
            'date': date_str, 'close': price, 'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })
        
    return trades, daily_values


def run_backtest_ma_reverse(df, short_window, long_window):
    """执行反向均线策略回测 (死叉买入，金叉卖出)"""
    df = df.copy()
    df['ma_short'] = df['close'].rolling(window=short_window).mean()
    df['ma_long'] = df['close'].rolling(window=long_window).mean()
    
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        
        # 死叉买入 (MA8 下穿 MA72)
        dead_cross = (prev_row['ma_short'] >= prev_row['ma_long']) and (row['ma_short'] < row['ma_long'])
        # 金叉卖出 (MA8 上穿 MA72)
        golden_cross = (prev_row['ma_short'] <= prev_row['ma_long']) and (row['ma_short'] > row['ma_long'])
        
        buy_signal = dead_cross and position == 0
        sell_signal = golden_cross and position == 1
        
        if buy_signal:
            shares_to_buy = cash / price
            if shares_to_buy > 0:
                shares += shares_to_buy
                cash = 0
                position = 1
                trades.append({
                    'date': date_str, 'action': '买入', 'price': price, 
                    'shares': shares_to_buy, 'amount': shares_to_buy * price
                })
        elif sell_signal:
            if shares > 0:
                cash += shares * price
                trades.append({
                    'date': date_str, 'action': '卖出', 'price': price, 
                    'shares': shares, 'amount': shares * price
                })
                shares = 0
                position = 0
        
        total_value = cash + shares * price
        daily_values.append({
            'date': date_str, 'close': price, 'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })
        
    return trades, daily_values


def run_backtest_kdj(df, n=9, k_smooth=3, d_smooth=3):
    """KDJ 金叉/死叉策略（场内整手）"""
    k_df = add_kdj(df, n, k_smooth, d_smooth)
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []

    for i, row in k_df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        k_val, d_val = row['K'], row['D']
        prev = k_df.iloc[i-1] if i > 0 else None

        golden = prev is not None and prev['K'] <= prev['D'] and k_val > d_val
        dead = prev is not None and prev['K'] >= prev['D'] and k_val < d_val

        if pd.notna(k_val) and pd.notna(d_val):
            if golden and position == 0:
                shares_to_buy = int(cash / price / 100) * 100
                if shares_to_buy > 0:
                    cost = shares_to_buy * price
                    cash -= cost
                    shares += shares_to_buy
                    position = 1
                    trades.append({
                        'date': date_str,
                        'action': '买入',
                        'price': price,
                        'shares': shares_to_buy,
                        'amount': cost,
                        'signal': 'KDJ金叉'
                    })
            elif dead and position == 1:
                sell_shares = int(shares / 100) * 100
                if sell_shares > 0:
                    revenue = sell_shares * price
                    cash += revenue
                    shares -= sell_shares
                    if shares < 100:
                        cash += shares * price
                        shares = 0
                    position = 0
                    trades.append({
                        'date': date_str,
                        'action': '卖出',
                        'price': price,
                        'shares': sell_shares,
                        'amount': revenue,
                        'signal': 'KDJ死叉'
                    })

        total_value = cash + shares * price
        daily_values.append({
            'date': date_str,
            'close': price,
            'K': k_val if pd.notna(k_val) else None,
            'D': d_val if pd.notna(d_val) else None,
            'cash': cash,
            'shares': shares,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })

    return trades, daily_values


def run_backtest_dynamic_rsi(df, params):
    """执行 动态RSI策略 (基于波动率调整阈值)"""
    df = df.copy()
    
    # 1. 计算指标
    df['rsi'] = calculate_rsi_ema(df['close'], params['rsi_period'])
    
    # 计算波动率 (年化)
    df['log_ret'] = np.log(df['close'] / df['close'].shift(1))
    df['volatility'] = df['log_ret'].rolling(window=params['vol_window']).std() * np.sqrt(252) * 100
    
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily_values = []
    
    # 基础参数
    base_buy = params['rsi_buy_base']
    base_sell = params['rsi_sell_base']
    k_vol = params['k_vol']
    
    for i, row in df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        rsi = row['rsi']
        vol = row['volatility']
        
        if pd.isna(rsi) or pd.isna(vol):
            daily_values.append({
                'date': date_str, 'close': price, 'total_value': cash + shares * price,
                'return': 0
            })
            continue
            
        # 动态调整阈值
        # Optimization Logic:
        # buy = base - k * (vol - 15)
        # sell = base + k * (vol - 15)
        
        vol_diff = vol - 15
        current_buy_threshold = base_buy - k_vol * vol_diff
        current_sell_threshold = base_sell + k_vol * vol_diff
        
        # 限制范围
        current_buy_threshold = max(20, min(50, current_buy_threshold))
        current_sell_threshold = max(60, min(90, current_sell_threshold))
        
        buy_signal = rsi < current_buy_threshold and position == 0
        sell_signal = rsi > current_sell_threshold and position == 1
            
        if buy_signal:
            shares_to_buy = cash / price
            if shares_to_buy > 0:
                shares += shares_to_buy
                cash = 0
                position = 1
                trades.append({
                    'date': date_str, 'action': '买入', 'price': price, 
                    'shares': shares_to_buy, 'amount': shares_to_buy * price,
                    'reason': f"RSI({rsi:.1f}) < 动态阈值({current_buy_threshold:.1f}) | Vol:{vol:.1f}",
                    'rsi': rsi
                })
        elif sell_signal:
            if shares > 0:
                cash += shares * price
                trades.append({
                    'date': date_str, 'action': '卖出', 'price': price, 
                    'shares': shares, 'amount': shares * price,
                    'reason': f"RSI({rsi:.1f}) > 动态阈值({current_sell_threshold:.1f}) | Vol:{vol:.1f}",
                    'rsi': rsi
                })
                shares = 0
                position = 0
        
        total_value = cash + shares * price
        daily_values.append({
            'date': date_str, 'close': price, 'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })
        
    return trades, daily_values


def calculate_statistics(daily_values, trades):
    """计算统计指标"""
    if not daily_values:
        return {}
    
    returns = [d['return'] for d in daily_values]
    values = [d['total_value'] for d in daily_values]
    
    # 计算最大回撤
    peak = values[0]
    max_drawdown = 0
    for v in values:
        if v > peak:
            peak = v
        drawdown = (peak - v) / peak * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    # 计算年化收益（使用自然日天数，而非交易日数）
    trading_days = len(daily_values)
    total_return = returns[-1]
    # 计算起止日期的自然天数
    start_date = datetime.strptime(daily_values[0]['date'], '%Y-%m-%d')
    end_date = datetime.strptime(daily_values[-1]['date'], '%Y-%m-%d')
    calendar_days = (end_date - start_date).days
    annual_return = ((1 + total_return / 100) ** (365 / calendar_days) - 1) * 100 if calendar_days > 0 else 0
    
    # 交易统计
    buy_trades = [t for t in trades if t['action'] == '买入']
    sell_trades = [t for t in trades if t['action'] == '卖出']
    
    wins = 0
    for i, sell in enumerate(sell_trades):
        if i < len(buy_trades):
            if sell['price'] > buy_trades[i]['price']:
                wins += 1
    win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0
    
    return {
        'total_return': round(total_return, 2),
        'annual_return': round(annual_return, 2),
        'max_drawdown': round(max_drawdown, 2),
        'trade_count': len(buy_trades),
        'win_rate': round(win_rate, 2),
        'start_date': daily_values[0]['date'],
        'end_date': daily_values[-1]['date'],
        'days': trading_days,
        'calendar_days': calendar_days
    }


def calculate_buy_and_hold(df):
    """计算买入持有策略
    
    注意：512890是累积型ETF，分红已体现在前复权价格中
    """
    start_price = df.iloc[0]['close']
    shares = int(INITIAL_CAPITAL / start_price / 100) * 100
    remaining_cash = INITIAL_CAPITAL - shares * start_price
    
    daily_values = []
    for _, row in df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        
        total_value = remaining_cash + shares * price
        daily_values.append({
            'date': date_str,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })
    
    return daily_values


def main():
    print("=" * 60)
    print("生成多组RSI策略回测数据")
    print("=" * 60)
    
    # 1. 获取数据
    df, benchmarks, old_data = get_data_from_json()
    print(f"从本地JSON获取到 {len(df)} 条数据")
    print(f"数据范围: {df['date'].min()} 至 {df['date'].max()}")
    
    # 2. 执行所有策略回测
    all_results = {}
    primary_strategy = None  # 主策略 (66/81)
    primary_trades = None
    
    for strategy in STRATEGIES:
        buy = strategy['buy']
        sell = strategy['sell']
        name = strategy['name']
        label = strategy['label']
        
        print(f"\n执行 {label} 策略...")
        trades, daily_values = run_backtest(df, buy, sell)
        stats = calculate_statistics(daily_values, trades)
        
        all_results[name] = {
            'trades': trades,
            'daily_values': daily_values,
            'stats': stats,
            'label': label,
            'buy': buy,
            'sell': sell
        }
        
        # 保存主策略 (34/78 - 最优参数)
        if strategy.get('primary'):
            primary_strategy = all_results[name]
            primary_trades = trades
        
        print(f"  总收益率: {stats['total_return']:.2f}%")
        print(f"  年化收益: {stats['annual_return']:.2f}%")
        print(f"  最大回撤: {stats['max_drawdown']:.2f}%")
        print(f"  交易次数: {stats['trade_count']} 次")
    
    # 3. 执行理想化策略 RSI(15) EMA 32/77
    print(f"\n执行 {IDEAL_STRATEGY['label']} 策略...")
    ideal_trades, ideal_daily_values = run_backtest_ideal(
        df, 
        IDEAL_STRATEGY['rsi_period'], 
        IDEAL_STRATEGY['buy'], 
        IDEAL_STRATEGY['sell']
    )
    ideal_stats = calculate_statistics(ideal_daily_values, ideal_trades)
    
    all_results[IDEAL_STRATEGY['name']] = {
        'trades': ideal_trades,
        'daily_values': ideal_daily_values,
        'stats': ideal_stats,
        'label': IDEAL_STRATEGY['label'],
        'buy': IDEAL_STRATEGY['buy'],
        'sell': IDEAL_STRATEGY['sell'],
        'rsi_period': IDEAL_STRATEGY['rsi_period']
    }
    
    print(f"  总收益率: {ideal_stats['total_return']:.2f}%")
    print(f"  年化收益: {ideal_stats['annual_return']:.2f}%")
    print(f"  最大回撤: {ideal_stats['max_drawdown']:.2f}%")
    print(f"  交易次数: {ideal_stats['trade_count']} 次")

    # 3.5 执行新增多因子策略
    print("\n执行均线金叉策略 (MA20/MA60)...")
    ma_trades, ma_daily_values = run_backtest_ma_cross(df, 20, 60)
    ma_stats = calculate_statistics(ma_daily_values, ma_trades)
    all_results['strategy_ma_20_60'] = {
        'trades': ma_trades,
        'daily_values': ma_daily_values,
        'stats': ma_stats,
        'label': 'MA20/MA60 金叉',
        'short': 20,
        'long': 60
    }
    print(f"  总收益率: {ma_stats['total_return']:.2f}% | 年化: {ma_stats['annual_return']:.2f}% | 回撤: {ma_stats['max_drawdown']:.2f}%")

    print("执行 MACD 金叉策略 (12/26/9)...")
    macd_trades, macd_daily_values = run_backtest_macd(df, 12, 26, 9)
    macd_stats = calculate_statistics(macd_daily_values, macd_trades)
    all_results['strategy_macd'] = {
        'trades': macd_trades,
        'daily_values': macd_daily_values,
        'stats': macd_stats,
        'label': 'MACD(12,26,9) 金叉',
        'fast': 12,
        'slow': 26,
        'signal': 9
    }
    print(f"  总收益率: {macd_stats['total_return']:.2f}% | 年化: {macd_stats['annual_return']:.2f}% | 回撤: {macd_stats['max_drawdown']:.2f}%")

    print("执行 RSI+MA 过滤策略 (RSI 34/78 + MA60)...")
    rsi_ma_trades, rsi_ma_daily_values = run_backtest_rsi_ma_filter(df, 34, 78, 60)
    rsi_ma_stats = calculate_statistics(rsi_ma_daily_values, rsi_ma_trades)
    all_results['strategy_rsi_ma'] = {
        'trades': rsi_ma_trades,
        'daily_values': rsi_ma_daily_values,
        'stats': rsi_ma_stats,
        'label': 'RSI 34/78 + MA60'
    }
    print(f"  总收益率: {rsi_ma_stats['total_return']:.2f}% | 年化: {rsi_ma_stats['annual_return']:.2f}% | 回撤: {rsi_ma_stats['max_drawdown']:.2f}%")

    print("执行 布林带突破策略 (20日, 2倍标准差)...")
    bb_trades, bb_daily_values = run_backtest_bollinger(df, 20, 2)
    bb_stats = calculate_statistics(bb_daily_values, bb_trades)
    all_results['strategy_bb_20_2'] = {
        'trades': bb_trades,
        'daily_values': bb_daily_values,
        'stats': bb_stats,
        'label': '布林带 20±2'
    }
    print(f"  总收益率: {bb_stats['total_return']:.2f}% | 年化: {bb_stats['annual_return']:.2f}% | 回撤: {bb_stats['max_drawdown']:.2f}%")

    print("执行 唐奇安通道策略 (20日高低点)...")
    don_trades, don_daily_values = run_backtest_donchian(df, 20)
    don_stats = calculate_statistics(don_daily_values, don_trades)
    all_results['strategy_don_20'] = {
        'trades': don_trades,
        'daily_values': don_daily_values,
        'stats': don_stats,
        'label': '唐奇安20 突破'
    }
    print(f"  总收益率: {don_stats['total_return']:.2f}% | 年化: {don_stats['annual_return']:.2f}% | 回撤: {don_stats['max_drawdown']:.2f}%")

    print("执行 MA+ATR 移动止损策略 (MA60, ATR14*2)...")
    atr_trades, atr_daily_values = run_backtest_atr_trailing(df, 60, 14, 2)
    atr_stats = calculate_statistics(atr_daily_values, atr_trades)
    all_results['strategy_atr_trailing'] = {
        'trades': atr_trades,
        'daily_values': atr_daily_values,
        'stats': atr_stats,
        'label': 'MA60 + ATR2'
    }
    print(f"  总收益率: {atr_stats['total_return']:.2f}% | 年化: {atr_stats['annual_return']:.2f}% | 回撤: {atr_stats['max_drawdown']:.2f}%")

    print("执行 KDJ 金叉/死叉策略 (9,3,3)...")
    kdj_trades, kdj_daily_values = run_backtest_kdj(df, 9, 3, 3)
    kdj_stats = calculate_statistics(kdj_daily_values, kdj_trades)
    all_results['strategy_kdj'] = {
        'trades': kdj_trades,
        'daily_values': kdj_daily_values,
        'stats': kdj_stats,
        'label': 'KDJ(9,3,3)'
    }
    print(f"  总收益率: {kdj_stats['total_return']:.2f}% | 年化: {kdj_stats['annual_return']:.2f}% | 回撤: {kdj_stats['max_drawdown']:.2f}%")

    print("执行 波动率策略 (HV16/7)...")
    vol_trades, vol_daily_values = run_backtest_volatility(df, 16, 7)
    vol_stats = calculate_statistics(vol_daily_values, vol_trades)
    all_results['strategy_volatility'] = {
        'trades': vol_trades,
        'daily_values': vol_daily_values,
        'stats': vol_stats,
        'label': '波动率 HV16/7'
    }
    print(f"  总收益率: {vol_stats['total_return']:.2f}% | 年化: {vol_stats['annual_return']:.2f}% | 回撤: {vol_stats['max_drawdown']:.2f}%")

    print("执行 量能策略 (1.5倍/0.5倍)...")
    # volume_trades, volume_daily_values = run_backtest_volume(df, 1.5, 0.5)
    # volume_stats = calculate_statistics(volume_daily_values, volume_trades)
    all_results['strategy_volume'] = {
        'trades': [],
        'daily_values': [],
        'stats': {'total_return': 0, 'annual_return': 0, 'max_drawdown': 0, 'trade_count': 0},
        'label': '量能 1.5倍/0.5倍 (无数据)'
    }
    # print(f"  总收益率: {volume_stats['total_return']:.2f}% | 年化: {volume_stats['annual_return']:.2f}% | 回撤: {volume_stats['max_drawdown']:.2f}%")

    print("执行 反向均线策略 (MA8/72)...")
    ma_rev_trades, ma_rev_daily_values = run_backtest_ma_reverse(df, 8, 72)
    ma_rev_stats = calculate_statistics(ma_rev_daily_values, ma_rev_trades)
    all_results['strategy_ma_reverse'] = {
        'trades': ma_rev_trades,
        'daily_values': ma_rev_daily_values,
        'stats': ma_rev_stats,
        'label': '反向均线 MA8/72'
    }
    print(f"  总收益率: {ma_rev_stats['total_return']:.2f}% | 年化: {ma_rev_stats['annual_return']:.2f}% | 回撤: {ma_rev_stats['max_drawdown']:.2f}%")

    # 3.6 执行 动态RSI策略
    print("\n执行 RSI+波动率 动态调优策略...")
    dynamic_params = {
        "rsi_period": 15,
        "rsi_buy_base": 34,
        "rsi_sell_base": 71,
        "vol_window": 47,
        "k_vol": -0.43
    }
    dynamic_trades, dynamic_daily_values = run_backtest_dynamic_rsi(df, dynamic_params)
    dynamic_stats = calculate_statistics(dynamic_daily_values, dynamic_trades)
    all_results['strategy_dynamic'] = {
        'trades': dynamic_trades,
        'daily_values': dynamic_daily_values,
        'stats': dynamic_stats,
        'label': 'RSI+波动率 动态调优'
    }
    print(f"  总收益率: {dynamic_stats['total_return']:.2f}% | 年化: {dynamic_stats['annual_return']:.2f}% | 回撤: {dynamic_stats['max_drawdown']:.2f}%")
    
    # 4. 计算买入持有收益（无需分红处理）
    print("\n计算买入持有收益...")
    buyhold_values = calculate_buy_and_hold(df)
    buyhold_stats = calculate_statistics(buyhold_values, [])
    print(f"  总收益率: {buyhold_stats['total_return']:.2f}%")
    print(f"  年化收益: {buyhold_stats['annual_return']:.2f}%")
    
    # 5. 保留原有基准数据的统计
    old_stats = old_data['statistics']
    backtest_days = primary_strategy['stats']['days']
    
    # 5. 准备导出数据
    export_data = {
        'meta': {
            'etf_code': ETF_CODE,
            'etf_name': ETF_NAME,
            'strategy': 'RSI(14) < 34 买入, > 78 卖出 (最优参数)',
            'strategies': [{'buy': s['buy'], 'sell': s['sell'], 'label': s['label']} for s in STRATEGIES],
            'initial_capital': INITIAL_CAPITAL,
            'start_date': primary_strategy['stats']['start_date'],
            'end_date': primary_strategy['stats']['end_date'],
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        },
        'statistics': {
            'strategy': primary_strategy['stats'],
            # 添加其他策略统计
            'strategy_34_78': all_results['strategy_34_78']['stats'],
            'strategy_36_78': all_results['strategy_36_78']['stats'],
            'strategy_66_81': all_results['strategy_66_81']['stats'],
            'strategy_ideal': all_results[IDEAL_STRATEGY['name']]['stats'],
            'strategy_ma_20_60': all_results['strategy_ma_20_60']['stats'],
            'strategy_macd': all_results['strategy_macd']['stats'],
            'strategy_rsi_ma': all_results['strategy_rsi_ma']['stats'],
            'strategy_bb_20_2': all_results['strategy_bb_20_2']['stats'],
            'strategy_don_20': all_results['strategy_don_20']['stats'],
            'strategy_atr_trailing': all_results['strategy_atr_trailing']['stats'],
            'strategy_kdj': all_results['strategy_kdj']['stats'],
            'strategy_volatility': all_results['strategy_volatility']['stats'],
            'strategy_volume': all_results['strategy_volume']['stats'],
            'strategy_ma_reverse': all_results['strategy_ma_reverse']['stats'],
            'strategy_dynamic': all_results['strategy_dynamic']['stats'],
            'buyhold': buyhold_stats,
            'hs300_return': old_stats.get('hs300_return'),
            'hs300_annual': old_stats.get('hs300_annual'),
            'gold_return': old_stats.get('gold_return'),
            'gold_annual': old_stats.get('gold_annual'),
            'nasdaq_return': old_stats.get('nasdaq_return'),
            'nasdaq_annual': old_stats.get('nasdaq_annual'),
            'sp500_return': old_stats.get('sp500_return'),
            'sp500_annual': old_stats.get('sp500_annual'),
            'backtest_days': backtest_days,
        },
        'trades': ideal_trades,  # 使用理想化策略的交易记录（ETF联结基金）
        'trades_34_78': primary_trades,  # 保留原整手交易记录
        'trades_dynamic': all_results['strategy_dynamic']['trades'],  # 动态调优交易记录
        'daily_values': {
            'strategy': primary_strategy['daily_values'],
            'strategy_34_78': all_results['strategy_34_78']['daily_values'],
            'strategy_36_78': all_results['strategy_36_78']['daily_values'],
            'strategy_66_81': all_results['strategy_66_81']['daily_values'],
            'strategy_ideal': all_results[IDEAL_STRATEGY['name']]['daily_values'],
            'strategy_ma_20_60': all_results['strategy_ma_20_60']['daily_values'],
            'strategy_macd': all_results['strategy_macd']['daily_values'],
            'strategy_rsi_ma': all_results['strategy_rsi_ma']['daily_values'],
            'strategy_bb_20_2': all_results['strategy_bb_20_2']['daily_values'],
            'strategy_don_20': all_results['strategy_don_20']['daily_values'],
            'strategy_atr_trailing': all_results['strategy_atr_trailing']['daily_values'],
            'strategy_kdj': all_results['strategy_kdj']['daily_values'],
            'strategy_volatility': all_results['strategy_volatility']['daily_values'],
            'strategy_volume': all_results['strategy_volume']['daily_values'],
            'strategy_ma_reverse': all_results['strategy_ma_reverse']['daily_values'],
            'strategy_dynamic': all_results['strategy_dynamic']['daily_values'],
            'buyhold': buyhold_values,
            'hs300': benchmarks.get('hs300', []),
            'gold': benchmarks.get('gold', []),
            'nasdaq': benchmarks.get('nasdaq', []),
            'sp500': benchmarks.get('sp500', []),
        }
    }
    
    # 6. 保存文件
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 保存到backtest目录
    output_file = os.path.join(script_dir, "backtest_result.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print(f"\n回测结果已保存至: {output_file}")
    
    # 保存到docs目录
    docs_output = os.path.join(os.path.dirname(script_dir), "docs", "backtest_result.json")
    with open(docs_output, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False)
    print(f"网页数据已保存至: {docs_output}")
    
    print("\n" + "=" * 60)
    print("完成！包含以下策略曲线:")
    for name, result in all_results.items():
        print(f"  - {result['label']}: {result['stats']['total_return']:.2f}%")


if __name__ == "__main__":
    main()
