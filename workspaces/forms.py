from django import forms
from .models import Workspace


class WorkspaceSLAForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ["first_response_target_minutes", "next_response_target_minutes", "resolution_target_minutes"]
