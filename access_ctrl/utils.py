
from access_ctrl.models import Permission as Perms

class Site_Permissions:

    def user_has_permission(user, codename, obj=None):
        """
        Check if a user has a permission, directly, via role, or object-level.
        """
        if user.is_superuser:
            return True
        
        try:
            perm = Perms.objects.get(codename=codename)
        except Perms.DoesNotExist:
            return False

        # Direct user permissions
        if hasattr(user, "custom_user_permissions") and perm in user.custom_user_permissions.permissions.all():
            return True

        # Role-based permissions
        if hasattr(user, "user_roles"):
            for role in user.user_roles.roles.all():
                if hasattr(role, "role_permissions") and perm in role.role_permissions.permissions.all():
                    return True

        return False
    
    def is_superuser(user):

        return user.is_superuser

    def landing_url_name(user):
        """The first page a signed-in user is allowed to open, or None if they have no permissions yet."""

        if Site_Permissions.user_has_permission(user, 'view_qr_dashboard'):
            return 'core:dashboard'
        if Site_Permissions.user_has_permission(user, 'reg_form_control'):
            return 'registration:registration_admin'
        if Site_Permissions.user_has_permission(user, 'view_reg_responses_list'):
            return 'registration:response_table'
        return None