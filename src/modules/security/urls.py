from django.urls import path

from . import views

urlpatterns = [
    path("security/", views.security_settings_view, name="security-settings"),
]
