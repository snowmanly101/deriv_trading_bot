import os
import sys
import asyncio
import json
import math
import django

# Setup Django Environment to access the Database & Models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from dashboard.models import Profile
from asgiref.sync import sync_to_async
import websockets

# Deriv WebSocket Gateway Endpoint
DERIV_WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

def calculate_ema(prices, period=200):
    """Calculates Exponential Moving Average."""
    if len(prices) < period:
        return [sum(prices) / len(prices)] * len(prices)
    
    multiplier = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return [ema[0]] * (period - 1) + ema

def calculate_rsi(prices, period=14):
    """Calculates Relative Strength Index."""
    if len(prices) < period + 1:
        return [50.0] * len(prices)
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    rsi_list = [50.0] * period
    for i in range(period, len(deltas)):
        gain = gains[i]
        loss = losses[i]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        rsi_list.append(rsi)
    return rsi_list

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """Calculates Bollinger Bands (Upper and Lower)."""
    if len(prices) < period:
        return prices, prices
    
    upper_bands = []
    lower_bands = []
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1: i + 1]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        deviation = math.sqrt(variance)
        upper_bands.append(mean + (std_dev * deviation))
        lower_bands.append(mean - (std_dev * deviation))
    
    pad = [prices[0]] * (period - 1)
    return pad + upper_bands, pad + lower_bands

def evaluate_triple_confluence(closes):
    """
    Evaluates 3 technical conditions simultaneously:
    1. Trend Direction via 200 EMA
    2. Momentum via 14 RSI
    3. Volatility boundary via Bollinger Bands
    """
    if len(closes) < 200:
        return None
        
    rsi = calculate_rsi(closes, period=14)
    ema_200 = calculate_ema(closes, period=200)
    upper_band, lower_band = calculate_bollinger_bands(closes, period=20)
    
    current_price = closes[-1]
    current_rsi = rsi[-1]
    current_ema = ema_200[-1]
    curr_upper = upper_band[-1]
    curr_lower = lower_band[-1]
    
    is_uptrend = current_price > current_ema
    is_oversold = current_rsi < 40
    is_touching_lower = current_price <= curr_lower
    
    if is_uptrend and is_oversold and is_touching_lower:
        return "BUY"
        
    is_downtrend = current_price < current_ema
    is_overbought = current_rsi > 60
    is_touching_upper = current_price >= curr_upper
    
    if is_downtrend and is_overbought and is_touching_upper:
        return "SELL"
        
    return None

async def execute_deriv_trade(ws, signal, account_balance, risk_profile='low'):
    """
    Calculates stake based on user risk profile and places a live contract on Deriv.
    """
    risk_percentages = {
        'low': 0.01,     # 1% Risk
        'medium': 0.015, # 1.5% Risk
        'high': 0.02     # 2% Risk
    }
    
    risk_pct = risk_percentages.get(risk_profile, 0.01)
    stake = round(account_balance * risk_pct, 2)
    
    if stake < 0.35:
        stake = 0.35  # Minimum Deriv stake

    contract_type = "CALL" if signal == "BUY" else "PUT"
    
    trade_request = {
        "buy": 1,
        "price": stake,
        "parameters": {
            "amount": stake,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "duration": 5,
            "duration_unit": "m",
            "symbol": "R_100"
        }
    }
    
    await ws.send(json.dumps(trade_request))
    print(f"[+] EXECUTED LIVE {contract_type} trade with stake ${stake} ({risk_pct*100}% Risk Profile)")

async def run_bot_async(user_id):
    print(f"[*] Starting async bot worker for User ID: {user_id}")
    
    try:
        profile = await sync_to_async(Profile.objects.get)(id=user_id)
        token = profile.deriv_api_token
        account_id = profile.deriv_account_id
        risk_profile = getattr(profile, 'risk_profile', 'low')
    except Profile.DoesNotExist:
        print(f"[!] Profile for user ID {user_id} not found.")
        return

    if not token:
        print(f"[!] No Deriv API token found for user ID {user_id}.")
        return

    starting_balance = 0.0
    current_balance = 100.0

    extra_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://app.deriv.com"
    }

    while True:
        try:
            print(f"[*] Connecting to Deriv WebSocket...")
            async with websockets.connect(DERIV_WS_URL, additional_headers=extra_headers) as ws:
                print(f"[+] Connected successfully. Authorizing...")
                await ws.send(json.dumps({"authorize": token}))

                async for message in ws:
                    data = json.loads(message)
                    msg_type = data.get('msg_type')

                    if msg_type == 'authorize':
                        if 'error' in data:
                            print(f"[!] Authorization failed: {data['error']['message']}")
                            return
                        else:
                            print(f"[+] Authorized successfully for account: {account_id}")
                            await ws.send(json.dumps({"balance": 1, "subscribe": 1}))
                            await ws.send(json.dumps({
                                "ticks_history": "R_100",
                                "adjust_start_time": 1,
                                "count": 250,
                                "end": "latest",
                                "style": "candles",
                                "granularity": 300
                            }))

                    elif msg_type == 'balance':
                        if 'balance' in data:
                            current_balance = data['balance'].get('balance')
                            if starting_balance == 0.0:
                                starting_balance = current_balance
                            
                            current_daily_loss = starting_balance - current_balance
                            max_allowed_loss = starting_balance * 0.05
                            
                            if current_daily_loss >= max_allowed_loss:
                                print(f"[!] CIRCUIT BREAKER TRIGGERED: Daily loss limit reached (${current_daily_loss:.2f}). Stopping bot.")
                                profile.is_bot_active = False
                                await sync_to_async(profile.save)()
                                return

                    elif msg_type == 'candles':
                        candles = data.get('candles', [])
                        closes = [c['close'] for c in candles]
                        
                        await sync_to_async(profile.refresh_from_db)()
                        if not profile.is_bot_active:
                            print(f"[*] Bot deactivated by user dashboard switch. Exiting worker.")
                            return

                        signal = evaluate_triple_confluence(closes)
                        if signal:
                            print(f"[*] TRIPLE CONFLUENCE SIGNAL DETECTED: {signal} | Price: {closes[-1]}")
                            await execute_deriv_trade(ws, signal, current_balance, risk_profile)

                    elif msg_type == 'history':
                        await ws.send(json.dumps({"ticks": "R_100", "subscribe": 1}))

                    elif msg_type == 'buy':
                        if 'error' in data:
                            print(f"[!] Trade Execution Error: {data['error']['message']}")
                        else:
                            contract_id = data['buy']['contract_id']
                            print(f"[SUCCESS] Contract Placed! Contract ID: {contract_id}")

        except Exception as e:
            print(f"[!] Connection Error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 user_bot_worker.py <user_id>")
        sys.exit(1)
    
    target_user_id = int(sys.argv[1])
    asyncio.run(run_bot_async(target_user_id))