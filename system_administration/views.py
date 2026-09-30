import mimetypes
import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.utils._os import safe_join
from django.core.exceptions import SuspiciousFileOperation

from access_ctrl.utils import Site_Permissions

# Top-level folder inside PROTECTED_ROOT -> permission required to read it.
# Anything not listed here is only readable by superusers.
PROTECTED_FOLDER_PERMISSIONS = {
    'Abstracts': 'view_reg_response',
    'Participant_QR': 'view_qr_dashboard',
}


def protected_serve(request, path):
    if not request.user.is_authenticated:
        return HttpResponseForbidden('Access Denied')

    # Resolve the path safely; rejects '..' and absolute paths escaping PROTECTED_ROOT
    try:
        file_path = safe_join(settings.PROTECTED_ROOT, path)
    except (SuspiciousFileOperation, ValueError):
        raise Http404("File not found")

    root = os.path.realpath(settings.PROTECTED_ROOT)
    real_path = os.path.realpath(file_path)
    if os.path.commonpath([root, real_path]) != root or not os.path.isfile(real_path):
        raise Http404("File not found")

    top_folder = os.path.relpath(real_path, root).split(os.sep)[0]
    required = PROTECTED_FOLDER_PERMISSIONS.get(top_folder)
    if required:
        allowed = Site_Permissions.user_has_permission(request.user, required)
    else:
        allowed = request.user.is_superuser
    if not allowed:
        return HttpResponseForbidden('Access Denied')

    content_type, _ = mimetypes.guess_type(real_path)
    response = FileResponse(open(real_path, 'rb'), content_type=content_type)
    response['X-Content-Type-Options'] = 'nosniff'
    return response
