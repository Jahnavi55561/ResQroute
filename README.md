# 🚑 ResQRoute – Smart Emergency Response & Ambulance Tracking System

**ResQRoute** is a web-based emergency response management prototype designed to streamline emergency requests, ambulance assignment, driver coordination, and live location tracking.

The platform connects patients, administrators, and ambulance drivers through a centralized system to demonstrate a faster and more organized emergency response workflow.

## 🎯 Problem Statement

During medical emergencies, delays in requesting ambulances, locating available vehicles, and coordinating with drivers can make emergency response difficult.

ResQRoute aims to address these challenges through a centralized digital platform that helps manage emergency requests and ambulance coordination.

## 💡 Proposed Solution

ResQRoute provides three connected portals:

- **Patient Portal:** Submit emergency requests and receive an Emergency ID.
- **Admin Portal:** View emergency requests, find nearby ambulances, and assign vehicles.
- **Driver Portal:** View assigned emergencies, update response status, and share GPS location.

## ✨ Key Features

### 🧑 Patient Portal
- Submit emergency requests.
- Generate a unique Emergency ID.
- Provide patient and emergency details.
- Track emergency and ambulance information.

### 🛠️ Admin Portal
- View registered emergency requests.
- Find the nearest available ambulance.
- Assign ambulances to emergency cases.
- Monitor emergency status.

### 🚑 Driver Portal
- View assigned emergency requests.
- Access patient and emergency details.
- Update emergency progress:
  - Accepted
  - Reached Patient
  - Patient Picked Up
  - Reached Hospital
- Share live GPS coordinates.

### 📍 Emergency Tracking
- View emergency status.
- Display patient and ambulance information.
- Receive driver and patient GPS location updates.
- Visualize locations using an interactive map.

## 🔄 System Workflow

1. Patient submits an SOS request.
2. System generates a unique Emergency ID.
3. Admin views the emergency request.
4. Admin finds and assigns an available ambulance.
5. Driver receives the assigned emergency details.
6. Driver updates the emergency response status.
7. Driver shares GPS coordinates.
8. Tracking page displays available emergency and location information.

## 🧰 Technology Stack

| Component | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, Flask |
| Database | SQLite |
| Maps | Leaflet.js, OpenStreetMap |
| GPS | Browser Geolocation API |
| Deployment | Gunicorn |

## 📂 Project Structure

```text
ResQRoute/
│
├── app.py
├── requirements.txt
├── Procfile
├── .gitignore
├── README.md
│
├── static/
│   └── style.css
│
