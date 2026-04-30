"""Audit views."""
from __future__ import annotations

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from modules.accounts.permissions import IsSuperAdmin

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventListView(generics.ListAPIView):
    queryset = AuditEvent.objects.all()
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
