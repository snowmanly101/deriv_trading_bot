from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    # Broker Choice: 'oanda', 'capital', or 'mt5'
    broker_type = models.CharField(max_length=20, default='oanda')
    
    # OANDA Broker Configuration
    oanda_environment = models.CharField(max_length=20, default='practice')
    oanda_account_id = models.CharField(max_length=100, blank=True, null=True)
    oanda_api_token = models.CharField(max_length=255, blank=True, null=True)
    
    # Capital.com Broker Configuration
    capital_email = models.EmailField(blank=True, null=True)
    capital_security_token = models.CharField(max_length=255, blank=True, null=True)
    capital_cst_token = models.CharField(max_length=255, blank=True, null=True)
    
    # MT5 Broker Configuration (For Exness, HFM, IC Markets, etc.)
    mt5_login = models.CharField(max_length=50, blank=True, null=True)
    mt5_password = models.CharField(max_length=100, blank=True, null=True)
    mt5_server = models.CharField(max_length=100, blank=True, null=True)
    
    # Risk Management Profile
    risk_level = models.CharField(max_length=20, default='medium')

    # Bot Control Flag
    is_bot_active = models.BooleanField(default=False)
    
    # Trial & Subscription Access
    trial_days_remaining = models.IntegerField(default=5)
    is_trial_active = models.BooleanField(default=True)
    has_paid_subscription = models.BooleanField(default=False)
    
    # Performance Metrics
    total_trades = models.IntegerField(default=0)
    total_wins = models.IntegerField(default=0)
    total_losses = models.IntegerField(default=0)
    win_rate = models.FloatField(default=0.0)
    net_profit = models.FloatField(default=0.0)

    def __str__(self):
        return self.user.username