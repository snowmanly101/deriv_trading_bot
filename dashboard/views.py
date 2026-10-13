from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Profile

@login_required
def dashboard_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    context = {
        'profile': profile
    }
    return render(request, 'dashboard/index.html', context)

@login_required
def update_broker_settings(request):
    if request.method == 'POST':
        profile, created = Profile.objects.get_or_create(user=request.user)
        
        # Update OANDA settings from the form
        profile.oanda_environment = request.POST.get('oanda_environment', 'practice')
        profile.oanda_account_id = request.POST.get('oanda_account_id', '').strip()
        profile.oanda_token = request.POST.get('oanda_api_token', '').strip()
        
        # Handle bot toggle switch
        is_active = request.POST.get('is_bot_active') == 'on'
        profile.is_bot_active = is_active
        
        profile.save()
    return redirect('dashboard_view')