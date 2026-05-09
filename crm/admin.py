from django.contrib import admin
from .models import CRMImportJob, CRMImportRow, Contact, Organization

admin.site.register(Organization)
admin.site.register(Contact)
admin.site.register(CRMImportJob)
admin.site.register(CRMImportRow)
