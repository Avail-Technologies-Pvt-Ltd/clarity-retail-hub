from django.urls import path
from . import views

urlpatterns = [
    path('', views.reports_dashboard, name='reports_dashboard'),
    path('stock-matrix/', views.stock_matrix_view, name='stock_matrix'),
    path('export/daily/', views.export_daily_csv, name='export_daily_csv'),
    path('export/stock-matrix/', views.export_stock_matrix_csv, name='export_stock_matrix_csv'),
]
