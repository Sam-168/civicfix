from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json, uuid, math, datetime, os, re
from pathlib import Path

app = Flask(__name__)
CORS(app)

DATA_FILE = Path("data/incidents.json")
DATA_FILE.parent.mkdir(exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────────────────

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
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

# ── AI classification (rule-based — no API key needed) ───────────────────────

ISSUE_RULES = [
    ("Water Leak",         ["leak","pipe","burst","flood","water","flowing","dripping","sewage","drain"]),
    ("Pothole",            ["pothole","hole","road","crack","tarmac","asphalt","bump","dip"]),
    ("Electricity Outage", ["electricity","power","outage","blackout","light","electric","cable","pylon"]),
    ("Waste Collection",   ["waste","rubbish","trash","garbage","bin","litter","refuse","dump"]),
    ("Broken Streetlight", ["streetlight","street light","lamp","lamppost","dark","broken light"]),
]

DEPT_MAP = {
    "Water Leak":         "Water & Sanitation",
    "Pothole":            "Roads & Transport",
    "Electricity Outage": "Electricity Department",
    "Waste Collection":   "Waste Management",
    "Broken Streetlight": "Public Lighting",
}

PRIORITY_KEYWORDS = {
    "critical": ["hospital","school","clinic","main road","highway","fire","emergency","flooding"],
    "high":     ["burst","leak","outage","blackout","flood","unsafe","danger","junction"],
    "medium":   ["road","street","area","neighbourhood"],
    "low":      [],
}

def classify(description):
    text = description.lower()
    issue_type = "General Issue"
    for label, keywords in ISSUE_RULES:
        if any(k in text for k in keywords):
            issue_type = label
            break

    priority = "Low"
    for level, keywords in PRIORITY_KEYWORDS.items():
        if any(k in text for k in keywords):
            priority = level.capitalize()
            break
    if priority == "Low" and issue_type in ("Water Leak","Electricity Outage"):
        priority = "Medium"

    reasons = []
    if any(k in text for k in PRIORITY_KEYWORDS["critical"]):
        reasons.append("near critical infrastructure")
    if issue_type == "Water Leak":
        reasons.append("water infrastructure risk")
    if issue_type == "Electricity Outage":
        reasons.append("power supply disruption")
    reason = "Auto-classified based on description keywords."
    if reasons:
        reason = f"Elevated priority: {', '.join(reasons)}."

    return {
        "issue_type": issue_type,
        "department": DEPT_MAP.get(issue_type, "General Services"),
        "priority":   priority,
        "reason":     reason,
    }

def find_duplicate(data, issue_type, lat, lon, radius_m=150, hours=72):
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    for inc in data["incidents"]:
        if inc["status"] == "Resolved":
            continue
        if inc["issue_type"] != issue_type:
            continue
        created = datetime.datetime.fromisoformat(inc["created_at"].replace("Z",""))
        if created < cutoff:
            continue
        dist = haversine_m(lat, lon, inc["lat"], inc["lon"])
        if dist <= radius_m:
            return inc
    return None

def priority_score(p):
    return {"Critical":4,"High":3,"Medium":2,"Low":1}.get(p,0)

# ── seed demo data ────────────────────────────────────────────────────────────

DEMO_INCIDENTS = [
    {"id":"INC-001","issue_type":"Pothole","department":"Roads & Transport","priority":"High",
     "description":"Large pothole on Main Road causing vehicle damage","lat":-33.9249,"lon":18.4241,
     "address":"Main Road, Cape Town","status":"In Progress","report_count":5,
     "created_at":"2025-03-25T07:30:00Z","updated_at":"2025-03-25T09:00:00Z","ward":"Ward 57"},
    {"id":"INC-002","issue_type":"Water Leak","department":"Water & Sanitation","priority":"Critical",
     "description":"Burst pipe flooding road near primary school","lat":-33.9210,"lon":18.4180,
     "address":"School Street, Observatory","status":"Assigned","report_count":8,
     "created_at":"2025-03-25T08:10:00Z","updated_at":"2025-03-25T08:45:00Z","ward":"Ward 58"},
    {"id":"INC-003","issue_type":"Broken Streetlight","department":"Public Lighting","priority":"Medium",
     "description":"Streetlight out for 3 nights creating unsafe conditions","lat":-33.9300,"lon":18.4300,
     "address":"Kloof Street, Gardens","status":"Submitted","report_count":2,
     "created_at":"2025-03-25T19:00:00Z","updated_at":"2025-03-25T19:00:00Z","ward":"Ward 77"},
    {"id":"INC-004","issue_type":"Electricity Outage","department":"Electricity Department","priority":"Critical",
     "description":"Power outage affecting 3 blocks near hospital","lat":-33.9350,"lon":18.4400,
     "address":"Hospital Road, Woodstock","status":"In Progress","report_count":12,
     "created_at":"2025-03-26T06:00:00Z","updated_at":"2025-03-26T06:30:00Z","ward":"Ward 59"},
    {"id":"INC-005","issue_type":"Waste Collection","department":"Waste Management","priority":"Low",
     "description":"Bins not collected for 2 weeks","lat":-33.9400,"lon":18.4500,
     "address":"Long Street, CBD","status":"Submitted","report_count":3,
     "created_at":"2025-03-26T10:00:00Z","updated_at":"2025-03-26T10:00:00Z","ward":"Ward 77"},
    {"id":"INC-006","issue_type":"Pothole","department":"Roads & Transport","priority":"Medium",
     "description":"Pothole near bus stop","lat":-33.9150,"lon":18.4100,
     "address":"Victoria Road, Salt River","status":"Resolved","report_count":2,
     "created_at":"2025-03-24T08:00:00Z","updated_at":"2025-03-26T12:00:00Z","ward":"Ward 56"},
    {"id":"INC-007","issue_type":"Water Leak","department":"Water & Sanitation","priority":"High",
     "description":"Water main leaking onto pavement","lat":-33.9280,"lon":18.4220,
     "address":"De Waal Drive, Cape Town","status":"Assigned","report_count":4,
     "created_at":"2025-03-26T09:00:00Z","updated_at":"2025-03-26T09:30:00Z","ward":"Ward 77"},
    {"id":"INC-008","issue_type":"Broken Streetlight","department":"Public Lighting","priority":"Low",
     "description":"Streetlight flickering","lat":-33.9320,"lon":18.4350,
     "address":"Buitenkant Street, Cape Town","status":"Submitted","report_count":1,
     "created_at":"2025-03-27T07:00:00Z","updated_at":"2025-03-27T07:00:00Z","ward":"Ward 77"},
]

def ensure_seed():
    data = load_data()
    if not data["incidents"]:
        data["incidents"] = DEMO_INCIDENTS
        data["reports"] = []
        save_data(data)

# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/report")
def report_page():
    return render_template("report.html")

@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")

@app.route("/api/submit", methods=["POST"])
def submit_report():
    body = request.get_json()
    description = body.get("description","").strip()
    lat  = float(body.get("lat", 0))
    lon  = float(body.get("lon", 0))
    addr = body.get("address","Unknown location")

    if not description:
        return jsonify({"error":"Description required"}), 400

    ai = classify(description)
    data = load_data()

    existing = find_duplicate(data, ai["issue_type"], lat, lon)
    report_id = "RPT-" + uuid.uuid4().hex[:6].upper()

    if existing:
        existing["report_count"] = existing.get("report_count",1) + 1
        existing["updated_at"] = now_iso()
        # bump priority if duplicates pile up
        if existing["report_count"] >= 5 and existing["priority"] in ("Low","Medium"):
            existing["priority"] = "High"
        if existing["report_count"] >= 10 and existing["priority"] != "Critical":
            existing["priority"] = "Critical"
        report = {"id":report_id,"incident_id":existing["id"],"description":description,
                  "lat":lat,"lon":lon,"address":addr,"submitted_at":now_iso(),"is_duplicate":True}
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
        })

    inc_id = "INC-" + str(100 + len(data["incidents"])).zfill(3)
    incident = {
        "id": inc_id,
        "issue_type": ai["issue_type"],
        "department": ai["department"],
        "priority": ai["priority"],
        "description": description,
        "lat": lat, "lon": lon,
        "address": addr,
        "status": "Submitted",
        "report_count": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "ward": body.get("ward","Unknown"),
    }
    report = {"id":report_id,"incident_id":inc_id,"description":description,
              "lat":lat,"lon":lon,"address":addr,"submitted_at":now_iso(),"is_duplicate":False}
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
    })

