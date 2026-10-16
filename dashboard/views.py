import requests
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import login, logout
from .models import Profile

def landing_view(request):
    return render(request, 'dashboard/landing.html')

def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if User.objects.filter(username=username).exists():
            return render(request, 'dashboard/signup.html', {'error': 'Username already taken.'})
            
        user = User.objects.create_user(username=username, email=email, password=password)
        Profile.objects.create(user=user)
        login(request, user)
        return redirect('dashboard_view')
        
    return render(request, 'dashboard/signup.html')

def payment_view(request):
    return render(request, 'dashboard/payment.html')

def custom_logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    market_intelligence = {
        'top_asset': 'XAU/USD (Gold) & EUR/USD',
        'market_bias': 'Bullish Confluence',
        'news_event': 'US Federal Reserve Policy Insights & CPI Inflation Data Watch',
        'trading_reason': '24-Hour macro daily trend shows strong buyer support above the 200 EMA. Short-term M5 pullbacks touching lower Bollinger Bands offer high-confluence entry setups.',
        'bot_status_directive': 'Active - Multi-asset scanner analyzing market structure & news guards.'
    }
    
    try:
        response = requests.get("https://finnhub.io/api/v1/news?category=forex&token=db7cg41r01qptb5pccs0db7cg41r01qptb5pccsg", timeout=3)
        if response.status_code == 200:
            news_data = response.json()
            if news_data and isinstance(news_data, list) and len(news_data) > 0:
                latest_headline = news_data[0].get('headline', '')
                if latest_headline:
                    market_intelligence['news_event'] = f"Live Feed: {latest_headline}"
    except Exception:
        pass

    return render(request, 'dashboard/index.html', {
        'profile': profile,
        'market_intel': market_intelligence
    })

@login_required
def update_broker_settings(request):
    if request.method == 'POST':
        profile, created = Profile.objects.get_or_create(user=request.user)
        
        # Broker Type Selection ('oanda', 'capital', 'mt5', or 'polymarket')
        profile.broker_type = request.POST.get('broker_type', 'oanda')
        
        # OANDA Broker Credentials & Settings
        profile.oanda_environment = request.POST.get('oanda_environment', 'practice')
        profile.oanda_account_id = request.POST.get('oanda_account_id', '').strip()
        profile.oanda_api_token = request.POST.get('oanda_api_token', '').strip()
        
        # Capital.com Broker Credentials & Settings
        profile.capital_email = request.POST.get('capital_email', '').strip()
        profile.capital_security_token = request.POST.get('capital_security_token', '').strip()
        profile.capital_cst_token = request.POST.get('capital_cst_token', '').strip()
        
        # MT5 Broker Credentials & Settings
        profile.mt5_login = request.POST.get('mt5_login', '').strip()
        profile.mt5_password = request.POST.get('mt5_password', '').strip()
        profile.mt5_server = request.POST.get('mt5_server', '').strip()

        # Polymarket Reward Bot Settings
        profile.poly_deposit_wallet = request.POST.get('poly_deposit_wallet', '').strip()
        profile.poly_private_key = request.POST.get('poly_private_key', '').strip()
        profile.poly_api_key = request.POST.get('poly_api_key', '').strip()
        profile.poly_api_secret = request.POST.get('poly_api_secret', '').strip()
        profile.poly_api_passphrase = request.POST.get('poly_api_passphrase', '').strip()
        profile.is_poly_bot_active = request.POST.get('is_poly_bot_active') == 'on'
        
        # Risk Management Settings
        risk_level = request.POST.get('risk_level', 'medium').lower()
        profile.risk_level = risk_level
            
        # Bot Toggle Control
        profile.is_bot_active = request.POST.get('is_bot_active') == 'on'
        
        profile.save()
    return redirect('dashboard_view')