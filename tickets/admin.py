from django.contrib import admin
from .models import Ticket, TicketAttachment, TicketComment

admin.site.register(Ticket)
admin.site.register(TicketComment)
admin.site.register(TicketAttachment)

# Register your models here.
