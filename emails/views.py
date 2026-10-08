import base64
import json
import os
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from time import sleep

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from dotenv import dotenv_values, set_key
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from access_ctrl.utils import Site_Permissions
from core.models import Registered_Participant
from system_administration.utils import log_exception

SENDER = "IEEE NSU SB Portal <ieeensusb.portal@gmail.com>"

QR_EMAIL_BODY = (
    "Dear Participant,\n\n"
    "Your QR code for the PPIS — Power Policy & Innovation Summit event is attached in this email.\n"
    "This QR code is essential to collect your food and goodies.\n\n"
    "Best regards,\n\n"
    "IEEE NSU SB."
)


def _is_local_host(request):
    return request.get_host() in ("127.0.0.1:8000", "localhost:8000")


def _attach_file(message, file_path, filename):
    """Attach a file from disk to a MIME message."""
    with open(file_path, "rb") as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment', filename=filename)
    message.attach(part)


def _send_message(service, message):
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": encoded_message}).execute()


def _build_service():
    """Returns a Gmail service, or None if Google API access needs to be re-authorised."""
    credentials = get_credentials()
    if not credentials:
        return None
    return build(settings.GOOGLE_MAIL_API_NAME, settings.GOOGLE_MAIL_API_VERSION, credentials=credentials)


@login_required
def send_emails(request):
    """Bulk-sends the QR code to every registered participant. Superuser only.
    Not routed by default because it is slow (rate-limited sends)."""
    if not Site_Permissions.is_superuser(request.user):
        return render(request, '404.html', status=404)

    service = _build_service()
    if service is None:
        return JsonResponse({'message': 'Please re-authorise google api'})

    for participant in Registered_Participant.objects.all():
        try:
            message = MIMEMultipart()
            message["From"] = SENDER
            message["To"] = participant.email
            message["Cc"] = 'nujhat.saleh@northsouth.edu'
            message["Subject"] = 'Registration Confirmation & Event Guidelines for PPIS — Power Policy & Innovation Summit'
            message.attach(MIMEText(render_to_string('email_template.html', {'name': participant.name}), 'html'))

            _attach_file(message, os.path.join(settings.PROTECTED_ROOT, 'Participant_QR', f'{participant.id}.png'), f'{participant.id}.png')
            _attach_file(message, os.path.join(settings.PROTECTED_ROOT, 'PPIS Timeline.pdf'), 'PPIS Timeline.pdf')
            _attach_file(message, os.path.join(settings.PROTECTED_ROOT, 'PPISBanner.webp'), 'PPISBanner.webp')

            _send_message(service, message)
            sleep(3)
        except Exception as e:
            log_exception(e, request)
            return JsonResponse({'message': 'error'})

    return JsonResponse({'message': 'success'})


@login_required
@require_POST
def send_email(request):
    """Re-sends a participant's QR code to a given email address."""
    if not Site_Permissions.user_has_permission(request.user, 'view_qr_dashboard'):
        return render(request, '404.html', status=404)

    try:
        data = json.loads(request.body)
        email_addr = str(data['emailAddr']).strip()
        validate_email(email_addr)
        participant_id = int(data['participant_id'])
    except (ValueError, KeyError, TypeError, ValidationError):
        return JsonResponse({'message': 'Invalid email address or participant'})

    qr_path = os.path.join(settings.PROTECTED_ROOT, 'Participant_QR', f'{participant_id}.png')
    if not os.path.isfile(qr_path):
        return JsonResponse({'message': 'QR code not found for this participant'})

    try:
        service = _build_service()
        if service is None:
            return JsonResponse({'message': 'Please re-authorise google api'})

        message = MIMEMultipart()
        message["From"] = SENDER
        message["To"] = email_addr
        message["Subject"] = "QR Code for PPIS — Power Policy & Innovation Summit"
        message.attach(MIMEText(QR_EMAIL_BODY, 'plain'))
        _attach_file(message, qr_path, f'{participant_id}.png')
        _send_message(service, message)
    except Exception as e:
        log_exception(e, request)
        return JsonResponse({'message': 'error'})

    return JsonResponse({'message': 'success'})


# One confirmation email per registration, chosen by registration type: type -> (subject, template)
REGISTRATION_EMAILS = {
    'participant': ('PPIS Registration Confirmation', 'registration_email_participant.html'),
    'competition': ('PPIS Policy Innovation Challenge Registration Confirmation', 'registration_email_contestant.html'),
}


