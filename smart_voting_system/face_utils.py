"""Face detection, feature extraction (128-d encodings) and matching."""
import base64
import io
import json

import face_recognition
import numpy as np
from PIL import Image


def decode_image(data_url):
    """Convert a browser data-URL (base64 JPEG/PNG) into an RGB numpy array."""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    raw = base64.b64decode(data_url)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    # Downscale large frames: faster detection with negligible accuracy loss
    img.thumbnail((640, 640))
    return np.array(img)


def extract_encoding(rgb_image):
    """Detect a face and return (encoding, error_message).

    Exactly one face must be present, otherwise an error is returned.
    """
    locations = face_recognition.face_locations(rgb_image, model="hog")
    if len(locations) == 0:
        return None, "No face detected. Face the camera in good lighting."
    if len(locations) > 1:
        return None, "Multiple faces detected. Only the voter should be in frame."
    encoding = face_recognition.face_encodings(rgb_image, known_face_locations=locations)[0]
    return encoding, None


def load_encodings(voter_row):
    return [np.array(e) for e in json.loads(voter_row["encodings"])]


def best_match(encoding, voters, tolerance):
    """1:N identification. Returns (voter_row, distance) or (None, best_distance)."""
    best_voter, best_dist = None, 1.0
    for voter in voters:
        known = load_encodings(voter)
        if not known:
            continue
        dist = float(np.min(face_recognition.face_distance(known, encoding)))
        if dist < best_dist:
            best_voter, best_dist = voter, dist
    if best_voter is not None and best_dist <= tolerance:
        return best_voter, best_dist
    return None, best_dist


def confidence_from_distance(distance, tolerance):
    """Rough 0-100 % confidence figure for display purposes."""
    return round(max(0.0, min(1.0, 1 - distance / (tolerance * 2))) * 100, 1)
