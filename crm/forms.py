from django import forms
from .models import Contact, Organization


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name", "domain", "notes"]


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["organization", "name", "email", "phone", "title", "notes"]
