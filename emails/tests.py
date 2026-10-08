import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings

from emails import views


# Point the token file at a path that does not exist, so tests never read the real .env or call Google
NO_ENV_FILE = override_settings(ENV_FILE=Path(tempfile.gettempdir()) / 'ppis-tests-no-such.env')


@NO_ENV_FILE
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
            self.assertIs(views.send_registration_email(self.request, 'a@example.com', 'participant'), False)

    def test_returns_false_for_invalid_address(self):
        self.assertIs(views.send_registration_email(self.request, 'bad\nBcc: x@y.z', 'participant'), False)

    def send_and_read(self, registration_type):
        import base64
        from email import message_from_bytes
        service = MagicMock()
        with patch.object(views, '_build_service', return_value=service):
            self.assertIs(views.send_registration_email(self.request, 'a@example.com', registration_type), True)
        calls = service.users().messages().send.call_args_list
        messages = [message_from_bytes(base64.urlsafe_b64decode(c.kwargs['body']['raw'])) for c in calls]
        bodies = [m.get_payload()[0].get_payload(decode=True).decode() for m in messages]
        return messages, bodies

    def test_participant_gets_only_the_participant_email(self):
        messages, bodies = self.send_and_read('participant')
        self.assertEqual(len(messages), 1)  # exactly one email
        self.assertEqual(messages[0]['Subject'], 'PPIS Registration Confirmation')
        self.assertEqual(messages[0]['To'], 'a@example.com')
        self.assertIn('Dear Participant,', bodies[0])
        self.assertIn('31 October 2026', bodies[0])
        self.assertIn('quiz competition', bodies[0])
        self.assertNotIn('Dear Innovator', bodies[0])
        self.assertIn('ieeensu.pessbc@gmail.com', bodies[0])
        self.assertEqual(len(messages[0].get_payload()), 1)  # no attachments

    def test_competitor_gets_only_the_innovator_email(self):
        messages, bodies = self.send_and_read('competition')
        self.assertEqual(len(messages), 1)  # exactly one email
        self.assertEqual(messages[0]['Subject'], 'PPIS Policy Innovation Challenge Registration Confirmation')
        self.assertIn('Dear Innovator,', bodies[0])
        self.assertIn('complete competition guidelines', bodies[0])
        self.assertNotIn('Dear Participant', bodies[0])
        self.assertNotIn('quiz competition', bodies[0])
        self.assertIn('ieeensu.pessbc@gmail.com', bodies[0])
        self.assertEqual(len(messages[0].get_payload()), 1)  # no attachments

    def test_unknown_registration_type_sends_nothing(self):
        service = MagicMock()
        with patch.object(views, '_build_service', return_value=service):
            self.assertIs(views.send_registration_email(self.request, 'a@example.com', 'bogus'), False)
        service.users().messages().send.assert_not_called()

    def test_returns_false_when_gmail_fails(self):
        with patch.object(views, '_build_service', side_effect=RuntimeError('boom')):
            self.assertIs(views.send_registration_email(self.request, 'a@example.com', 'participant'), False)

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


@NO_ENV_FILE
@override_settings(SECURE_SSL_REDIRECT=False)
class AuthorisationFlowTests(TestCase):
    def test_authorise_redirects_to_google_for_superuser(self):
        admin = User.objects.create_superuser('root', password='pw')
        self.client.force_login(admin)
        with override_settings(GOOGLE_CLOUD_TOKEN=None, GOOGLE_CLOUD_CLIENT_ID='cid.apps.googleusercontent.com',
                               GOOGLE_CLOUD_CLIENT_SECRET='sec', GOOGLE_CLOUD_PROJECT_ID='proj',
                               GOOGLE_CLOUD_AUTH_URI='https://accounts.google.com/o/oauth2/auth',
                               GOOGLE_CLOUD_TOKEN_URI='https://oauth2.googleapis.com/token',
                               GOOGLE_CLOUD_AUTH_PROVIDER_X509_CERT_URL='https://www.googleapis.com/oauth2/v1/certs',
                               SCOPES=['https://mail.google.com/']):
            response = self.client.get('/init/authorise/', HTTP_HOST='127.0.0.1:8000')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('https://accounts.google.com/o/oauth2/auth'))
        self.assertIn('redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Finit%2Foauth2callback', response['Location'])


class StaleEnvironmentTests(TestCase):
    def test_tokens_are_read_from_env_file_not_stale_process_settings(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            (Path(tmp) / '.env').write_text('GOOGLE_CLOUD_TOKEN=fresh-token\nGOOGLE_CLOUD_REFRESH_TOKEN=fresh-refresh\n')
            with override_settings(ENV_FILE=Path(tmp) / '.env', GOOGLE_CLOUD_TOKEN='stale-token',
                                   GOOGLE_CLOUD_REFRESH_TOKEN='stale-refresh', GOOGLE_CLOUD_EXPIRY=None):
                tokens = views._stored_google_tokens()
        self.assertEqual(tokens['token'], 'fresh-token')
        self.assertEqual(tokens['refresh_token'], 'fresh-refresh')

    def test_falls_back_to_settings_without_env_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            with override_settings(ENV_FILE=Path(tmp) / '.env', GOOGLE_CLOUD_TOKEN='from-settings',
                                   GOOGLE_CLOUD_REFRESH_TOKEN='r', GOOGLE_CLOUD_EXPIRY=None):
                self.assertEqual(views._stored_google_tokens()['token'], 'from-settings')
