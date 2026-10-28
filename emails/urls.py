
from django.urls import path
from .views import *

app_name='emails'

urlpatterns = [
    path('init/send_emails/', send_emails, name='send_bulk_emails'),
    path('api/send_email/', send_email, name='send_email'),
    path('init/authorise/', authorize),
    path('init/oauth2callback/', oauth2callback, name='oauth2callback'),
    
]
