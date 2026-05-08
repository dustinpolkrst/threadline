from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage
from django.db import OperationalError, ProgrammingError
from storages.backends.s3 import S3Storage


class ThreadlineMediaStorage(Storage):
    def __init__(self):
        self._local = None
        self._s3 = None
        self._s3_signature = None

    def _open(self, name, mode="rb"):
        return self._backend().open(name, mode)

    def _save(self, name, content):
        return self._backend().save(name, content)

    def delete(self, name):
        return self._backend().delete(name)

    def exists(self, name):
        return self._backend().exists(name)

    def size(self, name):
        return self._backend().size(name)

    def url(self, name):
        return self._backend().url(name)

    def get_available_name(self, name, max_length=None):
        return self._backend().get_available_name(name, max_length=max_length)

    def _backend(self):
        config = self._s3_config()
        if config:
            signature = tuple(sorted((key, value or "") for key, value in config.items()))
            if self._s3 is None or signature != self._s3_signature:
                self._s3 = S3Storage(**config)
                self._s3_signature = signature
            return self._s3
        if self._local is None:
            self._local = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)
        return self._local

    def _s3_config(self):
        if settings.MEDIA_STORAGE_BACKEND == "s3":
            return {
                "access_key": getattr(settings, "AWS_ACCESS_KEY_ID", ""),
                "secret_key": getattr(settings, "AWS_SECRET_ACCESS_KEY", ""),
                "bucket_name": settings.AWS_STORAGE_BUCKET_NAME,
                "endpoint_url": getattr(settings, "AWS_S3_ENDPOINT_URL", None),
                "region_name": getattr(settings, "AWS_S3_REGION_NAME", None),
                "custom_domain": getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None),
                "addressing_style": getattr(settings, "AWS_S3_ADDRESSING_STYLE", "auto"),
                "default_acl": None,
                "querystring_auth": True,
            }
        try:
            from workspaces.models import ApplicationStorageSettings

            storage_settings = ApplicationStorageSettings.objects.filter(backend=ApplicationStorageSettings.Backend.S3).exclude(bucket_name="").order_by("updated_at").last()
        except (OperationalError, ProgrammingError):
            storage_settings = None
        if not storage_settings:
            return None
        return {
            "access_key": storage_settings.access_key_id,
            "secret_key": storage_settings.secret_access_key,
            "bucket_name": storage_settings.bucket_name,
            "endpoint_url": storage_settings.endpoint_url or None,
            "region_name": storage_settings.region_name or None,
            "custom_domain": storage_settings.custom_domain or None,
            "addressing_style": storage_settings.addressing_style or "auto",
            "default_acl": None,
            "querystring_auth": True,
        }
