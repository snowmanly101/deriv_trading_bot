python -c "
code = '''import MetaTrader5 as mt5
import time
import pandas as pd
import numpy as np

SYMBOL = 'EURUSD'
LOT_SIZE = 0.01
RISK_REWARD_RATIO = 2.0
STOP_LOSS_PIPS = 20
MAGIC_NUMBER = 234000

def initialize_mt5():
    if not mt5.initialize():
        print('Initialization failed, error code =', mt5.last_error())
        return False
    return True

def get_market_data(symbol, timeframe=mt5.TIMEFRAME_M15, num_candles=100):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_candles)
    if rates is None:
        print(f'Failed to get data for {symbol}')
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def calculate_indicators(df):
    df['SMA_Fast'] = df['close'].rolling(window=9).mean()
    df['SMA_Slow'] = df['close'].rolling(window=21).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def check_signals(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['SMA_Fast'] <= prev['SMA_Slow'] and latest['SMA_Fast'] > latest['SMA_Slow']:
        if 45 < latest['RSI'] < 70:
            return 'BUY'
    if prev['SMA_Fast'] >= prev['SMA_Slow'] and latest['SMA_Fast'] < latest['SMA_Slow']:
        if 30 < latest['RSI'] < 55:
            return 'SELL'
    return None

def execute_trade(symbol, action):
    point = mt5.symbol_info(symbol).point
    price = mt5.symbol_info_tick(symbol).ask if action == 'BUY' else mt5.symbol_info_tick(symbol).bid
    if action == 'BUY':
        sl = price - (STOP_LOSS_PIPS * 10 * point)
        tp = price + (STOP_LOSS_PIPS * RISK_REWARD_RATIO * 10 * point)
        order_type = mt5.ORDER_TYPE_BUY
    else:
        sl = price + (STOP_LOSS_PIPS * 10 * point)
        tp = price - (STOP_LOSS_PIPS * RISK_REWARD_RATIO * 10 * point)
        order_type = mt5.ORDER_TYPE_SELL

    request = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': LOT_SIZE,
        'type': order_type,
        'price': price,
        'sl': sl,
        'tp': tp,
        'deviation': 20,
        'magic': MAGIC_NUMBER,
        'comment': 'Celooh Bot Auto Trade',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_FOK,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f'Order failed, retcode={result.retcode}')
    else:
        print(f'SUCCESS: {action} order placed for {symbol} at price {price}')

def run_bot():
    if not initialize_mt5():
        return
    print('Celooh Forex Trading Bot is running...')
    while True:
        df = get_market_data(SYMBOL)
        if df is not None:
            df = calculate_indicators(df)
            signal = check_signals(df)
            if signal:
                print(f'Signal detected: {signal}')
                positions = mt5.positions_get(symbol=SYMBOL)
                if len(positions) == 0:
                    execute_trade(SYMBOL, signal)
        time.sleep(60)

if __name__ == '__main__':
    run_bot()
'''
with open('trading_bot.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('trading_bot.py populated successfully!')
"