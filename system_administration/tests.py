import os
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from access_ctrl.models import Permission, UserPermission


@override_settings(SECURE_SSL_REDIRECT=False)
class ProtectedServeTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, 'Participant Files')
        os.makedirs(os.path.join(self.root, 'Abstracts'))
        os.makedirs(os.path.join(self.root, 'Participant_QR'))
        with open(os.path.join(self.root, 'Abstracts', 'a.pdf'), 'wb') as f:
            f.write(b'abstract')
        with open(os.path.join(self.root, 'Participant_QR', '1.png'), 'wb') as f:
            f.write(b'png')
        with open(os.path.join(self.root, 'secret.txt'), 'wb') as f:
            f.write(b'secret')
        # A file *outside* the protected root that must never be reachable
        with open(os.path.join(self.tmp.name, 'outside.txt'), 'wb') as f:
            f.write(b'outside')
        self.settings_override = override_settings(PROTECTED_ROOT=self.root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.user = User.objects.create_user('u', password='pw')
        self.admin = User.objects.create_superuser('root', password='pw')

    def grant(self, codename):
        perm = Permission.objects.create(name=codename, codename=codename)
        up = UserPermission.objects.create(user=self.user)
        up.permissions.add(perm)

    def test_anonymous_denied(self):
        self.assertEqual(self.client.get('/protected/Abstracts/a.pdf').status_code, 403)

    def test_user_without_permission_denied(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/protected/Abstracts/a.pdf').status_code, 403)
        self.assertEqual(self.client.get('/protected/Participant_QR/1.png').status_code, 403)

    def test_folder_permissions(self):
        self.grant('view_reg_response')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/protected/Abstracts/a.pdf').status_code, 200)
        self.assertEqual(self.client.get('/protected/Participant_QR/1.png').status_code, 403)

    def test_unlisted_files_superuser_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/protected/secret.txt').status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/protected/secret.txt').status_code, 200)

    def test_path_traversal_blocked(self):
        self.client.force_login(self.admin)
        for path in ('../outside.txt', 'Abstracts/../../outside.txt', '..%2Foutside.txt', '/etc/passwd'):
            response = self.client.get('/protected/' + path)
            self.assertIn(response.status_code, (301, 302, 400, 404), path)
        # Raw (un-normalised) traversal straight to the view
        from system_administration.views import protected_serve
        from django.http import Http404
        from django.test import RequestFactory
        request = RequestFactory().get('/protected/x')
        request.user = self.admin
        with self.assertRaises(Http404):
            protected_serve(request, '../outside.txt')
        with self.assertRaises(Http404):
            protected_serve(request, 'Abstracts/../../outside.txt')
