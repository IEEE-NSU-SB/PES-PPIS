import csv
import json
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth.models import auth
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from access_ctrl.decorators import permission_required
from access_ctrl.utils import Site_Permissions
from .renderData import Core

from core.forms import CSVImportForm
from core.models import Registered_Participant
from system_administration.utils import log_exception

# Create your views here.
def login(request):

    if request.user.is_authenticated:
        if not Site_Permissions.user_has_permission(request.user, 'reg_form_control'):
            return redirect('core:dashboard')
        elif not Site_Permissions.user_has_permission(request.user, 'view_qr_dashboard'):
            return redirect('registration:registration_admin')
        else:
            return redirect('core:dashboard')
    
    if(request.method == 'POST'):
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')

        user = auth.authenticate(username=username, password=password)
        if(user is not None):
            # Check for the 'next' parameter in the GET request
            next_url = request.GET.get('next')

            auth.login(request, user)
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                # Redirect to the originally requested URL
                return redirect(next_url)
            else:
                if not Site_Permissions.user_has_permission(request.user, 'reg_form_control'):
                    return redirect('core:dashboard')
                elif not Site_Permissions.user_has_permission(request.user, 'view_qr_dashboard'):
                    return redirect('registration:registration_admin')
                else:
                    return redirect('core:dashboard')
        else:
            messages.error(request, "Credentials don't match")

    return render(request, 'login.html')

def logout(request):
    auth.logout(request)
    return redirect('core:login')

class Process_QR_Data(View):
    def post(self, request):
        if not Site_Permissions.user_has_permission(request.user, 'scan_session'):
            return render(request, '404.html', status=404)
        try:
            return Core.process_qr_data(request)
        except Exception as e:
            log_exception(e, request)
            return JsonResponse({'status': 'error', 'message': 'error'})

    def get(self, request):
        return render(request, '404.html', status=404)


@login_required
def import_csv(request):
    if not Site_Permissions.is_superuser(request.user):
        return render(request, '404.html', status=404)

    form = CSVImportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        csv_file = request.FILES['csv_file'].read().decode('utf-8').splitlines()
        csv_reader = csv.DictReader(csv_file)

        for row in csv_reader:
            Registered_Participant.objects.create(
                id=row['Serial No.'],
                name=row['Name'],
                university=row['University Name'],
                email=row['Email Address'],
                contact_no=row['Contact'],
                role=row['Role'],
                t_shirt_size=row['T-shirt Size'],
                unique_code=Core.generate_unique_code(row['Name'], row['University Name'])
            )
        
        return redirect('core:dashboard')
    
    return render(request, 'csv.html', {'form': form})

@login_required
@permission_required('view_qr_dashboard')
def dashboard(request):
    
    token_sessions = Core.get_active_token_sessions()
    token_sessions_all = Core.get_all_token_sessions()
    token_sessions_with_participant_count = Core.get_all_token_sessions_with_participant_counts()
    universities = Core.get_all_participant_universities()
    registered_participants = Core.get_all_reg_participants_with_sessions()

    total_participants = len(registered_participants)

    permissions = {
        'update_session':Site_Permissions.user_has_permission(request.user, 'update_session'),
        'scan_session':Site_Permissions.user_has_permission(request.user, 'scan_session'),
        'scan_any_session':Site_Permissions.user_has_permission(request.user, 'scan_any_session'),
        'delete_participant':Site_Permissions.user_has_permission(request.user, 'delete_participant'),
    }
            
    request.session['active_sessions'] = Core.active_sessions_signature()

    context = {
        'token_sessions':token_sessions,
        'token_sessions_all':token_sessions_all,
        'token_sessions_with_participant_count':token_sessions_with_participant_count,
        'registered_participants':registered_participants,
        'total_participants':total_participants,
        'participant_universities':universities,
        'has_perm':permissions,
    }

    return render(request, 'dashboard.html', context)

class SessionUpdateAjax(View):
    def post(self, request):
        if not Site_Permissions.user_has_permission(request.user, 'update_session'):
            return render(request, '404.html', status=404)
        try:
            sessions = json.loads(request.body)['sessions']
            if Core.update_session(sessions=sessions):
                return JsonResponse({'message': "success"})
            return JsonResponse({'message': "error"})
        except Exception as e:
            log_exception(e, request)
            return JsonResponse({'message': 'error'})

    def get(self, request):
        return render(request, '404.html', status=404)

class GetSessionStatusAjax(View):
    def post(self, request):
        if not Site_Permissions.user_has_permission(request.user, 'view_qr_dashboard'):
            return render(request, '404.html', status=404)
        try:
            last_updated_date_time = json.loads(request.body)['last_updated_date_time']
            token_sessions_with_participant_count = Core.get_all_token_sessions_with_participant_counts()

            new_scans = Core.get_new_token_session_scans(last_updated_date_time)

            data = {}
            status = {}
            for x in token_sessions_with_participant_count:
                status.update({x['sessionid']: x['participant_count']})
            data.update({'status': status})
            scans = {}
            for x in new_scans:
                scans.update({x['registered_participant']: x['token_session']})
            data.update({'new_scans': scans})

            if request.session.get('active_sessions') != Core.active_sessions_signature():
                data.update({'session_update': ''})

            return JsonResponse(data)
        except Exception as e:
            log_exception(e, request)
            return JsonResponse({'message': 'error'})

    def get(self, request):
        return render(request, '404.html', status=404)

class UpdateParticipantSessionAjax(View):
    def post(self, request):
        if not Site_Permissions.user_has_permission(request.user, 'scan_session'):
            return render(request, '404.html', status=404)
        try:
            data = json.loads(request.body)
            return Core.update_participant_session(data['participant_id'], data['session_id'], data['status'])
        except Exception as e:
            log_exception(e, request)
            return JsonResponse({'message': 'error'})

    def get(self, request):
        return render(request, '404.html', status=404)

from .qrgenerator import *

@login_required
@require_POST
def gen(request):
    if Site_Permissions.is_superuser(request.user):
        generate_qr()
        return JsonResponse({'message': 'success'})
    return render(request, '404.html', status=404)


@login_required
@require_POST
def import_reg_participants(request):
    if Site_Permissions.is_superuser(request.user):
        Core.import_participants_from_reg()
        return JsonResponse({'message': 'success'})
    return render(request, '404.html', status=404)


@login_required
@require_POST
def delete_participant(request):
    if not Site_Permissions.user_has_permission(request.user, 'delete_participant'):
        return JsonResponse({'message': 'Permission denied'}, status=403)
    try:
        participant_id = int(json.loads(request.body)['participant_id'])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'message': 'Invalid participant'}, status=400)

    if Core.delete_participant(registered_id=participant_id):
        return JsonResponse({'message': 'success'})
    return JsonResponse({'message': 'Participant not found'}, status=404)
