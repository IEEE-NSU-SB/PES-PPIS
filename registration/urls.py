from django.urls import path

from .views import *

app_name='registration'
urlpatterns = [
    # Public/user registration form (only visible when published)
    path('', registration_form, name='registration_form'),
    # Staff-only admin view of the form and controls
    path('reg/', registration_redirect, name="registration_redirect"),
    path('registration/admin/', registration_admin, name='registration_admin'),
    # Publish toggle endpoint (staff-only)
    path('registration/toggle-publish/', toggle_publish, name='toggle_publish'),
    path('registration/responses/', response_table, name='response_table'),
    path('registration/response/<int:id>/', view_response, name='view_response'),
    path('registration/response/<int:id>/delete/', delete_response, name='delete_response'),
    path('submit-form/', submit_form, name='submit_form'),
    path('download-excel/', download_excel, name='download_excel'),

]   