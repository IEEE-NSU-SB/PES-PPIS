import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from access_ctrl.models import Permission, UserPermission
from core.models import Registered_Participant, Token_Participant, Token_Session
from core.renderData import Core
from registration.models import Form_Participant


class QRScanTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('root', password='pw')
        self.user = User.objects.create_user('vol', password='pw')
        self.participant = Registered_Participant.objects.create(name='A', unique_code='CODE123456789')
        self.session = Token_Session.objects.create(session_name='Lunch', is_active=True)
        self.url = '/api/process_qr_data/'

    def scan(self, code='CODE123456789', session_id=None):
        return self.client.post(
            self.url, data=json.dumps({'unqc': code}), content_type='application/json',
            headers={'session-id': str(session_id or self.session.id)})

    def test_requires_login_and_permission(self):
        self.assertEqual(self.scan().status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.scan().status_code, 404)
        self.assertEqual(Token_Participant.objects.count(), 0)

    def test_accept_then_reject_duplicate(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.scan().json()['status'], 'accepted')
        self.assertEqual(self.scan().json()['status'], 'rejected')
        self.assertEqual(Token_Participant.objects.count(), 1)

    def test_bad_inputs_return_error_not_crash(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.scan(code='nope').json()['status'], 'error')
        self.assertEqual(self.scan(session_id=9999).json()['status'], 'error')
        response = self.client.post(self.url, data='not json', content_type='application/json',
                                    headers={'session-id': str(self.session.id)})
        self.assertEqual(response.json()['status'], 'error')

    def test_update_participant_session(self):
        args = (self.participant.id, self.session.id)
        self.assertEqual(json.loads(Core.update_participant_session(*args, 'accepted').content)['message'], 'Accepted')
        self.assertIn('already', json.loads(Core.update_participant_session(*args, 'accepted').content)['message'])
        self.assertEqual(json.loads(Core.update_participant_session(*args, 'rejected').content)['message'], 'Rejected')
        self.assertIn('not in session', json.loads(Core.update_participant_session(*args, 'rejected').content)['message'])
        self.assertEqual(json.loads(Core.update_participant_session(*args, 'bogus').content)['message'], 'Invalid status')
        self.assertEqual(json.loads(Core.update_participant_session(9999, self.session.id, 'accepted').content)['message'],
                         'Invalid participant or session')

    def test_active_sessions_signature_changes(self):
        before = Core.active_sessions_signature()
        Core.update_session([])
        self.assertNotEqual(before, Core.active_sessions_signature())


class InitEndpointTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('root', password='pw')
        self.user = User.objects.create_user('u', password='pw')

    def test_init_endpoints_are_post_only_and_superuser_only(self):
        for url in ('/init/import_reg_participants/', '/init/gen_qr/'):
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get(url).status_code, 405)
            self.client.force_login(self.user)
            self.assertEqual(self.client.post(url).status_code, 404)

    def test_import_participants_dedupes_and_is_idempotent(self):
        for i, email in enumerate(['a@x.co', 'a@x.co', 'b@x.co']):
            Form_Participant.objects.create(
                registration_type='participant', name=f'P{i}', email=email, phone='1', university='U',
                department='cs', student_id=str(i), study_level='undergrad')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post('/init/import_reg_participants/').json()['message'], 'success')
        self.assertEqual(Registered_Participant.objects.count(), 2)
        self.client.post('/init/import_reg_participants/')
        self.assertEqual(Registered_Participant.objects.count(), 2)


@override_settings(SECURE_SSL_REDIRECT=False)
class LoginTests(TestCase):
    def setUp(self):
        User.objects.create_user('u', password='pw')

    def test_open_redirect_blocked(self):
        response = self.client.post('/login/?next=https://evil.example/', {'username': 'u', 'password': 'pw'})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('evil.example', response['Location'])

    def test_missing_fields_do_not_crash(self):
        self.assertEqual(self.client.post('/login/', {}).status_code, 200)


