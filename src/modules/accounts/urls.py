from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("totp/", views.totp_verify_view, name="totp-verify"),
    path("logout/", views.logout_view, name="logout"),
    path("me/", views.me_view, name="me"),
    path("change-password/", views.change_password_view, name="change-password"),
    path("login-history/", views.login_history_view, name="login-history"),
    path("totp/setup/", views.totp_setup_view, name="totp-setup"),
    path("totp/disable/", views.totp_disable_view, name="totp-disable"),
]
