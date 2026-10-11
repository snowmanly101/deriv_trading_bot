import subprocess
import os
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Profile

# Dictionary to track running process IDs per user in memory
RUNNING_BOTS = {}

@login_required
def dashboard_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        deriv_account_id = request.POST.get("deriv_account_id")
        deriv_api_token = request.POST.get("deriv_api_token")
        is_bot_active = request.POST.get("is_bot_active") == "on"

        # Lock account ID once set to prevent trial manipulation
        if not profile.deriv_account_id and deriv_account_id:
            profile.deriv_account_id = deriv_account_id

        profile.deriv_api_token = deriv_api_token
        profile.is_bot_active = is_bot_active
        profile.save()

        # Handle Dynamic Bot Launch/Termination per user session
        user_id = request.user.id
        app_id = "10354646"  # Your central App ID or user custom App ID

        if is_bot_active and profile.deriv_api_token:
            # Terminate any existing instance for this user first
            if user_id in RUNNING_BOTS and RUNNING_BOTS[user_id].poll() is None:
                RUNNING_BOTS[user_id].terminate()

            # Spawn a fresh background process specifically for this user's API token
            proc = subprocess.Popen([
                "python3", "user_bot_worker.py", str(app_id), profile.deriv_api_token
            ])
            RUNNING_BOTS[user_id] = proc
        else:
            # User turned off the switch -> Stop their specific process
            if user_id in RUNNING_BOTS and RUNNING_BOTS[user_id].poll() is None:
                RUNNING_BOTS[user_id].terminate()
                del RUNNING_BOTS[user_id]

        return redirect("dashboard")

    return render(request, "index.html", {"profile": profile, "username": request.user.username})