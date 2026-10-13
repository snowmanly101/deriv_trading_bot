from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard_view'),
    path('update-broker/', views.update_broker_settings, name='update_broker_settings'),
]