import os
import tempfile

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from access_ctrl.models import Permission
from core.models import Registered_Participant, Token_Participant, Token_Session
from registration.models import EventFormStatus, Form_Participant
from system_administration.models import ErrorLog

SITE_PERMISSIONS = {
    'view_qr_dashboard', 'scan_session', 'scan_any_session', 'update_session', 'reg_form_control',
    'view_reg_responses_list', 'view_reg_response', 'view_finance_info', 'delete_participant',
}


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('root', password='pw')
        base = dict(phone='1', university='NSU', department='cs', student_id='1', study_level='undergrad')
        cls.person = Form_Participant.objects.create(
            registration_type='participant', name='Ann', email='ann@x.co', membership_type='ieee', **base)
        cls.team = Form_Participant.objects.create(
            registration_type='competition', name='Lead', email='lead@x.co', team_name='Volt', total_members='3',
            ieee_id='I-1', track='track_a', project_title='Grid', abstract_file='2_Lead.pdf',
            mem2_name='Two', mem2_email='two@x.co', **base)
        cls.reg = Registered_Participant.objects.create(name='Ann', email='ann@x.co', unique_code='AAAAAAAAAAAAA')
        cls.session = Token_Session.objects.create(session_name='Lunch')
        Token_Participant.objects.create(registered_participant=cls.reg, token_session=cls.session)
        EventFormStatus.objects.create(is_published=True)
        ErrorLog.objects.create(exception_type='RefreshError', message='boom', traceback='tb')

    def setUp(self):
        self.client.force_login(self.admin)

    def test_every_registered_admin_page_loads(self):
        models = [m for m in admin.site._registry if m._meta.app_label in
                  ('registration', 'core', 'access_ctrl', 'system_administration', 'auth')]
        self.assertGreater(len(models), 8)
        for model in models:
            info = (model._meta.app_label, model._meta.model_name)
            url = reverse('admin:%s_%s_changelist' % info)
            self.assertEqual(self.client.get(url).status_code, 200, url)
            obj = model.objects.first()
            if obj:
                response = self.client.get(reverse('admin:%s_%s_change' % info, args=[obj.pk]))
                self.assertEqual(response.status_code, 200, f'{model} change page')

    def test_site_permissions_are_seeded(self):
        self.assertEqual(set(Permission.objects.values_list('codename', flat=True)) & SITE_PERMISSIONS, SITE_PERMISSIONS)

    def test_registration_admin_search_and_filters(self):
        url = reverse('admin:registration_form_participant_changelist')
        response = self.client.get(url, {'q': 'Volt'})
        self.assertContains(response, 'Lead')
        self.assertNotContains(response, '>Ann<')
        response = self.client.get(url, {'registration_type__exact': 'participant'})
        self.assertContains(response, 'Ann')
        self.assertNotContains(response, 'Volt')
        self.assertEqual(self.client.get(url, {'total_members__exact': '3', 'track__exact': 'track_a'}).status_code, 200)

    def test_registration_admin_shows_team_columns(self):
        html = self.client.get(reverse('admin:registration_form_participant_changelist')).content.decode()
        for text in ('Team of', 'IEEE ID', 'Team name', 'Registrations'):
            self.assertIn(text, html, text)

    def test_expected_404_and_403_are_not_logged_as_errors(self):
        before = ErrorLog.objects.count()
        self.client.get('/protected/Abstracts/missing.pdf')            # Http404
        self.client.get(reverse('admin:system_administration_errorlog_add'))  # PermissionDenied
        self.assertEqual(ErrorLog.objects.count(), before)

    def test_deleting_in_admin_removes_the_matching_dashboard_entry_and_files(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            os.makedirs(os.path.join(tmp, 'Participant_QR'))
            qr = os.path.join(tmp, 'Participant_QR', f'{self.reg.id}.png')
            open(qr, 'wb').write(b'x')
            with override_settings(PROTECTED_ROOT=tmp):
                url = reverse('admin:registration_form_participant_delete', args=[self.person.pk])
                self.assertEqual(self.client.post(url, {'post': 'yes'}).status_code, 302)
            self.assertFalse(os.path.exists(qr))
        self.assertFalse(Form_Participant.objects.filter(pk=self.person.pk).exists())
        self.assertFalse(Registered_Participant.objects.filter(pk=self.reg.pk).exists())
        self.assertEqual(Token_Participant.objects.count(), 0)
        self.assertTrue(Form_Participant.objects.filter(pk=self.team.pk).exists())  # others untouched

    def test_bulk_delete_action_in_admin_cascades_too(self):
        url = reverse('admin:registration_form_participant_changelist')
        response = self.client.post(url, {'action': 'delete_selected', '_selected_action': [self.person.pk],
                                          'post': 'yes'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Registered_Participant.objects.filter(pk=self.reg.pk).exists())

    def test_deleting_a_dashboard_participant_in_admin_removes_the_response(self):
        url = reverse('admin:core_registered_participant_delete', args=[self.reg.pk])
        self.client.post(url, {'post': 'yes'})
        self.assertFalse(Form_Participant.objects.filter(pk=self.person.pk).exists())

    def test_unique_code_is_read_only_for_existing_participants(self):
        response = self.client.get(reverse('admin:core_registered_participant_change', args=[self.reg.pk]))
        self.assertNotContains(response, 'name="unique_code"')
        response = self.client.get(reverse('admin:core_registered_participant_add'))
        self.assertContains(response, 'name="unique_code"')

    def test_event_form_status_is_a_single_row(self):
        self.assertEqual(self.client.get(reverse('admin:registration_eventformstatus_add')).status_code, 403)
        status = EventFormStatus.objects.get()
        self.assertEqual(
            self.client.get(reverse('admin:registration_eventformstatus_delete', args=[status.pk])).status_code, 403)
        self.assertContains(self.client.get(reverse('admin:registration_eventformstatus_changelist')),
                            'Published (open)')

    def test_error_log_is_read_only(self):
        self.assertEqual(self.client.get(reverse('admin:system_administration_errorlog_add')).status_code, 403)
        entry = ErrorLog.objects.get()
        response = self.client.get(reverse('admin:system_administration_errorlog_change', args=[entry.pk]))
        self.assertContains(response, 'RefreshError')
        self.assertNotContains(response, 'name="message"')
