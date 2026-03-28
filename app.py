from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
from functools import wraps
from dotenv import load_dotenv
from openai import OpenAI
import json, uuid, math, datetime, os
from pathlib import Path

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "civicfix-super-secret-key")
CORS(app)

DATA_FILE = Path("data/incidents.json")
DATA_FILE.parent.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

def get_admin_emails():
    raw = os.getenv("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def load_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"incidents": [], "reports": []}

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2, default=str))

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def current_user():
    return {
        "email": session.get("email"),
        "role": session.get("role"),
        "name": session.get("name", "User")
    }

def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "email" not in session:
                return redirect(url_for("login_page"))
            if role and session.get("role") != role:
                if session.get("role") == "admin":
                    return redirect(url_for("dashboard_page"))
                return redirect(url_for("user_home"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# ─────────────────────────────────────────────────────────────
# RULE-BASED CLASSIFICATION
# ─────────────────────────────────────────────────────────────

ISSUE_RULES = [
    ("Water Leak", ["leak", "pipe", "burst", "flood", "water", "flowing", "dripping", "sewage", "drain"]),
    ("Pothole", ["pothole", "hole", "road", "crack", "tarmac", "asphalt", "bump", "dip"]),
    ("Electricity Outage", ["electricity", "power", "outage", "blackout", "light", "electric", "cable", "pylon"]),
    ("Waste Collection", ["waste", "rubbish", "trash", "garbage", "bin", "litter", "refuse", "dump"]),
    ("Broken Streetlight", ["streetlight", "street light", "lamp", "lamppost", "dark", "broken light"]),
]

DEPT_MAP = {
    "Water Leak": "Water & Sanitation",
    "Pothole": "Roads & Transport",
    "Electricity Outage": "Electricity Department",
    "Waste Collection": "Waste Management",
    "Broken Streetlight": "Public Lighting",
}

PRIORITY_KEYWORDS = {
    "Critical": ["hospital", "school", "clinic", "main road", "highway", "fire", "emergency", "flooding"],
    "High": ["burst", "leak", "outage", "blackout", "flood", "unsafe", "danger", "junction"],
    "Medium": ["road", "street", "area", "neighbourhood"],
    "Low": [],
}

def classify_rules(description):
    text = (description or "").lower()
    issue_type = "General Issue"

    for label, keywords in ISSUE_RULES:
        if any(k in text for k in keywords):
            issue_type = label
            break

    priority = "Low"
    for level, keywords in PRIORITY_KEYWORDS.items():
        if any(k in text for k in keywords):
            priority = level
            break

    if priority == "Low" and issue_type in ("Water Leak", "Electricity Outage"):
        priority = "Medium"

    return {
        "issue_type": issue_type,
        "department": DEPT_MAP.get(issue_type, "General Services"),
        "priority": priority,
        "reason": "Classified using rule-based keyword matching.",
        "source": "rules"
    }

# ─────────────────────────────────────────────────────────────
# OPENAI + FALLBACK
# ─────────────────────────────────────────────────────────────

def classify_openai(description, image_base64=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        client = OpenAI(api_key=api_key)

        content = [
            {
                "type": "text",
                "text": f"""
You are classifying a municipal service issue.

Return strict JSON with:
issue_type, department, priority, reason

Allowed issue_type values:
Water Leak, Pothole, Electricity Outage, Waste Collection, Broken Streetlight, General Issue

Allowed department values:
Water & Sanitation, Roads & Transport, Electricity Department, Waste Management, Public Lighting, General Services

Allowed priority values:
Low, Medium, High, Critical

User description:
{description}
"""
            }
        ]

        if image_base64:
            content.append({
                "type": "image_url",
                "image_url": {"url": image_base64}
            })

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": content}]
        )

        parsed = json.loads(response.choices[0].message.content)

        return {
            "issue_type": parsed.get("issue_type", "General Issue"),
            "department": parsed.get("department", "General Services"),
            "priority": parsed.get("priority", "Medium"),
            "reason": parsed.get("reason", "AI-assisted classification."),
            "source": "openai"
        }
    except Exception:
        return None

def classify_issue(description, image_base64=None):
    ai = classify_openai(description, image_base64)
    if ai:
        return ai
    return classify_rules(description)

# ─────────────────────────────────────────────────────────────
# DUPLICATE / HOTSPOT LOGIC
# ─────────────────────────────────────────────────────────────

def find_duplicate(data, issue_type, lat, lon, radius_m=150, hours=72):
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    for inc in data["incidents"]:
        if inc["status"] == "Resolved":
            continue
        if inc["issue_type"] != issue_type:
            continue
        created = datetime.datetime.fromisoformat(inc["created_at"].replace("Z", ""))
        if created < cutoff:
            continue
        dist = haversine_m(lat, lon, inc["lat"], inc["lon"])
        if dist <= radius_m:
            return inc
    return None

def priority_score(p):
    return {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(p, 0)

def build_hotspots(data):
    hotspots = {}

    for inc in data["incidents"]:
        if inc["status"] == "Resolved":
            continue

        key = f"{inc.get('ward','Unknown')}|{inc['issue_type']}"
        if key not in hotspots:
            hotspots[key] = {
                "ward": inc.get("ward", "Unknown"),
                "issue_type": inc["issue_type"],
                "incident_count": 0,
                "total_reports": 0,
                "sample_addresses": [],
                "max_priority_score": 0,
                "max_priority": "Low",
            }

        hotspots[key]["incident_count"] += 1
        hotspots[key]["total_reports"] += inc.get("report_count", 1)

        pscore = priority_score(inc.get("priority", "Low"))
        if pscore > hotspots[key]["max_priority_score"]:
            hotspots[key]["max_priority_score"] = pscore
            hotspots[key]["max_priority"] = inc.get("priority", "Low")

        if len(hotspots[key]["sample_addresses"]) < 3:
            hotspots[key]["sample_addresses"].append(inc.get("address", "Unknown"))

    results = []
    for _, h in hotspots.items():
        if h["incident_count"] >= 2 or h["total_reports"] >= 8:
            results.append(h)

    results.sort(key=lambda x: (x["total_reports"], x["incident_count"]), reverse=True)
    return results

def build_action_recommendations(data):
    hotspots = build_hotspots(data)
    incidents = sorted(
        [i for i in data["incidents"] if i["status"] != "Resolved"],
        key=lambda x: (-priority_score(x.get("priority", "Low")), x.get("report_count", 1)),
    )

    recommendations = []

    for h in hotspots[:3]:
        recommendations.append({
            "title": f"Investigate chronic {h['issue_type']} in {h['ward']}",
            "reason": f"{h['incident_count']} open incidents and {h['total_reports']} total reports indicate a repeated service issue in this area.",
            "priority": h["max_priority"]
        })

    for inc in incidents[:3]:
        recommendations.append({
            "title": f"Prioritise {inc['issue_type']} at {inc.get('address', 'Unknown location')}",
            "reason": f"Current status is {inc['status']} with {inc.get('report_count', 1)} linked reports.",
            "priority": inc.get("priority", "Low")
        })

    return recommendations[:5]

# ─────────────────────────────────────────────────────────────
# DEMO SEED
# ─────────────────────────────────────────────────────────────

DEMO_INCIDENTS = [
    {
        "id": "INC-001",
        "issue_type": "Pothole",
        "department": "Roads & Transport",
        "priority": "High",
        "description": "Large pothole on Main Road causing vehicle damage",
        "lat": -33.9249,
        "lon": 18.4241,
        "address": "Main Road, Cape Town",
        "status": "Pending",
        "report_count": 5,
        "created_at": "2025-03-25T07:30:00Z",
        "updated_at": "2025-03-25T09:00:00Z",
        "ward": "Ward 57",
    },
    {
        "id": "INC-002",
        "issue_type": "Water Leak",
        "department": "Water & Sanitation",
        "priority": "Critical",
        "description": "Burst pipe flooding road near primary school",
        "lat": -33.9210,
        "lon": 18.4180,
        "address": "School Street, Observatory",
        "status": "Pending",
        "report_count": 8,
        "created_at": "2025-03-25T08:10:00Z",
        "updated_at": "2025-03-25T08:45:00Z",
        "ward": "Ward 58",
    },
    {
        "id": "INC-003",
        "issue_type": "Broken Streetlight",
        "department": "Public Lighting",
        "priority": "Medium",
        "description": "Streetlight out for 3 nights creating unsafe conditions",
        "lat": -33.9300,
        "lon": 18.4300,
        "address": "Kloof Street, Gardens",
        "status": "Submitted",
        "report_count": 2,
        "created_at": "2025-03-25T19:00:00Z",
        "updated_at": "2025-03-25T19:00:00Z",
        "ward": "Ward 77",
    },
    {
        "id": "INC-004",
        "issue_type": "Electricity Outage",
        "department": "Electricity Department",
        "priority": "Critical",
        "description": "Power outage affecting 3 blocks near hospital",
        "lat": -33.9350,
        "lon": 18.4400,
        "address": "Hospital Road, Woodstock",
        "status": "Pending",
        "report_count": 12,
        "created_at": "2025-03-26T06:00:00Z",
        "updated_at": "2025-03-26T06:30:00Z",
        "ward": "Ward 59",
    },
    {
        "id": "INC-005",
        "issue_type": "Waste Collection",
        "department": "Waste Management",
        "priority": "Low",
        "description": "Bins not collected for 2 weeks",
        "lat": -33.9400,
        "lon": 18.4500,
        "address": "Long Street, CBD",
        "status": "Submitted",
        "report_count": 3,
        "created_at": "2025-03-26T10:00:00Z",
        "updated_at": "2025-03-26T10:00:00Z",
        "ward": "Ward 77",
    },
]

def ensure_seed():
    data = load_data()
    if not data["incidents"]:
        data["incidents"] = DEMO_INCIDENTS
        data["reports"] = []
        save_data(data)

# ─────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", user=current_user())

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "User").strip() or "User"
        login_as = request.form.get("login_as", "user").strip().lower()

        if not email:
            return render_template("login.html", error="Email is required.")

        admin_emails = get_admin_emails()

        if login_as == "admin":
            if email not in admin_emails:
                return render_template("login.html", error="This email is not authorised for admin access.")
            session["email"] = email
            session["name"] = name
            session["role"] = "admin"
            return redirect(url_for("dashboard_page"))

        session["email"] = email
        session["name"] = name
        session["role"] = "user"
        return redirect(url_for("user_home"))

    return render_template("login.html", error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ─────────────────────────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────────────────────────

@app.route("/home")
@login_required(role="user")
def user_home():
    return render_template("home.html", user=current_user())

@app.route("/report")
@login_required(role="user")
def report_page():
    return render_template("report.html", user=current_user())

@app.route("/my-reports")
@login_required(role="user")
def my_reports_page():
    return render_template("my_reports.html", user=current_user())

@app.route("/dashboard")
@login_required(role="admin")
def dashboard_page():
    return render_template("dashboard.html", user=current_user())

@app.route("/incidents")
@login_required(role="admin")
def incidents_page():
    return render_template("incidents.html", user=current_user())

# ─────────────────────────────────────────────────────────────
# USER API
# ─────────────────────────────────────────────────────────────

@app.route("/api/submit", methods=["POST"])
@login_required(role="user")
def submit_report():
    body = request.get_json()
    description = body.get("description", "").strip()
    lat = float(body.get("lat", 0))
    lon = float(body.get("lon", 0))
    addr = body.get("address", "Unknown location")
    image_base64 = body.get("image_base64")

    if not description:
        return jsonify({"error": "Description required"}), 400

    ai = classify_issue(description, image_base64)
    data = load_data()

    existing = find_duplicate(data, ai["issue_type"], lat, lon)
    report_id = "RPT-" + uuid.uuid4().hex[:6].upper()

    if existing:
        existing["report_count"] = existing.get("report_count", 1) + 1
        existing["updated_at"] = now_iso()

        if existing["report_count"] >= 5 and existing["priority"] in ("Low", "Medium"):
            existing["priority"] = "High"
        if existing["report_count"] >= 10 and existing["priority"] != "Critical":
            existing["priority"] = "Critical"

        report = {
            "id": report_id,
            "incident_id": existing["id"],
            "description": description,
            "lat": lat,
            "lon": lon,
            "address": addr,
            "submitted_at": now_iso(),
            "is_duplicate": True,
            "submitted_by": session.get("email"),
        }
        data["reports"].append(report)
        save_data(data)

        return jsonify({
            "report_id": report_id,
            "linked_incident": existing["id"],
            "is_duplicate": True,
            "issue_type": existing["issue_type"],
            "department": existing["department"],
            "priority": existing["priority"],
            "status": existing["status"],
            "reason": "Your report has been linked to an existing incident in your area.",
            "report_count": existing["report_count"],
            "ai_source": ai.get("source", "rules")
        })

    inc_id = "INC-" + str(100 + len(data["incidents"])).zfill(3)
    incident = {
        "id": inc_id,
        "issue_type": ai["issue_type"],
        "department": ai["department"],
        "priority": ai["priority"],
        "description": description,
        "lat": lat,
        "lon": lon,
        "address": addr,
        "status": "Submitted",
        "report_count": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "ward": body.get("ward", "Unknown"),
        "classification_source": ai.get("source", "rules")
    }

    report = {
        "id": report_id,
        "incident_id": inc_id,
        "description": description,
        "lat": lat,
        "lon": lon,
        "address": addr,
        "submitted_at": now_iso(),
        "is_duplicate": False,
        "submitted_by": session.get("email"),
    }

    data["incidents"].append(incident)
    data["reports"].append(report)
    save_data(data)

    return jsonify({
        "report_id": report_id,
        "incident_id": inc_id,
        "is_duplicate": False,
        "issue_type": ai["issue_type"],
        "department": ai["department"],
        "priority": ai["priority"],
        "status": "Submitted",
        "reason": ai["reason"],
        "report_count": 1,
        "ai_source": ai.get("source", "rules")
    })

@app.route("/api/my-reports", methods=["GET"])
@login_required(role="user")
def my_reports():
    data = load_data()
    email = session.get("email")
    reports = [r for r in data["reports"] if r.get("submitted_by") == email]

    enriched = []
    for r in reports:
        inc = next((i for i in data["incidents"] if i["id"] == r["incident_id"]), None)
        enriched.append({
            "report_id": r["id"],
            "incident_id": r["incident_id"],
            "description": r["description"],
            "address": r["address"],
            "submitted_at": r["submitted_at"],
            "issue_type": inc["issue_type"] if inc else "Unknown",
            "department": inc["department"] if inc else "Unknown",
            "priority": inc["priority"] if inc else "Unknown",
            "status": inc["status"] if inc else "Unknown",
        })

    enriched.sort(key=lambda x: x["submitted_at"], reverse=True)
    return jsonify(enriched)

# ─────────────────────────────────────────────────────────────
# ADMIN API
# ─────────────────────────────────────────────────────────────

@app.route("/api/incidents", methods=["GET"])
@login_required(role="admin")
def get_incidents():
    data = load_data()
    incidents = sorted(
        data["incidents"],
        key=lambda x: (-priority_score(x.get("priority", "Low")), x.get("created_at", "")),
    )
    return jsonify(incidents)

@app.route("/api/incidents/<inc_id>/status", methods=["PATCH"])
@login_required(role="admin")
def update_status(inc_id):
    data = load_data()
    inc = next((i for i in data["incidents"] if i["id"] == inc_id), None)
    if not inc:
        return jsonify({"error": "Not found"}), 404

    body = request.get_json()
    new_status = body.get("status", inc["status"])

    if new_status not in ["Submitted", "Pending", "Resolved"]:
        return jsonify({"error": "Invalid status"}), 400

    inc["status"] = new_status
    inc["updated_at"] = now_iso()
    save_data(data)
    return jsonify(inc)

@app.route("/api/stats", methods=["GET"])
@login_required(role="admin")
def get_stats():
    data = load_data()
    incs = data["incidents"]

    total = len(incs)
    open_ = sum(1 for i in incs if i["status"] != "Resolved")
    high = sum(1 for i in incs if i["priority"] in ("High", "Critical"))
    resolved_today = sum(
        1 for i in incs
        if i["status"] == "Resolved" and i.get("updated_at", "")[:10] == datetime.date.today().isoformat()
    )

    cats = {}
    for i in incs:
        t = i["issue_type"]
        cats[t] = cats.get(t, 0) + 1

    top_cat = max(cats, key=cats.get) if cats else "—"

    return jsonify({
        "total": total,
        "open": open_,
        "high_priority": high,
        "resolved_today": resolved_today,
        "top_category": top_cat,
        "by_category": cats,
        "by_status": {
            s: sum(1 for i in incs if i["status"] == s)
            for s in ["Submitted", "Pending", "Resolved"]
        },
    })

@app.route("/api/chronic-hotspots", methods=["GET"])
@login_required(role="admin")
def chronic_hotspots():
    data = load_data()
    return jsonify(build_hotspots(data))

@app.route("/api/action-recommendations", methods=["GET"])
@login_required(role="admin")
def action_recommendations():
    data = load_data()
    return jsonify(build_action_recommendations(data))

if __name__ == "__main__":
    ensure_seed()
    app.run(debug=True, port=5000)