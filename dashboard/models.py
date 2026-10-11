from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    
    # Deriv / MT5 Settings
    deriv_account_id = models.CharField(max_length=50, blank=True, null=True)
    deriv_api_token = models.CharField(max_length=255, blank=True, null=True)
    is_bot_active = models.BooleanField(default=False)
    
    # Registration & 5-Day Free Trial Logic
    created_at = models.DateTimeField(auto_now_add=True)
    has_paid_subscription = models.BooleanField(default=False)
    btc_tx_hash = models.CharField(max_length=255, blank=True, null=True)

    @property
    def is_trial_active(self):
        """Returns True if user is within their 5-day free trial period."""
        if self.has_paid_subscription:
            return True
        expiration_date = self.created_at + datetime.timedelta(days=5)
        return timezone.now() < expiration_date

    @property
    def trial_days_remaining(self):
        """Returns days left in trial."""
        expiration_date = self.created_at + datetime.timedelta(days=5)
        remaining = expiration_date - timezone.now()
        return max(0, remaining.days)

    def __str__(self):
        return f"{self.user.username}'s Profile"