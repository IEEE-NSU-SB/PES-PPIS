from django.db import migrations

# Every permission the site checks. Creating them here means they exist on every install
# (they used to be created by hand in the admin) and can simply be ticked for users and roles.
PERMISSIONS = [
    ('view_qr_dashboard', 'View QR dashboard', 'See the dashboard with participants and session scans.'),
    ('scan_session', 'Scan sessions', 'Scan QR codes / tick participants for active sessions.'),
    ('scan_any_session', 'Scan any session', 'Scan for any session, including inactive ones.'),
    ('update_session', 'Update sessions', 'Choose which sessions are active.'),
    ('reg_form_control', 'Registration form control',
     'Open the registration admin view, publish/unpublish the form and download the Excel export.'),
    ('view_reg_responses_list', 'View responses list', 'See the registration responses tables.'),
    ('view_reg_response', 'View a response', 'Open a single registration response and its abstract file.'),
    ('view_finance_info', 'View statistics', 'See registration statistics (fees and totals).'),
    ('delete_participant', 'Delete participants',
     'Permanently delete a participant from the dashboard and the registration responses.'),
]


def seed_permissions(apps, schema_editor):
    Permission = apps.get_model('access_ctrl', 'Permission')
    for codename, name, description in PERMISSIONS:
        Permission.objects.get_or_create(codename=codename, defaults={'name': name, 'description': description})


class Migration(migrations.Migration):

    dependencies = [
        ('access_ctrl', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_permissions, migrations.RunPython.noop),
    ]
