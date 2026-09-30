import os
import re
import pandas as pd
from io import BytesIO
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Count, Min
from django.db.models.functions import Lower, Trim

from access_ctrl.decorators import permission_required
from access_ctrl.utils import Site_Permissions
from system_administration.utils import log_exception
from core.renderData import Core
from emails.views import send_registration_email

from .models import EventFormStatus, Form_Participant


def _get_publish_status() -> bool:
    status = EventFormStatus.objects.order_by('-updated_at', '-id').first()
    return bool(status and status.is_published)


def registration_form(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('registration:registration_admin')
    if request.user.is_authenticated:
        if not Site_Permissions.user_has_permission(request.user, 'reg_form_control'):
            return redirect('core:dashboard')
        elif not Site_Permissions.user_has_permission(request.user, 'view_qr_dashboard'):
            return redirect('registration:registration_admin')
        else:
            return redirect('core:dashboard')

    context = {
        'is_staff_view': False,
        'is_published': _get_publish_status(),
    }
    return render(request, 'form.html', context)


@login_required
@permission_required('reg_form_control')
def registration_admin(request):
    registration_count = Form_Participant.objects.count()
    permissions = {
        'reg_form_control': Site_Permissions.user_has_permission(request.user, 'reg_form_control'),
        'view_reg_responses_list': Site_Permissions.user_has_permission(request.user, 'view_reg_responses_list'),
        'view_finance_info': Site_Permissions.user_has_permission(request.user, 'view_finance_info'),
        'view_qr_dashboard': Site_Permissions.user_has_permission(request.user, 'view_qr_dashboard'),
    }
    context = {
        'is_staff_view': True,
        'is_published': _get_publish_status(),
        'registration_count': registration_count,
        'has_perm': permissions,
    }
    return render(request, 'form.html', context)


def registration_redirect(request):
    if request.user.is_authenticated:
        return redirect('registration:registration_admin')
    else:
        return redirect('registration:registration_form')


@login_required
@permission_required('reg_form_control')
@require_POST
def toggle_publish(request):
    status = EventFormStatus.objects.order_by('-updated_at', '-id').first()
    if not status:
        status = EventFormStatus.objects.create(is_published=True)
    else:
        status.is_published = not status.is_published
        status.save(update_fields=['is_published'])
    return JsonResponse({'success': True, 'is_published': status.is_published})


SUBMIT_RATE_LIMIT = 20          # submissions allowed ...
SUBMIT_RATE_WINDOW = 60 * 60    # ... per this many seconds, per client IP


def _client_ip(request):
    return request.META.get('REMOTE_ADDR', '')


def _rate_limited(request):
    key = f'reg_submit:{_client_ip(request)}'
    cache.add(key, 0, SUBMIT_RATE_WINDOW)
    try:
        return cache.incr(key) > SUBMIT_RATE_LIMIT
    except ValueError:
        return False


def _choice_values(choices):
    return {value for value, _ in choices}


def _post(request, name, max_length=None):
    value = request.POST.get(name, '').strip()
    return value[:max_length] if max_length else value


def _validate_abstract(upload):
    """Returns an error message for an invalid abstract upload, or None if it is fine."""
    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in settings.ABSTRACT_ALLOWED_EXTENSIONS:
        return 'Abstract must be a ' + ', '.join(settings.ABSTRACT_ALLOWED_EXTENSIONS) + ' file.'
    if upload.size > settings.ABSTRACT_MAX_UPLOAD_BYTES:
        return f'Abstract file must be smaller than {settings.ABSTRACT_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.'
    return None


def submit_form(request):
    try:
        if request.method != 'POST':
            return JsonResponse({'success': False, 'message': 'Invalid request method'})

        status = EventFormStatus.objects.order_by('-updated_at', '-id').first()
        is_admin = Site_Permissions.user_has_permission(request.user, 'reg_form_control')
        if not is_admin:
            if not status or not status.is_published:
                return JsonResponse({'success': False, 'message': 'Registration is currently closed.'})
            if _rate_limited(request):
                return JsonResponse({'success': False, 'message': 'Too many submissions. Please try again later.'})

        registration_type = _post(request, 'registration_type')
        if registration_type not in ('participant', 'competition'):
            return JsonResponse({'success': False, 'message': 'Invalid registration type.'})

        # Common fields
        participant = Form_Participant(
            registration_type=registration_type,
            name=_post(request, 'name', 200),
            email=_post(request, 'email', 254),
            phone=_post(request, 'phone', 20),
            university=_post(request, 'university', 200),
            department=_post(request, 'department'),
            student_id=_post(request, 'student_id', 50),
            study_level=_post(request, 'study_level'),
            ambassador_code=_post(request, 'ambassador_code', 50),
        )

        errors = []
        for label, value in (('Name', participant.name), ('Email', participant.email), ('Phone', participant.phone),
                             ('University', participant.university), ('Student ID', participant.student_id)):
            if not value:
                errors.append(f'{label} is required.')
        if participant.department not in _choice_values(Form_Participant.DEPARTMENT_CHOICES):
            errors.append('Please select a valid department.')
        if participant.study_level not in _choice_values(Form_Participant.STUDY_LEVEL_CHOICES):
            errors.append('Please select a valid study level.')
        if participant.email:
            try:
                validate_email(participant.email)
            except ValidationError:
                errors.append('Please enter a valid email address.')

        abstract = None
        if registration_type == 'participant':
            participant.membership_type = _post(request, 'membership_type')
            participant.transaction_id = _post(request, 'transaction_id', 100)
            if participant.membership_type not in _choice_values(Form_Participant.MEMBERSHIP_CHOICES):
                errors.append('Please select a valid membership type.')

        else:
            participant.ieee_id = _post(request, 'ieee_id', 50)
            participant.team_name = _post(request, 'team_name', 200)
            participant.total_members = _post(request, 'total_members')

            for prefix in ('mem2', 'mem3'):
                setattr(participant, f'{prefix}_name', _post(request, f'{prefix}_name', 200))
                setattr(participant, f'{prefix}_university', _post(request, f'{prefix}_university', 200))
                setattr(participant, f'{prefix}_department', _post(request, f'{prefix}_department', 200))
                setattr(participant, f'{prefix}_student_id', _post(request, f'{prefix}_student_id', 50))
                setattr(participant, f'{prefix}_email', _post(request, f'{prefix}_email', 254))
                setattr(participant, f'{prefix}_phone', _post(request, f'{prefix}_phone', 20))
                member_email = getattr(participant, f'{prefix}_email')
                if member_email:
                    try:
                        validate_email(member_email)
                    except ValidationError:
                        errors.append(f'Please enter a valid email address for member {prefix[-1]}.')

            participant.track = _post(request, 'track')
            participant.project_title = _post(request, 'project_title', 300)
            participant.problem_statement = _post(request, 'problem_statement', 5000)
            participant.proposed_solution = _post(request, 'proposed_solution', 5000)
            valid_sdgs = ('SDG 7', 'SDG 9', 'SDG 11', 'SDG 13')
            participant.sdg_alignment = [x for x in request.POST.getlist('sdg_alignment') if x in valid_sdgs]
            participant.comp_transaction_id = _post(request, 'comp_transaction_id', 100)

            if not participant.team_name:
                errors.append('Team name is required.')
            if participant.total_members not in _choice_values(Form_Participant.MEMBER_COUNT_CHOICES):
                errors.append('Please select a valid team size.')
            if participant.track not in _choice_values(Form_Participant.TRACK_CHOICES):
                errors.append('Please select a valid track.')
            if not participant.project_title:
                errors.append('Project title is required.')

            abstract = request.FILES.get('abstract_file')
            if abstract:
                abstract_error = _validate_abstract(abstract)
                if abstract_error:
                    errors.append(abstract_error)

        if errors:
            return JsonResponse({'success': False, 'message': errors[0], 'errors': errors})

        if Form_Participant.objects.filter(registration_type=registration_type, email__iexact=participant.email).exists():
            return JsonResponse({'success': False, 'message': 'This email address has already been registered.'})

        participant.save()

        # Handle abstract file upload (competition only)
        if abstract:
            abstracts_dir = os.path.join(settings.PROTECTED_ROOT, 'Abstracts')
            os.makedirs(abstracts_dir, exist_ok=True)
            ext = os.path.splitext(abstract.name)[1].lower()
            safe_name = re.sub(r'[^A-Za-z0-9_-]', '', participant.name.replace(' ', '_'))[:40] or 'team'
            filename = f"{participant.id}_{safe_name}{ext}"
            with open(os.path.join(abstracts_dir, filename), 'wb') as dest:
                for chunk in abstract.chunks():
                    dest.write(chunk)
            participant.abstract_file = filename
            participant.save(update_fields=['abstract_file'])

        email_success = send_registration_email(request, participant.name, participant.email)

        if registration_type == 'competition':
            if participant.mem2_email and not send_registration_email(request, participant.mem2_name or 'Team Member', participant.mem2_email):
                email_success = False
            if participant.mem3_email and not send_registration_email(request, participant.mem3_name or 'Team Member', participant.mem3_email):
                email_success = False

        if not email_success:
            return JsonResponse({
                'success': False,
                'message': 'Registration was saved, but the confirmation email could not be sent. Please contact the organizers.',
                'participant_id': participant.id,
            })

        return JsonResponse({
            'success': True,
            'message': f'Registration successful! Your registration ID is: {participant.id}',
            'participant_id': participant.id,
        })

    except Exception as e:
        log_exception(e, request)
        return JsonResponse({'success': False, 'message': 'Registration failed. Please try again.'})


def _excel_safe(value):
    # Prevent spreadsheet formula injection from user-supplied text
    if isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


@login_required
@permission_required('reg_form_control')
def download_excel(request):
    participants = Form_Participant.objects.all().order_by('created_at')

    participant_rows = []
    competition_rows = []

    for p in participants:
        if p.registration_type == 'participant':
            participant_rows.append({
                'ID': p.id,
                'Name': p.name,
                'Email': p.email,
                'Phone': p.phone,
                'University': p.university,
                'Department': p.get_department_display(),
                'Student ID': p.student_id,
                'Study Level': p.get_study_level_display(),
                'Membership': p.get_membership_type_display() if p.membership_type else '',
                'Transaction ID': p.transaction_id,
                'Ambassador Code': p.ambassador_code,
                'Registered At': p.created_at.astimezone().strftime('%Y-%m-%d %H:%M:%S'),
            })
        elif p.registration_type == 'competition':
            competition_rows.append({
                'ID': p.id,
                'Team Leader': p.name,
                'Email': p.email,
                'Phone': p.phone,
                'University': p.university,
                'Department': p.get_department_display(),
                'Student ID': p.student_id,
                'Study Level': p.get_study_level_display(),
                'IEEE ID': p.ieee_id,
                'Team Name': p.team_name,
                'Total Members': p.total_members,
                'Track': p.get_track_display() if p.track else '',
                'Project Title': p.project_title,
                'SDG Alignment': ', '.join(p.sdg_alignment) if p.sdg_alignment else '',
                'Abstract File': p.abstract_file,
                'Transaction ID': p.comp_transaction_id,
                'Ambassador Code': p.ambassador_code,
                'Registered At': p.created_at.astimezone().strftime('%Y-%m-%d %H:%M:%S'),
            })

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df = pd.DataFrame([{k: _excel_safe(v) for k, v in r.items()} for r in participant_rows]) if participant_rows else pd.DataFrame({'Message': ['No participants yet']})
        df.to_excel(writer, index=False, sheet_name='Participants')

        df2 = pd.DataFrame([{k: _excel_safe(v) for k, v in r.items()} for r in competition_rows]) if competition_rows else pd.DataFrame({'Message': ['No competition entries yet']})
        df2.to_excel(writer, index=False, sheet_name='Competition')

    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="ppis_registrations.xlsx"'
    return response


@login_required
@permission_required('view_reg_responses_list')
def response_table(request):
    permissions = {
        'view_finance_info': Site_Permissions.user_has_permission(request.user, 'view_finance_info'),
        'delete_participant': Site_Permissions.user_has_permission(request.user, 'delete_participant'),
    }

    participants = Form_Participant.objects.all().order_by('created_at')
    participant_rows = participants.filter(registration_type='participant')
    contestant_rows = participants.filter(registration_type='competition')
    # Total people coming with the teams (each team registers 1, 2 or 3 members)
    contestant_headcount = sum(int(x) for x in contestant_rows.values_list('total_members', flat=True) if x and x.isdigit())

    stats = {}
    if permissions['view_finance_info']:
        fees = settings.REGISTRATION_FEES
        comp_fees = settings.COMPETITION_FEES
        stats['participant_count'] = participants.filter(registration_type='participant').count()
        stats['competition_count'] = participants.filter(registration_type='competition').count()

        # General participants by membership
        stats['ieee_fee'] = fees['ieee']
        stats['non_ieee_fee'] = fees['non_ieee']
        stats['ieee_count'] = participants.filter(registration_type='participant', membership_type='ieee').count()
        stats['non_ieee_count'] = participants.filter(registration_type='participant', membership_type='non_ieee').count()
        stats['ieee_total'] = stats['ieee_count'] * fees['ieee']
        stats['non_ieee_total'] = stats['non_ieee_count'] * fees['non_ieee']

        # Contestant teams: an IEEE member is a team leader who gave an IEEE ID
        comp = participants.filter(registration_type='competition')
        stats['comp_ieee_fee'] = comp_fees['ieee']
        stats['comp_non_ieee_fee'] = comp_fees['non_ieee']
        stats['comp_ieee_count'] = comp.exclude(ieee_id__isnull=True).exclude(ieee_id='').count()
        stats['comp_non_ieee_count'] = stats['competition_count'] - stats['comp_ieee_count']
        stats['comp_ieee_total'] = stats['comp_ieee_count'] * comp_fees['ieee']
        stats['comp_non_ieee_total'] = stats['comp_non_ieee_count'] * comp_fees['non_ieee']

        stats['total_count'] = stats['participant_count'] + stats['competition_count']
        stats['total_amount'] = (stats['ieee_total'] + stats['non_ieee_total']
                                 + stats['comp_ieee_total'] + stats['comp_non_ieee_total'])

        # Group universities ignoring case and surrounding spaces
        university_data = (
            participants
            .annotate(university_trimmed=Trim('university'))
            .exclude(university_trimmed='')
            .annotate(university_key=Lower('university_trimmed'))
            .values('university_key')
            .annotate(university_sanitized=Min('university_trimmed'), total=Count('id'))
            .order_by('-total', 'university_key')
        )
    else:
        university_data = []

    context = {
        'participants': participants,
        'participant_rows': participant_rows,
        'contestant_rows': contestant_rows,
        'contestant_headcount': contestant_headcount,
        'stats': stats,
        'university_data': university_data,
        'has_perm': permissions,
    }
    return render(request, 'response_table.html', context)


@login_required
@permission_required('view_reg_response')
def view_response(request, id):
    participant = get_object_or_404(Form_Participant, id=id)
    context = {
        'participant': participant,
        'has_perm': {'view_finance_info': Site_Permissions.user_has_permission(request.user, 'view_finance_info')},
    }
    return render(request, 'participant_response.html', context)


@login_required
@permission_required('delete_participant')
@require_POST
def delete_response(request, id):
    if Core.delete_participant(form_id=id):
        return JsonResponse({'message': 'success'})
    return JsonResponse({'message': 'Participant not found'}, status=404)
