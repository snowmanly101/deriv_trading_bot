from django.contrib import admin
from django.urls import path
from dashboard import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard_view, name='dashboard_view'),
    path('update-broker/', views.update_broker_settings, name='update_broker_settings'),
]