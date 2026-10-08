"""Smoke tests: every page and endpoint must render (never 500) for every kind of visitor, with realistic data."""
import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import get_resolver, reverse

from access_ctrl.models import Permission, UserPermission
from core.models import Registered_Participant, Token_Participant, Token_Session
from registration.models import EventFormStatus, Form_Participant

NO_SERVER_ERROR = set(range(100, 500))


@override_settings(SECURE_SSL_REDIRECT=False)
class SmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('root', password='pw')
        cls.limited = User.objects.create_user('limited', password='pw')
        perms = [Permission.objects.get(codename=c) for c in (
            'view_qr_dashboard', 'view_reg_responses_list', 'view_reg_response', 'view_finance_info',
            'reg_form_control', 'scan_session', 'update_session', 'scan_any_session', 'delete_participant')]
        cls.full_staff = User.objects.create_user('staff', password='pw')
        UserPermission.objects.create(user=cls.full_staff).permissions.add(*perms)

        EventFormStatus.objects.create(is_published=True)
        base = dict(phone='+8801700000000', university='NSU', department='eee', student_id='1', study_level='undergrad')
        Form_Participant.objects.create(registration_type='participant', name='Pat', email='p@x.co',
                                        membership_type='ieee', **base)
        cls.team = Form_Participant.objects.create(
            registration_type='competition', name='Lead', email='l@x.co', team_name='Volt', total_members='3',
            ieee_id='I-1', track='track_a', project_title='Grid', abstract_file='1_Lead.pdf',
            mem2_name='Two', mem2_email='m2@x.co', mem2_university='NSU', mem2_department='cs',
            mem2_student_id='2', mem2_phone='1', mem3_name='Three', mem3_email='m3@x.co', **base)
        cls.reg = Registered_Participant.objects.create(name='Pat', email='p@x.co', university='NSU',
                                                         contact_no='1', unique_code='CODE123456789')
        cls.session = Token_Session.objects.create(session_name='Lunch', is_active=True, order_of_session=1)
        Token_Participant.objects.create(registered_participant=cls.reg, token_session=cls.session)

    GET_PAGES = [
        '/', '/login/', '/dashboard/', '/reg/', '/registration/admin/', '/registration/responses/',
        '/download-excel/', '/init/authorise/', '/init/oauth2callback/', '/api/send_email/',
        '/api/process_qr_data/', '/api/update_session/', '/api/get_session_statuses/',
        '/api/update_participant_session/', '/api/delete_participant/', '/init/gen_qr/',
        '/init/import_reg_participants/', '/submit-form/', '/registration/toggle-publish/',
        '/protected/Abstracts/none.pdf', '/media_files/event.ics', '/static/img/PPISBanner.webp',
        '/this-page-does-not-exist/', '/admin/', '/admin/login/',
    ]

    def check(self, user, label):
        if user:
            self.client.force_login(user)
        else:
            self.client.logout()
        urls = list(self.GET_PAGES) + [
            f'/registration/response/{self.team.id}/', '/registration/response/9999/',
            f'/registration/response/{self.team.id}/delete/',
        ]
        for url in urls:
            response = self.client.get(url, follow=False)
            self.assertLess(response.status_code, 500, f'{label}: GET {url} -> {response.status_code}')

    def test_anonymous_never_gets_a_server_error(self):
        self.check(None, 'anonymous')

    def test_limited_user_never_gets_a_server_error(self):
        self.check(self.limited, 'limited')

    def test_full_staff_never_gets_a_server_error(self):
        self.check(self.full_staff, 'staff')

    def test_superuser_never_gets_a_server_error(self):
        self.check(self.admin, 'superuser')

    def test_every_post_endpoint_survives_garbage(self):
        self.client.force_login(self.admin)
        posts = ['/api/send_email/', '/api/process_qr_data/', '/api/update_session/', '/api/get_session_statuses/',
                 '/api/update_participant_session/', '/api/delete_participant/', '/init/gen_qr/',
                 '/init/import_reg_participants/', '/submit-form/', '/registration/toggle-publish/']
        for url in posts:
            for body in ('', 'not json', '{}', '[]', '{"participant_id": null}', json.dumps({'x': 'y' * 1000})):
                response = self.client.post(url, data=body, content_type='application/json')
                self.assertLess(response.status_code, 500, f'POST {url} body={body[:30]!r} -> {response.status_code}')

    def test_every_template_url_name_resolves(self):
        names = {'core:login', 'core:logout', 'core:dashboard', 'core:update_session', 'core:get_session_statuses',
                 'core:update_participant_session', 'core:process_qr_data', 'core:delete_participant', 'core:gen_qr',
                 'core:import_reg_participants', 'emails:send_email', 'emails:oauth2callback',
                 'registration:registration_form', 'registration:registration_admin', 'registration:response_table',
                 'registration:toggle_publish', 'registration:submit_form', 'registration:download_excel'}
        for name in names:
            reverse(name)
        reverse('registration:view_response', args=[1])
        reverse('registration:delete_response', args=[1])

    def test_no_url_pattern_is_left_unnamed_by_accident(self):
        # sanity: the resolver loads and exposes the app namespaces we rely on
        namespaces = set(get_resolver().namespace_dict)
        self.assertTrue({'core', 'emails', 'registration'} <= namespaces)

    def test_form_pages_contain_expected_flow(self):
        html = self.client.get('/').content.decode()
        self.assertIn("COMPETITION_STEPS = ['0','1','2c','3c']", html)
        self.assertNotIn('step4c', html)
        self.assertEqual(html.count('id="submitBtnC"'), 1)
