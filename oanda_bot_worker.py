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

# 10 Major Forex Currency Pairs
ASSET_LIST = [
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD",
    "USD_CHF", "NZD_USD", "EUR_GBP", "EUR_JPY", "GBP_JPY"
]

# Hardcoded Telegram credentials
TELEGRAM_BOT_TOKEN = "8733660618:AAHnB2D6rTzg8ghaxw97gshxTTJu1Eu-mOg"
TELEGRAM_CHAT_ID = "7573543350"

def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}", flush=True)

# ==========================================
# 1. ECONOMIC NEWS GUARD (Daily News Filter)
# ==========================================
def is_high_impact_news_imminent():
    """
    Checks if high-impact USD or EUR news is scheduled within the next 30 minutes.
    """
    try:
        response = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=5)
        if response.status_code == 200:
            events = response.json()
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            for event in events:
                if event.get('impact') == 'High' and event.get('country') in ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD']:
                    event_date_str = event.get('date', '').replace('Z', '+00:00')
                    if event_date_str:
                        event_time = datetime.fromisoformat(event_date_str)
                        time_diff_minutes = (event_time - now).total_seconds() / 60
                        if -30 <= time_diff_minutes <= 30:
                            print(f"🚨 [NEWS GUARD] Pausing trading due to high-impact news: {event.get('title')}", flush=True)
                            return True
    except Exception as e:
        print(f"[NEWS GUARD WARNING] Could not fetch calendar feed: {e}", flush=True)
    return False

# ==========================================
# 2. TECHNICAL INDICATORS & ATR CALCULATION
# ==========================================
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
            gains.append(0)
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

def calculate_atr(candles, period=14):
    if len(candles) < period + 1:
        return 0.0010
    tr_list = []
    for i in range(1, len(candles)):
        high = candles[i]['high']
        low = candles[i]['low']
        prev_close = candles[i-1]['close']
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / period

# ==========================================
# 3. ADVANCED MARKET STRUCTURE (HH, LH, HL, LL)
# ==========================================
def analyze_market_structure(candles):
    if len(candles) < 6:
        return "NEUTRAL"
    
    highs = [c['high'] for c in candles[-6:]]
    lows = [c['low'] for c in candles[-6:]]
    
    h1, h2 = highs[-3], highs[-1]
    l1, l2 = lows[-3], lows[-1]
    
    if h2 > h1 and l2 > l1:
        return "BULLISH_HH_HL"
    elif h2 < h1 and l2 < l1:
        return "BEARISH_LH_LL"
    return "NEUTRAL"

def check_candlestick_patterns(candles):
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
    
    if (lower_wick / total_range) >= 0.60:
        return "BULLISH_PINBAR"
    if (upper_wick / total_range) >= 0.60:
        return "BEARISH_PINBAR"
    if prev['close'] < prev['open'] and curr['close'] > curr['open']:
        if curr['close'] >= prev['open'] and curr['open'] <= prev['close']:
            return "BULLISH_ENGULFING"
    if prev['close'] > prev['open'] and curr['close'] < curr['open']:
        if curr['close'] <= prev['open'] and curr['open'] >= prev['close']:
            return "BEARISH_ENGULFING"
    return "NONE"

# ==========================================
# 4. BROKER API CLIENTS (OANDA, Capital.com)
# ==========================================
def get_oanda_headers(api_token):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}"
    }

def get_oanda_base_url(environment):
    if environment == 'live':
        return "https://api-fxtrade.oanda.com/v3"
    return "https://api-fxpractice.oanda.com/v3"

def fetch_full_candles(base_url, headers, instrument="EUR_USD", count=50, granularity="M5"):
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
        print(f"[ERROR] Candle fetch failed for {instrument}: {e}", flush=True)
    return []

