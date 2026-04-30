"""Audit serializers."""
from __future__ import annotations

from rest_framework import serializers

from .models import AuditEvent


def _hex_bytes(value: bytes | None) -> str | None:
    if value is None:
        return None
    return value.hex()


class AuditEventSerializer(serializers.ModelSerializer):
    prev_hash_hex = serializers.SerializerMethodField()
    hash_hex = serializers.SerializerMethodField()
    signature_hex = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "ts",
            "actor_id",
            "actor_name",
            "actor_kind",
            "actor_ip",
            "action",
            "target_kind",
            "target_id",
            "request_id",
            "payload",
            "created_at",
            "prev_hash_hex",
            "hash_hex",
            "signature_hex",
            "signature_kid",
        ]
        read_only_fields = fields

    def get_prev_hash_hex(self, obj: AuditEvent) -> str | None:
        return _hex_bytes(obj.prev_hash)

    def get_hash_hex(self, obj: AuditEvent) -> str | None:
        return _hex_bytes(obj.hash)

    def get_signature_hex(self, obj: AuditEvent) -> str | None:
        return _hex_bytes(obj.signature)
