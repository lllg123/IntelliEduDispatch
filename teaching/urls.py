from django.urls import path

from . import views

app_name = 'teaching'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('resources/', views.resource_list, name='resource_list'),
    path('resources/new/', views.resource_create, name='resource_create'),
    path('resources/<int:pk>/edit/', views.resource_edit, name='resource_edit'),
    path('requests/', views.request_list, name='request_list'),
    path('requests/new/', views.request_create, name='request_create'),
    path('requests/assistant/', views.request_assistant, name='request_assistant'),
    path('requests/<int:pk>/', views.request_detail, name='request_detail'),
    path('requests/<int:pk>/recommend/', views.recommend, name='recommend'),
    path('requests/<int:pk>/confirm/', views.confirm, name='confirm'),
    path('requests/<int:pk>/cancel/', views.cancel, name='cancel'),
]
