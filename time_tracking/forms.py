from django import forms
from django.utils import timezone
from .models import TimeEntry


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = ["started_at", "duration_minutes", "billable", "customer_visible", "notes"]
        widgets = {"started_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["started_at"].initial = timezone.now().strftime("%Y-%m-%dT%H:%M")


class TimerStartForm(forms.Form):
    billable = forms.BooleanField(required=False, initial=True)
    customer_visible = forms.BooleanField(required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class TimerStopForm(forms.Form):
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
