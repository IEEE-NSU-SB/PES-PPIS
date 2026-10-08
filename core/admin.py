from django.contrib import admin

from core.admin_mixins import PermanentDeleteAdminMixin
from core.models import Registered_Participant, Token_Participant, Token_Session


@admin.register(Token_Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['session_name', 'is_active', 'order_of_session']
    list_editable = ['is_active', 'order_of_session']
    ordering = ['order_of_session']


@admin.register(Registered_Participant)
class Registered_ParticipantAdmin(PermanentDeleteAdminMixin, admin.ModelAdmin):
    """The people on the QR dashboard (imported from the registration responses)."""

    delete_by = 'registered_id'

    list_display = ['id', 'name', 'email', 'contact_no', 'university', 'unique_code']
    list_display_links = ['id', 'name']
    list_filter = ['university']
    search_fields = ['name', 'email', 'contact_no', 'university', 'unique_code']
    ordering = ['id']
    list_per_page = 50

    def get_readonly_fields(self, request, obj=None):
        # Changing the code of an existing participant would invalidate the QR code they already received
        return ['unique_code'] if obj else []


@admin.register(Token_Participant)
class Token_ParticipantAdmin(admin.ModelAdmin):
    list_display = ['registered_participant', 'token_session', 'date_time']
    list_filter = ['token_session']
    search_fields = ['registered_participant__name', 'registered_participant__email']
    ordering = ['-date_time']
    autocomplete_fields = ['registered_participant']
