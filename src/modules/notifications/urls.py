from django.urls import path

from . import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("unread-count/", views.NotificationUnreadCountView.as_view(), name="notification-unread-count"),
    path("<uuid:pk>/read/", views.mark_read_view, name="notification-mark-read"),
    path("mark-all-read/", views.mark_all_read_view, name="notification-mark-all-read"),
    path("<uuid:pk>/", views.delete_notification_view, name="notification-delete"),
]
