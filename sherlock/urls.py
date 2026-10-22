# sherlock-python/sherlock/urls.py
"""
Main URL Configuration for the Sherlock project.
...
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from inventory import views as inventory_views


urlpatterns = [
    path('admin/', admin.site.urls),

    path('', RedirectView.as_view(pattern_name='teaching:dashboard', permanent=False), name='homepage'),

    path('teaching/', include('teaching.urls')),

    path('accounts/signup/', inventory_views.signup, name='signup'),
    path('accounts/', include('django.contrib.auth.urls')),

    path('', include('inventory.urls')),
]

handler404 = 'inventory.views.custom_page_not_found_view'
