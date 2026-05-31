from django import forms

from .models import MailboxChannel


class MailboxChannelAdminForm(forms.ModelForm):
    imap_password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), help_text="Leave blank to keep the current IMAP password.")
    smtp_password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), help_text="Leave blank to keep the current SMTP password.")

    class Meta:
        model = MailboxChannel
        exclude = ["encrypted_imap_password", "encrypted_smtp_password"]

    def save(self, commit=True):
        instance = super().save(commit=False)
        imap_password = self.cleaned_data.get("imap_password", "").strip()
        smtp_password = self.cleaned_data.get("smtp_password", "").strip()
        if imap_password:
            instance.set_imap_password(imap_password)
        elif instance.pk:
            instance.encrypted_imap_password = MailboxChannel.objects.get(pk=instance.pk).encrypted_imap_password
        if smtp_password:
            instance.set_smtp_password(smtp_password)
        elif instance.pk:
            instance.encrypted_smtp_password = MailboxChannel.objects.get(pk=instance.pk).encrypted_smtp_password
        if commit:
            instance.save()
        return instance
