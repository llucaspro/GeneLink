import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth

_firebase_app = None
_firestore_client = None


def _init_firebase():
    global _firebase_app, _firestore_client
    if _firebase_app is not None:
        return

    service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        cred_dict = json.loads(service_account_json)
        cred = credentials.Certificate(cred_dict)
    else:
        service_account_path = os.environ.get(
            "FIREBASE_SERVICE_ACCOUNT_PATH", "firebase-service-account.json"
        )
        if not os.path.exists(service_account_path):
            raise RuntimeError(
                "Firebase credentials not found. Set FIREBASE_SERVICE_ACCOUNT_JSON "
                "or FIREBASE_SERVICE_ACCOUNT_PATH environment variable."
            )
        cred = credentials.Certificate(service_account_path)

    _firebase_app = firebase_admin.initialize_app(cred)
    _firestore_client = firestore.client()
    print("[GeneLink] Firebase initialized.")


def get_firestore():
    _init_firebase()
    return _firestore_client


def get_firebase_auth():
    _init_firebase()
    return firebase_auth


def verify_firebase_token(id_token: str) -> dict:
    """Verify a Firebase ID token and return the decoded claims."""
    _init_firebase()
    try:
        decoded = firebase_auth.verify_id_token(id_token)
        return decoded
    except Exception as e:
        raise ValueError(f"Invalid Firebase token: {e}")
