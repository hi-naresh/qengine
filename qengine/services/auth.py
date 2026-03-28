import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.responses import JSONResponse

from qengine.services.env import ENV_VALUES


# JWT config
def _get_jwt_secret():
    return ENV_VALUES.get('JWT_SECRET', ENV_VALUES.get('PASSWORD', 'change-me-in-production'))


def _get_jwt_expiration_hours():
    return int(ENV_VALUES.get('JWT_EXPIRATION_HOURS', '24'))


# --- Password hashing (PBKDF2-SHA256, no external dependency) ---

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
    return f"pbkdf2:sha256:100000${salt.hex()}${dk.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        parts = password_hash.split('$')
        if len(parts) != 3:
            return False
        salt = bytes.fromhex(parts[1])
        stored_dk = parts[2]
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
        return hmac.compare_digest(dk.hex(), stored_dk)
    except Exception:
        return False


# --- JWT tokens ---

def create_jwt(user_id: str, role: str, username: str, impersonating_user_id: str = None, impersonating_username: str = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'user_id': str(user_id),
        'role': role,
        'username': username,
        'iat': now,
        'exp': now + timedelta(hours=_get_jwt_expiration_hours()),
    }
    if impersonating_user_id:
        payload['imp'] = str(impersonating_user_id)
        payload['imp_username'] = impersonating_username or ''
    return jwt.encode(payload, _get_jwt_secret(), algorithm='HS256')


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, _get_jwt_secret(), algorithms=['HS256'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# --- Legacy support (backward compat during migration) ---

def _legacy_is_valid_token(auth_token: str) -> bool:
    hashed_local_pass = hashlib.sha256(ENV_VALUES['PASSWORD'].encode('utf-8')).hexdigest()
    return hmac.compare_digest(auth_token, hashed_local_pass)


def is_valid_token(auth_token: str) -> bool:
    if not auth_token:
        return False

    # Try JWT first
    payload = decode_jwt(auth_token)
    if payload:
        return True

    # Fall back to legacy SHA256 token
    try:
        return _legacy_is_valid_token(auth_token)
    except Exception:
        return False


def password_to_token(password: str) -> JSONResponse:
    if password != ENV_VALUES['PASSWORD']:
        return unauthorized_response()

    auth_token = hashlib.sha256(password.encode('utf-8')).hexdigest()

    return JSONResponse({
        'auth_token': auth_token,
    }, status_code=200)


def unauthorized_response() -> JSONResponse:
    return JSONResponse({
        'message': "Unauthorized",
    }, status_code=401)


def forbidden_response(message: str = "Forbidden") -> JSONResponse:
    return JSONResponse({
        'message': message,
    }, status_code=403)


def get_access_token():
    if 'LICENSE_API_TOKEN' not in ENV_VALUES:
        return None
    if not ENV_VALUES['LICENSE_API_TOKEN']:
        return None
    return ENV_VALUES['LICENSE_API_TOKEN']


def user_validation(password: str) -> JSONResponse:
    if password != ENV_VALUES['PASSWORD']:
        return unauthorized_response()

    auth_token = hashlib.sha256(password.encode('utf-8')).hexdigest()

    return JSONResponse({
        'auth_token': auth_token,
    }, status_code=200)
