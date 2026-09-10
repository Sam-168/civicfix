# CivicFix AI

CivicFix AI is a Flask web application that turns geolocated citizen reports into prioritised municipal action. Citizens can report local faults, while municipal administrators can monitor incidents, identify chronic hotspots, and update service-delivery progress.

**Live application:** [civicfix-ten.vercel.app](https://civicfix-ten.vercel.app)

**Maintained by:** [Sam-168](https://github.com/Sam-168)

**Repository:** [Sam-168/civicfix](https://github.com/Sam-168/civicfix)

**Forked from:** [AvuzwaMtsolongo/civicfix](https://github.com/AvuzwaMtsolongo/civicfix)

## Features

- Citizen and municipal-administrator access
- Geolocated civic issue reporting
- Image-assisted or text-based issue classification
- Automatic department and priority assignment
- Duplicate detection within 150 metres and 72 hours
- Priority escalation as related reports accumulate
- Incident status tracking
- Dashboard statistics, chronic hotspots, and recommended actions
- Twelve seeded Cape Town incidents for demonstrations

## Technology

- Python and Flask
- Jinja templates
- Flask-CORS
- OpenAI API integration with a rule-based fallback
- JSON-backed demo storage
- Vercel deployment

## Run locally

~~~bash
git clone https://github.com/Sam-168/civicfix.git
cd civicfix
python -m venv .venv
pip install -r requirements.txt
python app.py
~~~

Open [http://localhost:5000](http://localhost:5000).

## Environment variables

| Variable | Required | Purpose |
|---|---:|---|
| SECRET_KEY | Production | Signs Flask session cookies. Use a long, random value. |
| ADMIN_EMAILS | For admin access | Comma-separated email addresses permitted to sign in as administrators. |
| OPENAI_API_KEY | No | Enables OpenAI-assisted classification. The rule-based classifier is used when omitted or unavailable. |
| DATA_FILE | No | Overrides the JSON data-file location. |

Do not commit real secrets or a local .env file to the repository.

## Application pages

| Route | Purpose |
|---|---|
| / | Public landing page |
| /login | User or administrator sign-in |
| /home | Citizen home page |
| /report | Citizen report form |
| /my-reports | Reports submitted by the signed-in citizen |
| /dashboard | Administrator analytics dashboard |
| /incidents | Administrator incident management |

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /api/submit | Submit and classify a citizen report |
| GET | /api/my-reports | List reports for the signed-in citizen |
| GET | /api/incidents | List incidents by priority |
| PATCH | /api/incidents/<inc_id>/status | Update an incident's status |
| GET | /api/stats | Return dashboard statistics |
| GET | /api/chronic-hotspots | Identify recurring issue hotspots |
| GET | /api/action-recommendations | Generate prioritised municipal actions |

## Classification

When OPENAI_API_KEY is configured, CivicFix can classify reports using text and an optional uploaded image. If the API is unavailable, the application automatically falls back to local keyword rules.

The classifier determines:

1. Issue type
2. Responsible municipal department
3. Priority level
4. A short classification reason

Duplicate reports are linked when they describe the same issue type within 150 metres and 72 hours. Five or more reports raise an incident to High priority; ten or more raise it to Critical.

## Deploying to Vercel

Vercel detects the root app.py file and Flask dependency automatically.

1. Import [Sam-168/civicfix](https://github.com/Sam-168/civicfix) into Vercel.
2. Keep the Flask preset and root directory ./.
3. Configure SECRET_KEY and ADMIN_EMAILS.
4. Optionally configure OPENAI_API_KEY.
5. Deploy the main branch.

### Demo-storage limitation

Vercel Functions cannot write to the deployed project filesystem. On Vercel, CivicFix writes demo changes to /tmp/civicfix/incidents.json and initializes from the bundled seed data.

This storage is intentionally temporary: reports and status updates can reset when a function instance is recycled or the project is redeployed. Replace the JSON file with a hosted database such as PostgreSQL before using the application for persistent production data.

## Demo

1. Sign in as a citizen.
2. Report: “Burst pipe flooding the road near the primary school.”
3. CivicFix classifies and prioritises the issue.
4. Submit a nearby matching report to demonstrate duplicate linking.
5. Sign in as an administrator to review the dashboard, hotspots, and recommended actions.

## License and attribution

This repository is maintained in the [Sam-168](https://github.com/Sam-168) GitHub account and was forked from [AvuzwaMtsolongo/civicfix](https://github.com/AvuzwaMtsolongo/civicfix). Review the upstream repository for its original history and licensing terms.
