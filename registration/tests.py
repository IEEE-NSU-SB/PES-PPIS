import os
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from registration.models import EventFormStatus, Form_Participant


def participant_payload(**overrides):
    data = {
        'registration_type': 'participant',
        'name': 'Test User',
        'email': 'test@example.com',
        'phone': '1234567890',
        'university': 'North South University',
        'department': 'cs',
        'student_id': '2021-1234',
        'study_level': 'undergrad',
        'membership_type': 'non_ieee',
        'transaction_id': 'TX-123',
    }
    data.update(overrides)
    return data


def competition_payload(**overrides):
    data = participant_payload(
        registration_type='competition',
        team_name='Team A',
        total_members='1',
        track='track_a',
        project_title='Smart grid',
        problem_statement='p',
        proposed_solution='s',
    )
    data.pop('membership_type')
    data.pop('transaction_id')
    data.update(overrides)
    return data


class SubmitFormEmailFailureTests(TestCase):
    @patch('registration.views.Site_Permissions.user_has_permission', return_value=True)
    @patch('registration.views.send_registration_email', return_value=False)
    def test_submit_form_reports_email_failure_without_failing_registration(self, mock_send_email, mock_permission):
        EventFormStatus.objects.create(is_published=True)

        response = self.client.post(reverse('registration:submit_form'), participant_payload())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # The registration is saved, so it is reported as a success with an email warning
        self.assertTrue(data['success'])
        self.assertFalse(data['email_sent'])
        self.assertIn('email', data['message'].lower())
        mock_send_email.assert_called_once()
        self.assertEqual(Form_Participant.objects.count(), 1)


class SubmitFormTests(TestCase):
    def setUp(self):
        cache.clear()
        EventFormStatus.objects.create(is_published=True)
        self.url = reverse('registration:submit_form')
        patcher = patch('registration.views.send_registration_email', return_value=True)
        self.mock_email = patcher.start()
        self.addCleanup(patcher.stop)

    def test_successful_participant_registration(self):
        response = self.client.post(self.url, participant_payload())
        self.assertTrue(response.json()['success'])
        self.mock_email.assert_called_once_with(response.wsgi_request, 'test@example.com', 'participant')
        self.assertEqual(Form_Participant.objects.count(), 1)

    def test_closed_registration_is_rejected(self):
        EventFormStatus.objects.create(is_published=False)
        response = self.client.post(self.url, participant_payload())
        self.assertFalse(response.json()['success'])
        self.assertEqual(Form_Participant.objects.count(), 0)

    def test_invalid_choice_and_email_rejected(self):
        for bad in ({'department': 'nope'}, {'study_level': 'nope'}, {'email': 'not-an-email'},
                    {'membership_type': 'nope'}, {'name': ''}):
            response = self.client.post(self.url, participant_payload(**bad))
            self.assertFalse(response.json()['success'], bad)
        self.assertEqual(Form_Participant.objects.count(), 0)

    def test_duplicate_email_rejected(self):
        self.client.post(self.url, participant_payload())
        response = self.client.post(self.url, participant_payload(email='TEST@example.com'))
        self.assertFalse(response.json()['success'])
        self.assertEqual(Form_Participant.objects.count(), 1)

    def test_rate_limit(self):
        with patch('registration.views.SUBMIT_RATE_LIMIT', 2):
            for i in range(2):
                self.client.post(self.url, participant_payload(email=f'u{i}@example.com'))
            response = self.client.post(self.url, participant_payload(email='u9@example.com'))
        self.assertFalse(response.json()['success'])
        self.assertIn('too many', response.json()['message'].lower())

    def test_abstract_upload_validation_and_storage(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, override_settings(PROTECTED_ROOT=tmp):
            bad = SimpleUploadedFile('evil.exe', b'MZ')
            response = self.client.post(self.url, {**competition_payload(), 'abstract_file': bad})
            self.assertFalse(response.json()['success'])
            self.assertEqual(Form_Participant.objects.count(), 0)

            good = SimpleUploadedFile('abstract.pdf', b'%PDF-1.4')
            response = self.client.post(self.url, {**competition_payload(name='Ann/../Lee'), 'abstract_file': good})
            self.assertTrue(response.json()['success'], response.json())
            participant = Form_Participant.objects.get()
            self.assertNotIn('/', participant.abstract_file)
            self.assertNotIn('..', participant.abstract_file)
            self.assertTrue(os.path.isfile(os.path.join(tmp, 'Abstracts', participant.abstract_file)))

    def test_oversized_abstract_rejected(self):
        with override_settings(ABSTRACT_MAX_UPLOAD_BYTES=10):
            big = SimpleUploadedFile('abstract.pdf', b'x' * 50)
            response = self.client.post(self.url, {**competition_payload(), 'abstract_file': big})
        self.assertFalse(response.json()['success'])


class AdminEndpointPermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('staff', password='pw')
        self.admin = User.objects.create_superuser('root', password='pw')

    def test_toggle_publish_requires_permission(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('registration:toggle_publish'))
        self.assertEqual(EventFormStatus.objects.count(), 0)
        self.assertNotEqual(response.headers.get('Content-Type'), 'application/json')

    def test_toggle_publish_as_superuser(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('registration:toggle_publish'))
        self.assertTrue(response.json()['is_published'])
        response = self.client.post(reverse('registration:toggle_publish'))
        self.assertFalse(response.json()['is_published'])

    def test_view_response_missing_returns_404(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('registration:view_response', args=[9999]))
        self.assertEqual(response.status_code, 404)

    def test_excel_export_neutralises_formulas(self):
        Form_Participant.objects.create(
            registration_type='participant', name='=HYPERLINK("http://x")', email='a@b.co', phone='1',
            university='u', department='cs', student_id='1', study_level='undergrad')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('registration:download_excel'))
        self.assertEqual(response.status_code, 200)
        import pandas as pd
        from io import BytesIO
        df = pd.read_excel(BytesIO(response.content), sheet_name='Participants')
        self.assertTrue(df['Name'][0].startswith("'="))


