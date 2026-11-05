# Smart Voting System using Face Recognition

CS3664 Mini Project – Machine Learning + Full Stack.
Flask + SQLite backend, `face_recognition` (dlib HOG detector + ResNet 128-d embeddings), browser webcam capture.

## Features (maps to the presentation)

| Module (slide 15)        | Where it lives                                  |
|--------------------------|-------------------------------------------------|
| User Registration        | `/register` – `app.py::register`                |
| Face Capture             | `static/js/camera.js` (webcam in the browser)   |
| Face Recognition         | `face_utils.py` (detect, encode, match)         |
| Authentication           | `/verify` – face match + "already voted" check  |
| Voting                   | `/vote` – atomic transaction in `database.py`   |
| Database Management      | `database.py` (SQLite: voters, votes, audit_log)|

Extras: duplicate-face registration block, session timeout after verification,
ballot secrecy (votes table holds no voter reference), audit log, admin
dashboard with live results, and `evaluate.py` for accuracy / FAR / FRR.

## Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 (camera access works only on `localhost` or HTTPS).

### Installing dlib / face_recognition
- **Linux/Mac:** `sudo apt install cmake build-essential` (or `brew install cmake`), then `pip install dlib face_recognition`.
- **Windows:** install "Desktop development with C++" (Visual Studio Build Tools) and CMake first,
  or use a prebuilt wheel matching your Python version: `pip install dlib-bin face_recognition`.

## Usage
1. **New User** – fill Legal Identifier, Age (18+), ID Number, Secure Contact, press *Begin Scan* (auto-captures 3 face frames), then *Confirm Identity*.
2. **Party Voting** – press *Begin Scan*; if matched and not yet voted, the party ballot opens. Click a party card to highlight it, press *Vote* to cast.
3. **Check Eligibility** – public page showing only registered / voted status for an ID number.
4. **Admin** (Registered Voters Registry, live results, ledger check) – `/admin/login` (default `admin` / `admin123`). Change with env vars:
   `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SECRET_KEY`.

## Evaluating accuracy (slide 14: Training and Testing)
```
dataset/
  person_1/ 1.jpg 2.jpg 3.jpg 4.jpg ...
  person_2/ ...
python evaluate.py dataset --train 3 --tolerance 0.5
```
Reports Accuracy, FAR and FRR. Tune `FACE_TOLERANCE` in `config.py`.

## Limitations (good viva answers)
- No liveness detection: a printed photo or screen replay could fool it. Future work: blink / head-turn challenge or depth sensor.
- Identical twins have near-identical embeddings; the paper's multi-factor option (OTP / voter-ID entry) is the mitigation.
- Face encodings are biometric data – in production encrypt the DB, use HTTPS and follow data-protection law.
- This is an academic prototype, not a certified election system.

## Ballot ledger
Each vote stores `prev_hash` and `hash` (SHA-256), forming a tamper-evident chain; the admin page re-verifies it. This is a hash chain, not a distributed blockchain.
