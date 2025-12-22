"""
基于波动率指标优化买卖参数，并回测红利低波ETF (512890)

定义：
  使用历史价格波动率（HV）作为市场波动指标的代理
  HV = 收盘价的滚动标准差 * sqrt(252) / 均价（年化波动率百分比）

策略逻辑：
  - 高波动环境（市场恐慌）→ 加仓机会：HV > 买入阈值 → 买入
  - 低波动环境（市场过热）→ 减仓信号：HV < 卖出阈值 → 卖出

流程：
  1) 获取标的ETF日线（前复权）
  2) 计算滚动历史波动率（20日窗口）
  3) 穷举买入/卖出阈值（HV 高于买入阈值买，低于卖出阈值卖）
  4) 输出最优参数与回测结果
"""

import os
import json
from datetime import datetime
import pandas as pd
import numpy as np

INITIAL_CAPITAL = 100000
ETF_CODE = "512890"
USE_LOCAL_BACKTEST_JSON = True  # 使用本地 backtest_result.json 避免联网

# 波动率计算参数
HV_WINDOW = 20  # 历史波动率窗口（20日）

# 网格搜索范围（单位：百分比年化波动率）- 围绕最优值16/7精细化搜索
BUY_THRESHOLDS = np.arange(10.0, 25.1, 0.5)   # HV 高于此值买入（波动率高=恐慌），范围10-25%，步长0.5
SELL_THRESHOLDS = np.arange(4.0, 12.1, 0.5)   # HV 低于此值卖出（波动率低=过热），范围4-12%，步长0.5


