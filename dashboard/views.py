import subprocess
import os
import signal
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Profile

@login_required(login_url='login')
def dashboard_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        deriv_account_id = request.POST.get('deriv_account_id')
        deriv_api_token = request.POST.get('deriv_api_token')
        is_bot_active = request.POST.get('is_bot_active') == 'on'
        
        # Save credentials
        if deriv_account_id:
            profile.deriv_account_id = deriv_account_id
        if deriv_api_token:
            profile.deriv_api_token = deriv_api_token
            
        # Check if bot state is changing
        bot_state_changed = profile.is_bot_active != is_bot_active
        profile.is_bot_active = is_bot_active
        profile.save()
        
        # Handle Worker Process Spawning / Termination
        if bot_state_changed:
            if is_bot_active and profile.deriv_api_token:
                # Spawn worker script as an isolated background process
                worker_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(_file_))), 'user_bot_worker.py')
                subprocess.Popen(['python3', worker_path, str(request.user.id)])
            else:
                # When turned off, the worker script automatically checks db flag and exits itself,
                # or you can implement a process kill tracker if needed.
                pass
            
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