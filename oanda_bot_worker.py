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
    gains, losses = [], []
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

def get_oanda_headers(api_token):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}"
    }

def get_oanda_base_url(environment):
    if environment == 'live':
        return "https://api-fxtrade.oanda.com/v3"
    return "https://api-fxpractice.oanda.com/v3"

def fetch_full_candles(base_url, headers, instrument, count=50, granularity="M5"):
    url = f"{base_url}/instruments/{instrument}/candles"
    params = {"count": count, "granularity": granularity, "price": "M"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            raw_candles = data.get('candles', [])
            parsed = []
            for c in raw_candles:
                if c.get('complete', True):
                    mid = c['mid']
                    parsed.append({
                        'open': float(mid['o']),
                        'high': float(mid['h']),
                        'low': float(mid['l']),
                        'close': float(mid['c'])
                    })
            return parsed
    except Exception as e:
        print(f"[ERROR] Candle fetch failed for {instrument}: {e}")
    return []

def analyze_market_structure(candles):
    """
    Identifies if market structure forms Higher Highs & Higher Lows (Bullish)
    or Lower Highs & Lower Lows (Bearish).
    """
    if len(candles) < 4:
        return "NEUTRAL"
        
    c1, c2, c3, c4 = candles[-4], candles[-3], candles[-2], candles[-1]
    
    # Check Higher Highs and Higher Lows
    if c4['high'] > c3['high'] and c3['high'] > c2['high'] and c4['low'] > c3['low'] and c3['low'] > c2['low']:
        return "BULLISH_STRUCTURE"
        
    # Check Lower Highs and Lower Lows
    if c4['high'] < c3['high'] and c3['high'] < c2['high'] and c4['low'] < c3['low'] and c3['low'] < c2['low']:
        return "BEARISH_STRUCTURE"
        
    return "NEUTRAL"

def check_candlestick_patterns(candles):
    """
    Detects powerful Pin Bar rejection wicks and Engulfing reversal candles.
    """
    if len(candles) < 2:
        return "NONE"
        
    curr = candles[-1]
    prev = candles[-2]
    
    total_range = curr['high'] - curr['low']
    if total_range == 0:
        return "NONE"
        
    body_size = abs(curr['close'] - curr['open'])
    upper_wick = curr['high'] - max(curr['open'], curr['close'])
    lower_wick = min(curr['open'], curr['close']) - curr['low']
    
    # 1. Bullish Pin Bar Rejection (Long lower wick >= 60% of total candle)
    if (lower_wick / total_range) >= 0.60:
        return "BULLISH_PINBAR"
        
    # 2. Bearish Pin Bar Rejection (Long upper wick >= 60% of total candle)
    if (upper_wick / total_range) >= 0.60:
        return "BEARISH_PINBAR"
        
    # 3. Bullish Engulfing (Green candle engulfs previous red body)
    if prev['close'] < prev['open'] and curr['close'] > curr['open']:
        if curr['close'] >= prev['open'] and curr['open'] <= prev['close']:
            return "BULLISH_ENGULFING"
            
    # 4. Bearish Engulfing (Red candle engulfs previous green body)
    if prev['close'] > prev['open'] and curr['close'] < curr['open']:
        if curr['close'] <= prev['open'] and curr['open'] >= prev['close']:
            return "BEARISH_ENGULFING"
            
    return "NONE"

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
            print(f"✅ [ORDER EXECUTED] {units} units of {instrument}")
            return True
        else:
            print(f"❌ [ORDER REJECTED] {instrument}: {response.text}")
    except Exception as e:
        print(f"[ERROR] Exception submitting order: {e}")
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

        for instrument in ASSET_LIST:
            # 1. Fetch Daily Candles for Macro Structure (HH/HL vs LH/LL)
            daily_candles = fetch_full_candles(base_url, headers, instrument=instrument, count=10, granularity="D")
            macro_structure = analyze_market_structure(daily_candles)
            
            # 2. Fetch Short-Term M5 Candles for Reversal Pattern Detection
            m5_candles = fetch_full_candles(base_url, headers, instrument=instrument, count=250, granularity="M5")
            if len(m5_candles) < 200:
                continue

            close_prices = [c['close'] for c in m5_candles]
            current_price = close_prices[-1]
            ema_200 = calculate_ema(close_prices, 200)
            rsi_14 = calculate_rsi(close_prices, 14)
            candle_signal = check_candlestick_patterns(m5_candles)

            if ema_200 is None or rsi_14 is None:
                continue

            print(f"[{profile.user.username}] {instrument} | Structure: {macro_structure} | Pattern: {candle_signal} | RSI: {rsi_14:.1f}")

            # 3. HIGH CONFLUENCE BUY EXECUTION
            # Condition: Macro structure or price above EMA AND Bullish Candlestick Signal AND RSI <= 40
            if (macro_structure == "BULLISH_STRUCTURE" or current_price > ema_200) and \
               candle_signal in ["BULLISH_PINBAR", "BULLISH_ENGULFING"] and rsi_14 <= 40:
                
                units = 1000 if instrument == "EUR_USD" else 1
                print(f"🎯 [HIGH CONFLUENCE BUY] {instrument} - Pattern: {candle_signal}")
                if place_order(base_url, headers, profile.oanda_account_id, instrument, units=units):
                    profile.total_trades = (profile.total_trades or 0) + 1
                    profile.save()

            # 4. HIGH CONFLUENCE SELL EXECUTION
            # Condition: Bearish structure or price below EMA AND Bearish Candlestick Signal AND RSI >= 60
            elif (macro_structure == "BEARISH_STRUCTURE" or current_price < ema_200) and \
                 candle_signal in ["BEARISH_PINBAR", "BEARISH_ENGULFING"] and rsi_14 >= 60:
                
                units = -1000 if instrument == "EUR_USD" else -1
                print(f"🎯 [HIGH CONFLUENCE SELL] {instrument} - Pattern: {candle_signal}")
                if place_order(base_url, headers, profile.oanda_account_id, instrument, units=units):
                    profile.total_trades = (profile.total_trades or 0) + 1
                    profile.save()

if __name__ == "__main__":
    print("🚀 Multi-Confluence Price Action & Structure Bot Started...")
    while True:
        try:
            run_bot_cycle()
        except Exception as e:
            print(f"[UNHANDLED EXCEPTION] {e}")
        time.sleep(15)