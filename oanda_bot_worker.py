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
        print(f"[TELEGRAM ERROR] {e}")

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
    if len(candles) < 4:
        return "NEUTRAL"
    c1, c2, c3, c4 = candles[-4], candles[-3], candles[-2], candles[-1]
    if c4['high'] > c3['high'] and c3['high'] > c2['high'] and c4['low'] > c3['low'] and c3['low'] > c2['low']:
        return "BULLISH_STRUCTURE"
    if c4['high'] < c3['high'] and c3['high'] < c2['high'] and c4['low'] < c3['low'] and c3['low'] < c2['low']:
        return "BEARISH_STRUCTURE"
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

def place_oanda_order(profile, instrument, direction, current_price):
    risk_level = getattr(profile, 'risk_level', 'medium')
    if instrument == "XAU_USD":
        sl_distance = 5.0 if risk_level == 'low' else (3.0 if risk_level == 'medium' else 2.0)
        tp_distance = sl_distance * 2.0
        units = 1 if risk_level == 'low' else (2 if risk_level == 'medium' else 3)
    else:
        sl_distance = 0.0030 if risk_level == 'low' else (0.0020 if risk_level == 'medium' else 0.0010)
        tp_distance = sl_distance * 2.0
        units = 1000 if risk_level == 'low' else (2000 if risk_level == 'medium' else 5000)

    if direction == "BUY":
        units_str = str(units)
        sl_price = round(current_price - sl_distance, 5 if instrument == "EUR_USD" else 2)
        tp_price = round(current_price + tp_distance, 5 if instrument == "EUR_USD" else 2)
    else:
        units_str = str(-units)
        sl_price = round(current_price + sl_distance, 5 if instrument == "EUR_USD" else 2)
        tp_price = round(current_price - tp_distance, 5 if instrument == "EUR_USD" else 2)

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
            msg = f"🚀 CELOOH BOT TRADE EXECUTED (OANDA)\nAsset: {instrument}\nDirection: {direction}\nUnits: {units_str}\nSL: {sl_price} | TP: {tp_price}"
            print(f"✅ [OANDA ORDER SUCCESS] {instrument} {direction}")
            send_telegram_alert(msg)
            return True
        else:
            print(f"❌ [OANDA REJECTED] {instrument}: {response.text}")
    except Exception as e:
        print(f"[ERROR] OANDA order exception: {e}")
    return False

def place_mt5_order(profile, instrument, direction, current_price):
    """
    Placeholder handler for MT5 broker execution (Exness, HFM, etc.).
    """
    print(f"⚡ [MT5 SIGNAL] User {profile.user.username} -> {instrument} {direction} at {current_price} (Server: {profile.mt5_server})")
    send_telegram_alert(f"🚀 CELOOH BOT TRADE (MT5)\nAsset: {instrument}\nDirection: {direction}\nLogin: {profile.mt5_login}")
    return True

def sync_closed_trades_pnl(profile):
    if profile.broker_type == 'oanda':
        if not profile.oanda_account_id or not profile.oanda_api_token:
            return
        base_url = get_oanda_base_url(profile.oanda_environment)
        headers = get_oanda_headers(profile.oanda_api_token)
        url = f"{base_url}/accounts/{profile.oanda_account_id}/trades?state=CLOSED"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                closed_trades = response.json().get('trades', [])
                total_wins, total_losses, net_profit = 0, 0, 0.0
                for trade in closed_trades:
                    realized_pl = float(trade.get('realizedPL', 0.0))
                    net_profit += realized_pl
                    if realized_pl > 0: total_wins += 1
                    elif realized_pl < 0: total_losses += 1
                profile.total_wins = total_wins
                profile.total_losses = total_losses
                profile.total_trades = total_wins + total_losses
                profile.net_profit = round(net_profit, 2)
                if profile.total_trades > 0:
                    profile.win_rate = round((total_wins / profile.total_trades) * 100, 1)
                profile.save()
        except Exception as e:
            print(f"[SYNC ERROR] {e}")

def run_bot_cycle():
    active_profiles = Profile.objects.filter(is_bot_active=True)
    if not active_profiles.exists():
        return

    for profile in active_profiles:
        # Validate Credentials based on Broker Type
        if profile.broker_type == 'oanda':
            if not profile.oanda_account_id or not profile.oanda_api_token:
                continue
            base_url = get_oanda_base_url(profile.oanda_environment)
            headers = get_oanda_headers(profile.oanda_api_token)
        elif profile.broker_type == 'mt5':
            if not profile.mt5_login or not profile.mt5_password or not profile.mt5_server:
                continue
            # For MT5 data fetching, fall back to public OANDA practice feed for analysis
            base_url = get_oanda_base_url('practice')
            headers = {"Content-Type": "application/json"}
        else:
            continue

        sync_closed_trades_pnl(profile)

        for instrument in ASSET_LIST:
            daily_candles = fetch_full_candles(base_url, headers, instrument=instrument, count=10, granularity="D")
            macro_structure = analyze_market_structure(daily_candles)
            
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

            # HIGH CONFLUENCE BUY
            if (macro_structure == "BULLISH_STRUCTURE" or current_price > ema_200) and \
               candle_signal in ["BULLISH_PINBAR", "BULLISH_ENGULFING"] and rsi_14 <= 40:
                print(f"🎯 [{profile.user.username}] High Confluence BUY Signal on {instrument}")
                if profile.broker_type == 'oanda':
                    place_oanda_order(profile, instrument, "BUY", current_price)
                else:
                    place_mt5_order(profile, instrument, "BUY", current_price)

            # HIGH CONFLUENCE SELL
            elif (macro_structure == "BEARISH_STRUCTURE" or current_price < ema_200) and \
                 candle_signal in ["BEARISH_PINBAR", "BEARISH_ENGULFING"] and rsi_14 >= 60:
                print(f"🎯 [{profile.user.username}] High Confluence SELL Signal on {instrument}")
                if profile.broker_type == 'oanda':
                    place_oanda_order(profile, instrument, "SELL", current_price)
                else:
                    place_mt5_order(profile, instrument, "SELL", current_price)

if __name__ == "__main__":
    print("🚀 Dual-Broker Celooh Bot Engine Started...")
    while True:
        try:
            run_bot_cycle()
        except Exception as e:
            print(f"[UNHANDLED EXCEPTION] {e}")
        time.sleep(15)