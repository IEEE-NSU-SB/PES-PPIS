import traceback
from system_administration.models import ErrorLog

def log_exception(exception, request=None):
    try:
        tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))

        ErrorLog.objects.create(
            path=request.path if request else None,
            method=request.method if request else None,
            user=str(request.user) if request and hasattr(request, "user") and request.user.is_authenticated else None,
            exception_type=type(exception).__name__,
            message=str(exception),
            traceback=tb
        )
    except Exception:
        pass