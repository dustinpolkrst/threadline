from celery import shared_task

from .models import TicketAIAnalysis
from .services import run_ticket_analysis


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def analyze_ticket_with_ai(self, analysis_id):
    analysis = TicketAIAnalysis.objects.select_related("workspace", "ticket").get(pk=analysis_id)
    run_ticket_analysis(analysis)
    return str(analysis.pk)
