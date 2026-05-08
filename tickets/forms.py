from django import forms
from .models import Ticket, TicketComment


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["organization", "contact", "title", "description", "status", "priority", "assignee", "tags", "due_date"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}


class PortalTicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["title", "description", "priority"]


class CommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ["body", "visibility"]


class PortalCommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ["body"]
