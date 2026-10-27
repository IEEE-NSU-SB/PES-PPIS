"""Regression tests for bugs found in the whole-project audit. One test class per scenario."""
import os
import re
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from access_ctrl.models import Permission, UserPermission
from access_ctrl.utils import Site_Permissions
from registration.models import EventFormStatus, Form_Participant
from system_administration.utils import client_ip

PDF = b'%PDF-1.4 test'


def team_payload(**overrides):
    data = {
        'registration_type': 'competition', 'name': 'Lead', 'email': 'lead@x.co', 'phone': '1',
        'university': 'U', 'department': 'cs', 'student_id': '1', 'study_level': 'undergrad',
        'team_name': 'Volt', 'total_members': '3', 'track': 'track_a', 'project_title': 'Grid',
        'mem2_name': 'Two', 'mem2_email': 'two@x.co', 'mem3_name': 'Three', 'mem3_email': 'three@x.co',
    }
    data.update(overrides)
    return data


def grant(user, *codenames):
    up, _ = UserPermission.objects.get_or_create(user=user)
    up.permissions.add(*Permission.objects.filter(codename__in=codenames))


@override_settings(SECURE_SSL_REDIRECT=False)
class ScriptEscapingTests(TestCase):
    """Names come from the public form, so they must never be put into staff pop-ups as raw HTML."""

    def scripts(self, url):
        admin = User.objects.create_superuser('root', password='pw')
        self.client.force_login(admin)
        return self.client.get(url).content.decode()

    def test_dashboard_escapes_names(self):
        html = self.scripts('/dashboard/')
        self.assertIn('function escapeHtml', html)
        self.assertNotIn('${data.participant.name}', html.replace('{% comment %}', ''))
        self.assertNotRegex(html, r'\$\{btn\.dataset\.name\}')
        self.assertNotRegex(html, r"data-name=\"\$\{detailsBtn[^}]*textContent\}\"")
        self.assertNotIn('${session.name}</button>', html)

    def test_responses_page_escapes_names(self):
        html = self.scripts('/registration/responses/')
        self.assertIn('function escapeHtml', html)
        self.assertNotRegex(html, r'\$\{btn\.dataset\.name\}')

    def test_registration_form_escapes_file_names(self):
        EventFormStatus.objects.create(is_published=True)
        html = self.client.get('/').content.decode()
        self.assertIn('function escapeHtml', html)
        self.assertNotIn('✓ ${file.name}', html)

    def test_hostile_name_is_escaped_in_the_tables(self):
        Form_Participant.objects.create(
            registration_type='participant', name='<img src=x onerror=alert(1)>', email='a@x.co', phone='1',
            university='<script>alert(2)</script>', department='cs', student_id='1', study_level='undergrad')
        html = self.scripts('/registration/responses/')
        self.assertNotIn('<img src=x onerror=alert(1)>', html)
        self.assertNotIn('<script>alert(2)</script>', html)


