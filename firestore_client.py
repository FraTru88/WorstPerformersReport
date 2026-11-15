# firestore_client.py
import json
import os

import firebase_admin
from firebase_admin import credentials, firestore


def init_firestore():
    if not firebase_admin._apps:
        creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
        creds_path = os.getenv("FIREBASE_CREDENTIALS")
        if creds_json:
            cred = credentials.Certificate(json.loads(creds_json))
        elif creds_path:
            cred = credentials.Certificate(creds_path)
        else:
            raise RuntimeError("Imposta FIREBASE_CREDENTIALS o FIREBASE_CREDENTIALS_JSON.")
        firebase_admin.initialize_app(cred)
    return firestore.client()


def get_collection(db, name: str) -> list[tuple[object, dict]]:
    return [(d.reference, d.to_dict()) for d in db.collection(name).stream()]


def close_firestore():
    if firebase_admin._apps:
        firebase_admin.delete_app(firebase_admin.get_app())