class DeleteParticipantTests(TestCase):
    def setUp(self):
        import os
        import tempfile
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.override = override_settings(PROTECTED_ROOT=self.tmp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        os.makedirs(os.path.join(self.tmp.name, 'Abstracts'))
        os.makedirs(os.path.join(self.tmp.name, 'Participant_QR'))

        self.admin = User.objects.create_superuser('root', password='pw')
        self.user = User.objects.create_user('u', password='pw')
        self.form = Form_Participant.objects.create(
            registration_type='competition', name='Ann', email='Ann@x.co', phone='1', university='U',
            department='cs', student_id='1', study_level='undergrad', abstract_file='1_Ann.pdf')
        self.other_form = Form_Participant.objects.create(
            registration_type='participant', name='Bob', email='bob@x.co', phone='1', university='U',
            department='cs', student_id='2', study_level='undergrad')
        self.reg = Registered_Participant.objects.create(name='Ann', email='ann@x.co', unique_code='AAAAAAAAAAAAA')
        self.other_reg = Registered_Participant.objects.create(name='Bob', email='bob@x.co', unique_code='BBBBBBBBBBBBB')
        self.session = Token_Session.objects.create(session_name='Lunch')
        Token_Participant.objects.create(registered_participant=self.reg, token_session=self.session)
        self.abstract = os.path.join(self.tmp.name, 'Abstracts', '1_Ann.pdf')
        self.qr = os.path.join(self.tmp.name, 'Participant_QR', f'{self.reg.id}.png')
        for path in (self.abstract, self.qr):
            open(path, 'wb').write(b'x')

    def assert_ann_gone_bob_kept(self):
        import os
        self.assertFalse(Form_Participant.objects.filter(name='Ann').exists())
        self.assertFalse(Registered_Participant.objects.filter(name='Ann').exists())
        self.assertEqual(Token_Participant.objects.count(), 0)
        self.assertFalse(os.path.exists(self.abstract))
        self.assertFalse(os.path.exists(self.qr))
        self.assertTrue(Form_Participant.objects.filter(name='Bob').exists())
        self.assertTrue(Registered_Participant.objects.filter(name='Bob').exists())

    def test_delete_from_dashboard_removes_response_too(self):
        self.client.force_login(self.admin)
        response = self.client.post('/api/delete_participant/', json.dumps({'participant_id': self.reg.id}),
                                    content_type='application/json')
        self.assertEqual(response.json()['message'], 'success')
        self.assert_ann_gone_bob_kept()

    def test_delete_from_response_removes_dashboard_entry_too(self):
        self.client.force_login(self.admin)
        response = self.client.post(f'/registration/response/{self.form.id}/delete/')
        self.assertEqual(response.json()['message'], 'success')
        self.assert_ann_gone_bob_kept()

    def test_requires_permission_and_post(self):
        self.client.force_login(self.user)
        body = json.dumps({'participant_id': self.reg.id})
        self.assertEqual(self.client.post('/api/delete_participant/', body, content_type='application/json').status_code, 403)
        self.assertNotIn(b'"success"', self.client.post(f'/registration/response/{self.form.id}/delete/').content)
        self.assertEqual(Registered_Participant.objects.count(), 2)
        self.assertEqual(Form_Participant.objects.count(), 2)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/delete_participant/').status_code, 405)

    def test_granted_permission_allows_delete(self):
        perm = Permission.objects.create(name='Delete', codename='delete_participant')
        UserPermission.objects.create(user=self.user).permissions.add(perm)
        self.client.force_login(self.user)
        response = self.client.post('/api/delete_participant/', json.dumps({'participant_id': self.reg.id}),
                                    content_type='application/json')
        self.assertEqual(response.json()['message'], 'success')

    def test_unknown_and_invalid_ids(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post('/api/delete_participant/', json.dumps({'participant_id': 9999}),
                                          content_type='application/json').status_code, 404)
        self.assertEqual(self.client.post('/api/delete_participant/', json.dumps({'participant_id': 'x'}),
                                          content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post('/registration/response/9999/delete/').status_code, 404)

    def test_pages_show_delete_buttons_only_with_permission(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/registration/responses/'), 'Delete</button>')
        self.assertContains(self.client.get('/dashboard/'), 'delete_participant')
        perm = Permission.objects.create(name='V', codename='view_reg_responses_list')
        perm2 = Permission.objects.create(name='D', codename='view_qr_dashboard')
        up = UserPermission.objects.create(user=self.user)
        up.permissions.add(perm, perm2)
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get('/registration/responses/'), 'Delete</button>')
        self.assertNotContains(self.client.get('/dashboard/'), 'delete_participant')
