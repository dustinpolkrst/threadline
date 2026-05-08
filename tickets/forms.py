from django import forms
from .models import SavedTicketFilter, Ticket, TicketAttachment, TicketComment, TicketRelation


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
        fields = ["body"]


class PortalCommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ["body"]


class TicketAttachmentForm(forms.ModelForm):
    class Meta:
        model = TicketAttachment
        fields = ["file"]


class TicketRelationForm(forms.ModelForm):
    class Meta:
        model = TicketRelation
        fields = ["target", "relation_type", "note"]


class SavedTicketFilterForm(forms.ModelForm):
    class Meta:
        model = SavedTicketFilter
        fields = ["name", "is_default"]


class BulkTicketActionForm(forms.Form):
    ACTION_CHOICES = [
        ("assign", "Assign"),
        ("status", "Change status"),
        ("priority", "Change priority"),
        ("tag", "Add tag"),
    ]
    ticket_ids = forms.CharField(widget=forms.HiddenInput)
    action = forms.ChoiceField(choices=ACTION_CHOICES)
    assignee = forms.ModelChoiceField(queryset=None, required=False)
    status = forms.ChoiceField(choices=Ticket.Status.choices, required=False)
    priority = forms.ChoiceField(choices=Ticket.Priority.choices, required=False)
    tag = forms.CharField(max_length=80, required=False)
