from django.urls import path
from . import views

urlpatterns = [
    path('', views.notifications_list, name='notifications_list'),
    path('ajax/mark-read/', views.ajax_mark_all_read, name='ajax_mark_all_read'),
    path('ajax/unread-count/', views.ajax_unread_count, name='ajax_unread_count'),
]
