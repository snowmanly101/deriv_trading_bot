import sys
import asyncio
import json
import logging
import pandas as pd
import numpy as np
import websockets

# Accept dynamic user credentials passed via CLI parameters
if len(sys.argv) < 3:
    print("Usage: python3 user_bot_worker.py <APP_ID> <API_TOKEN>")
    sys.exit(1)

APP_ID = sys.argv[1]
API_TOKEN = sys.argv[2]
SYMBOL = 'frxEURUSD'
LOT_SIZE = 10.0  # Stake amount in USD

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def get_candles(websocket):
    req = {
        "ticks_history": SYMBOL,
        "adjust_start_time": 1,
        "count": 100,
        "end": "latest",
        "granularity": 900,
        "style": "candles"
    }
    await websocket.send(json.dumps(req))
    response = await websocket.recv()
    data = json.loads(response)
    
    if "candles" in data:
        df = pd.DataFrame(data["candles"])
        df['time'] = pd.to_datetime(df['epoch'], unit='s')
        df['close'] = df['close'].astype(float)
        return df
    return None

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
    if len(df) < 2:
        return None
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    if prev['SMA_Fast'] <= prev['SMA_Slow'] and latest['SMA_Fast'] > latest['SMA_Slow']:
        if 45 < latest['RSI'] < 70:
            return 'BUY'
    if prev['SMA_Fast'] >= prev['SMA_Slow'] and latest['SMA_Fast'] < latest['SMA_Slow']:
        if 30 < latest['RSI'] < 55:
            return 'SELL'
    return None

async def execute_trade(websocket, action):
    contract_type = "CALL" if action == 'BUY' else "PUT"
    buy_req = {
        "buy": 1,
        "price": LOT_SIZE,
        "parameters": {
            "amount": LOT_SIZE,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "symbol": SYMBOL,
            "duration": 5,
            "duration_unit": "m"
        }
    }
    await websocket.send(json.dumps(buy_req))
    res = json.loads(await websocket.recv())
    if "buy" in res:
        logging.info(f"SUCCESS: Trade placed for ID {res['buy']['contract_id']}")
    else:
        logging.error(f"Trade Error: {res}")

async def run_user_bot():
    uri = f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}"
    try:
        async with websockets.connect(uri) as websocket:
            auth_req = {"authorize": API_TOKEN}
            await websocket.send(json.dumps(auth_req))
            auth_res = json.loads(await websocket.recv())
            
            if "error" in auth_res:
                logging.error(f"Auth Failed: {auth_res['error']['message']}")
                return

            logging.info(f"Bot successfully authorized for Account: {auth_res['authorize']['loginid']}")

            while True:
                df = await get_candles(websocket)
                if df is not None:
                    df = calculate_indicators(df)
                    signal = check_signals(df)
                    if signal:
                        await execute_trade(websocket, signal)
                await asyncio.sleep(60)
    except Exception as e:
        logging.error(f"Connection Exception: {e}")

if __name__ == '__main__':
    asyncio.run(run_user_bot())