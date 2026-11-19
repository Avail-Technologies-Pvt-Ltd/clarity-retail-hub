from django.urls import path
from . import views

urlpatterns = [
    path('', views.subscription_page, name='subscription_page'),
    path('ajax/request-upgrade/', views.ajax_request_upgrade, name='ajax_request_upgrade'),
]
