from celery import shared_task


@shared_task
def example_health_task():
    return "threadline celery ok"
