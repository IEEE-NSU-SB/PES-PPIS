from django.contrib import admin

from system_administration.models import ErrorLog


@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    """Read-only error log written by the site itself (failed emails, Google token problems, crashes)."""

    list_display = ['timestamp', 'exception_type', 'short_message', 'path', 'method', 'user']
    list_filter = ['exception_type', 'method', 'timestamp']
    search_fields = ['message', 'path', 'user', 'traceback']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']
    readonly_fields = ['timestamp', 'path', 'method', 'user', 'exception_type', 'message', 'traceback']

    @admin.display(description='Message')
    def short_message(self, obj):
        return obj.message[:100]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
