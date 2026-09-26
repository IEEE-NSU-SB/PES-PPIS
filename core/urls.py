
from django.urls import path
from .views import *

app_name='core'

urlpatterns = [
    path('login/', login, name="login"),
    path('logout/', logout, name="logout"),
    path('dashboard/', dashboard, name='dashboard'),
    path('api/process_qr_data/', Process_QR_Data.as_view(), name="process_qr_data"),
    path('api/update_session/', SessionUpdateAjax.as_view(), name='update_session'),
    path('api/get_session_statuses/', GetSessionStatusAjax.as_view(), name="get_session_statuses"),
    path('api/update_participant_session/', UpdateParticipantSessionAjax.as_view(), name="update_participant_session"),
    # path('init/import_csv/', import_csv, name='import_csv'),
    path('init/gen_qr/', gen, name='gen_qr'),
    path('init/import_reg_participants/', import_reg_participants, name='import_reg_participants'),
    # path('init/set_increment_counter/', set_db_increment_counter),
    # path('init/update_db_serial/', update_db_serial)
]
