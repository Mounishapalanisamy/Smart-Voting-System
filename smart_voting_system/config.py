import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-in-production")
    DATABASE = os.path.join(BASE_DIR, "voting.db")

    # Face recognition settings
    FACE_TOLERANCE = 0.50          # lower = stricter (0.6 is the library default)
    MIN_REGISTRATION_IMAGES = 3    # face samples required per voter
    DUPLICATE_FACE_TOLERANCE = 0.45  # block the same face registering twice
    VERIFICATION_VALID_SECONDS = 120  # how long a verified session may cast a vote

    # Admin credentials (override with environment variables)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
