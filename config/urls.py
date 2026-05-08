"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from core import views as core_views
from activity import views as activity_views
from crm import views as crm_views
from customer_portal import views as portal_views
from communications import views as comm_views
from search import views as search_views
from tickets import views as ticket_views
from time_tracking import views as time_views
from workspaces import views as workspace_views

urlpatterns = [
    path("", core_views.dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("tickets/", ticket_views.ticket_list, name="ticket_list"),
    path("tickets/new/", ticket_views.ticket_create, name="ticket_create"),
    path("tickets/<uuid:pk>/", ticket_views.ticket_detail, name="ticket_detail"),
    path("tickets/<uuid:pk>/comments/", ticket_views.ticket_add_comment, name="ticket_add_comment"),
    path("tickets/<uuid:pk>/resolve/", ticket_views.ticket_resolve, name="ticket_resolve"),
    path("tickets/<uuid:pk>/time/", ticket_views.ticket_add_time, name="ticket_add_time"),
    path("tickets/<uuid:pk>/timer/start/", ticket_views.ticket_start_timer, name="ticket_start_timer"),
    path("tickets/<uuid:pk>/timer/stop/", ticket_views.ticket_stop_timer, name="ticket_stop_timer"),
    path("tickets/<uuid:pk>/attachments/", ticket_views.ticket_upload_attachment, name="ticket_upload_attachment"),
    path("tickets/<uuid:pk>/attachments/<uuid:attachment_id>/", ticket_views.ticket_download_attachment, name="ticket_download_attachment"),
    path("tickets/<uuid:pk>/attachments/<uuid:attachment_id>/delete/", ticket_views.ticket_delete_attachment, name="ticket_delete_attachment"),
    path("tickets/<uuid:pk>/relations/", ticket_views.ticket_add_relation, name="ticket_add_relation"),
    path("tickets/<uuid:pk>/merge/", ticket_views.ticket_merge, name="ticket_merge"),
    path("tickets/filters/save/", ticket_views.ticket_save_filter, name="ticket_save_filter"),
    path("tickets/bulk/", ticket_views.ticket_bulk_action, name="ticket_bulk_action"),
    path("organizations/", crm_views.organization_list, name="organization_list"),
    path("organizations/new/", crm_views.organization_create, name="organization_create"),
    path("organizations/<uuid:pk>/edit/", crm_views.organization_edit, name="organization_edit"),
    path("organizations/<uuid:pk>/", crm_views.organization_detail, name="organization_detail"),
    path("contacts/", crm_views.contact_list, name="contact_list"),
    path("contacts/new/", crm_views.contact_create, name="contact_create"),
    path("contacts/<uuid:pk>/", crm_views.contact_detail, name="contact_detail"),
    path("timesheet/", time_views.timesheet, name="timesheet"),
    path("time/<uuid:pk>/edit/", time_views.time_entry_edit, name="time_entry_edit"),
    path("reports/time/", time_views.time_report, name="time_report"),
    path("settings/team/", crm_views.team_settings, name="team_settings"),
    path("settings/import/", crm_views.crm_import_upload, name="crm_import_upload"),
    path("settings/import/template/<str:import_type>/", crm_views.crm_import_template, name="crm_import_template"),
    path("settings/import/<uuid:pk>/", crm_views.crm_import_preview, name="crm_import_preview"),
    path("settings/email/", comm_views.email_plumbing_settings, name="email_plumbing_settings"),
    path("activity/", activity_views.activity_log, name="activity_log"),
    path("search/", search_views.search_page, name="search"),
    path("portal/tickets/", portal_views.portal_ticket_list, name="portal_ticket_list"),
    path("portal/tickets/new/", portal_views.portal_ticket_create, name="portal_ticket_create"),
    path("portal/tickets/<uuid:pk>/", portal_views.portal_ticket_detail, name="portal_ticket_detail"),
    path("portal/tickets/<uuid:pk>/reply/", portal_views.portal_ticket_reply, name="portal_ticket_reply"),
    path("portal/tickets/<uuid:pk>/attachments/", portal_views.portal_upload_attachment, name="portal_upload_attachment"),
    path("portal/tickets/<uuid:pk>/attachments/<uuid:attachment_id>/", portal_views.portal_download_attachment, name="portal_download_attachment"),
    path("portal/account/", portal_views.portal_account, name="portal_account"),
    path("invites/<str:token>/", workspace_views.accept_invitation, name="accept_invitation"),
]
