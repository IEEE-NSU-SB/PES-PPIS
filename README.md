
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
