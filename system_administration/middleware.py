from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from system_administration.utils import log_exception

# 404 / 403 / bad-request responses are normal outcomes, not bugs, so they stay out of the error log
EXPECTED_EXCEPTIONS = (Http404, PermissionDenied, SuspiciousOperation)


class GlobalExceptionLoggingMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        if not isinstance(exception, EXPECTED_EXCEPTIONS):
            log_exception(exception, request)
        # Let Django continue handling (show debug page or 500 page)
        return None
