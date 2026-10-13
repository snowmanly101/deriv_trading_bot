import os
import sys
import time
import requests
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from dashboard.models import Profile

# Assets you love to trade
ASSET_LIST = ["EUR_USD", "XAU_USD"]

def calculate_sma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period

def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price * k) + (ema * (1 - k))
    return ema

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(abs(change))
            losses.append(abs(change))
            
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        return 100
        
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100
        
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_bollinger_bands(prices, period=20, num_std=2):
    if len(prices) < period:
        return None, None
    sma = calculate_sma(prices, period)
    variance = sum((x - sma) ** 2 for x in prices[-period:]) / period
    std_dev = variance ** 0.5
    upper_band = sma + (std_dev * num_std)
    lower_band = sma - (std_dev * num_std)
    return upper_band, lower_band

def get_oanda_headers(api_token):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}"
    }

def get_oanda_base_url(environment):
    if environment == 'live':
        return "https://api-fxtrade.oanda.com/v3"
    return "https://api-fxpractice.oanda.com/v3"

def fetch_candles(base_url, headers, instrument, count=250, granularity="M5"):
    url = f"{base_url}/instruments/{instrument}/candles"
    params = {
        "count": count,
        "granularity": granularity,
        "price": "M"
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            candles = [float(c['mid']['c']) for c in data.get('candles', []) if c.get('complete', True)]
            return candles
    except Exception as e:
        print(f"[ERROR] Failed to fetch {instrument} candles: {e}")
    return []

def place_order(base_url, headers, account_id, instrument, units):
    url = f"{base_url}/accounts/{account_id}/orders"
    payload = {
        "order": {
            "units": str(units),
            "instrument": instrument,
            "timeInForce": "FOK",
            "type": "MARKET",
            "positionFill": "DEFAULT"
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"✅ [SUCCESS] Executed order for {units} units of {instrument}")
            return True
        else:
            print(f"❌ [FAILED] Order rejected for {instrument}: {response.text}")
    except Exception as e:
        print(f"[ERROR] Exception placing order: {e}")
    return False

def run_bot_cycle():
    active_profiles = Profile.objects.filter(is_bot_active=True)
    if not active_profiles.exists():
        return

    for profile in active_profiles:
        if not profile.oanda_account_id or not profile.oanda_api_token:
            continue

        base_url = get_oanda_base_url(profile.oanda_environment)
        headers = get_oanda_headers(profile.oanda_api_token)

        # Loop through your favorite assets: EUR/USD and XAU/USD
        for instrument in ASSET_LIST:
            # 1. Fetch 24-hour daily trend context
            daily_prices = fetch_candles(base_url, headers, instrument=instrument, count=10, granularity="D")
            macro_trend = "BULLISH"
            if len(daily_prices) >= 2:
                if daily_prices[-1] < daily_prices[-2]:
                    macro_trend = "BEARISH"

            # 2. Fetch short-term M5 candles for precise entry setup
            prices = fetch_candles(base_url, headers, instrument=instrument, count=250, granularity="M5")
            if len(prices) < 200:
                continue

            current_price = prices[-1]
            ema_200 = calculate_ema(prices, 200)
            rsi_14 = calculate_rsi(prices, 14)
            upper_bb, lower_bb = calculate_bollinger_bands(prices, 20)

            if None in (ema_200, rsi_14, upper_bb, lower_bb):
                continue

            print(f"[{profile.user.username}] {instrument} | Trend: {macro_trend} | Price: {current_price} | RSI: {rsi_14:.1f}")

            # 3. Execution Logic with 24H Trend Alignment
            # BUY: Macro is Bullish AND Price > 200 EMA AND RSI Oversold (< 35) AND touches Lower BB
            if macro_trend == "BULLISH" and current_price > ema_200 and rsi_14 < 35 and current_price <= lower_bb:
                units = 1000 if instrument == "EUR_USD" else 1  # Standard sizing adjustment for Gold vs Forex
                print(f"🎯 [BUY SIGNAL] {instrument} for {profile.user.username}")
                if place_order(base_url, headers, profile.oanda_account_id, instrument, units=units):
                    profile.total_trades = (profile.total_trades or 0) + 1
                    profile.save()

            # SELL: Macro is Bearish AND Price < 200 EMA AND RSI Overbought (> 65) AND touches Upper BB
            elif macro_trend == "BEARISH" and current_price < ema_200 and rsi_14 > 65 and current_price >= upper_bb:
                units = -1000 if instrument == "EUR_USD" else -1
                print(f"🎯 [SELL SIGNAL] {instrument} for {profile.user.username}")
                if place_order(base_url, headers, profile.oanda_account_id, instrument, units=units):
                    profile.total_trades = (profile.total_trades or 0) + 1
                    profile.save()

if __name__ == "__main__":
    print("🚀 Multi-Asset OANDA Forex & Gold Engine Started...")
    while True:
        try:
            run_bot_cycle()
        except Exception as e:
            print(f"[UNHANDLED EXCEPTION] {e}")
        time.sleep(15)