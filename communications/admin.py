from django.contrib import admin
from .models import EmailAttachment, EmailDeliveryAttempt, EmailIngestLog, EmailMessage, MailboxChannel


admin.site.register(MailboxChannel)
admin.site.register(EmailMessage)
admin.site.register(EmailDeliveryAttempt)
admin.site.register(EmailIngestLog)
admin.site.register(EmailAttachment)

# Register your models here.