def send_registration_email(request, email, registration_type):
    """Sends the confirmation email for a registration type ('participant' or 'competition').
    Returns True on success, False otherwise."""
    try:
        subject, template = REGISTRATION_EMAILS[registration_type]
        validate_email(str(email))
        service = _build_service()
        if service is None:
            return False

        message = MIMEMultipart()
        message["From"] = SENDER
        message["To"] = str(email)
        message["Subject"] = subject
        message.attach(MIMEText(render_to_string(template), 'html'))
        _send_message(service, message)
    except Exception as e:
        log_exception(e, request)
        return False

    return True


@login_required
def authorize(request):
    if not Site_Permissions.is_superuser(request.user):
        return render(request, '404.html', status=404)

    credentials = get_credentials()
    if not credentials:
        flow = get_google_auth_flow(request)
        if _is_local_host(request):
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
            )
        else:
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                login_hint='ieeensusb.portal@gmail.com'
            )
        request.session['state'] = state
        return redirect(authorization_url)

    return redirect('core:dashboard')


@login_required
def oauth2callback(request):
    if not Site_Permissions.is_superuser(request.user):
        return render(request, '404.html', status=404)

    try:
        if _is_local_host(request):
            os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        state = request.GET.get('state')
        if not state or state != request.session.pop('state', None):
            return HttpResponseBadRequest('Invalid state parameter')

        flow = get_google_auth_flow(request)
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        save_credentials(flow.credentials)
        return redirect('core:dashboard')
    except Exception as e:
        log_exception(e, request)
        return redirect('core:dashboard')


def get_google_auth_flow(request):
    client_config = {
        'web': {
            'client_id': settings.GOOGLE_CLOUD_CLIENT_ID,
            'project_id': settings.GOOGLE_CLOUD_PROJECT_ID,
            'auth_uri': settings.GOOGLE_CLOUD_AUTH_URI,
            'token_uri': settings.GOOGLE_CLOUD_TOKEN_URI,
            'auth_provider_x509_cert_url': settings.GOOGLE_CLOUD_AUTH_PROVIDER_X509_CERT_URL,
            'client_secret': settings.GOOGLE_CLOUD_CLIENT_SECRET,
        }
    }
    scheme = "http" if _is_local_host(request) else "https"
    redirect_uri = f"{scheme}://{request.get_host()}/init/oauth2callback"

    return Flow.from_client_config(
        client_config,
        settings.SCOPES,
        redirect_uri=redirect_uri
    )


def save_credentials(credentials):
    env_path = str(settings.ENV_FILE)
    set_key(env_path, 'GOOGLE_CLOUD_TOKEN', credentials.token)
    settings.GOOGLE_CLOUD_TOKEN = credentials.token
    if credentials.refresh_token:
        set_key(env_path, 'GOOGLE_CLOUD_REFRESH_TOKEN', credentials.refresh_token)
        settings.GOOGLE_CLOUD_REFRESH_TOKEN = credentials.refresh_token
    if credentials.expiry:
        set_key(env_path, 'GOOGLE_CLOUD_EXPIRY', credentials.expiry.isoformat())
        settings.GOOGLE_CLOUD_EXPIRY = credentials.expiry.isoformat()


def _stored_google_tokens():
    """The Google tokens live in .env and are rewritten by the app, so .env is the source of truth.
    Reading it here (instead of the process environment, which `load_dotenv` never refreshes) keeps every
    worker and every auto-reload on the latest token."""
    stored = dotenv_values(settings.ENV_FILE)
    return {
        'token': stored.get('GOOGLE_CLOUD_TOKEN') or settings.GOOGLE_CLOUD_TOKEN,
        'refresh_token': stored.get('GOOGLE_CLOUD_REFRESH_TOKEN') or settings.GOOGLE_CLOUD_REFRESH_TOKEN,
        'expiry': stored.get('GOOGLE_CLOUD_EXPIRY') or settings.GOOGLE_CLOUD_EXPIRY,
    }


def get_credentials():
    """Returns valid Google credentials (refreshing if needed), or None if re-authorisation is required."""
    tokens = _stored_google_tokens()
    if not tokens['token']:
        return None

    info = {
        'token': tokens['token'],
        'refresh_token': tokens['refresh_token'],
        'token_uri': settings.GOOGLE_CLOUD_TOKEN_URI,
        'client_id': settings.GOOGLE_CLOUD_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLOUD_CLIENT_SECRET,
    }
    if tokens['expiry']:
        info['expiry'] = tokens['expiry']

    try:
        creds = Credentials.from_authorized_user_info(info, scopes=settings.SCOPES)
    except (ValueError, TypeError):
        return None

    if creds.valid:
        return creds

    if creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(creds)
            return creds
        except Exception as e:
            # Usually 'invalid_grant': the refresh token expired or was revoked and needs re-authorising
            log_exception(e)
            return None

    return None
