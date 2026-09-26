import os
import csv
import pandas as pd
from io import BytesIO
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Count
from django.db.models.functions import Trim

from access_ctrl.decorators import permission_required
from access_ctrl.utils import Site_Permissions
from system_administration.utils import log_exception
from emails.views import send_registration_email

from .models import EventFormStatus, Form_Participant


def _get_publish_status() -> bool:
    status = EventFormStatus.objects.order_by('-updated_at').first()
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
@require_POST
def toggle_publish(request):
    status = EventFormStatus.objects.order_by('-updated_at').first()
    if not status:
        status = EventFormStatus.objects.create(is_published=True)
    else:
        status.is_published = not status.is_published
        status.save(update_fields=['is_published'])
    return JsonResponse({'success': True, 'is_published': status.is_published})


def submit_form(request):
    try:
        if request.method != 'POST':
            return JsonResponse({'success': False, 'message': 'Invalid request method'})

        status = EventFormStatus.objects.order_by('-updated_at').first()
        if not Site_Permissions.user_has_permission(request.user, 'reg_form_control'):
            if not status or not status.is_published:
                return JsonResponse({'success': False, 'message': 'Registration is currently closed.'})

        registration_type = request.POST.get('registration_type', '').strip()
        if registration_type not in ('participant', 'competition'):
            return JsonResponse({'success': False, 'message': 'Invalid registration type.'})

        # Common fields
        participant = Form_Participant(
            registration_type=registration_type,
            name=request.POST.get('name', '').strip(),
            email=request.POST.get('email', '').strip(),
            phone=request.POST.get('phone', '').strip(),
            university=request.POST.get('university', '').strip(),
            department=request.POST.get('department', '').strip(),
            student_id=request.POST.get('student_id', '').strip(),
            study_level=request.POST.get('study_level', '').strip(),
            ambassador_code=request.POST.get('ambassador_code', '').strip(),
        )

        if registration_type == 'participant':
            participant.membership_type = request.POST.get('membership_type', '').strip()
            participant.transaction_id = request.POST.get('transaction_id', '').strip()

        elif registration_type == 'competition':
            participant.ieee_id = request.POST.get('ieee_id', '').strip()
            participant.team_name = request.POST.get('team_name', '').strip()
            participant.total_members = request.POST.get('total_members', '').strip()

            participant.mem2_name = request.POST.get('mem2_name', '').strip()
            participant.mem2_university = request.POST.get('mem2_university', '').strip()
            participant.mem2_department = request.POST.get('mem2_department', '').strip()
            participant.mem2_student_id = request.POST.get('mem2_student_id', '').strip()
            participant.mem2_email = request.POST.get('mem2_email', '').strip()
            participant.mem2_phone = request.POST.get('mem2_phone', '').strip()

            participant.mem3_name = request.POST.get('mem3_name', '').strip()
            participant.mem3_university = request.POST.get('mem3_university', '').strip()
            participant.mem3_department = request.POST.get('mem3_department', '').strip()
            participant.mem3_student_id = request.POST.get('mem3_student_id', '').strip()
            participant.mem3_email = request.POST.get('mem3_email', '').strip()
            participant.mem3_phone = request.POST.get('mem3_phone', '').strip()

            participant.track = request.POST.get('track', '').strip()
            participant.project_title = request.POST.get('project_title', '').strip()
            participant.problem_statement = request.POST.get('problem_statement', '').strip()
            participant.proposed_solution = request.POST.get('proposed_solution', '').strip()
            participant.sdg_alignment = request.POST.getlist('sdg_alignment')
            participant.comp_transaction_id = request.POST.get('comp_transaction_id', '').strip()

        participant.save()

        # Handle abstract file upload (competition only)
        if registration_type == 'competition':
            abstract = request.FILES.get('abstract_file')
            if abstract:
                abstracts_dir = os.path.join(settings.PROTECTED_ROOT, 'Abstracts')
                os.makedirs(abstracts_dir, exist_ok=True)
                ext = os.path.splitext(abstract.name)[1].lower()
                safe_name = participant.name.replace(' ', '_')[:40]
                filename = f"{participant.id}_{safe_name}{ext}"
                filepath = os.path.join(abstracts_dir, filename)
                with open(filepath, 'wb+') as dest:
                    for chunk in abstract.chunks():
                        dest.write(chunk)
                participant.abstract_file = filename
                participant.save(update_fields=['abstract_file'])

        send_registration_email(request, participant.name, participant.email)

        if registration_type == 'competition':
            if participant.mem2_email:
                send_registration_email(request, participant.mem2_name or 'Team Member', participant.mem2_email)
            if participant.mem3_email:
                send_registration_email(request, participant.mem3_name or 'Team Member', participant.mem3_email)

        return JsonResponse({
            'success': True,
            'message': f'Registration successful! Your registration ID is: {participant.id}',
            'participant_id': participant.id,
        })

    except Exception as e:
        log_exception(e, request)
        return JsonResponse({'success': False, 'message': 'Registration failed. Please try again.'})


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
        df = pd.DataFrame(participant_rows) if participant_rows else pd.DataFrame({'Message': ['No participants yet']})
        df.to_excel(writer, index=False, sheet_name='Participants')

        df2 = pd.DataFrame(competition_rows) if competition_rows else pd.DataFrame({'Message': ['No competition entries yet']})
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
    }

    participants = Form_Participant.objects.all().order_by('created_at')

    stats = Form_Participant.objects.values('registration_type').annotate(total=Count('id'))
    summary = {entry['registration_type']: entry['total'] for entry in stats}

    university_data = (
        Form_Participant.objects
        .exclude(university__isnull=True)
        .exclude(university='')
        .annotate(university_sanitized=Trim('university'))
        .values('university_sanitized')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    context = {
        'participants': participants,
        'registration_stats': summary,
        'university_data': university_data,
        'has_perm': permissions,
    }
    return render(request, 'response_table.html', context)


@login_required
@permission_required('view_reg_response')
def view_response(request, id):
    participant = Form_Participant.objects.get(id=id)
    context = {'participant': participant}
    return render(request, 'participant_response.html', context)
