import csv
import io

from django.utils import timezone

from search.services import index_contact, index_organization

from .models import CRMImportJob, CRMImportRow, Contact, Organization


def create_import_job(*, workspace, import_type, uploaded_file, user):
    job = CRMImportJob.objects.create(workspace=workspace, import_type=import_type, filename=uploaded_file.name, created_by=user)
    text = uploaded_file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    for index, row in enumerate(reader, start=2):
        errors = validate_import_row(workspace, job.import_type, row)
        duplicate, warnings = detect_duplicate(workspace, job.import_type, row)
        resolution = CRMImportRow.Resolution.UPDATE if duplicate else CRMImportRow.Resolution.CREATE
        CRMImportRow.objects.create(job=job, row_number=index, data=dict(row), errors=errors, warnings=warnings, duplicate_object_id=duplicate.pk if duplicate else None, resolution=resolution)
    return job


def save_import_resolutions(job, post_data):
    for row in job.rows.filter(errors=[]):
        value = post_data.get(f"resolution_{row.pk}")
        if value in CRMImportRow.Resolution.values:
            row.resolution = value
            row.save(update_fields=["resolution"])


def confirm_import_job(workspace, job):
    if job.rows.exclude(errors=[]).exists():
        return False
    for row in job.rows.all():
        created = import_row(workspace, job.import_type, row)
        if created:
            row.created_object_id = created.pk
            row.save(update_fields=["created_object_id"])
            if job.import_type == CRMImportJob.ImportType.ORGANIZATIONS:
                index_organization(created)
            else:
                index_contact(created)
    job.status = CRMImportJob.Status.IMPORTED
    job.imported_at = timezone.now()
    job.save(update_fields=["status", "imported_at"])
    return True


def validate_import_row(workspace, import_type, row):
    errors = []
    if import_type == CRMImportJob.ImportType.ORGANIZATIONS and not row.get("name"):
        errors.append("name is required")
    if import_type == CRMImportJob.ImportType.CONTACTS:
        if not row.get("email"):
            errors.append("email is required")
        if not row.get("organization"):
            errors.append("organization is required")
        elif not Organization.objects.filter(workspace=workspace, name=row.get("organization")).exists():
            errors.append("organization must already exist")
    return errors


def detect_duplicate(workspace, import_type, row):
    if import_type == CRMImportJob.ImportType.ORGANIZATIONS:
        duplicate = None
        name = row.get("name", "").strip()
        domain = row.get("domain", "").strip()
        if name:
            duplicate = Organization.objects.filter(workspace=workspace, name=name).first()
        if not duplicate and domain:
            duplicate = Organization.objects.filter(workspace=workspace, domain=domain).first()
        return duplicate, [f"Matches existing organization: {duplicate.name}"] if duplicate else []
    email = row.get("email", "").strip()
    duplicate = Contact.objects.filter(workspace=workspace, email=email).first() if email else None
    return duplicate, [f"Matches existing contact: {duplicate.email}"] if duplicate else []


def import_row(workspace, import_type, import_row):
    if import_row.resolution == CRMImportRow.Resolution.SKIP:
        return None
    row = import_row.data
    if import_type == CRMImportJob.ImportType.ORGANIZATIONS:
        organization = None
        if import_row.resolution == CRMImportRow.Resolution.UPDATE and import_row.duplicate_object_id:
            organization = Organization.objects.filter(workspace=workspace, pk=import_row.duplicate_object_id).first()
        if not organization:
            organization = Organization(workspace=workspace, name=row["name"])
        apply_organization_row(organization, row)
        organization.save()
        return organization
    organization = Organization.objects.get(workspace=workspace, name=row["organization"])
    contact = None
    if import_row.resolution == CRMImportRow.Resolution.UPDATE and import_row.duplicate_object_id:
        contact = Contact.objects.filter(workspace=workspace, pk=import_row.duplicate_object_id).first()
    if not contact:
        contact = Contact(workspace=workspace, email=row["email"])
    contact.organization = organization
    contact.name = row.get("name") or row["email"]
    contact.phone = row.get("phone", "")
    contact.title = row.get("title", "")
    contact.notes = row.get("notes", "")
    contact.save()
    return contact


def apply_organization_row(organization, row):
    for field in ["name", "domain", "website", "phone", "billing_email", "account_owner", "status", "tier", "industry", "address", "renewal_date", "notes"]:
        if row.get(field) is not None:
            setattr(organization, field, row.get(field) or "")
    for field in ["employee_count", "annual_revenue", "health_score"]:
        value = row.get(field)
        if value not in [None, ""]:
            setattr(organization, field, value)
