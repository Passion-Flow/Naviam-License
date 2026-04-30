"""Notification views."""
from __future__ import annotations

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread_only") == "true":
            qs = qs.filter(is_read=False)
        return qs


class NotificationUnreadCountView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread_count": count})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_read_view(request, pk):
    try:
        notif = Notification.objects.get(pk=pk, user=request.user)
    except Notification.DoesNotExist:
        return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
    notif.is_read = True
    notif.save(update_fields=["is_read"])
    return Response({"detail": "marked as read"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_read_view(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"detail": "all marked as read"})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_notification_view(request, pk):
    try:
        notif = Notification.objects.get(pk=pk, user=request.user)
    except Notification.DoesNotExist:
        return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
    notif.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
