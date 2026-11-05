import re
import time
from functools import wraps

import numpy as np
from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   session, url_for)

import database as db
import face_utils
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.teardown_appcontext(db.close_db)

with app.app_context():
    db.init_db()

VOTER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
CONTACT_RE = re.compile(r"^\+?\d{7,15}$")


# ---------------------------------------------------------------- helpers
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


def verified_voter():
    """Return the voter row for the current verified session, or None."""
    pk = session.get("verified_voter")
    issued = session.get("verified_at", 0)
    if not pk or time.time() - issued > app.config["VERIFICATION_VALID_SECONDS"]:
        session.pop("verified_voter", None)
        session.pop("verified_at", None)
        return None
    return db.get_voter(pk)


# ----------------------------------------------------------------- pages
@app.route("/")
def index():
    return render_template("index.html", stats=db.stats())


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html",
                               min_images=app.config["MIN_REGISTRATION_IMAGES"])

    data = request.get_json(silent=True) or {}
    voter_id = (data.get("voter_id") or "").strip()
    name = (data.get("name") or "").strip()
    contact = re.sub(r"[\s-]", "", (data.get("contact") or ""))
    images = data.get("images") or []
    try:
        age = int(data.get("age"))
    except (TypeError, ValueError):
        age = 0

    if not VOTER_ID_RE.match(voter_id):
        return jsonify(ok=False, error="Voter ID must be 3-20 letters, digits, - or _."), 400
    if len(name) < 2:
        return jsonify(ok=False, error="Please enter the voter's full name."), 400
    if age < 18 or age > 120:
        return jsonify(ok=False, error="Voter must be 18 years or older."), 400
    if not CONTACT_RE.match(contact):
        return jsonify(ok=False, error="Enter a valid contact number (7-15 digits)."), 400
    if len(images) < app.config["MIN_REGISTRATION_IMAGES"]:
        return jsonify(ok=False, error="Face scan incomplete. Press 'Begin Scan' first."), 400
    if db.get_voter_by_voter_id(voter_id):
        return jsonify(ok=False, error="This ID number is already registered."), 409

    encodings = []
    for i, img in enumerate(images, start=1):
        try:
            rgb = face_utils.decode_image(img)
        except Exception:
            return jsonify(ok=False, error=f"Image {i} could not be read."), 400
        enc, err = face_utils.extract_encoding(rgb)
        if err:
            return jsonify(ok=False, error=f"Image {i}: {err}"), 400
        encodings.append(enc)

    # Samples must all belong to the same person
    spread = max(np.linalg.norm(a - b) for a in encodings for b in encodings)
    if spread > 0.6:
        return jsonify(ok=False, error="Captured images look like different people. "
                                       "Retake the photos."), 400

    # The same face must not register under a second Voter ID
    existing, _ = face_utils.best_match(np.mean(encodings, axis=0), db.all_voters(),
                                        app.config["DUPLICATE_FACE_TOLERANCE"])
    if existing:
        db.log_event(voter_id, "DUPLICATE_REGISTRATION",
                     f"Face already registered as {existing['voter_id']}")
        return jsonify(ok=False, error="This face is already registered."), 409

    db.add_voter(voter_id, name, age, contact, encodings)
    db.log_event(voter_id, "REGISTERED", name)
    return jsonify(ok=True, message=f"{name} registered successfully.")


@app.route("/eligibility", methods=["GET", "POST"])
def eligibility():
    """Public status check: exposes only registered / voted flags, no personal data."""
    if request.method == "GET":
        return render_template("eligibility.html")
    voter_id = ((request.get_json(silent=True) or {}).get("voter_id") or "").strip()
    voter = db.get_voter_by_voter_id(voter_id) if VOTER_ID_RE.match(voter_id) else None
    if voter is None:
        return jsonify(ok=True, registered=False, voted=False)
    return jsonify(ok=True, registered=True, voted=bool(voter["has_voted"]))


@app.route("/verify", methods=["GET", "POST"])
def verify():
    if request.method == "GET":
        return render_template("verify.html")

    data = request.get_json(silent=True) or {}
    image = data.get("image")
    if not image:
        return jsonify(ok=False, error="No image received."), 400

    try:
        rgb = face_utils.decode_image(image)
    except Exception:
        return jsonify(ok=False, error="Image could not be read."), 400

    enc, err = face_utils.extract_encoding(rgb)
    if err:
        return jsonify(ok=False, error=err), 400

    tol = app.config["FACE_TOLERANCE"]
    voter, dist = face_utils.best_match(enc, db.all_voters(), tol)

    if voter is None:
        db.log_event(None, "FACE_MISMATCH", f"best distance {dist:.3f}")
        return jsonify(ok=False, error="Face not recognised. Access denied."), 401

    if voter["has_voted"]:
        db.log_event(voter["voter_id"], "DUPLICATE_VOTE_ATTEMPT", f"distance {dist:.3f}")
        return jsonify(ok=False, error=f"{voter['name']}, you have already voted. "
                                       "Access denied."), 403

    session["verified_voter"] = voter["id"]
    session["verified_at"] = time.time()
    db.log_event(voter["voter_id"], "FACE_VERIFIED", f"distance {dist:.3f}")
    return jsonify(ok=True, name=voter["name"],
                   confidence=face_utils.confidence_from_distance(dist, tol),
                   redirect=url_for("vote"))


@app.route("/vote", methods=["GET", "POST"])
def vote():
    voter = verified_voter()
    if voter is None:
        flash("Please verify your face before voting.", "error")
        return redirect(url_for("verify"))

    if request.method == "GET":
        return render_template("vote.html", voter=voter, candidates=db.all_candidates())

    try:
        candidate_id = int(request.form.get("candidate_id", ""))
    except ValueError:
        flash("Please select a candidate.", "error")
        return redirect(url_for("vote"))

    valid_ids = {c["id"] for c in db.all_candidates()}
    if candidate_id not in valid_ids:
        flash("Invalid candidate selected.", "error")
        return redirect(url_for("vote"))

    if db.cast_vote(voter["id"], candidate_id):
        db.log_event(voter["voter_id"], "VOTE_CAST")
        session.pop("verified_voter", None)
        session.pop("verified_at", None)
        return render_template("done.html", name=voter["name"])

    flash("You have already voted.", "error")
    return redirect(url_for("index"))


# ----------------------------------------------------------------- admin
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (request.form.get("username") == app.config["ADMIN_USERNAME"]
                and request.form.get("password") == app.config["ADMIN_PASSWORD"]):
            session["is_admin"] = True
            return redirect(url_for("admin"))
        flash("Invalid admin credentials.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin():
    return render_template("admin.html", results=db.results(), stats=db.stats(),
                           voters=db.all_voters(), logs=db.recent_logs(),
                           ledger=db.ledger_status())


@app.route("/admin/candidates", methods=["POST"])
@admin_required
def admin_add_candidate():
    name = request.form.get("name", "").strip()
    slogan = request.form.get("slogan", "").strip()
    color = request.form.get("color", "#0b2545")
    if name:
        db.add_candidate(name, slogan, color)
        flash("Party added to the ballot.", "success")
    return redirect(url_for("admin"))


@app.route("/api/results")
@admin_required
def api_results():
    return jsonify(results=[dict(r) for r in db.results()], stats=db.stats())


if __name__ == "__main__":
    # Browsers only allow camera access on localhost or HTTPS.
    app.run(host="127.0.0.1", port=5000, debug=True)
