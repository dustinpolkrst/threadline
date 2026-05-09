from django.db.models.signals import post_delete
from django.dispatch import receiver

from crm.models import Contact, Organization
from tickets.models import Ticket, TicketComment

from .models import SearchDocument


ENTITY_BY_MODEL = {
    Ticket: SearchDocument.EntityType.TICKET,
    TicketComment: SearchDocument.EntityType.COMMENT,
    Organization: SearchDocument.EntityType.ORGANIZATION,
    Contact: SearchDocument.EntityType.CONTACT,
}


@receiver(post_delete, sender=Ticket)
@receiver(post_delete, sender=TicketComment)
@receiver(post_delete, sender=Organization)
@receiver(post_delete, sender=Contact)
def delete_search_document(sender, instance, **kwargs):
    SearchDocument.objects.filter(
        workspace=instance.workspace,
        entity_type=ENTITY_BY_MODEL[sender],
        object_id=instance.pk,
    ).delete()
