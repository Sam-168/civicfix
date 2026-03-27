# CivicFix AI — Setup & Run Guide

## Quick start (3 commands)

```bash
cd civicfix
pip install flask flask-cors
python app.py
```

Then open: http://localhost:5000

---

## Project structure

```
civicfix/
├── app.py              ← Flask backend (all API logic)
├── requirements.txt
├── data/
│   └── incidents.json  ← auto-created on first run (demo data seeded)
└── templates/
    ├── index.html      ← Landing page
    ├── report.html     ← Citizen report form
    └── dashboard.html  ← Admin dashboard + chatbot
```

---

## Pages

| URL | What it is |
|-----|-----------|
| `/` | Landing page — pitch-ready hero + features |
| `/report` | Citizen report form with GPS + AI classification |
| `/dashboard` | Admin: overview, incidents, map, analytics, chatbot |

---

## API endpoints

| Method | Endpoint | What it does |
|--------|----------|-------------|
| POST | `/api/submit` | Submit a citizen report, get AI classification |
| GET | `/api/incidents` | All incidents (sorted by priority) |
| GET | `/api/incidents/<id>` | Single incident detail |
| PATCH | `/api/incidents/<id>/status` | Update incident status |
| GET | `/api/stats` | Stats for dashboard cards + charts |

---

## How the AI works (no API key needed)

The classification is rule-based keyword matching — fast, free, demo-ready:

1. **Issue type detection** — scans description for keywords (leak, pipe → Water Leak, pothole, road → Pothole, etc.)
2. **Priority scoring** — keywords like "school", "hospital", "burst", "flooding" elevate priority
3. **Duplicate detection** — same issue type + within 150m + incident not resolved + within 72hrs → link to existing incident
4. **Auto-escalation** — 5+ duplicate reports → High, 10+ reports → Critical

To plug in OpenAI later: replace the `classify()` function in `app.py` with an API call.

---

## Demo scenario (for judges)

1. Go to `/report`
2. Click "📍 Detect" to capture location (or it uses Cape Town defaults)
3. Type: *"Burst pipe flooding the road near the primary school"*
4. Hit Submit — watch it classify as Water Leak, High/Critical priority
5. Submit again from same location — it detects duplicate and links reports
6. Go to `/dashboard` — see it at the top of the priority queue
7. Show the map view — incident pin grows with each report
8. Use the AI assistant: *"What needs urgent attention?"*

---

## Demo data

8 pre-seeded incidents across Cape Town covering all issue types and statuses. Located around the -33.92, 18.42 area.

---

## Pitch one-liner

*"CivicFix AI turns geolocated citizen complaints into prioritised municipal action."*
