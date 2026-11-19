from django.urls import path
from . import views

urlpatterns = [
    path('', views.branches_page, name='branches_page'),
    path('create/', views.branch_create, name='branch_create'),
    path('<uuid:branch_id>/update/', views.branch_update, name='branch_update'),
    path('<uuid:branch_id>/set-main/', views.ajax_set_main_branch, name='set_main_branch'),
    path('<uuid:branch_id>/toggle-status/', views.branch_toggle_status, name='branch_toggle_status'),
    path('<uuid:branch_id>/lock-toggle/', views.branch_lock_toggle, name='branch_lock_toggle'),
    path('<uuid:branch_id>/regenerate-token/', views.branch_token_regenerate, name='branch_token_regenerate'),
    path('transfers/', views.transfers_buffer_view, name='transfers_buffer'),
    path('approvals/', views.approvals_list, name='approvals_list'),
    path('approvals/<int:approval_id>/review/', views.ajax_review_approval, name='review_approval'),
]