@override_settings(COMPETITION_REGISTRATION_OPEN=True)
class TeamMemberValidationTests(TestCase):
    def setUp(self):
        cache.clear()
        EventFormStatus.objects.create(is_published=True)
        patcher = patch('registration.views.send_registration_email', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse('registration:submit_form')

    def submit(self, **overrides):
        return self.client.post(self.url, team_payload(**overrides)).json()

    def test_every_member_of_the_team_needs_a_name_and_email(self):
        self.assertFalse(self.submit(mem3_email='')['success'])
        self.assertFalse(self.submit(mem2_name='')['success'])
        self.assertFalse(self.submit(total_members='2', mem2_email='')['success'])
        self.assertEqual(Form_Participant.objects.count(), 0)

    def test_team_emails_must_all_be_different(self):
        self.assertFalse(self.submit(mem2_email='LEAD@x.co')['success'])
        self.assertFalse(self.submit(mem3_email='two@x.co')['success'])
        self.assertEqual(Form_Participant.objects.count(), 0)

    def test_members_beyond_the_team_size_are_ignored(self):
        result = self.submit(total_members='2', mem3_name='Ghost', mem3_email='ghost@x.co')
        self.assertTrue(result['success'], result)
        team = Form_Participant.objects.get()
        self.assertEqual(team.mem2_email, 'two@x.co')
        self.assertFalse(team.mem3_name)
        self.assertFalse(team.mem3_email)

    def test_a_full_team_is_saved(self):
        self.assertTrue(self.submit()['success'])
        team = Form_Participant.objects.get()
        self.assertEqual((team.mem2_name, team.mem3_email), ('Two', 'three@x.co'))

    def test_only_the_selected_team_members_get_emails(self):
        sent = []
        with patch('registration.views.send_registration_email',
                   side_effect=lambda r, email, kind: sent.append(email) or True):
            self.submit(total_members='2', mem3_email='ghost@x.co', mem3_name='Ghost')
        self.assertEqual(sent, ['lead@x.co', 'two@x.co'])


@override_settings(COMPETITION_REGISTRATION_OPEN=True)
class AbstractUploadTests(TestCase):
    def setUp(self):
        cache.clear()
        EventFormStatus.objects.create(is_published=True)
        patcher = patch('registration.views.send_registration_email', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        override = override_settings(PROTECTED_ROOT=self.tmp.name)
        override.enable()
        self.addCleanup(override.disable)

    def submit(self, upload, **overrides):
        data = team_payload(total_members='2', **overrides)
        return self.client.post(reverse('registration:submit_form'), {**data, 'abstract_file': upload}).json()

    def test_a_renamed_file_is_not_accepted_as_a_pdf(self):
        result = self.submit(SimpleUploadedFile('abstract.pdf', b'MZ\x90\x00 not a pdf'))
        self.assertFalse(result['success'])
        self.assertIn('pdf', result['message'].lower())
        self.assertEqual(Form_Participant.objects.count(), 0)

    def test_a_real_pdf_is_stored_with_a_safe_name(self):
        result = self.submit(SimpleUploadedFile('Abstract.PDF', PDF), name='Ann ../ Lee')
        self.assertTrue(result['success'], result)
        stored = Form_Participant.objects.get().abstract_file
        self.assertTrue(stored.endswith('.pdf'))
        self.assertNotIn('/', stored)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, 'Abstracts', stored)))

    def test_registration_is_rolled_back_if_the_file_cannot_be_written(self):
        real_open = open

        def failing_open(path, mode='r', *args, **kwargs):
            if str(path).endswith('.pdf') and 'w' in mode:
                raise OSError('disk full')
            return real_open(path, mode, *args, **kwargs)

        with patch('registration.views.open', side_effect=failing_open, create=True):
            result = self.submit(SimpleUploadedFile('abstract.pdf', PDF))
        self.assertFalse(result['success'])
        self.assertEqual(Form_Participant.objects.count(), 0)  # nothing half-saved
        # so the same person can simply try again
        self.assertTrue(self.submit(SimpleUploadedFile('abstract.pdf', PDF))['success'])


class RateLimitBehindProxyTests(TestCase):
    def setUp(self):
        cache.clear()
        EventFormStatus.objects.create(is_published=True)
        patcher = patch('registration.views.send_registration_email', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, n, forwarded):
        payload = {'registration_type': 'participant', 'name': f'P{n}', 'email': f'p{n}@x.co', 'phone': '1',
                   'university': 'U', 'department': 'cs', 'student_id': '1', 'study_level': 'undergrad',
                   'membership_type': 'ieee', 'transaction_id': f'T{n}'}
        return self.client.post(reverse('registration:submit_form'), payload,
                                HTTP_X_FORWARDED_FOR=forwarded, REMOTE_ADDR='10.0.0.1').json()

    def test_visitors_behind_the_proxy_do_not_share_one_limit(self):
        with override_settings(TRUST_FORWARDED_FOR=True), patch('registration.views.SUBMIT_RATE_LIMIT', 2):
            self.assertTrue(self.post(1, '203.0.113.1')['success'])
            self.assertTrue(self.post(2, '203.0.113.1')['success'])
            self.assertFalse(self.post(3, '203.0.113.1')['success'])         # this visitor hit the limit
            self.assertTrue(self.post(4, '203.0.113.2')['success'])          # a different visitor is fine

    def test_forwarded_header_is_ignored_when_not_trusted(self):
        request = RequestFactory().get('/', HTTP_X_FORWARDED_FOR='203.0.113.9', REMOTE_ADDR='10.0.0.1')
        with override_settings(TRUST_FORWARDED_FOR=False):
            self.assertEqual(client_ip(request), '10.0.0.1')
        with override_settings(TRUST_FORWARDED_FOR=True):
            self.assertEqual(client_ip(request), '203.0.113.9')

    def test_garbage_in_the_forwarded_header_falls_back_to_the_connection_address(self):
        request = RequestFactory().get('/', HTTP_X_FORWARDED_FOR='not-an-ip', REMOTE_ADDR='10.0.0.1')
        with override_settings(TRUST_FORWARDED_FOR=True):
            self.assertEqual(client_ip(request), '10.0.0.1')


