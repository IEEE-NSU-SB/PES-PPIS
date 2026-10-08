from core.renderData import Core


class PermanentDeleteAdminMixin:
    """Makes deleting a participant in the admin behave like the delete buttons on the site:
    the person is removed from BOTH the dashboard and the registration responses (matched by email),
    together with their scan records, QR image and uploaded abstract.

    Set `delete_by` to 'form_id' (registration responses) or 'registered_id' (dashboard participants)."""

    delete_by = None

    def delete_model(self, request, obj):
        Core.delete_participant(**{self.delete_by: obj.pk})
        self.message_user(request, 'Deleted permanently, including the matching dashboard/registration entry '
                                   '(same email), QR code and abstract file.')

    def delete_queryset(self, request, queryset):
        for pk in list(queryset.values_list('pk', flat=True)):
            Core.delete_participant(**{self.delete_by: pk})
        self.message_user(request, 'Deleted permanently, including matching dashboard/registration entries '
                                   '(same email), QR codes and abstract files.')
