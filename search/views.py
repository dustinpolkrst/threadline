from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .services import search_documents_for_user


@login_required
def search_page(request):
    q = request.GET.get("q", "").strip()
    entity = request.GET.get("type", "all")
    results, is_customer = search_documents_for_user(request.user, q, entity)
    return render(request, "search/search.html", {"q": q, "entity": entity, "results": results, "is_customer": is_customer})