@override_settings(SECURE_SSL_REDIRECT=False)
class PermissionAndLandingTests(TestCase):
    def test_denied_pages_are_a_real_403(self):
        user = User.objects.create_user('nobody', password='pw')
        self.client.force_login(user)
        for url in ('/dashboard/', '/registration/admin/', '/registration/responses/', '/download-excel/'):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_each_kind_of_staff_lands_on_a_page_they_can_open(self):
        cases = [
            (('view_qr_dashboard',), 'core:dashboard'),
            (('reg_form_control',), 'registration:registration_admin'),
            (('view_reg_responses_list',), 'registration:response_table'),   # used to land on a denied dashboard
            (('view_qr_dashboard', 'reg_form_control'), 'core:dashboard'),
        ]
        for index, (codenames, expected) in enumerate(cases):
            user = User.objects.create_user(f'staff{index}', password='pw')
            grant(user, *codenames)
            self.assertEqual(Site_Permissions.landing_url_name(user), expected)
            self.client.logout()
            response = self.client.post('/login/', {'username': f'staff{index}', 'password': 'pw'})
            self.assertRedirects(response, reverse(expected), fetch_redirect_response=False)
            self.assertEqual(self.client.get(reverse(expected)).status_code, 200)

    def test_user_without_any_permission_is_told_so_not_bounced_around(self):
        user = User.objects.create_user('nobody', password='pw')
        self.assertIsNone(Site_Permissions.landing_url_name(user))
        response = self.client.post('/login/', {'username': 'nobody', 'password': 'pw'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/login/').status_code, 403)

    def test_the_public_form_page_also_uses_the_landing_page(self):
        user = User.objects.create_user('resp', password='pw')
        grant(user, 'view_reg_responses_list')
        self.client.force_login(user)
        self.assertRedirects(self.client.get('/'), reverse('registration:response_table'), fetch_redirect_response=False)


@override_settings(SECURE_SSL_REDIRECT=False)
class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        grant(User.objects.create_user('victim', password='right-password'), 'view_qr_dashboard')

    def test_repeated_wrong_passwords_are_blocked_then_the_right_one_works_for_others(self):
        for _ in range(8):
            self.assertEqual(self.client.post('/login/', {'username': 'victim', 'password': 'wrong'}).status_code, 200)
        blocked = self.client.post('/login/', {'username': 'victim', 'password': 'right-password'})
        self.assertEqual(blocked.status_code, 429)           # even the right password waits
        grant(User.objects.create_user('other', password='pw'), 'view_qr_dashboard')
        self.assertEqual(self.client.post('/login/', {'username': 'other', 'password': 'pw'}).status_code, 302)

    def test_a_successful_login_resets_the_counter(self):
        for _ in range(5):
            self.client.post('/login/', {'username': 'victim', 'password': 'wrong'})
        self.assertEqual(self.client.post('/login/', {'username': 'victim', 'password': 'right-password'}).status_code, 302)
        self.client.logout()
        for _ in range(5):
            self.assertEqual(self.client.post('/login/', {'username': 'victim', 'password': 'wrong'}).status_code, 200)


class ProtectedFileEdgeCaseTests(TestCase):
    def test_a_path_on_another_drive_is_a_404_not_a_crash(self):
        from django.http import Http404
        from system_administration.views import protected_serve
        admin = User.objects.create_superuser('root', password='pw')
        request = RequestFactory().get('/protected/x')
        request.user = admin
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            open(os.path.join(tmp, 'f.txt'), 'w').write('x')
            with override_settings(PROTECTED_ROOT=tmp), patch('os.path.commonpath', side_effect=ValueError('drives')):
                with self.assertRaises(Http404):
                    protected_serve(request, 'f.txt')


class DeploymentSettingsTests(TestCase):
    def test_https_redirect_is_opt_in(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ppis', 'settings.py'),
                      encoding='utf-8').read()
        self.assertIn("os.environ.get('SECURE_SSL_REDIRECT', '0') == '1'", source)


@override_settings(SECURE_SSL_REDIRECT=False)
class CompetitionAndPublishTests(TestCase):
    def setUp(self):
        cache.clear()
        EventFormStatus.objects.create(is_published=True)
        patcher = patch('registration.views.send_registration_email', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse('registration:submit_form')

    def participant(self, n=1):
        return {'registration_type': 'participant', 'name': f'P{n}', 'email': f'p{n}@x.co', 'phone': '1',
                'university': 'U', 'department': 'cs', 'student_id': '1', 'study_level': 'undergrad',
                'membership_type': 'ieee', 'transaction_id': f'T{n}'}

    # ---- team registrations
    def test_server_refuses_team_registrations_while_they_are_closed(self):
        self.assertFalse(settings.COMPETITION_REGISTRATION_OPEN)   # closed by default
        result = self.client.post(self.url, team_payload()).json()
        self.assertFalse(result['success'])
        self.assertIn('closed', result['message'].lower())
        self.assertEqual(Form_Participant.objects.count(), 0)

    def test_even_staff_cannot_post_a_team_while_closed(self):
        admin = User.objects.create_superuser('root', password='pw')
        self.client.force_login(admin)
        self.assertFalse(self.client.post(self.url, team_payload()).json()['success'])

    @override_settings(COMPETITION_REGISTRATION_OPEN=True)
    def test_teams_are_accepted_when_the_setting_is_on(self):
        self.assertTrue(self.client.post(self.url, team_payload()).json()['success'])

    def test_participants_are_not_affected_by_the_team_setting(self):
        self.assertTrue(self.client.post(self.url, self.participant()).json()['success'])

    def test_publish_switch_controls_public_form_and_submissions(self):
        status = EventFormStatus.objects.get()
        status.is_published = False
        status.save(update_fields=['is_published'])

        page = self.client.get('/').content.decode()
        self.assertNotIn('id="registrationForm"', page)
        result = self.client.post(self.url, self.participant()).json()
        self.assertFalse(result['success'])
        self.assertIn('closed', result['message'].lower())

        status.is_published = True
        status.save(update_fields=['is_published'])
        page = self.client.get('/').content.decode()
        self.assertIn('id="registrationForm"', page)
        self.assertTrue(self.client.post(self.url, self.participant()).json()['success'])

    # ---- team size and team names
    @override_settings(COMPETITION_REGISTRATION_OPEN=True)
    def test_solo_teams_are_rejected(self):
        result = self.client.post(self.url, team_payload(total_members='1', mem2_name='', mem2_email='',
                                                         mem3_name='', mem3_email='')).json()
        self.assertFalse(result['success'])
        self.assertIn('2 or 3', result['message'])
        self.assertNotIn('1', dict(Form_Participant.MEMBER_COUNT_CHOICES))

    @override_settings(COMPETITION_REGISTRATION_OPEN=True)
    def test_team_names_must_be_unique_ignoring_case(self):
        self.assertTrue(self.client.post(self.url, team_payload()).json()['success'])
        other = team_payload(name='Other', email='o@x.co', mem2_email='o2@x.co', mem3_email='o3@x.co', team_name='  volt ')
        result = self.client.post(self.url, other).json()
        self.assertFalse(result['success'])
        self.assertIn('already registered', result['message'])
        self.assertEqual(Form_Participant.objects.filter(registration_type='competition').count(), 1)
        other['team_name'] = 'Volt Two'
        self.assertTrue(self.client.post(self.url, other).json()['success'])

    def test_the_form_offers_only_teams_of_two_or_three(self):
        html = self.client.get('/').content.decode()
        select = html[html.index('id="totalMembersSelect"'):]
        select = select[:select.index('</select>')]
        self.assertIn('value="2"', select)
        self.assertIn('value="3"', select)
        self.assertNotIn('value="1"', select)
