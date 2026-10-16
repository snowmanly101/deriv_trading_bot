import os
import sys
import time
import requests
import django
import pandas as pd

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from dashboard.models import Profile

# 1. Asset List - EXCLUSIVELY TRADING GOLD
ASSET_LIST = ["GOLD"]

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

def get_capital_session(profile):
    base_url = "https://api-capital.backend-capital.com/api/v1" if profile.oanda_environment == 'live' else "https://demo-api-capital.backend-capital.com/api/v1"
    
    url = f"{base_url}/session"
    headers = {
        "X-CAP-API-KEY": getattr(profile, 'capital_security_token', ''),
        "Content-Type": "application/json"
    }
    
    capital_email = getattr(profile, 'capital_email', '') or profile.user.email
    payload = {
        "identifier": capital_email,
        "password": getattr(profile, 'capital_cst_token', '')
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            cst = response.headers.get("CST")
            x_sec = response.headers.get("X-SECURITY-TOKEN")
            return cst, x_sec
    except Exception as e:
        print(f"[CAPITAL SESSION ERROR] {e}", flush=True)
    return None, None

def get_oanda_base_url(environment):
    if environment == 'live':
        return "https://api-fxtrade.oanda.com/v3"
    return "https://api-fxpractice.oanda.com/v3"

def get_oanda_headers(api_token):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}"
    }

def fetch_full_candles(base_url, headers, instrument="GOLD", count=30, granularity="M5"):
    if "capital.backend-capital.com" in base_url:
        epic = "GOLD" if instrument in ["GOLD", "XAU_USD"] else instrument.replace("_", "")
        cap_res = "MINUTE_5" if granularity == "M5" else "MINUTE"
        url = f"{base_url}/prices/{epic}?resolution={cap_res}&max={count}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                prices = response.json().get('prices', [])
                parsed = []
                for p in prices:
                    parsed.append({
                        'open': float(p['openPrice']['bid']),
                        'high': float(p['highPrice']['bid']),
                        'low': float(p['lowPrice']['bid']),
                        'close': float(p['closePrice']['bid'])
                    })
                return parsed
        except Exception as e:
            print(f"[ERROR] Capital candle fetch failed: {e}", flush=True)
        return []
    else:
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
            print(f"[ERROR] OANDA candle fetch failed: {e}", flush=True)
        return []

def evaluate_gold_signal(candles):
    if len(candles) < 15:
        return None
    df = pd.DataFrame(candles)
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

    ema9 = df['ema9'].iloc[-1]
    ema21 = df['ema21'].iloc[-1]

    if ema9 > ema21:
        return "BUY"
    elif ema9 < ema21:
        return "SELL"
    return None

def place_capital_com_order(profile, instrument, direction):
    cst, x_sec = get_capital_session(profile)
    if not cst or not x_sec:
        return False

    base_url = "https://api-capital.backend-capital.com/api/v1" if profile.oanda_environment == 'live' else "https://demo-api-capital.backend-capital.com/api/v1"
    epic_symbol = "GOLD" if instrument in ["GOLD", "XAU_USD"] else instrument.replace("_", "")

    payload = {
        "epic": epic_symbol,
        "direction": direction,
        "size": 1.0,
        "guaranteedStopLoss": False
    }
    headers = {"CST": cst, "X-SECURITY-TOKEN": x_sec, "Content-Type": "application/json"}
    
    try:
        response = requests.post(f"{base_url}/positions", headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"✅ [CAPITAL ORDER SUCCESS] {direction} GOLD", flush=True)
            send_telegram_alert(f"🚀 CELOOH BOT TRADE (Capital.com)\nAsset: GOLD\nDirection: {direction}\nSize: 1.0 Lot")
            return True
    except Exception as e:
        print(f"[CAPITAL ERROR] {e}", flush=True)
    return False

def place_oanda_order(profile, instrument, direction):
    risk_level = getattr(profile, 'risk_level', 'medium')
    units = 1000 if risk_level == 'low' else 2000
    units_str = str(units) if direction == "BUY" else str(-units)

    base_url = get_oanda_base_url(profile.oanda_environment)
    headers = get_oanda_headers(profile.oanda_api_token)
    url = f"{base_url}/accounts/{profile.oanda_account_id}/orders"
    
    payload = {
        "order": {
            "units": units_str,
            "instrument": "XAU_USD" if instrument == "GOLD" else instrument,
            "timeInForce": "FOK",
            "type": "MARKET",
            "positionFill": "DEFAULT"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"✅ [OANDA ORDER SUCCESS] {direction} GOLD", flush=True)
            send_telegram_alert(f"🚀 CELOOH BOT TRADE (OANDA)\nAsset: GOLD\nDirection: {direction}")
            return True
    except Exception as e:
        print(f"[OANDA ERROR] {e}", flush=True)
    return False

def run_bot_cycle():
    active_profiles = Profile.objects.filter(is_bot_active=True)
    if not active_profiles.exists():
        print("🔍 [BOT SCAN] Waiting for active user profile...", flush=True)
        return

    for profile in active_profiles:
        broker_type = getattr(profile, 'broker_type', 'oanda')
        if broker_type == 'polymarket':
            continue  # Handled separately if polymarket service is active

        print(f"⚡ [SCAN] User: {profile.user.username} | Broker: {broker_type.upper()} | Asset: GOLD ONLY", flush=True)

        if broker_type == 'capital':
            cst, xsec = get_capital_session(profile)
            if not cst or not xsec:
                continue
            headers = {"CST": cst, "X-SECURITY-TOKEN": xsec, "Content-Type": "application/json"}
            base_url = "https://api-capital.backend-capital.com/api/v1" if profile.oanda_environment == 'live' else "https://demo-api-capital.backend-capital.com/api/v1"
        else:
            base_url = get_oanda_base_url(getattr(profile, 'oanda_environment', 'practice'))
            headers = get_oanda_headers(getattr(profile, 'oanda_api_token', ''))

        m5_candles = fetch_full_candles(base_url, headers, instrument="GOLD", count=30, granularity="M5")
        if len(m5_candles) < 15:
            continue

        signal = evaluate_gold_signal(m5_candles)
        if signal:
            print(f"⚡ Signal Detected: {signal} on GOLD", flush=True)
            if broker_type == 'capital':
                place_capital_com_order(profile, "GOLD", signal)
            else:
                place_oanda_order(profile, "GOLD", signal)

if __name__ == "__main__":
    print("⚡ Celooh Gold Engine Active...", flush=True)
    while True:
        try:
            run_bot_cycle()
        except Exception as e:
            print(f"[ERROR] {e}", flush=True)
        time.sleep(10)