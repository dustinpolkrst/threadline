from django.contrib import admin
from .models import SavedTicketFilter, Ticket, TicketAttachment, TicketComment, TicketRelation

admin.site.register(Ticket)
admin.site.register(TicketComment)
admin.site.register(TicketAttachment)
admin.site.register(TicketRelation)
admin.site.register(SavedTicketFilter)

# Register your models here.
