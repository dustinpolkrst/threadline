from django import forms
from .models import Contact, Organization


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = [
            "name",
            "domain",
            "website",
            "phone",
            "billing_email",
            "account_owner",
            "status",
            "tier",
            "industry",
            "employee_count",
            "annual_revenue",
            "address",
            "renewal_date",
            "health_score",
            "notes",
        ]
        widgets = {"renewal_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            base_class = "w-full border border-slate-300 px-3 py-2 text-sm"
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("rows", 4)
                base_class = "w-full border border-slate-300 px-3 py-2 text-sm"
            field.widget.attrs["class"] = base_class


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["organization", "name", "email", "phone", "title", "notes"]