def fetch_etf():
    """从本地 backtest_result.json 获取 ETF 数据"""
    if USE_LOCAL_BACKTEST_JSON:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(script_dir, 'backtest_result.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        daily = data['daily_values']['strategy']
        df = pd.DataFrame([{'date': pd.to_datetime(d['date']), 'close': d['close']} for d in daily])
        return df.sort_values('date').reset_index(drop=True)
    raise RuntimeError("请先运行 rsi_backtest.py 生成 backtest_result.json")


def calculate_historical_volatility(prices, window=20):
    """
    计算历史波动率（年化百分比）
    HV = std(log_returns) * sqrt(252) * 100
    """
    log_returns = np.log(prices / prices.shift(1))
    hv = log_returns.rolling(window=window, min_periods=window).std() * np.sqrt(252) * 100
    return hv


def backtest_volatility(etf_df, buy_thr, sell_thr):
    """执行波动率策略回测"""
    df = etf_df.copy()
    df['hv'] = calculate_historical_volatility(df['close'], HV_WINDOW)
    
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily = []

    for _, row in df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        hv = row['hv']

        # 波动率信号：高波动买入（恐慌），低波动卖出（过热）
        buy_signal = pd.notna(hv) and hv > buy_thr and position == 0
        sell_signal = pd.notna(hv) and hv < sell_thr and position == 1

        if buy_signal:
            shares_to_buy = cash / price  # 联接基金：全仓买入，支持小数份额
            if shares_to_buy > 0:
                cost = cash  # 全仓买入
                shares += shares_to_buy
                cash = 0
                position = 1
                trades.append({
                    'date': date_str,
                    'action': '买入',
                    'price': price,
                    'shares': shares_to_buy,
                    'amount': cost,
                    'hv': hv
                })
        elif sell_signal:
            if shares > 0:
                revenue = shares * price  # 联接基金：全仓卖出
                cash += revenue
                sell_shares = shares
                shares = 0
                position = 0
                trades.append({
                    'date': date_str,
                    'action': '卖出',
                    'price': price,
                    'shares': sell_shares,
                    'amount': revenue,
                    'hv': hv
                })

        total_value = cash + shares * price
        daily.append({
            'date': date_str,
            'close': price,
            'hv': hv if pd.notna(hv) else None,
            'cash': cash,
            'shares': shares,
            'total_value': total_value,
            'return': (total_value / INITIAL_CAPITAL - 1) * 100
        })

    # 统计
    returns = [d['return'] for d in daily]
    values = [d['total_value'] for d in daily]
    peak = values[0]
    max_dd = 0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    total_return = returns[-1]
    days = len(daily)
    calendar_days = (etf_df['date'].max() - etf_df['date'].min()).days
    annual = ((1 + total_return / 100) ** (365 / calendar_days) - 1) * 100 if calendar_days > 0 else 0
    
    buy_trades = [t for t in trades if t['action'] == '买入']
    sell_trades = [t for t in trades if t['action'] == '卖出']
    wins = 0
    for i, s in enumerate(sell_trades):
        if i < len(buy_trades) and s['price'] > buy_trades[i]['price']:
            wins += 1
    win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0

    return {
        'buy_thr': buy_thr,
        'sell_thr': sell_thr,
        'total_return': round(total_return, 2),
        'annual_return': round(annual, 2),
        'max_drawdown': round(max_dd, 2),
        'trade_count': len(buy_trades),
        'win_rate': round(win_rate, 2),
        'trades': trades,
        'daily': daily,
        'days': days,
        'calendar_days': calendar_days,
    }


def optimize(etf_df):
    """网格搜索最优参数"""
    results = []
    total_combinations = 0
    for buy in BUY_THRESHOLDS:
        for sell in SELL_THRESHOLDS:
            if buy <= sell:  # 买入阈值必须高于卖出阈值（高波动买，低波动卖）
                continue
            total_combinations += 1
            res = backtest_volatility(etf_df, buy, sell)
            results.append(res)
    
    print(f"测试了 {total_combinations} 组参数组合")
    results_sorted = sorted(results, key=lambda x: x['total_return'], reverse=True)
    best = results_sorted[0]
    return best, results_sorted


def main():
    print("=" * 70)
    print("波动率策略优化回测 (历史波动率 HV20)")
    print("=" * 70)

    etf_df = fetch_etf()
    print(f"ETF 数据: {etf_df['date'].min().date()} 至 {etf_df['date'].max().date()} 共 {len(etf_df)} 条")

    best, results_sorted = optimize(etf_df)

    print("\n最优参数 (按总收益)：")
    print(f"  买入阈值 HV > {best['buy_thr']:.1f}% (年化波动率)")
    print(f"  卖出阈值 HV < {best['sell_thr']:.1f}% (年化波动率)")
    print(f"  总收益: {best['total_return']:.2f}% | 年化: {best['annual_return']:.2f}% | 回撤: {best['max_drawdown']:.2f}%")
    print(f"  交易次数: {best['trade_count']} | 胜率: {best['win_rate']:.2f}%")

    # 保存结果
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output = {
        'meta': {
            'etf_code': ETF_CODE,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'hv_window': HV_WINDOW,
            'buy_thresholds': list(map(float, BUY_THRESHOLDS)),
            'sell_thresholds': list(map(float, SELL_THRESHOLDS)),
            'strategy': '高波动买入(恐慌), 低波动卖出(过热)',
        },
        'best': best,
        'top_20': results_sorted[:20],
    }
    out_file = os.path.join(script_dir, 'volatility_optimization_results.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_file}")
    
    # 打印Top5参数对比
    print("\nTop 5 参数组合:")
    print(f"{'排名':<4} {'买入HV':<8} {'卖出HV':<8} {'总收益':<10} {'年化':<8} {'回撤':<8} {'交易次数':<8}")
    print("-" * 70)
    for i, res in enumerate(results_sorted[:5], 1):
        print(f"{i:<4} {res['buy_thr']:<8.1f} {res['sell_thr']:<8.1f} {res['total_return']:<10.2f}% {res['annual_return']:<8.2f}% {res['max_drawdown']:<8.2f}% {res['trade_count']:<8}")


if __name__ == "__main__":
    main()
