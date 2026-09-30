
import json
import os
import random
import string

from django.conf import settings

from django.http import JsonResponse
from core.models import Registered_Participant, Token_Participant, Token_Session
from django.db import transaction
from django.db.models import Count, F, Prefetch, Value
from django.db.models.functions import Coalesce

from registration.models import Form_Participant

class Core:

    def get_active_token_sessions():
        '''Gets token sessions that have `is_active` set to True, ordered by the `order_of_session`'''

        return Token_Session.objects.filter(is_active=True).order_by('order_of_session')

    def get_all_token_sessions():
        '''Gets all token sessions, ordered by the `order_of_session`'''
        
        return Token_Session.objects.all().order_by('order_of_session')

    def get_all_token_sessions_with_participant_counts():
        '''Gets all token sessions along with the participant counts for each session, ordered by the `order_of_session`.\n
            It returns a list with `session_name`, `sessionid` and `participant_count`'''
        
        return Token_Session.objects.values('session_name',sessionid=F('id')).annotate(participant_count=Coalesce(Count('token_participant'), Value(0))).order_by('order_of_session')

    def get_all_participant_universities():
        '''Gets all distinct participant universities.'''
        
        return Registered_Participant.objects.values('university').distinct()
    
    def get_all_reg_participants_with_sessions():
        '''Gets all registered_participants along with their token session data.\n
            Returns a list of registered_participants with each participant having a list of `tokens` that have been scanned already.'''

        registered_participants = Registered_Participant.objects.prefetch_related(
            Prefetch(
                'token_participant_set',  # Related name for Token_Participant
                queryset=Token_Participant.objects.only('token_session'),
                to_attr='tokens'
            )
        )
        return registered_participants
    
    def get_new_token_session_scans(last_updated_date_time):
        '''Gets token sessions with `date_time` greater than the param-`last_updated_date_time`.'''
        
        return Token_Participant.objects.filter(date_time__gte=last_updated_date_time).values('token_session', 'registered_participant')
    
    def process_qr_data(request):
        '''Processes the scanned QR data. It returns a JSON response:\n
            -`status` accepted or rejected\n
            -`session` the session name for which the qr is scanned\n
            -`session_id` the session id for which the qr is scanned\n
            -`participant.sl` the participant id for which the qr is scanned\n
            -`participant.name` the participant name for which the qr is scanned'''
        
        # Get the session id from header
        sessionid = request.headers.get('session-id')
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'error': 'Invalid JSON'})

        try:
            participant = Registered_Participant.objects.get(unique_code=data.get('unqc'))
            session = Token_Session.objects.get(id=sessionid)
        except (Registered_Participant.DoesNotExist, Token_Session.DoesNotExist, ValueError, TypeError, AttributeError):
            return JsonResponse({'status': 'error', 'error': 'Invalid QR code or session'})

        # Add the participant for this session, or reject if already scanned (atomic to avoid duplicate scans)
        with transaction.atomic():
            _, created = Token_Participant.objects.get_or_create(registered_participant=participant, token_session=session)

        return JsonResponse({
            'status': 'accepted' if created else 'rejected',
            'session': session.session_name,
            'session_id': session.id,
            'participant': {'sl': participant.id, 'name': participant.name},
        })

    def active_sessions_signature():
        # A string that changes whenever the set of active sessions changes. Used to tell open dashboards to refresh.

        return ','.join(str(i) for i in Token_Session.objects.filter(is_active=True).order_by('id').values_list('id', flat=True))

    def update_session(sessions):
        '''Sets sessions to active or inactive. The param `sessions` is a list of session ids that need to be active.'''

        # Get all token sessions
        all_sessions = Core.get_all_token_sessions()

        # For each session in all sessions
        for session in all_sessions:
            # If the session id is in sessions
            if str(session.id) in sessions:
                # Set it to active
                session.is_active = True
            else:
                # Set it to inactive
                session.is_active = False
            
            session.save()
        
        return True
    
    def update_participant_session(participant_id, session_id, status):
        '''Updates token_session for a participant without scanning. It takes the parameters:\n
            -`participant_id` for which to update the token_session\n
            -`session_id` for which to update the token_session\n
            -`status` accepted or rejected\n\n
            
            It returns a JSON response:\n
            -`message` accepted, rejected or other\n
            -`session` the session name for which the qr is scanned\n
            -`participant.sl` the participant id for which the qr is scanned\n
            -`participant.name` the participant name for which the qr is scanned'''

        try:
            participant = Registered_Participant.objects.get(id=participant_id)
            session = Token_Session.objects.get(id=session_id)
        except (Registered_Participant.DoesNotExist, Token_Session.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'message': 'Invalid participant or session'})

        info = {'session': session.session_name, 'participant': {'sl': participant.id, 'name': participant.name}}

        if status == 'accepted':
            _, created = Token_Participant.objects.get_or_create(registered_participant=participant, token_session=session)
            if created:
                return JsonResponse({'message': 'Accepted', **info})
            # The participant is already scanned/added previously, hence reject it
            return JsonResponse({'message': 'Participant is already in session', **info})
        elif status == 'rejected':
            deleted, _ = Token_Participant.objects.filter(registered_participant=participant, token_session=session).delete()
            if deleted:
                return JsonResponse({'message': 'Rejected', **info})
            # The participant has not been scanned/added for this session
            return JsonResponse({'message': 'Participant is not in session', **info})

        return JsonResponse({'message': 'Invalid status'})

    def generate_unique_code(name: str, university: str) -> str:
        # Function to pick a random part of a string
        def get_random_part(s):
            if len(s) > 1:  # Ensure there are at least 2 characters to pick from
                start = random.randint(0, len(s) - 1)
                end = random.randint(start + 1, len(s))  # Ensure end > start
                return s[start:end]
            return s  # Return the whole string if it's too short
        
        # Pick random parts of the name and university
        name_part = get_random_part(name.replace(" ", "").replace(".", ""))
        university_part = get_random_part(university.replace(" ", "").replace(".", ""))
        
        # Combine the random parts
        base_string = name_part + university_part
        
        # Randomly shuffle the base string
        shuffled = ''.join(random.sample(base_string, len(base_string)))
        
        # Add random characters to make the code between 13 and 16 characters
        random_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        
        # Combine shuffled string with random characters
        combined = shuffled + random_chars
        
        # Ensure the length is between 13 and 16 characters
        unique_code = combined[:random.randint(13, 16)]
        
        return unique_code
    
    def import_participants_from_reg():
        '''Imports all participants from form_participant table to registered_participant table and also generates their unique codes\n
            This is done when participants are confirmed for event.'''
        
        seen_emails = set(
            Registered_Participant.objects.values_list('email', flat=True)
        )
        used_codes = set(
            Registered_Participant.objects.values_list('unique_code', flat=True)
        )
        objects = []
        for participant in Form_Participant.objects.order_by('created_at'):
            if participant.email in seen_emails:
                continue
            seen_emails.add(participant.email)

            # unique_code has a unique constraint, so make sure a random collision cannot break the import
            code = Core.generate_unique_code(participant.name, participant.university)
            while code in used_codes:
                code = Core.generate_unique_code(participant.name, participant.university)
            used_codes.add(code)

            objects.append(Registered_Participant(
                name=participant.name,
                university=participant.university,
                contact_no=participant.phone,
                email=participant.email,
                unique_code=code,
            ))

        Registered_Participant.objects.bulk_create(objects)

        return True

    def _remove_file(*parts):
        # Deletes a file inside PROTECTED_ROOT (parts are reduced to bare file names, so nothing outside can be touched)
        safe_parts = [os.path.basename(str(x)) for x in parts if x]
        if not safe_parts:
            return
        path = os.path.join(settings.PROTECTED_ROOT, *safe_parts)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass

    def delete_participant(registered_id=None, form_id=None):
        """Permanently deletes a participant from BOTH the dashboard (`Registered_Participant`, with its scan records and QR image)
            and the registration responses (`Form_Participant`, with its uploaded abstract). The two records are matched by email.\n
            Pass either `registered_id` (dashboard) or `form_id` (response). Returns True if anything was deleted."""

        registered = list(Registered_Participant.objects.filter(id=registered_id)) if registered_id is not None else []
        forms = list(Form_Participant.objects.filter(id=form_id)) if form_id is not None else []

        # Find the matching record on the other side by email
        emails = {x.email.strip().lower() for x in registered + forms if x.email and x.email.strip()}
        for email in emails:
            registered += [x for x in Registered_Participant.objects.filter(email__iexact=email) if x not in registered]
            forms += [x for x in Form_Participant.objects.filter(email__iexact=email) if x not in forms]

        if not registered and not forms:
            return False

        # Django clears `id` after delete(), so collect the file names first
        abstract_files = [form.abstract_file for form in forms]
        qr_files = [f'{reg.id}.png' for reg in registered]

        with transaction.atomic():
            for form in forms:
                form.delete()
            for reg in registered:
                reg.delete()

        for name in abstract_files:
            Core._remove_file('Abstracts', name)
        for name in qr_files:
            Core._remove_file('Participant_QR', name)
        return True
