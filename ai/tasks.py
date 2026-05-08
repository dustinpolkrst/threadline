from celery import shared_task

from .models import TicketAIAnalysis
from .services import run_ticket_analysis


@shared_task
def analyze_ticket_with_ai(analysis_id):
    analysis = TicketAIAnalysis.objects.select_related("workspace", "ticket").get(pk=analysis_id)
    run_ticket_analysis(analysis)
    return str(analysis.pk)
