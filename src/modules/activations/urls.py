from django.urls import path

from .views import decode_cloud_id_view

urlpatterns = [
    path("decode/", decode_cloud_id_view, name="decode-cloud-id"),
]
