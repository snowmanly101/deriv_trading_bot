from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from dashboard import views as dashboard_views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Landing & Authentication Routes
    path('', dashboard_views.landing_view, name='landing'),
    path('login/', auth_views.LoginView.as_view(template_name='dashboard/login.html', next_page='dashboard_view'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('signup/', dashboard_views.signup_view, name='signup'),
    path('payment/', dashboard_views.payment_view, name='payment'),
    
    # Dashboard Routes
    path('dashboard/', dashboard_views.dashboard_view, name='dashboard_view'),
    path('update-broker/', dashboard_views.update_broker_settings, name='update_broker_settings'),
]