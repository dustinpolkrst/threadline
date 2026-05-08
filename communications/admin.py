from django.contrib import admin
from .models import EmailDeliveryAttempt, EmailIngestLog, EmailMessage, MailboxChannel


admin.site.register(MailboxChannel)
admin.site.register(EmailMessage)
admin.site.register(EmailDeliveryAttempt)
admin.site.register(EmailIngestLog)

# Register your models here.
