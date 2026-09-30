from django.utils.deprecation import MiddlewareMixin

from system_administration.utils import log_exception


class GlobalExceptionLoggingMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        log_exception(exception, request)
        # Let Django continue handling (show debug page or 500 page)
        return None
