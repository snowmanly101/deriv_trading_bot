import os
import sys
import time
import math
import requests
import django

# Setup Django Environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from dashboard.models import Profile

# OANDA API Endpoints
OANDA_URLS = {
    "practice": "https://api-fxpractice.oanda.com/v3",
    "live": "https://api-fxtrade.oanda.com/v3"
}

def calculate_indicators(prices):
    """Calculates 200 EMA, 14 RSI, and Bollinger Bands."""
    if len(prices) < 200:
        return None, None, None, None, None

    # 200 EMA
    period_ema = 200
    multiplier = 2 / (period_ema + 1)
    ema = [sum(prices[:period_ema]) / period_ema]
    for p in prices[period_ema:]:
        ema.append((p - ema[-1]) * multiplier + ema[-1])
    current_ema = ema[-1]

    # 14 RSI
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:14]) / 14
    avg_loss = sum(losses[:14]) / 14
    
    rsi_list = [50.0] * 14
    for i in range(14, len(deltas)):
        avg_gain = (avg_gain * 13 + gains[i]) / 14
        avg_loss = (avg_loss * 13 + losses[i]) / 14
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi_list.append(100 - (100 / (1 + rs)))
    current_rsi = rsi_list[-1]

    # Bollinger Bands (20 Period, 2 StdDev)
    window = prices[-20:]
    mean = sum(window) / 20
    variance = sum((x - mean) ** 2 for x in window) / 20
    deviation = math.sqrt(variance)
    upper_band = mean + (2 * deviation)
    lower_band = mean - (2 * deviation)

    return prices[-1], current_ema, current_rsi, upper_band, lower_band

def evaluate_confluence(price, ema, rsi, upper, lower):
    """Triple Confluence Strategy Logic"""
    if price > ema and rsi < 40 and price <= lower:
        return "BUY"
    elif price < ema and rsi > 60 and price >= upper:
        return "SELL"
    return None

def execute_oanda_trade(base_url, token, account_id, instrument, units):
    """Executes a market order on OANDA"""
    endpoint = f"{base_url}/accounts/{account_id}/orders"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "order": {
            "units": str(units),
            "instrument": instrument,
            "timeInForce": "FOK",
            "type": "MARKET",
            "positionFill": "DEFAULT"
        }
    }
    response = requests.post(endpoint, json=payload, headers=headers)
    if response.status_code == 201:
        print(f"[SUCCESS] OANDA Trade Placed for {instrument}! Units: {units}")
    else:
        print(f"[!] Trade Error: {response.text}")

def run_oanda_worker(user_id):
    print(f"[*] Starting OANDA Bot Worker for User ID: {user_id}")
    
    try:
        profile = Profile.objects.get(id=user_id)
    except Profile.DoesNotExist:
        print(f"[!] Profile for User ID {user_id} not found.")
        return

    token = profile.oanda_api_token
    account_id = profile.oanda_account_id
    env = profile.oanda_environment

    if not token or not account_id:
        print(f"[!] Missing OANDA API Token or Account ID for User ID {user_id}.")
        return

    base_url = OANDA_URLS.get(env, OANDA_URLS["practice"])
    instrument = "EUR_USD"  # Primary forex pair

    headers = {"Authorization": f"Bearer {token}"}

    while True:
        try:
            profile.refresh_from_db()
            if not profile.is_bot_active:
                print(f"[*] Bot deactivated from dashboard. Stopping worker.")
                break

            # Fetch account balance
            acc_resp = requests.get(f"{base_url}/accounts/{account_id}", headers=headers)
            if acc_resp.status_code == 200:
                account_data = acc_resp.json().get("account", {})
                balance = float(account_data.get("balance", 1000.0))
            else:
                balance = 1000.0

            # Fetch recent candles (Granularity: M5 for 5-minute candles)
            candles_url = f"{base_url}/instruments/{instrument}/candles?count=250&granularity=M5&price=M"
            c_resp = requests.get(candles_url, headers=headers)
            
            if c_resp.status_code == 200:
                candles_data = c_resp.json().get("candles", [])
                prices = [float(c["mid"]["c"]) for c in candles_data if c["complete"]]

                if len(prices) >= 200:
                    price, ema, rsi, upper, lower = calculate_indicators(prices)
                    signal = evaluate_confluence(price, ema, rsi, upper, lower)

                    if signal:
                        print(f"[*] SIGNAL DETECTED: {signal} on {instrument} at price {price}")
                        units = 1000 if signal == "BUY" else -1000 
                        execute_oanda_trade(base_url, token, account_id, instrument, units)

            # Poll every 60 seconds
            time.sleep(60)

        except Exception as e:
            print(f"[!] OANDA Worker Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 oanda_bot_worker.py <user_id>")
        sys.exit(1)
    run_oanda_worker(int(sys.argv[1]))