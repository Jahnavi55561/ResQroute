
import os
import re
import math
import uuid
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, session
)


# =========================================
# APPLICATION CONFIGURATION
# =========================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "RESQROUTE_SECRET_KEY",
    "resqroute-local-demo-secret-change-before-deployment"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "resqroute.db")

ADMIN_USERNAME = os.environ.get("RESQROUTE_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("RESQROUTE_ADMIN_PASSWORD", "jaanu")


# =========================================
# DATABASE CONNECTION
# =========================================

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# =========================================
# AUTHENTICATION
# =========================================

def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please login as administrator.")
            return redirect(url_for("admin_login"))
        return function(*args, **kwargs)
    return wrapper


def driver_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("driver_ambulance_id"):
            flash("Please login as a driver.")
            return redirect(url_for("driver_login"))
        return function(*args, **kwargs)
    return wrapper


# =========================================
# GPS AND DISTANCE FUNCTIONS
# =========================================

def extract_coordinates(location):
    if not location:
        return None, None

    pattern = (
        r"GPS(?:\s+Coordinates)?:\s*"
        r"(-?\d+(?:\.\d+)?)\s*,\s*"
        r"(-?\d+(?:\.\d+)?)"
    )

    match = re.search(pattern, location, re.IGNORECASE)

    if not match:
        return None, None

    try:
        latitude = float(match.group(1))
        longitude = float(match.group(2))

        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            return latitude, longitude
    except (ValueError, TypeError):
        pass

    return None, None


def calculate_distance(lat1, lon1, lat2, lon2):
    earth_radius = 6371

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius * c


# =========================================
# DATABASE CREATION AND MIGRATIONS
# =========================================

def create_database():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS emergencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emergency_id TEXT UNIQUE,
            patient_name TEXT,
            phone TEXT,
            emergency_type TEXT,
            location TEXT,
            status TEXT,
            created_at TEXT
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS ambulances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_number TEXT UNIQUE,
            driver_name TEXT,
            phone TEXT,
            ambulance_type TEXT,
            location TEXT,
            status TEXT DEFAULT 'Available',
            created_at TEXT
        )
    """)

    emergency_columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(emergencies)"
        ).fetchall()
    }

    ambulance_columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(ambulances)"
        ).fetchall()
    }

    emergency_migrations = {
        "latitude": "REAL",
        "longitude": "REAL",
        "ambulance_id": "INTEGER",
        "assigned_at": "TEXT"
    }

    ambulance_migrations = {
        "latitude": "REAL",
        "longitude": "REAL",
        "gps_updated_at": "TEXT"
    }

    for column, column_type in emergency_migrations.items():
        if column not in emergency_columns:
            connection.execute(
                f"ALTER TABLE emergencies ADD COLUMN {column} {column_type}"
            )

    for column, column_type in ambulance_migrations.items():
        if column not in ambulance_columns:
            connection.execute(
                f"ALTER TABLE ambulances ADD COLUMN {column} {column_type}"
            )

    rows = connection.execute("""
        SELECT id, location, latitude, longitude
        FROM emergencies
        WHERE latitude IS NULL OR longitude IS NULL
    """).fetchall()

    for row in rows:
        extracted_lat, extracted_lon = extract_coordinates(row["location"])

        latitude = (
            row["latitude"]
            if row["latitude"] is not None
            else extracted_lat
        )

        longitude = (
            row["longitude"]
            if row["longitude"] is not None
            else extracted_lon
        )

        if latitude is not None and longitude is not None:
            connection.execute("""
                UPDATE emergencies
                SET latitude = ?, longitude = ?
                WHERE id = ?
            """, (latitude, longitude, row["id"]))

    connection.commit()
    connection.close()


# =========================================
# PUBLIC PORTAL HOMEPAGE
# =========================================

@app.route("/")
@app.route("/portals")
def portal_home():
    return render_template("portals.html")


# =========================================
# PATIENT PORTAL
# =========================================

@app.route("/patient")
def patient_portal():
    return render_template(
        "patient.html",
        latest_emergency_id=session.get("latest_emergency_id")
    )


# =========================================
# ADMIN LOGIN
# =========================================

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if session.get("admin_logged_in"):
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.clear()
            session["admin_logged_in"] = True
            session["admin_username"] = username

            flash("Admin login successful.")
            return redirect(url_for("home"))

        flash("Invalid admin username or password.")

    return render_template("admin_login.html")


# =========================================
# ADMIN LOGOUT
# =========================================

@app.route("/admin-logout")
def admin_logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("portal_home"))


# =========================================
# ADMIN DASHBOARD
# =========================================

@app.route("/admin-dashboard")
@admin_required
def home():

    connection = get_db()

    emergencies = connection.execute("""
        SELECT
            emergencies.*,
            ambulances.vehicle_number AS assigned_vehicle,
            ambulances.driver_name AS assigned_driver
        FROM emergencies
        LEFT JOIN ambulances
        ON emergencies.ambulance_id = ambulances.id
        ORDER BY emergencies.id DESC
    """).fetchall()

    ambulances = connection.execute("""
        SELECT * FROM ambulances ORDER BY id DESC
    """).fetchall()

    total_requests = connection.execute(
        "SELECT COUNT(*) FROM emergencies"
    ).fetchone()[0]

    pending_count = connection.execute("""
        SELECT COUNT(*) FROM emergencies
        WHERE status = 'SOS Received - Demo'
    """).fetchone()[0]

    assigned_count = connection.execute("""
        SELECT COUNT(*) FROM emergencies
        WHERE status IN (
            'Ambulance Assigned - Demo',
            'Accepted - Demo',
            'Reached Patient - Demo',
            'Patient Picked Up - Demo'
        )
    """).fetchone()[0]

    ambulance_count = connection.execute(
        "SELECT COUNT(*) FROM ambulances"
    ).fetchone()[0]

    connection.close()

    return render_template(
        "index.html",
        emergencies=emergencies,
        ambulances=ambulances,
        total_requests=total_requests,
        pending_count=pending_count,
        assigned_count=assigned_count,
        ambulance_count=ambulance_count
    )


# =========================================
# CREATE PATIENT SOS
# =========================================

@app.route("/sos", methods=["POST"])
def create_sos():

    patient_name = request.form.get("patient_name", "").strip()
    phone = request.form.get("phone", "").strip()
    emergency_type = request.form.get("emergency_type", "").strip()
    location = request.form.get("location", "").strip()

    latitude, longitude = extract_coordinates(location)

    try:
        form_latitude = request.form.get("latitude", "").strip()
        form_longitude = request.form.get("longitude", "").strip()

        if form_latitude:
            latitude = float(form_latitude)

        if form_longitude:
            longitude = float(form_longitude)

    except (ValueError, TypeError):
        flash("Invalid GPS coordinates.")
        return redirect(url_for("patient_portal"))

    if not all([patient_name, phone, emergency_type, location]):
        flash("Please fill in all required details.")
        return redirect(url_for("patient_portal"))

    if not re.fullmatch(r"\d{10}", phone):
        flash("Enter a valid 10-digit phone number.")
        return redirect(url_for("patient_portal"))

    if latitude is not None and not -90 <= latitude <= 90:
        flash("Invalid patient latitude.")
        return redirect(url_for("patient_portal"))

    if longitude is not None and not -180 <= longitude <= 180:
        flash("Invalid patient longitude.")
        return redirect(url_for("patient_portal"))

    emergency_id = "RQ-" + uuid.uuid4().hex[:8].upper()

    connection = get_db()

    connection.execute("""
        INSERT INTO emergencies (
            emergency_id,
            patient_name,
            phone,
            emergency_type,
            location,
            status,
            created_at,
            latitude,
            longitude
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        emergency_id,
        patient_name,
        phone,
        emergency_type,
        location,
        "SOS Received - Demo",
        datetime.now().strftime("%d-%m-%Y %I:%M %p"),
        latitude,
        longitude
    ))

    connection.commit()
    connection.close()

    # NEW: Save the latest SOS ID for the patient tracking button.
    session["latest_emergency_id"] = emergency_id

    flash(
        f"Demo SOS created successfully! Emergency ID: {emergency_id}"
    )

    return redirect(url_for("patient_portal"))


