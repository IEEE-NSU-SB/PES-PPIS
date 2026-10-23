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


def client_ip(request):
    """The visitor's IP address, used for rate limiting. Behind a trusted proxy the real address is the first
    entry of X-Forwarded-For; otherwise every visitor would look like the proxy and share one limit."""
    import ipaddress
    from django.conf import settings

    if getattr(settings, 'TRUST_FORWARDED_FOR', False):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return request.META.get('REMOTE_ADDR', '')