class TeamEmailTests(TestCase):
    def setUp(self):
        cache.clear()
        EventFormStatus.objects.create(is_published=True)

    def test_every_team_member_gets_the_confirmation_emails(self):
        sent = []
        payload = competition_payload(
            name='Leader One', email='leader@example.com', total_members='3',
            mem2_name='Mate Two', mem2_email='m2@example.com',
            mem3_name='Mate Three', mem3_email='m3@example.com')
        with patch('registration.views.send_registration_email',
                   side_effect=lambda r, email, reg_type: sent.append((email, reg_type)) or True):
            response = self.client.post(reverse('registration:submit_form'), payload)
        self.assertTrue(response.json()['success'], response.json())
        self.assertEqual(sent, [('leader@example.com', 'competition'),
                                ('m2@example.com', 'competition'),
                                ('m3@example.com', 'competition')])


class ResponseTablePageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('root', password='pw')
        self.client.force_login(self.admin)

        def make(name, email, uni, **kw):
            base = dict(registration_type='participant', name=name, email=email, phone='+8801700000000',
                        university=uni, department='mech_civil', student_id='1', study_level='undergrad')
            base.update(kw)
            return Form_Participant.objects.create(**base)

        make('A', 'a@x.co', 'North South University', membership_type='ieee')
        make('B', 'b@x.co', ' north south university ', membership_type='non_ieee')
        make('C', 'c@x.co', 'BRAC', membership_type='non_ieee')
        make('D', 'd@x.co', 'BUET', registration_type='competition', team_name='T', track='track_a')

    def test_contact_number_and_labels_are_shown(self):
        response = self.client.get(reverse('registration:response_table'))
        self.assertContains(response, '+8801700000000')
        self.assertContains(response, 'Mechanical / Civil Engineering')
        self.assertNotContains(response, '>mech_civil<')
        self.assertContains(response, 'Contestants (1 teams')

    def test_statistics_are_correct(self):
        response = self.client.get(reverse('registration:response_table'))
        stats = response.context['stats']
        self.assertEqual((stats['ieee_count'], stats['non_ieee_count']), (1, 2))
        self.assertEqual((stats['ieee_total'], stats['non_ieee_total']), (600, 1500))
        self.assertEqual(stats['total_amount'], 600 + 1500)
        self.assertEqual((stats['participant_count'], stats['competition_count'], stats['total_count']), (3, 1, 4))

    def test_universities_grouped_ignoring_case_and_spaces(self):
        universities = {u['university_sanitized'].lower(): u['total']
                        for u in self.client.get(reverse('registration:response_table')).context['university_data']}
        self.assertEqual(universities, {'north south university': 2, 'brac': 1, 'buet': 1})

    def test_empty_page_renders(self):
        Form_Participant.objects.all().delete()
        response = self.client.get(reverse('registration:response_table'))
        self.assertContains(response, 'No participants found.')
        self.assertContains(response, 'No registrations yet.')
        self.assertEqual(response.context['stats']['total_amount'], 0)

    def test_stats_hidden_without_finance_permission(self):
        from access_ctrl.models import Permission, UserPermission
        user = User.objects.create_user('viewer', password='pw')
        perm = Permission.objects.get(codename='view_reg_responses_list')
        UserPermission.objects.create(user=user).permissions.add(perm)
        self.client.force_login(user)
        response = self.client.get(reverse('registration:response_table'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'statsModal')
        self.assertEqual(response.context['stats'], {})


class ResponseTabsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('root', password='pw')
        self.client.force_login(self.admin)
        base = dict(email='x@x.co', phone='+8801711111111', university='U', department='cs',
                    student_id='1', study_level='undergrad')
        Form_Participant.objects.create(registration_type='participant', name='Pat', membership_type='ieee',
                                        transaction_id='TXN-P', **{**base, 'email': 'p@x.co'})
        Form_Participant.objects.create(registration_type='competition', name='Lead', team_name='Volt', total_members='3',
                                        ieee_id='IEEE-99', track='track_b',
                                        **{**base, 'email': 'c1@x.co'})
        Form_Participant.objects.create(registration_type='competition', name='Solo', team_name='Amp', total_members='1',
                                        **{**base, 'email': 'c2@x.co'})

    def test_rows_are_split_into_two_tables(self):
        response = self.client.get(reverse('registration:response_table'))
        self.assertEqual([p.name for p in response.context['participant_rows']], ['Pat'])
        self.assertEqual(sorted(p.name for p in response.context['contestant_rows']), ['Lead', 'Solo'])
        self.assertEqual(response.context['contestant_headcount'], 4)
        self.assertContains(response, 'Participants (1)')
        self.assertContains(response, 'Contestants (2 teams')

    def test_contestant_table_columns(self):
        response = self.client.get(reverse('registration:response_table'))
        for text in ('IEEE-99', 'IEEE ID', 'Team of'):
            self.assertContains(response, text)

    def test_transaction_id_column_is_only_on_the_participants_tab(self):
        response = self.client.get(reverse('registration:response_table'))
        html = response.content.decode()
        participants_panel = html[html.index('id="panel-participants"'):html.index('id="panel-contestants"')]
        contestants_panel = html[html.index('id="panel-contestants"'):html.index('<!-- Modal -->')]
        self.assertIn('Transaction ID', participants_panel)
        self.assertNotIn('Transaction ID', contestants_panel)
        self.assertIn('TXN-P', participants_panel)

    def test_transaction_id_hidden_without_finance_permission(self):
        from access_ctrl.models import Permission, UserPermission
        user = User.objects.create_user('viewer', password='pw')
        perm = Permission.objects.get(codename='view_reg_responses_list')
        UserPermission.objects.create(user=user).permissions.add(perm)
        self.client.force_login(user)
        response = self.client.get(reverse('registration:response_table'))
        self.assertNotContains(response, 'TXN-P')
        self.assertNotContains(response, 'Transaction ID')


class ParticipantTransactionIdTests(TestCase):
    def setUp(self):
        cache.clear()
        EventFormStatus.objects.create(is_published=True)
        patcher = patch('registration.views.send_registration_email', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse('registration:submit_form')

    def test_participant_must_give_a_transaction_id(self):
        response = self.client.post(self.url, participant_payload(transaction_id='  '))
        self.assertFalse(response.json()['success'])
        self.assertIn('transaction', response.json()['message'].lower())
        self.assertEqual(Form_Participant.objects.count(), 0)

    def test_transaction_id_is_saved_and_trimmed(self):
        response = self.client.post(self.url, participant_payload(transaction_id=' ABC123 '))
        self.assertTrue(response.json()['success'])
        self.assertEqual(Form_Participant.objects.get().transaction_id, 'ABC123')

    def test_competition_does_not_need_one(self):
        self.assertTrue(self.client.post(self.url, competition_payload()).json()['success'])
        self.assertFalse(Form_Participant.objects.get().transaction_id)

    def test_form_has_the_input_for_participants_only(self):
        html = self.client.get('/').content.decode()
        step_p = html[html.index('id="step2p"'):html.index('id="step2c"')]
        step_c = html[html.index('id="step2c"'):]
        self.assertEqual(step_p.count('name="transaction_id"'), 1)
        self.assertNotIn('name="transaction_id"', step_c)
        self.assertIn("{ name: 'transaction_id', label: 'Bkash Transaction ID' }", html)

    def test_excel_export_has_the_column(self):
        from io import BytesIO
        import pandas as pd
        Form_Participant.objects.create(registration_type='participant', name='P', email='p@x.co', phone='1',
                                        university='U', department='cs', student_id='1', study_level='undergrad',
                                        membership_type='ieee', transaction_id='TXN-X')
        self.client.force_login(User.objects.create_superuser('root', password='pw'))
        df = pd.read_excel(BytesIO(self.client.get(reverse('registration:download_excel')).content),
                           sheet_name='Participants')
        self.assertEqual(df['Transaction ID'][0], 'TXN-X')

    def test_detail_page_shows_it_only_with_finance_permission(self):
        from access_ctrl.models import Permission, UserPermission
        p = Form_Participant.objects.create(registration_type='participant', name='P', email='p@x.co', phone='1',
                                            university='U', department='cs', student_id='1',
                                            study_level='undergrad', membership_type='ieee', transaction_id='TXN-D')
        user = User.objects.create_user('viewer', password='pw')
        up = UserPermission.objects.create(user=user)
        up.permissions.add(Permission.objects.get(codename='view_reg_response'))
        self.client.force_login(user)
        url = reverse('registration:view_response', args=[p.id])
        self.assertNotContains(self.client.get(url), 'TXN-D')
        up.permissions.add(Permission.objects.get(codename='view_finance_info'))
        self.assertContains(self.client.get(url), 'TXN-D')


class StatisticsLayoutTests(TestCase):
    def test_only_participants_are_charged(self):
        admin = User.objects.create_superuser('root', password='pw')
        self.client.force_login(admin)
        base = dict(phone='1', university='U', department='cs', student_id='1', study_level='undergrad')
        Form_Participant.objects.create(registration_type='participant', name='P', email='p@x.co', membership_type='ieee', **base)
        Form_Participant.objects.create(registration_type='competition', name='L1', email='l1@x.co', ieee_id='I-1', **base)
        Form_Participant.objects.create(registration_type='competition', name='L2', email='l2@x.co', **base)
        response = self.client.get(reverse('registration:response_table'))
        stats = response.context['stats']
        self.assertEqual(stats['total_amount'], 600)           # contestants add nothing
        self.assertEqual(stats['total_count'], 3)               # but they are still registrations
        self.assertEqual(stats['competition_count'], 2)
        self.assertNotIn('comp_ieee_count', stats)
        self.assertNotContains(response, 'Contestants (PPIS Policy Innovation Challenge)')
        self.assertContains(response, 'Total Registration:')


class TrackAndFormFieldTests(TestCase):
    def setUp(self):
        cache.clear()
        EventFormStatus.objects.create(is_published=True)
        patcher = patch('registration.views.send_registration_email', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def submit(self, **overrides):
        payload = competition_payload(**overrides)
        for key in ('problem_statement', 'proposed_solution'):
            payload.pop(key, None)  # the form no longer sends these
        return self.client.post(reverse('registration:submit_form'), payload).json()

    def test_new_tracks_accepted_and_removed_track_rejected(self):
        self.assertTrue(self.submit(track='track_a', email='a@x.co')['success'])
        self.assertTrue(self.submit(track='track_b', email='b@x.co')['success'])
        self.assertFalse(self.submit(track='track_c', email='c@x.co')['success'])

    def test_registration_works_without_problem_statement_solution_or_sdg(self):
        self.assertTrue(self.submit(email='d@x.co')['success'])
        participant = Form_Participant.objects.get(email='d@x.co')
        self.assertFalse(participant.problem_statement)
        self.assertEqual(participant.sdg_alignment, [])

    def test_track_labels(self):
        labels = dict(Form_Participant.TRACK_CHOICES)
        self.assertEqual(labels['track_a'], 'Track A: Irrigation, Community Village, EV Charging')
        self.assertIn('Economically Feasible', labels['track_b'])
        self.assertNotIn('track_c', labels)

    def test_detail_page_hides_unused_fields(self):
        admin = User.objects.create_superuser('root', password='pw')
        self.client.force_login(admin)
        self.submit(email='e@x.co')
        participant = Form_Participant.objects.get(email='e@x.co')
        response = self.client.get(reverse('registration:view_response', args=[participant.id]))
        self.assertNotContains(response, 'Problem Statement')
        self.assertNotContains(response, 'Proposed Solution')
        self.assertNotContains(response, 'SDG Alignment')
        self.assertContains(response, 'Track A: Irrigation, Community Village, EV Charging')


class ChallengeDetailsTests(TestCase):
    def test_details_are_shown_above_the_registration_type_choice(self):
        EventFormStatus.objects.create(is_published=True)
        html = self.client.get('/').content.decode()
        step0 = html[html.index('id="step0"'):html.index('id="step1"')]
        details = step0.index('id="challengeDetails"')
        heading = step0.index('Choose Your Registration Type')
        self.assertLess(details, heading)
        for text in ('Power Policy Innovation Challenge', 'Prize Pool:', '65,000 BDT', 'October 8 - October 15, 2026',
                     '2-3 members per team (no solo entries)', 'Each team must have a unique team name',
                     'Round 2 (Top 20 Pitch)', 'AUDI801', 'Grand Finale (Top 5 Defense)',
                     'Only one registration per team is needed', 'Lutful Islam Nabid', '+8801712902722',
                     'Ridwan Islam Rifath', '+8801919356207'):
            self.assertIn(text, step0, text)
        # not repeated on the later steps
        self.assertEqual(html.count('id="challengeDetails"'), 1)
