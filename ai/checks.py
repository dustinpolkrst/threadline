from django.conf import settings
from django.core.checks import Error, register


@register()
def ai_secret_key_check(app_configs, **kwargs):
    if settings.DEBUG or getattr(settings, "THREADLINE_FIELD_ENCRYPTION_KEY", ""):
        return []
    return [
        Error(
            "THREADLINE_FIELD_ENCRYPTION_KEY must be set when DEBUG is false.",
            hint="Set a stable high-entropy THREADLINE_FIELD_ENCRYPTION_KEY before configuring AI provider credentials.",
            id="ai.E001",
        )
    ]
