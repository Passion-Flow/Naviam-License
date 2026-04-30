"""Activation views.

V1：
- POST /v1/activations/decode/ — Console 端验证 Cloud ID 内容。
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from modules.accounts.permissions import IsSuperAdmin

from .cloud_id_codec import CloudIDError, decode as decode_cloud_id


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def decode_cloud_id_view(request: Request) -> Response:
    text = request.data.get("cloud_id_text", "")
    if not text:
        return Response(
            {"detail": "cloud_id_text required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        obj = decode_cloud_id(text)
    except CloudIDError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {
            "schema_version": obj.get("schema_version"),
            "product_code": obj.get("product_code"),
            "instance_id": obj.get("instance_id"),
            "instance_pubkey_fp": obj.get("instance_pubkey_fp"),
            "hardware_fp": obj.get("hardware_fp"),
            "nonce": obj.get("nonce"),
            "created_at": obj.get("created_at"),
        },
        status=status.HTTP_200_OK,
    )
