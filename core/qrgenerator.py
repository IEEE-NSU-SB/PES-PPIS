
# Importing library
import json
import os
import qrcode
from django.conf import settings

from core.models import Registered_Participant


def generate_qr():

    output_folder = os.path.join(settings.PROTECTED_ROOT, "Participant_QR")

    # Make sure the folder exists
    os.makedirs(output_folder, exist_ok=True)  # ✅ creates folder if it doesn't exist

    data_list = Registered_Participant.objects.all().order_by('id').values_list('unique_code','id')

    # Iterating over the data list
    for i, data in enumerate(data_list, start=1):
        # Encoding data using make() function
        img = qrcode.make(json.dumps({"unqc":data[0]}))
    
        # Saving each QR code as an image file
        img.save(os.path.join(output_folder, f'{data[1]}.png'))
