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
    
    # Daily Market Intelligence & News Directives Data
    market_intelligence = {
        'top_asset': 'XAU/USD (Gold) & EUR/USD',
        'market_bias': 'Bullish Confluence',
        'news_event': 'US Federal Reserve Policy Insights & CPI Inflation Data Watch',
        'trading_reason': '24-Hour macro daily trend shows strong buyer support above the 200 EMA. Short-term M5 pullbacks touching lower Bollinger Bands offer high-confluence entry setups.',
        'bot_status_directive': 'Active - Multi-asset scanner analyzing 15s intervals with risk controls.'
    }
    
    return render(request, 'dashboard/index.html', {
        'profile': profile,
        'market_intel': market_intelligence
    })

@login_required
def update_broker_settings(request):
    if request.method == 'POST':
        profile, created = Profile.objects.get_or_create(user=request.user)
        
        # OANDA Broker Credentials & Settings
        profile.oanda_environment = request.POST.get('oanda_environment', 'practice')
        profile.oanda_account_id = request.POST.get('oanda_account_id', '').strip()
        profile.oanda_api_token = request.POST.get('oanda_api_token', '').strip()
        
        # Risk Management Settings (Low / Medium / High)
        risk_level = request.POST.get('risk_level', 'medium').lower()
        if hasattr(profile, 'risk_level'):
            profile.risk_level = risk_level
            
        # Bot Toggle Control
        profile.is_bot_active = request.POST.get('is_bot_active') == 'on'
        
        profile.save()
    return redirect('dashboard_view')