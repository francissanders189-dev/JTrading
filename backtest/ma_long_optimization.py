"""
长期均线系统优化 - 红利低波ETF (512890) - 反向策略

策略逻辑（反向操作）：
  买入信号：短期均线下穿长期均线（死叉买入）- 利用均线滞后性，在回调时低吸
  卖出信号：短期均线上穿长期均线（金叉卖出）- 突破后高位套利

理论依据：
  红利低波ETF是防御性资产，传统趋势策略失效
  反向操作：死叉=短期回调=买入机会，金叉=过度追高=卖出时机

数据源：
  使用本地 backtest_result.json 避免网络问题
"""

import os
import json
from datetime import datetime
import pandas as pd
import numpy as np

INITIAL_CAPITAL = 100000
ETF_CODE = "512890"

# 精细化优化范围（基于初步结果 MA25/80 和 MA10/170）
# 围绕最优参数缩小范围，步长降至1日
SHORT_MA_RANGE = range(8, 35, 1)      # 短期均线：8-34 日，步长 1（覆盖MA10和MA25附近）
LONG_MA_RANGE = range(70, 181, 2)     # 长期均线：70-180 日，步长 2（覆盖MA80和MA170附近）


def fetch_etf_local():
    """从本地 backtest_result.json 读取 ETF 数据"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, 'backtest_result.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    daily = data['daily_values']['strategy']
    df = pd.DataFrame([{
        'date': pd.to_datetime(d['date']), 
        'close': d['close']
    } for d in daily])
    return df.sort_values('date').reset_index(drop=True)


def add_ma(df, short_window, long_window):
    """计算短期和长期均线"""
    ma_df = df.copy()
    ma_df['ma_short'] = ma_df['close'].rolling(window=short_window, min_periods=short_window).mean()
    ma_df['ma_long'] = ma_df['close'].rolling(window=long_window, min_periods=long_window).mean()
    return ma_df


def backtest_ma_system(df, short_ma, long_ma):
    """
    长期均线系统回测 - 反向策略
    买入：短期均线下穿长期均线（死叉买入）
    卖出：短期均线上穿长期均线（金叉卖出）
    """
    ma_df = add_ma(df, short_ma, long_ma)
    cash = INITIAL_CAPITAL
    shares = 0
    position = 0
    trades = []
    daily = []

    for i, row in ma_df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        price = row['close']
        ma_s = row['ma_short']
        ma_l = row['ma_long']
        
        prev = ma_df.iloc[i-1] if i > 0 else None
        
        # 死叉：短期均线下穿长期均线（反向策略：死叉买入）
        dead_cross = (prev is not None and 
                     pd.notna(ma_s) and pd.notna(ma_l) and
                     pd.notna(prev['ma_short']) and pd.notna(prev['ma_long']) and
                     prev['ma_short'] >= prev['ma_long'] and 
                     ma_s < ma_l)
        
        # 金叉：短期均线上穿长期均线（反向策略：金叉卖出）
        golden_cross = (prev is not None and 
                       pd.notna(ma_s) and pd.notna(ma_l) and
                       pd.notna(prev['ma_short']) and pd.notna(prev['ma_long']) and
                       prev['ma_short'] <= prev['ma_long'] and 
                       ma_s > ma_l)
        
        if dead_cross and position == 0:
            shares_to_buy = cash / price  # 联接基金：全仓买入
            if shares_to_buy > 0:
                cost = cash
                shares += shares_to_buy
                cash = 0
                position = 1
                trades.append({
                    'date': date_str,
                    'action': '买入',
                    'price': price,
                    'shares': shares_to_buy,
                    'amount': cost,
                    'signal': f'死叉买入 MA{short_ma}/{long_ma}'
                })
        
        elif golden_cross and position == 1:
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
                    'signal': f'金叉卖出 MA{short_ma}/{long_ma}'
                })
        
        total_value = cash + shares * price
        daily.append({
            'date': date_str,
            'close': price,
            'ma_short': ma_s if pd.notna(ma_s) else None,
            'ma_long': ma_l if pd.notna(ma_l) else None,
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
    start_date = pd.to_datetime(daily[0]['date'])
    end_date = pd.to_datetime(daily[-1]['date'])
    calendar_days = (end_date - start_date).days
    annual = ((1 + total_return / 100) ** (365 / calendar_days) - 1) * 100 if calendar_days > 0 else 0
    
    buy_trades = [t for t in trades if t['action'] == '买入']
    sell_trades = [t for t in trades if t['action'] == '卖出']
    wins = 0
    for i, s in enumerate(sell_trades):
        if i < len(buy_trades) and s['price'] > buy_trades[i]['price']:
            wins += 1
    win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0
    
    return {
        'short_ma': short_ma,
        'long_ma': long_ma,
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


def optimize(df):
    """网格搜索最优均线参数"""
    results = []
    total_combinations = len(SHORT_MA_RANGE) * len(LONG_MA_RANGE)
    count = 0
    
    print(f"开始网格搜索，共 {total_combinations} 种参数组合...")
    
    for short_ma in SHORT_MA_RANGE:
        for long_ma in LONG_MA_RANGE:
            if short_ma >= long_ma:
                continue
            count += 1
            if count % 10 == 0:
                print(f"  进度: {count}/{total_combinations}")
            
            res = backtest_ma_system(df, short_ma, long_ma)
            results.append(res)
    
    # 按总收益排序
    results_sorted = sorted(results, key=lambda x: x['total_return'], reverse=True)
    # 按年化收益排序
    results_by_annual = sorted(results, key=lambda x: x['annual_return'], reverse=True)
    # 按夏普比率排序（简化版：年化/回撤）
    results_by_sharpe = sorted(results, key=lambda x: x['annual_return'] / (x['max_drawdown'] + 1), reverse=True)
    
    return {
        'by_total_return': results_sorted[0],
        'by_annual_return': results_by_annual[0],
        'by_sharpe': results_by_sharpe[0],
        'all_results': results_sorted[:30]  # 保留前30
    }


def main():
    print("=" * 80)
    print("长期均线系统优化 - 红利低波ETF (512890)")
    print("=" * 80)
    
    df = fetch_etf_local()
    print(f"数据范围: {df['date'].min().date()} 至 {df['date'].max().date()} 共 {len(df)} 条")
    
    best_results = optimize(df)
    
    print("\n" + "=" * 80)
    print("优化结果")
    print("=" * 80)
    
    print("\n【按总收益最优】")
    best = best_results['by_total_return']
    print(f"  参数: MA{best['short_ma']}/{best['long_ma']}")
    print(f"  总收益: {best['total_return']:.2f}% | 年化: {best['annual_return']:.2f}% | 回撤: {best['max_drawdown']:.2f}%")
    print(f"  交易次数: {best['trade_count']} | 胜率: {best['win_rate']:.2f}%")
    
    print("\n【按年化收益最优】")
    best_annual = best_results['by_annual_return']
    print(f"  参数: MA{best_annual['short_ma']}/{best_annual['long_ma']}")
    print(f"  总收益: {best_annual['total_return']:.2f}% | 年化: {best_annual['annual_return']:.2f}% | 回撤: {best_annual['max_drawdown']:.2f}%")
    print(f"  交易次数: {best_annual['trade_count']} | 胜率: {best_annual['win_rate']:.2f}%")
    
    print("\n【按风险调整收益最优（夏普近似）】")
    best_sharpe = best_results['by_sharpe']
    print(f"  参数: MA{best_sharpe['short_ma']}/{best_sharpe['long_ma']}")
    print(f"  总收益: {best_sharpe['total_return']:.2f}% | 年化: {best_sharpe['annual_return']:.2f}% | 回撤: {best_sharpe['max_drawdown']:.2f}%")
    print(f"  交易次数: {best_sharpe['trade_count']} | 胜率: {best_sharpe['win_rate']:.2f}%")
    print(f"  风险调整比: {best_sharpe['annual_return'] / (best_sharpe['max_drawdown'] + 1):.2f}")
    
    # 保存结果
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output = {
        'meta': {
            'etf_code': ETF_CODE,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'short_ma_range': list(SHORT_MA_RANGE),
            'long_ma_range': list(LONG_MA_RANGE),
            'strategy': '反向均线系统（死叉买入，金叉卖出）'
        },
        'best_by_total_return': best_results['by_total_return'],
        'best_by_annual_return': best_results['by_annual_return'],
        'best_by_sharpe': best_results['by_sharpe'],
        'top_30': best_results['all_results'],
    }
    
    out_file = os.path.join(script_dir, 'ma_reverse_optimization_results.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_file}")
    
    # 对比基准
    print("\n" + "=" * 80)
    print("与现有策略对比")
    print("=" * 80)
    print("RSI(15) 32/77 联结基金: 总收益 258.85% | 年化 20.33%")
    print("RSI(14) 34/78 ETF整手: 总收益 203.96% | 年化 17.47%")
    print(f"MA{best['short_ma']}/{best['long_ma']} 长期均线: 总收益 {best['total_return']:.2f}% | 年化 {best['annual_return']:.2f}%")


if __name__ == "__main__":
    main()
