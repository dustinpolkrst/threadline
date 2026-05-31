from django.contrib import admin
from .forms import MailboxChannelAdminForm
from .models import EmailAttachment, EmailDeliveryAttempt, EmailIngestLog, EmailMessage, MailboxChannel


@admin.register(MailboxChannel)
class MailboxChannelAdmin(admin.ModelAdmin):
    form = MailboxChannelAdminForm
    list_display = ["name", "address", "status", "inbound_enabled", "outbound_enabled", "provider"]
    list_filter = ["status", "inbound_enabled", "outbound_enabled", "provider"]


admin.site.register(EmailMessage)
admin.site.register(EmailDeliveryAttempt)
admin.site.register(EmailIngestLog)
admin.site.register(EmailAttachment)
