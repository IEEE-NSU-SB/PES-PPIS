from functools import wraps
from django.shortcuts import render
from .utils import Site_Permissions

def permission_required(codename, obj=None):
    """
    Decorator to check if a user has a given permission.
    Optionally, pass an object for object-level permission checks.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # obj can be a string key from kwargs or a direct object
            # obj_instance = kwargs.get(obj) if isinstance(obj, str) else obj
            # if not Permission.user_has_permission(request.user, codename, obj=obj_instance):
            if not Site_Permissions.user_has_permission(request.user, codename):
                return render(request, "AccessDenied.html")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator