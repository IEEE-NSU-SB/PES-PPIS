from django.apps import AppConfig
from django.contrib.auth.apps import AuthConfig as BaseAuthConfig


class AccessCtrlConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'access_ctrl'
    verbose_name = 'Access Control'
    default = True

class CustomAuthConfig(BaseAuthConfig):
    verbose_name = "User Management"

    def ready(self):
        super().ready()  # registers User & Group
        from django.contrib import admin
        from django.contrib.auth.models import Group

        # Unregister Group after it's registered
        try:
            admin.site.unregister(Group)
        except admin.sites.NotRegistered:
            pass