def get_capital_session(profile):
    base_url = "https://api-capital.backend-capital.com/api/v1" if profile.oanda_environment == 'live' else "https://demo-api-capital.backend-capital.com/api/v1"
    
    url = f"{base_url}/session"
    headers = {
        "X-CAP-API-KEY": getattr(profile, 'capital_security_token', ''),
        "Content-Type": "application/json"
    }
    payload = {
        "identifier": profile.user.email,
        "password": getattr(profile, 'capital_cst_token', '')
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            cst = response.headers.get("CST")
            x_sec = response.headers.get("X-SECURITY-TOKEN")
            return cst, x_sec
        else:
            print(f"[CAPITAL SESSION REJECTED] {response.text}", flush=True)
    except Exception as e:
        print(f"[CAPITAL SESSION ERROR] {e}", flush=True)
        
    return None, None

def place_capital_com_order(profile, instrument, direction, current_price, atr_value):
    cst, x_sec = get_capital_session(profile)
    if not cst or not x_sec:
        print("❌ [CAPITAL ERROR] Session creation failed. Verify API Key and Custom Password on dashboard.", flush=True)
        return False

    base_url = "https://api-capital.backend-capital.com/api/v1" if profile.oanda_environment == 'live' else "https://demo-api-capital.backend-capital.com/api/v1"
    
    sl_distance = atr_value * 1.5
    tp_distance = sl_distance * 2.0
    
    if direction == "BUY":
        sl_price = round(current_price - sl_distance, 5)
        tp_price = round(current_price + tp_distance, 5)
    else:
        sl_price = round(current_price + sl_distance, 5)
        tp_price = round(current_price - tp_distance, 5)
        
    payload = {
        "epic": instrument.replace("_", ""),
        "direction": direction,
        "size": 0.1,
        "guaranteedStopLoss": False,
        "stopLossLevel": sl_price,
        "takeProfitLevel": tp_price
    }
    
    headers = {
        "CST": cst,
        "X-SECURITY-TOKEN": x_sec,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(f"{base_url}/positions", headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"✅ [CAPITAL.COM ORDER SUCCESS] {instrument} {direction}", flush=True)
            send_telegram_alert(f"🚀 CELOOH BOT TRADE (Capital.com)\nAsset: {instrument}\nDirection: {direction}\nSL: {sl_price} | TP: {tp_price}")
            return True
        else:
            print(f"❌ [Capital.com REJECTED]: {response.text}", flush=True)
    except Exception as e:
        print(f"[CAPITAL ERROR] {e}", flush=True)
    return False

def place_oanda_order(profile, instrument, direction, current_price, atr_value):
    risk_level = getattr(profile, 'risk_level', 'medium')
    sl_distance = atr_value * (1.2 if risk_level == 'low' else 1.5)
    tp_distance = sl_distance * 2.0
    
    units = 1000 if risk_level == 'low' else 2000
    if direction == "BUY":
        units_str = str(units)
        sl_price = round(current_price - sl_distance, 5)
        tp_price = round(current_price + tp_distance, 5)
    else:
        units_str = str(-units)
        sl_price = round(current_price + sl_distance, 5)
        tp_price = round(current_price - tp_distance, 5)

    base_url = get_oanda_base_url(profile.oanda_environment)
    headers = get_oanda_headers(profile.oanda_api_token)
    url = f"{base_url}/accounts/{profile.oanda_account_id}/orders"
    payload = {
        "order": {
            "units": units_str,
            "instrument": instrument,
            "timeInForce": "FOK",
            "type": "MARKET",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {"price": str(sl_price), "timeInForce": "GTC"},
            "takeProfitOnFill": {"price": str(tp_price), "timeInForce": "GTC"}
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"✅ [OANDA ORDER SUCCESS] {instrument} {direction}", flush=True)
            send_telegram_alert(f"🚀 CELOOH BOT TRADE (OANDA)\nAsset: {instrument}\nDirection: {direction}\nSL: {sl_price} | TP: {tp_price}")
            return True
    except Exception as e:
        print(f"[ERROR] OANDA order exception: {e}", flush=True)
    return False

# ==========================================
# 5. MAIN BOT EXECUTION LOOP
# ==========================================
def run_bot_cycle():
    active_profiles = Profile.objects.filter(is_bot_active=True)
    if not active_profiles.exists():
        print("🔍 [BOT SCAN] Waiting for active user profile on dashboard...", flush=True)
        return

    # Check Economic News Guard before processing trades
    if is_high_impact_news_imminent():
        return

    for profile in active_profiles:
        broker_type = getattr(profile, 'broker_type', 'oanda')
        print(f"🔍 [BOT SCAN] User: {profile.user.username} | Broker: {broker_type.upper()} | Scanning 10 pairs...", flush=True)
        
        if broker_type == 'capital':
            base_url = "https://api-capital.backend-capital.com/api/v1"
        else:
            base_url = get_oanda_base_url(getattr(profile, 'oanda_environment', 'practice'))
            
        headers = {"Content-Type": "application/json"}

        for instrument in ASSET_LIST:
            m5_candles = fetch_full_candles(base_url, headers, instrument=instrument, count=250, granularity="M5")
            if len(m5_candles) < 200:
                continue

            close_prices = [c['close'] for c in m5_candles]
            current_price = close_prices[-1]
            ema_200 = calculate_ema(close_prices, 200)
            rsi_14 = calculate_rsi(close_prices, 14)
            atr_value = calculate_atr(m5_candles, 14)
            market_structure = analyze_market_structure(m5_candles)
            candle_signal = check_candlestick_patterns(m5_candles)

            if ema_200 is None or rsi_14 is None:
                continue

            # HIGH CONFLUENCE BUY
            if market_structure == "BULLISH_HH_HL" and current_price > ema_200 and \
               candle_signal in ["BULLISH_PINBAR", "BULLISH_ENGULFING"] and rsi_14 <= 42:
                print(f"🎯 [{profile.user.username}] Bullish Confluence Triggered on {instrument}!", flush=True)
                if broker_type == 'capital':
                    place_capital_com_order(profile, instrument, "BUY", current_price, atr_value)
                else:
                    place_oanda_order(profile, instrument, "BUY", current_price, atr_value)

            # HIGH CONFLUENCE SELL
            elif market_structure == "BEARISH_LH_LL" and current_price < ema_200 and \
                 candle_signal in ["BEARISH_PINBAR", "BEARISH_ENGULFING"] and rsi_14 >= 58:
                print(f"🎯 [{profile.user.username}] Bearish Confluence Triggered on {instrument}!", flush=True)
                if broker_type == 'capital':
                    place_capital_com_order(profile, instrument, "SELL", current_price, atr_value)
                else:
                    place_oanda_order(profile, instrument, "SELL", current_price, atr_value)

if __name__ == "__main__":
    print("🚀 Elite Celooh 10-Asset Multi-Broker Bot Engine Started...", flush=True)
    while True:
        try:
            run_bot_cycle()
        except Exception as e:
            print(f"[UNHANDLED EXCEPTION] {e}", flush=True)
        time.sleep(15)