@app.route("/api/incidents", methods=["GET"])
def get_incidents():
    data = load_data()
    incs = data["incidents"]
    # sort by priority then date
    incs_sorted = sorted(incs, key=lambda x: (-priority_score(x.get("priority","Low")), x.get("created_at","")))
    return jsonify(incs_sorted)

@app.route("/api/incidents/<inc_id>", methods=["GET"])
def get_incident(inc_id):
    data = load_data()
    inc = next((i for i in data["incidents"] if i["id"]==inc_id), None)
    if not inc:
        return jsonify({"error":"Not found"}),404
    return jsonify(inc)

@app.route("/api/incidents/<inc_id>/status", methods=["PATCH"])
def update_status(inc_id):
    data = load_data()
    inc = next((i for i in data["incidents"] if i["id"]==inc_id), None)
    if not inc:
        return jsonify({"error":"Not found"}),404
    body = request.get_json()
    inc["status"] = body.get("status", inc["status"])
    inc["updated_at"] = now_iso()
    save_data(data)
    return jsonify(inc)

@app.route("/api/stats", methods=["GET"])
def get_stats():
    data = load_data()
    incs = data["incidents"]
    total   = len(incs)
    open_   = sum(1 for i in incs if i["status"] != "Resolved")
    high    = sum(1 for i in incs if i["priority"] in ("High","Critical"))
    resolved_today = sum(
        1 for i in incs
        if i["status"]=="Resolved" and
           i.get("updated_at","")[:10] == datetime.date.today().isoformat()
    )
    cats = {}
    for i in incs:
        t = i["issue_type"]
        cats[t] = cats.get(t,0)+1
    top_cat = max(cats, key=cats.get) if cats else "—"
    return jsonify({
        "total": total,
        "open": open_,
        "high_priority": high,
        "resolved_today": resolved_today,
        "top_category": top_cat,
        "by_category": cats,
        "by_status": {
            s: sum(1 for i in incs if i["status"]==s)
            for s in ["Submitted","Assigned","In Progress","Resolved"]
        }
    })

if __name__ == "__main__":
    ensure_seed()
    app.run(debug=True, port=5000)
