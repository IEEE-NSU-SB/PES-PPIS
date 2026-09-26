# pip install ics
from datetime import datetime
from zoneinfo import ZoneInfo
from ics import Calendar, Event

# Bangladesh timezone
tz = ZoneInfo("Asia/Dhaka")

# Event details
event_name = "PPIS — Power Policy & Innovation Summit"
event_start = datetime(2026, 10, 23, 8, 30, tzinfo=tz)   # 8:30 AM Bangladesh time
event_end   = datetime(2026, 10, 31, 19, 0, tzinfo=tz)  # 7:00 PM Bangladesh time
event_location = "North South University, Dhaka, Bangladesh"
event_description = (
    "PPIS (Power Policy & Innovation Summit) — IEEE NSU PES SBC's flagship event bringing together "
    "students, young professionals, industry leaders, and policy experts to tackle Bangladesh's "
    "energy challenges through innovation and collaboration."
)
event_url = "https://www.facebook.com/ieeensupes"
uid = "ppis-2026@ieeensu.org"

# Create calendar and event
cal = Calendar()
ev = Event(
    name=event_name,
    begin=event_start,
    end=event_end,
    location=event_location,
    description=event_description,
    url=event_url,
    uid=uid,
    created=datetime.now(tz),
    last_modified=datetime.now(tz)
)

cal.events.add(ev)

# Serialize and write ICS file
ics_text = cal.serialize()
ics_text_crlf = ics_text.replace("\r\n", "\n").replace("\n", "\r\n")

out_path = './event.ics'
with open(out_path, "w", encoding="utf-8", newline="") as f:
    f.write(ics_text_crlf)

print("ICS written to:", out_path)
