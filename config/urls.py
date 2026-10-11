from django.contrib import admin
from django.urls import path
from dashboard.views import dashboard_home, signup_view, login_view, logout_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard_home, name='dashboard-home'),
    path('signup/', signup_view, name='signup'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
]