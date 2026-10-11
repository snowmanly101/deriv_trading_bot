from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from .models import UserProfile

def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Automatically create a UserProfile for the new user
            UserProfile.objects.create(user=user)
            login(request, user)
            return redirect('dashboard-home')
    else:
        form = UserCreationForm()
    return render(request, 'dashboard/signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard-home')
    else:
        form = AuthenticationForm()
    return render(request, 'dashboard/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required(login_url='/login/')
def dashboard_home(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        profile.deriv_account_id = request.POST.get('deriv_account_id')
        profile.deriv_api_token = request.POST.get('deriv_api_token')
        profile.is_bot_active = 'is_bot_active' in request.POST
        profile.save()
        return redirect('dashboard-home')

    context = {
        'username': request.user.username,
        'profile': profile,
    }
    return render(request, 'dashboard/index.html', context)