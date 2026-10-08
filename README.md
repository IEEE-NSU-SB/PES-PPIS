
## Acknowledgments  

This system was developed by the **IEEE NSU SB Website Development Team**, whose efforts made the event management process efficient and streamlined.  

---


## Key Features  

- **QR Code Generation**  
  Every participant receives a unique QR code to ensure secure and organized token management.  

- **QR Code Scanning**  
  Quickly scan QR codes during each session to validate and track token usage.  

- **Session-Based Management**  
  Seamlessly handles multiple sessions across the event for different food and goodies distributions.  

- **Data Tracking**  
  Keeps a real-time record of distributed food and goodies, ensuring no duplicates or errors in allocation.  

- **Efficiency and Speed**  
  Used by **190+ participants** across numerous sessions, significantly reducing manual effort and improving overall process efficiency.

- **Gmail API Integration**  
  - Automatically sends QR codes to all participants via email on api call.  
  - Provides a feature to resend the QR code to a provided email address if a participant cannot find their original email/QR code.

---

## Benefits  

- **Faster Queue Management**  
  Participants were served quickly without unnecessary delays.  

- **Accurate Tracking**  
  The system ensured a transparent count of distributed items, avoiding over-distribution or duplication.  

- **Streamlined Workflow**  
  Event organizers saved time and resources by automating the management process.  

---

## Technologies Used  

- **Backend**: Django (Python)  
- **Frontend**: HTML, CSS, JavaScript  
- **Database**: SQLite/MySQL  
- **QR Code Generation & Scanning**: QR code libraries (e.g., `qrcode`, `zxing`)  

---

## How It Works  

1. **Participant Registration**  
   - Each participant is registered in the system and assigned a unique QR code.  

2. **Session Scanning**  
   - QR codes are scanned at designated token distribution points.  
   - The system validates the QR code and logs the transaction.  

3. **Real-Time Updates**  
   - Organizers can view real-time statistics of distributed items for efficient inventory management.  


---

## Registration, Emails and Admin

**Registration form** (`/`, staff see the admin view at `/registration/admin/`)
- *General participant*: personal details and IEEE membership (IEEE BDT 600, non-IEEE BDT 750).
- *Competition (PPIS Policy Innovation Challenge)*: team leader, team of 1-3 members, track, project title and a PDF abstract (max 10 MB). The team currently pays nothing through the site.
- Staff can publish/unpublish the form. The same email cannot register twice for the same type.

**Confirmation emails** are sent through the Gmail API after registering: one email per registration, chosen by type (general participant, or competition for the leader and every teammate who gave an email). The text lives in `emails/templates/registration_email_*.html`.
Gmail must be authorised once by a superuser at `/init/authorise/`. If the Google app is in "Testing" mode the login expires after 7 days; publish the app to "In production" to avoid that.

**Responses** (`/registration/responses/`): Participants and Contestants tabs, Statistics (fees and totals, set in `REGISTRATION_FEES` in `ppis/settings.py`), Excel export and permanent delete.
Deleting a person removes them from both the registration responses and the QR dashboard (matched by email), together with their scan records, QR image and abstract.

**Admin** (`/admin/`): registrations (search, filters, team columns, abstract link), dashboard participants, sessions and scans, the single form on/off switch, a read-only error log, and users, roles and permissions. Deleting in the admin behaves like the delete buttons on the site.

**Permissions** (created automatically, tick them for a user or role under *Access Control*; superusers have all):
`view_qr_dashboard`, `scan_session`, `scan_any_session`, `update_session`, `reg_form_control`, `view_reg_responses_list`, `view_reg_response`, `view_finance_info`, `delete_participant`.

**Setup**
```
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then fill it in
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py test       # run the tests
```
