from django.contrib import admin
from django.urls import path
from dashboard.views import (
    dashboard_view, 
    signup_view, 
    login_view, 
    logout_view, 
    tradingview_webhook, 
    create_crypto_invoice, 
    crypto_payment_ipn
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard_view, name='dashboard'),
    path('signup/', signup_view, name='signup'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    
    # API Webhooks & Payment Routes
    path('api/v1/webhook/', tradingview_webhook, name='tradingview_webhook'),
    path('api/v1/subscribe/', create_crypto_invoice, name='create_crypto_invoice'),
    path('api/v1/ipn/', crypto_payment_ipn, name='crypto_payment_ipn'),
]