import os
import sys
import time
import json
import websocket
import django
import math

# Setup Django Environment to access the Database & Models
sys.path.append(os.path.dirname(os.path.abspath(_file_)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from dashboard.models import Profile

# Deriv WebSocket Endpoint (Using public Deriv demo/live endpoint)
DERIV_WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

def calculate_ema(prices, period=200):
    """Calculates Exponential Moving Average."""
    if len(prices) < period:
        # Fallback simple average if not enough candles yet
        return [sum(prices) / len(prices)] * len(prices)
    
    multiplier = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    # Pad the beginning to match length
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
    
    # Pad beginning
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
        return None  # Wait for enough data history
        
    rsi = calculate_rsi(closes, period=14)
    ema_200 = calculate_ema(closes, period=200)
    upper_band, lower_band = calculate_bollinger_bands(closes, period=20)
    
    current_price = closes[-1]
    current_rsi = rsi[-1]
    current_ema = ema_200[-1]
    curr_upper = upper_band[-1]
    curr_lower = lower_band[-1]
    
    # 3 Confluence Conditions for BUY
    is_uptrend = current_price > current_ema
    is_oversold = current_rsi < 40
    is_touching_lower = current_price <= curr_lower
    
    if is_uptrend and is_oversold and is_touching_lower:
        return "BUY"
        
    # 3 Confluence Conditions for SELL
    is_downtrend = current_price < current_ema
    is_overbought = current_rsi > 60
    is_touching_upper = current_price >= curr_upper
    
    if is_downtrend and is_overbought and is_touching_upper:
        return "SELL"
        
    return None

def run_bot(user_id):
    """Main worker execution loop for a specific user."""
    print(f"[*] Starting bot worker for User ID: {user_id}")
    
    # Fetch profile and token from DB
    try:
        profile = Profile.objects.get(id=user_id)
        token = profile.deriv_api_token
        account_id = profile.deriv_account_id
    except Profile.DoesNotExist:
        print(f"[!] Profile for user ID {user_id} not found.")
        return

    if not token:
        print(f"[!] No Deriv API token found for user ID {user_id}.")
        return

    starting_balance = 0.0
    current_daily_loss = 0.0

    def on_message(ws, message):
        nonlocal starting_balance, current_daily_loss
        data = json.loads(message)
        msg_type = data.get('msg_type')
        
        # 1. Authorize with Deriv API
        if msg_type == 'authorize':
            if 'error' in data:
                print(f"[!] Authorization failed: {data['error']['message']}")
                ws.close()
            else:
                print(f"[+] Authorized successfully for account: {account_id}")
                # Fetch balance to track daily drawdown
                ws.send(json.dumps({"balance": 1, "subscribe": 1}))
                # Subscribe to historical candles for analysis (e.g., EUR/USD or Volatility 75 Index)
                ws.send(json.dumps({
                    "ticks_history": "R_100",
                    "adjust_start_time": 1,
                    "count": 250,
                    "end": "latest",
                    "style": "candles",
                    "granularity": 300  # 5-minute candles
                }))

        # 2. Handle Balance & Circuit Breaker Check
        elif msg_type == 'balance':
            if 'balance' in data:
                balance = data['balance'].get('balance')
                if starting_balance == 0.0:
                    starting_balance = balance
                
                # Check 5% Daily Drawdown Circuit Breaker
                current_daily_loss = starting_balance - balance
                max_allowed_loss = starting_balance * 0.05
                
                if current_daily_loss >= max_allowed_loss:
                    print(f"[!] CIRCUIT BREAKER TRIGGERED: Daily loss limit reached (${current_daily_loss:.2f}). Stopping bot.")
                    profile.is_bot_active = False
                    profile.save()
                    ws.close()

        # 3. Handle Candles & Run Confluence Engine
        elif msg_type == 'candles':
            candles = data.get('candles', [])
            closes = [c['close'] for c in candles]
            
            # Check if bot is still active in database
            profile.refresh_from_db()
            if not profile.is_bot_active:
                print(f"[*] Bot deactivated by user dashboard switch. Exiting worker.")
                ws.close()
                return

            signal = evaluate_triple_confluence(closes)
            if signal:
                print(f"[*] TRIPLE CONFLUENCE SIGNAL DETECTED: {signal} | Price: {closes[-1]}")
                
                # Calculate 1% Risk Position Sizing
                # Send Buy/Sell trade request to Deriv WebSocket here
                # ws.send(json.dumps({...}))

        # Subscribe to live ticks for continuous updates
        elif msg_type == 'history':
            ws.send(json.dumps({"ticks": "R_100", "subscribe": 1}))

        elif msg_type == 'tick':
            # Live tick feed can trigger micro-evaluations if needed
            pass

    def on_open(ws):
        print(f"[*] Connected to Deriv WebSocket. Authorizing...")
        ws.send(json.dumps({"authorize": token}))

    def on_error(ws, error):
        print(f"[!] WebSocket Error: {error}")

    def on_close(ws, close_status_code, close_msg):
        print(f"[*] WebSocket closed for user {user_id}.")

    # Run WebSocket connection loop
    ws = websocket.WebSocketApp(
        DERIV_WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 user_bot_worker.py <user_id>")
        sys.exit(1)
    
    target_user_id = int(sys.argv[1])
    run_bot(target_user_id)