# =========================================
# REGISTER AMBULANCE - ADMIN ONLY
# =========================================

@app.route("/register-ambulance", methods=["POST"])
@admin_required
def register_ambulance():

    vehicle_number = request.form.get(
        "vehicle_number", ""
    ).strip().upper()

    driver_name = request.form.get("driver_name", "").strip()
    phone = request.form.get("ambulance_phone", "").strip()
    ambulance_type = request.form.get("ambulance_type", "").strip()
    location = request.form.get("ambulance_location", "").strip()

    latitude = request.form.get("ambulance_latitude", "").strip()
    longitude = request.form.get("ambulance_longitude", "").strip()

    extracted_lat, extracted_lon = extract_coordinates(location)

    try:
        latitude = float(latitude) if latitude else extracted_lat
        longitude = float(longitude) if longitude else extracted_lon
    except (ValueError, TypeError):
        flash("Invalid ambulance GPS coordinates.")
        return redirect(url_for("home"))

    if not all([
        vehicle_number, driver_name, phone,
        ambulance_type, location
    ]):
        flash("Please fill in all ambulance details.")
        return redirect(url_for("home"))

    if latitude is not None and not -90 <= latitude <= 90:
        flash("Invalid ambulance latitude.")
        return redirect(url_for("home"))

    if longitude is not None and not -180 <= longitude <= 180:
        flash("Invalid ambulance longitude.")
        return redirect(url_for("home"))

    connection = get_db()

    try:
        connection.execute("""
            INSERT INTO ambulances (
                vehicle_number, driver_name, phone,
                ambulance_type, location, status,
                created_at, latitude, longitude
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            vehicle_number,
            driver_name,
            phone,
            ambulance_type,
            location,
            "Available",
            datetime.now().strftime("%d-%m-%Y %I:%M %p"),
            latitude,
            longitude
        ))

        connection.commit()
        flash(f"Ambulance {vehicle_number} registered successfully.")

    except sqlite3.IntegrityError:
        flash("This vehicle number is already registered.")

    finally:
        connection.close()

    return redirect(url_for("home"))


# =========================================
# UPDATE AMBULANCE AVAILABILITY
# =========================================

@app.route("/ambulance-status/<int:ambulance_id>", methods=["POST"])
@admin_required
def update_ambulance_status(ambulance_id):

    connection = get_db()

    ambulance = connection.execute(
        "SELECT * FROM ambulances WHERE id = ?",
        (ambulance_id,)
    ).fetchone()

    if ambulance is None:
        connection.close()
        flash("Ambulance not found.")
        return redirect(url_for("home"))

    active_assignment = connection.execute("""
        SELECT id FROM emergencies
        WHERE ambulance_id = ?
        AND status IN (
            'Ambulance Assigned - Demo',
            'Accepted - Demo',
            'Reached Patient - Demo',
            'Patient Picked Up - Demo'
        )
        LIMIT 1
    """, (ambulance_id,)).fetchone()

    if active_assignment:
        connection.close()
        flash("This ambulance has an active emergency.")
        return redirect(url_for("home"))

    new_status = (
        "On Duty" if ambulance["status"] == "Available"
        else "Available"
    )

    connection.execute("""
        UPDATE ambulances SET status = ? WHERE id = ?
    """, (new_status, ambulance_id))

    connection.commit()
    connection.close()

    flash(f"Ambulance status updated to {new_status}.")
    return redirect(url_for("home"))


# =========================================
# FIND NEAREST AVAILABLE AMBULANCE
# =========================================

@app.route("/nearest-ambulance/<emergency_id>")
@admin_required
def nearest_ambulance(emergency_id):

    connection = get_db()

    emergency = connection.execute(
        "SELECT * FROM emergencies WHERE emergency_id = ?",
        (emergency_id,)
    ).fetchone()

    if emergency is None:
        connection.close()
        return jsonify({
            "success": False,
            "message": "Emergency not found."
        }), 404

    if emergency["ambulance_id"] is not None:

        assigned = connection.execute(
            "SELECT * FROM ambulances WHERE id = ?",
            (emergency["ambulance_id"],)
        ).fetchone()

        connection.close()

        return jsonify({
            "success": True,
            "already_assigned": True,
            "message": "An ambulance is already assigned.",
            "assigned_ambulance": {
                "vehicle_number": assigned["vehicle_number"],
                "driver_name": assigned["driver_name"]
            } if assigned else None
        })

    patient_lat = emergency["latitude"]
    patient_lon = emergency["longitude"]

    if patient_lat is None or patient_lon is None:
        extracted_lat, extracted_lon = extract_coordinates(
            emergency["location"]
        )
        patient_lat = patient_lat if patient_lat is not None else extracted_lat
        patient_lon = patient_lon if patient_lon is not None else extracted_lon

    if patient_lat is None or patient_lon is None:
        connection.close()
        return jsonify({
            "success": False,
            "message": "Patient GPS location is not available."
        }), 400

    ambulances = connection.execute("""
        SELECT * FROM ambulances
        WHERE status = 'Available'
        AND latitude IS NOT NULL
        AND longitude IS NOT NULL
    """).fetchall()

    connection.close()

    if not ambulances:
        return jsonify({
            "success": False,
            "message": "No available ambulances with GPS coordinates found."
        }), 404

    matches = []

    for ambulance in ambulances:
        distance = calculate_distance(
            patient_lat,
            patient_lon,
            ambulance["latitude"],
            ambulance["longitude"]
        )

        matches.append({
            "ambulance_id": ambulance["id"],
            "vehicle_number": ambulance["vehicle_number"],
            "driver_name": ambulance["driver_name"],
            "phone": ambulance["phone"],
            "ambulance_type": ambulance["ambulance_type"],
            "location": ambulance["location"],
            "distance_km": round(distance, 2)
        })

    matches.sort(key=lambda item: item["distance_km"])

    return jsonify({
        "success": True,
        "emergency_id": emergency_id,
        "patient_location": {
            "latitude": patient_lat,
            "longitude": patient_lon
        },
        "nearest_ambulance": matches[0],
        "all_matches": matches,
        "note": "Demo straight-line distance, not actual road distance."
    })


# =========================================
# ASSIGN AMBULANCE
# =========================================

@app.route(
    "/assign-ambulance/<emergency_id>/<int:ambulance_id>",
    methods=["POST"]
)
@admin_required
def assign_ambulance(emergency_id, ambulance_id):

    connection = get_db()

    try:
        connection.execute("BEGIN IMMEDIATE")

        emergency = connection.execute(
            "SELECT * FROM emergencies WHERE emergency_id = ?",
            (emergency_id,)
        ).fetchone()

        if emergency is None:
            connection.rollback()
            flash("Emergency not found.")
            return redirect(url_for("home"))

        if emergency["ambulance_id"] is not None:
            connection.rollback()
            flash("An ambulance is already assigned.")
            return redirect(url_for("home"))

        if emergency["status"] != "SOS Received - Demo":
            connection.rollback()
            flash("This emergency is not available for assignment.")
            return redirect(url_for("home"))

        ambulance = connection.execute(
            "SELECT * FROM ambulances WHERE id = ?",
            (ambulance_id,)
        ).fetchone()

        if ambulance is None:
            connection.rollback()
            flash("Ambulance not found.")
            return redirect(url_for("home"))

        if ambulance["status"] != "Available":
            connection.rollback()
            flash("This ambulance is no longer available.")
            return redirect(url_for("home"))

        connection.execute("""
            UPDATE emergencies
            SET ambulance_id = ?,
                assigned_at = ?,
                status = ?
            WHERE emergency_id = ?
        """, (
            ambulance_id,
            datetime.now().strftime("%d-%m-%Y %I:%M %p"),
            "Ambulance Assigned - Demo",
            emergency_id
        ))

        connection.execute("""
            UPDATE ambulances
            SET status = 'On Duty'
            WHERE id = ?
        """, (ambulance_id,))

        connection.commit()

        flash(
            f"Ambulance {ambulance['vehicle_number']} "
            f"assigned to {emergency_id}."
        )

    except sqlite3.Error:
        connection.rollback()
        flash("Assignment failed. Please try again.")

    finally:
        connection.close()

    return redirect(url_for("home"))


# =========================================
# DRIVER LOGIN
# =========================================

@app.route("/driver-login", methods=["GET", "POST"])
def driver_login():

    if session.get("driver_ambulance_id"):
        return redirect(url_for("driver_dashboard"))

    if request.method == "POST":

        vehicle_number = request.form.get(
            "vehicle_number", ""
        ).strip().upper()

        phone = request.form.get("phone", "").strip()

        connection = get_db()

        ambulance = connection.execute("""
            SELECT * FROM ambulances
            WHERE UPPER(vehicle_number) = ?
            AND phone = ?
        """, (vehicle_number, phone)).fetchone()

        connection.close()

        if ambulance:
            session.clear()
            session["driver_ambulance_id"] = ambulance["id"]

            flash("Driver login successful - Demo.")
            return redirect(url_for("driver_dashboard"))

        flash("Invalid vehicle number or registered phone number.")

    return render_template("driver.html")


# =========================================
# DRIVER DASHBOARD
# =========================================

@app.route("/driver-dashboard")
@driver_required
def driver_dashboard():

    ambulance_id = session.get("driver_ambulance_id")
    connection = get_db()

    ambulance = connection.execute(
        "SELECT * FROM ambulances WHERE id = ?",
        (ambulance_id,)
    ).fetchone()

    if ambulance is None:
        connection.close()
        session.clear()
        flash("Driver account not found.")
        return redirect(url_for("driver_login"))

    emergencies = connection.execute("""
        SELECT * FROM emergencies
        WHERE ambulance_id = ?
        ORDER BY id DESC
    """, (ambulance_id,)).fetchall()

    connection.close()

    return render_template(
        "driver.html",
        ambulance=ambulance,
        emergencies=emergencies
    )


# =========================================
# DRIVER ACCEPT EMERGENCY
# =========================================

@app.route("/driver-accept/<int:emergency_id>", methods=["POST"])
@driver_required
def driver_accept(emergency_id):

    ambulance_id = session.get("driver_ambulance_id")
    connection = get_db()

    try:
        result = connection.execute("""
            UPDATE emergencies
            SET status = 'Accepted - Demo'
            WHERE id = ?
            AND ambulance_id = ?
            AND status = 'Ambulance Assigned - Demo'
        """, (emergency_id, ambulance_id))

        if result.rowcount == 1:
            connection.commit()
            flash("Emergency accepted successfully - Demo.")
        else:
            connection.rollback()
            flash("This emergency cannot be accepted.")

    except sqlite3.Error:
        connection.rollback()
        flash("Unable to accept emergency.")

    finally:
        connection.close()

    return redirect(url_for("driver_dashboard"))


# =========================================
# DRIVER REJECT EMERGENCY
# =========================================

@app.route("/driver-reject/<int:emergency_id>", methods=["POST"])
@driver_required
def driver_reject(emergency_id):

    ambulance_id = session.get("driver_ambulance_id")
    connection = get_db()

    try:
        connection.execute("BEGIN IMMEDIATE")

        result = connection.execute("""
            UPDATE emergencies
            SET status = 'SOS Received - Demo',
                ambulance_id = NULL,
                assigned_at = NULL
            WHERE id = ?
            AND ambulance_id = ?
            AND status = 'Ambulance Assigned - Demo'
        """, (emergency_id, ambulance_id))

        if result.rowcount == 1:
            connection.execute("""
                UPDATE ambulances
                SET status = 'Available'
                WHERE id = ?
            """, (ambulance_id,))

            connection.commit()
            flash("Emergency rejected. Ambulance is available again.")
        else:
            connection.rollback()
            flash("This emergency cannot be rejected now.")

    except sqlite3.Error:
        connection.rollback()
        flash("Unable to reject emergency.")

    finally:
        connection.close()

    return redirect(url_for("driver_dashboard"))


# =========================================
# DRIVER STATUS WORKFLOW
# =========================================

@app.route("/driver-update-status/<int:emergency_id>", methods=["POST"])
@driver_required
def driver_update_status(emergency_id):

    ambulance_id = session.get("driver_ambulance_id")

    allowed_transitions = {
        "Accepted - Demo": "Reached Patient - Demo",
        "Reached Patient - Demo": "Patient Picked Up - Demo",
        "Patient Picked Up - Demo": "Reached Hospital - Demo"
    }

    connection = get_db()

    try:
        connection.execute("BEGIN IMMEDIATE")

        emergency = connection.execute("""
            SELECT * FROM emergencies
            WHERE id = ? AND ambulance_id = ?
        """, (emergency_id, ambulance_id)).fetchone()

        if emergency is None:
            connection.rollback()
            flash("Emergency not found or not assigned to you.")
            return redirect(url_for("driver_dashboard"))

        next_status = allowed_transitions.get(emergency["status"])

        if not next_status:
            connection.rollback()
            flash("This emergency cannot be updated further.")
            return redirect(url_for("driver_dashboard"))

        connection.execute("""
            UPDATE emergencies
            SET status = ?
            WHERE id = ? AND ambulance_id = ?
        """, (next_status, emergency_id, ambulance_id))

        if next_status == "Reached Hospital - Demo":
            connection.execute("""
                UPDATE ambulances
                SET status = 'Available'
                WHERE id = ?
            """, (ambulance_id,))

        connection.commit()
        flash(f"Emergency status updated: {next_status}")

    except sqlite3.Error:
        connection.rollback()
        flash("Unable to update emergency status.")

    finally:
        connection.close()

    return redirect(url_for("driver_dashboard"))


# =========================================
# DRIVER LOGOUT
# =========================================

@app.route("/driver-logout")
def driver_logout():
    session.clear()
    flash("Driver logged out.")
    return redirect(url_for("portal_home"))


# =========================================
# DRIVER LIVE GPS UPDATE
# =========================================

@app.route("/driver-update-location", methods=["POST"])
@driver_required
def driver_update_location():

    ambulance_id = session.get("driver_ambulance_id")
    data = request.get_json(silent=True) or {}

    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Invalid GPS coordinates."
        }), 400

    if not (
        -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return jsonify({
            "success": False,
            "message": "GPS coordinates are outside valid ranges."
        }), 400

    connection = get_db()

    ambulance = connection.execute(
        "SELECT id FROM ambulances WHERE id = ?",
        (ambulance_id,)
    ).fetchone()

    if ambulance is None:
        connection.close()
        session.clear()

        return jsonify({
            "success": False,
            "message": "Ambulance not found."
        }), 404

    connection.execute("""
        UPDATE ambulances
        SET latitude = ?,
            longitude = ?,
            gps_updated_at = ?
        WHERE id = ?
    """, (
        latitude,
        longitude,
        datetime.now().strftime("%d-%m-%Y %I:%M:%S %p"),
        ambulance_id
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True,
        "message": "Driver GPS location updated - Demo.",
        "latitude": latitude,
        "longitude": longitude
    })


# =========================================
# PATIENT TRACKING PAGE
# =========================================

@app.route("/track/<emergency_id>")
def track_emergency(emergency_id):

    connection = get_db()

    emergency = connection.execute("""
        SELECT
            emergencies.*,
            ambulances.vehicle_number AS assigned_vehicle,
            ambulances.driver_name AS assigned_driver,
            ambulances.latitude AS ambulance_latitude,
            ambulances.longitude AS ambulance_longitude,
            ambulances.gps_updated_at AS gps_updated_at
        FROM emergencies
        LEFT JOIN ambulances
        ON emergencies.ambulance_id = ambulances.id
        WHERE emergencies.emergency_id = ?
    """, (emergency_id,)).fetchone()

    connection.close()

    if emergency is None:
        return "Emergency not found.", 404

    if emergency["ambulance_id"] is None:
        return "No ambulance has been assigned yet. Please check again after admin assignment.", 200

    if emergency["latitude"] is None or emergency["longitude"] is None:
        extracted_lat, extracted_lon = extract_coordinates(
            emergency["location"]
        )

        emergency = dict(emergency)

        if emergency["latitude"] is None:
            emergency["latitude"] = extracted_lat

        if emergency["longitude"] is None:
            emergency["longitude"] = extracted_lon

    return render_template(
        "tracking.html",
        emergency=emergency
    )


# =========================================
# TRACKING DATA API
# =========================================

@app.route("/tracking-data/<emergency_id>")
def tracking_data(emergency_id):

    connection = get_db()

    emergency = connection.execute("""
        SELECT
            emergencies.emergency_id,
            emergencies.patient_name,
            emergencies.location AS patient_location,
            emergencies.latitude AS patient_latitude,
            emergencies.longitude AS patient_longitude,
            emergencies.status,
            ambulances.vehicle_number,
            ambulances.driver_name,
            ambulances.latitude AS ambulance_latitude,
            ambulances.longitude AS ambulance_longitude,
            ambulances.gps_updated_at
        FROM emergencies
        LEFT JOIN ambulances
        ON emergencies.ambulance_id = ambulances.id
        WHERE emergencies.emergency_id = ?
    """, (emergency_id,)).fetchone()

    connection.close()

    if emergency is None:
        return jsonify({
            "success": False,
            "message": "Emergency not found."
        }), 404

    patient_lat = emergency["patient_latitude"]
    patient_lon = emergency["patient_longitude"]

    if patient_lat is None or patient_lon is None:
        extracted_lat, extracted_lon = extract_coordinates(
            emergency["patient_location"]
        )

        patient_lat = (
            patient_lat if patient_lat is not None else extracted_lat
        )
        patient_lon = (
            patient_lon if patient_lon is not None else extracted_lon
        )

    return jsonify({
        "success": True,
        "emergency_id": emergency["emergency_id"],
        "patient": {
            "name": emergency["patient_name"],
            "latitude": patient_lat,
            "longitude": patient_lon
        },
        "ambulance": {
            "vehicle_number": emergency["vehicle_number"],
            "driver_name": emergency["driver_name"],
            "latitude": emergency["ambulance_latitude"],
            "longitude": emergency["ambulance_longitude"],
            "gps_updated_at": emergency["gps_updated_at"]
        },
        "status": emergency["status"]
    })


# =========================================
# APPLICATION START
# =========================================

create_database()

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
