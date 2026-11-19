from django.urls import path
from . import views

urlpatterns = [
    path('', views.marketplace_home, name='marketplace_home'),
    path('ajax/toggle-optin/', views.ajax_toggle_optin, name='ajax_toggle_optin'),
    path('ajax/create-request/', views.ajax_create_request, name='ajax_create_request'),
    path('ajax/cancel-request/<int:req_id>/', views.ajax_cancel_request, name='ajax_cancel_request'),
]
