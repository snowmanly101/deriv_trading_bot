import subprocess
import os
import json
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Profile

@login_required(login_url='login')
def dashboard_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        deriv_account_id = request.POST.get('deriv_account_id')
        deriv_api_token = request.POST.get('deriv_api_token')
        risk_profile = request.POST.get('risk_profile')
        is_bot_active = request.POST.get('is_bot_active') == 'on'
        
        # Save credentials and preferences
        if deriv_account_id:
            profile.deriv_account_id = deriv_account_id
        if deriv_api_token:
            profile.deriv_api_token = deriv_api_token
        if risk_profile:
            profile.risk_profile = risk_profile
            
        bot_state_changed = profile.is_bot_active != is_bot_active
        profile.is_bot_active = is_bot_active
        profile.save()
        
        # Handle Worker Process Spawning
        if bot_state_changed and is_bot_active and profile.deriv_api_token:
            worker_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(_file_))), 'user_bot_worker.py')
            subprocess.Popen(['python3', worker_path, str(request.user.id)])
            
        return redirect('dashboard')

    context = {
        'profile': profile,
    }
    return render(request, 'dashboard/index.html', context)

def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            Profile.objects.create(user=user)
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'dashboard/signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'dashboard/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')

# --- TRADINGVIEW WEBHOOK API ---
@csrf_exempt
def tradingview_webhook(request):
    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            signal = payload.get('signal')      # 'BUY' or 'SELL'
            symbol = payload.get('symbol')      # e.g., 'R_100'
            secret_key = payload.get('key')    # Secret security token
            
            if secret_key != "CeloohSecureWebhookKey2026":
                return JsonResponse({'status': 'unauthorized'}, status=401)
                
            print(f"[WEBHOOK RECEIVED] Symbol: {symbol} | Signal: {signal}")
            return JsonResponse({'status': 'success', 'signal': signal})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'invalid method'}, status=405)

# --- CRYPTO PAYMENT GATEWAY (NOWPayments / CoinGate IPN) ---
@login_required
def create_crypto_invoice(request):
    # Generates link for $30 monthly crypto subscription
    invoice_url = "https://nowpayments.io/payment/?iid=YOUR_NOWPAYMENTS_INVOICE_ID"
    return redirect(invoice_url)

@csrf_exempt
def crypto_payment_ipn(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        payment_status = data.get('payment_status')
        custom_user_id = data.get('order_id')
        
        if payment_status == 'finished':
            try:
                profile = Profile.objects.get(user_id=custom_user_id)
                profile.has_paid_subscription = True
                profile.subscription_expiry = timezone.now() + timedelta(days=30)
                profile.save()
                return JsonResponse({'status': 'subscription renewed'})
            except Profile.DoesNotExist:
                return JsonResponse({'status': 'user not found'}, status=404)
                
    return JsonResponse({'status': 'ignored'})