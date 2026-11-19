from django.urls import path
from . import views

urlpatterns = [
    path('', views.team_list, name='team_list'),
    path('ajax/save/', views.ajax_save_user, name='ajax_save_user'),
    path('ajax/toggle/<int:user_id>/', views.ajax_toggle_user_status, name='ajax_toggle_user_status'),
    path('profile/update/', views.ajax_update_profile, name='ajax_update_profile'),
    path('profile/password/', views.ajax_change_password, name='ajax_change_password'),
]
