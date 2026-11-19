from django.urls import path
from . import views

urlpatterns = [
    path('ping/', views.sync_ping, name='sync_ping'),
    path('push/', views.sync_push, name='sync_push'),
    path('branches/pull/', views.sync_branches_pull, name='sync_branches_pull'),
    path('transfers/pending/', views.sync_pending_transfers, name='sync_pending_transfers'),
    path('transfers/outgoing-status/', views.sync_outgoing_transfers_status, name='sync_outgoing_transfers_status'),
    path('catalog/pull/', views.sync_catalog_pull, name='sync_catalog_pull'),
    path('monitor/', views.sync_status_dashboard, name='sync_status_dashboard'),
]
