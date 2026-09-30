import os
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings

from emails import views


class GetCredentialsTests(TestCase):
    @override_settings(GOOGLE_CLOUD_TOKEN=None)
    def test_no_token_returns_none(self):
        self.assertIsNone(views.get_credentials())

    @override_settings(GOOGLE_CLOUD_TOKEN='tok', GOOGLE_CLOUD_REFRESH_TOKEN=None, GOOGLE_CLOUD_EXPIRY=None,
                       GOOGLE_CLOUD_TOKEN_URI='https://oauth2.googleapis.com/token',
                       GOOGLE_CLOUD_CLIENT_ID='cid', GOOGLE_CLOUD_CLIENT_SECRET='sec', SCOPES=['scope'])
    def test_missing_expiry_setting_does_not_crash(self):
        # Regression: settings.GOOGLE_CLOUD_EXPIRY used to be undefined after a restart -> AttributeError
        creds = views.get_credentials()
        self.assertTrue(creds is None or creds.token == 'tok')


class SendRegistrationEmailTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/')

    def test_returns_false_when_reauthorisation_needed(self):
        with patch.object(views, 'get_credentials', return_value=None):
            self.assertIs(views.send_registration_email(self.request, 'A', 'a@example.com'), False)

    def test_returns_false_for_invalid_address(self):
        self.assertIs(views.send_registration_email(self.request, 'A', 'bad\nBcc: x@y.z'), False)

    def test_returns_true_on_success(self):
        service = MagicMock()
        service.users().messages().send().execute.return_value = {'id': '1'}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, override_settings(MEDIA_ROOT=tmp):
            with open(os.path.join(tmp, 'event.ics'), 'wb') as f:
                f.write(b'BEGIN:VCALENDAR')
            with patch.object(views, '_build_service', return_value=service):
                self.assertIs(views.send_registration_email(self.request, 'A', 'a@example.com'), True)

    def test_returns_false_when_gmail_fails(self):
        with patch.object(views, '_build_service', side_effect=RuntimeError('boom')):
            self.assertIs(views.send_registration_email(self.request, 'A', 'a@example.com'), False)

    def test_bundled_ics_exists_in_media_root(self):
        from django.conf import settings
        self.assertTrue(os.path.isfile(os.path.join(settings.MEDIA_ROOT, 'event.ics')))


@override_settings(SECURE_SSL_REDIRECT=False)
class EmailEndpointPermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u', password='pw')
        self.admin = User.objects.create_superuser('root', password='pw')

    def test_send_email_requires_permission(self):
        self.client.force_login(self.user)
        with patch.object(views, '_build_service') as build:
            response = self.client.post('/api/send_email/', data='{"emailAddr":"a@b.co","participant_id":1}',
                                        content_type='application/json')
        self.assertEqual(response.status_code, 404)
        build.assert_not_called()

    def test_send_email_rejects_traversal_and_bad_email(self):
        self.client.force_login(self.admin)
        for body in ('{"emailAddr":"a@b.co","participant_id":"../../x"}', '{"emailAddr":"nope","participant_id":1}', 'x'):
            response = self.client.post('/api/send_email/', data=body, content_type='application/json')
            self.assertIn('Invalid', response.json()['message'])

    def test_send_email_is_post_only(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/send_email/').status_code, 405)

    def test_authorize_superuser_only(self):
        self.client.force_login(self.user)
        with patch.object(views, 'get_credentials') as creds:
            self.client.get('/init/authorise/')
        creds.assert_not_called()
        self.client.get('/init/oauth2callback/')  # must not raise
