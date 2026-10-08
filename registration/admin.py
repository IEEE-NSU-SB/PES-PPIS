from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from core.admin_mixins import PermanentDeleteAdminMixin

from .models import EventFormStatus, Form_Participant


@admin.register(EventFormStatus)
class EventFormStatusAdmin(admin.ModelAdmin):
    """The newest row decides whether the registration form is open, so keep a single row."""

    list_display = ['status', 'updated_at']
    list_display_links = ['status']
    fields = ['is_published', 'updated_at']
    readonly_fields = ['updated_at']

    @admin.display(description='Registration form')
    def status(self, obj):
        return 'Published (open)' if obj.is_published else 'Unpublished (closed)'

    def has_add_permission(self, request):
        return not EventFormStatus.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Form_Participant)
class Form_ParticipantAdmin(PermanentDeleteAdminMixin, admin.ModelAdmin):
    delete_by = 'form_id'

    list_display = ['id', 'name', 'registration_type', 'team_name', 'team_of', 'ieee_id_column', 'university',
                    'email', 'phone', 'transaction_id', 'created_at']
    list_display_links = ['id', 'name']
    list_filter = ['registration_type', 'membership_type', 'track', 'total_members', 'department',
                   'study_level', 'created_at']
    search_fields = ['name', 'email', 'phone', 'university', 'student_id', 'ambassador_code', 'transaction_id', 'team_name',
                     'ieee_id', 'project_title', 'mem2_name', 'mem2_email', 'mem3_name', 'mem3_email']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    list_per_page = 50
    readonly_fields = ['created_at', 'abstract_download']

    fieldsets = [
        ('Registration', {'fields': ['registration_type', 'created_at']}),
        ('Personal information', {'fields': ['name', 'email', 'phone', 'university', 'department', 'student_id',
                                             'study_level', 'ambassador_code']}),
        ('General participant', {'fields': ['membership_type', 'transaction_id']}),
        ('Contestant team', {'fields': ['team_name', 'total_members', 'ieee_id']}),
        ('Team member 2', {'classes': ['collapse'],
                           'fields': ['mem2_name', 'mem2_email', 'mem2_phone', 'mem2_university',
                                      'mem2_department', 'mem2_student_id']}),
        ('Team member 3', {'classes': ['collapse'],
                           'fields': ['mem3_name', 'mem3_email', 'mem3_phone', 'mem3_university',
                                      'mem3_department', 'mem3_student_id']}),
        ('Project and abstract', {'fields': ['track', 'project_title', 'abstract_file', 'abstract_download']}),
        ('Older fields (no longer asked on the form)', {'classes': ['collapse'],
                                                        'fields': ['problem_statement', 'proposed_solution',
                                                                   'sdg_alignment']}),
    ]

    @admin.display(description='IEEE ID', ordering='ieee_id')
    def ieee_id_column(self, obj):
        return obj.ieee_id or '—'

    @admin.display(description='Team of', ordering='total_members')
    def team_of(self, obj):
        return obj.total_members or '—'

    @admin.display(description='Abstract')
    def abstract_download(self, obj):
        if not obj.abstract_file:
            return '—'
        return format_html('<a href="{}" target="_blank">{}</a>',
                           reverse('protected_serve', args=[f'Abstracts/{obj.abstract_file}']), obj.abstract_file)
