import uuid
from typing import Optional
from fastapi import APIRouter, Header, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
import requests
from qengine.services.env import ENV_VALUES
from qengine.services import auth as authenticator
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
from qengine.services.multiprocessing import process_manager
from qengine.services.web import LoginRequestJson, RegisterRequestJson, ImpersonateRequestJson, UpdateUserQuotaRequestJson, UpdateUserRequestJson, UpdateProfileRequestJson, DeleteAccountRequestJson, AdminCreateUserRequestJson, AdminDeleteUserRequestJson, AdminResetPasswordRequestJson, QuotaRequestJson, ReviewQuotaRequestJson
import qengine.helpers as jh
from qengine.info import QENGINE_API2_URL
from qengine.services.audit_logger import audit

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
def login(json_request: LoginRequestJson):
    """
    Authenticate user with username+password and return a JWT token.
    Falls back to legacy password-only auth if no username provided.
    """
    # New username+password flow
    if json_request.username:
        from qengine.models.User import get_user_by_username
        user = get_user_by_username(json_request.username, include_deleted=True)
        if not user:
            return authenticator.unauthorized_response()
        if user.is_deleted:
            return JSONResponse({'message': 'Account has been deleted'}, status_code=403)
        if not user.is_active:
            return JSONResponse({'message': 'Account is disabled'}, status_code=403)
        if not authenticator.verify_password(json_request.password, user.password_hash):
            audit('login_failed', username=json_request.username, detail='bad password')
            return authenticator.unauthorized_response()

        token = authenticator.create_jwt(str(user.id), user.role, user.username)
        audit('login', user_id=str(user.id), username=user.username)
        return JSONResponse({
            'auth_token': token,
            'user': user.to_dict(),
        })

    # Legacy password-only flow (backward compat)
    return authenticator.password_to_token(json_request.password)


@router.post("")
def auth(json_request: LoginRequestJson):
    """
    Authenticate user — alias for /login
    """
    return login(json_request)


@router.post("/user-validation")
def user_validation(json_request: LoginRequestJson):
    """
    Validate user credentials
    """
    return login(json_request)


@router.post("/register")
def register(json_request: RegisterRequestJson):
    """
    Register a new user with username+password. Returns JWT token.
    """
    from qengine.models.User import get_user_by_username, create_user
    from qengine.models.UserQuota import seed_default_quotas

    if not json_request.username or len(json_request.username) < 3:
        return JSONResponse({'message': 'Username must be at least 3 characters'}, status_code=400)
    if not json_request.password or len(json_request.password) < 6:
        return JSONResponse({'message': 'Password must be at least 6 characters'}, status_code=400)

    existing = get_user_by_username(json_request.username)
    if existing:
        return JSONResponse({'message': 'Username already taken'}, status_code=400)

    user_id = str(uuid.uuid4())
    password_hash = authenticator.hash_password(json_request.password)
    user = create_user(user_id, json_request.username, password_hash, role='user', name=json_request.name or '')

    # Seed default quotas for the new user
    seed_default_quotas(user_id)

    token = authenticator.create_jwt(user_id, 'user', json_request.username)
    audit('register', user_id=user_id, username=json_request.username)

    # Notify admins in real-time
    try:
        from qengine.services.redis import publish_admin_notification
        publish_admin_notification({
            'type': 'new_user',
            'username': json_request.username,
            'name': json_request.name or '',
        })
    except Exception:
        pass

    return JSONResponse({
        'auth_token': token,
        'user': user.to_dict(),
    })


@router.get("/me")
def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """
    Get current authenticated user info
    """
    from qengine.models.User import get_user_by_id
    from qengine.models.UserQuota import get_quotas_for_user

    user = get_user_by_id(current_user.id)
    if not user:
        return JSONResponse({'message': 'User not found'}, status_code=404)

    result = user.to_dict()
    # Include quotas
    quotas = get_quotas_for_user(current_user.id)
    result['quotas'] = [q.to_dict() for q in quotas]

    if current_user.is_impersonating:
        result['impersonating'] = {
            'user_id': current_user.effective_user_id,
            'username': current_user.impersonating_username,
        }

    return JSONResponse(result)


@router.post("/update-profile")
def update_profile(json_request: UpdateProfileRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """Update current user's profile (name, password)."""
    from qengine.models.User import get_user_by_id, update_user

    user = get_user_by_id(current_user.id)
    if not user:
        return JSONResponse({'message': 'User not found'}, status_code=404)

    updates = {}
    if json_request.name is not None:
        updates['name'] = json_request.name

    if json_request.password:
        if not json_request.current_password:
            return JSONResponse({'message': 'Current password is required'}, status_code=400)
        if not authenticator.verify_password(json_request.current_password, user.password_hash):
            return JSONResponse({'message': 'Current password is incorrect'}, status_code=400)
        if len(json_request.password) < 6:
            return JSONResponse({'message': 'New password must be at least 6 characters'}, status_code=400)
        updates['password_hash'] = authenticator.hash_password(json_request.password)

    if updates:
        update_user(current_user.id, **updates)
        changed = list(updates.keys())
        audit('profile_update', user_id=current_user.id, username=current_user.username,
              detail=', '.join(k.replace('password_hash', 'password') for k in changed))

    updated = get_user_by_id(current_user.id)
    token = authenticator.create_jwt(str(updated.id), updated.role, updated.username)
    return JSONResponse({
        'message': 'Profile updated',
        'auth_token': token,
        'user': updated.to_dict(),
    })


@router.post("/delete-my-data")
def delete_my_data(json_request: DeleteAccountRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """Delete all user data but keep the account. Issues are never deleted."""
    from qengine.models.User import get_user_by_id

    user = get_user_by_id(current_user.id)
    if not user:
        return JSONResponse({'message': 'User not found'}, status_code=404)
    if not authenticator.verify_password(json_request.password, user.password_hash):
        return JSONResponse({'message': 'Incorrect password'}, status_code=400)

    deleted = _delete_user_data(current_user.id)
    audit('delete_data', user_id=current_user.id, username=current_user.username,
          detail=f'tables: {", ".join(deleted.keys())}' if deleted else 'no data')
    return JSONResponse({'message': 'Your data has been deleted', 'deleted': deleted})


@router.post("/delete-account")
def delete_account(json_request: DeleteAccountRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """Delete user account. Optionally delete all data (issues are never deleted). Admins cannot delete themselves."""
    from qengine.models.User import get_user_by_id, soft_delete_user

    user = get_user_by_id(current_user.id)
    if not user:
        return JSONResponse({'message': 'User not found'}, status_code=404)
    if user.role == 'admin':
        return JSONResponse({'message': 'Admin account cannot be deleted'}, status_code=403)
    if not authenticator.verify_password(json_request.password, user.password_hash):
        return JSONResponse({'message': 'Incorrect password'}, status_code=400)

    # Snapshot stats before deleting data
    stats = _get_user_stats(current_user.id, is_admin=current_user.is_admin)

    if json_request.delete_data:
        _delete_user_data(current_user.id)

    # Delete user's strategy files
    try:
        import shutil, os
        from qengine.services.strategy_handler import STRATEGIES_BASE
        user_strat_dir = os.path.join(STRATEGIES_BASE, current_user.id)
        if os.path.isdir(user_strat_dir):
            shutil.rmtree(user_strat_dir)
    except Exception:
        pass

    # Soft-delete: keep user record with stats snapshot
    soft_delete_user(current_user.id, stats=stats)
    audit('delete_account', user_id=current_user.id, username=current_user.username,
          detail=f'with_data={json_request.delete_data}')

    return JSONResponse({'message': 'Account deleted'})


def _delete_user_data(user_id: str) -> dict:
    """Delete all data owned by a user. Issues and comments are NEVER deleted. Returns counts."""
    from qengine.services.db import database

    if database.is_closed():
        database.open_connection()

    # Tables to purge (with user_id column) — issues excluded
    tables = [
        'backtestsession', 'livesession', 'optimizationsession',
        'montecarlosession', 'exchange_api_keys', 'notificationapikeys',
        'opentab', 'option', 'closedtrade', 'order', 'liveequitysnapshot',
    ]

    deleted = {}
    for table in tables:
        if table in database.db.get_tables():
            try:
                count = database.db.execute_sql(
                    f"DELETE FROM {table} WHERE user_id = %s", (user_id,)
                ).rowcount
                if count > 0:
                    deleted[table] = count
            except Exception:
                pass

    return deleted


def _get_user_stats(user_id: str, is_admin: bool = False) -> dict:
    """Get resource counts for a user."""
    from qengine.services.db import database as _db
    if _db.is_closed():
        _db.open_connection()

    from qengine.models.BacktestSession import BacktestSession
    from qengine.models.LiveSession import LiveSession
    from qengine.models.OptimizationSession import OptimizationSession
    from qengine.models.MonteCarloSession import MonteCarloSession
    from qengine.models.ExchangeApiKeys import ExchangeApiKeys
    from qengine.models.NotificationApiKeys import NotificationApiKeys
    from qengine.models.Issue import Issue
    import json

    def count(model):
        try:
            return model.select().where(model.user_id == user_id).count()
        except Exception:
            return 0

    stats = {
        'backtest_sessions': count(BacktestSession),
        'live_sessions': count(LiveSession),
        'optimization_sessions': count(OptimizationSession),
        'monte_carlo_sessions': count(MonteCarloSession),
        'broker_keys': count(ExchangeApiKeys),
        'notification_keys': count(NotificationApiKeys),
        'issues': count(Issue),
    }

    # Strategy count
    try:
        import os
        from qengine.services.strategy_handler import STRATEGIES_BASE
        user_strat_dir = os.path.join(STRATEGIES_BASE, user_id)
        if os.path.isdir(user_strat_dir):
            stats['strategies'] = len([d for d in os.listdir(user_strat_dir) if os.path.isdir(os.path.join(user_strat_dir, d)) and not d.startswith('_')])
        else:
            stats['strategies'] = 0
    except Exception:
        stats['strategies'] = 0

    # LLM + Broker connection check from settings
    try:
        from qengine.controllers.settings_controller import _get_settings_from_db, _get_env_settings, ADMIN_SETTINGS_ID
        # Admins share settings (ADMIN_SETTINGS_ID + .env fallback). Regular users have their own.
        settings_uid = ADMIN_SETTINGS_ID if is_admin else user_id
        settings = _get_settings_from_db(settings_uid)
        if is_admin:
            env_settings = _get_env_settings()
            if not settings.get('llm') and env_settings.get('llm'):
                settings['llm'] = env_settings['llm']
            if not settings.get('brokers') and env_settings.get('brokers'):
                settings['brokers'] = env_settings['brokers']

        llm_conf = settings.get('llm', {})
        stats['llm_configured'] = bool(llm_conf.get('api_key') and llm_conf.get('provider'))
        stats['llm_provider'] = llm_conf.get('provider') if stats['llm_configured'] else None

        broker_settings = settings.get('brokers', {})
        stats['broker_names'] = [bid for bid, conf in broker_settings.items() if conf.get('api_key')]
        stats['broker_keys'] = len(stats['broker_names'])
    except Exception:
        stats['llm_configured'] = False
        stats['llm_provider'] = None
        stats['broker_names'] = []

    # Re-open DB connection (_get_settings_from_db closes it in its finally block)
    if _db.is_closed():
        _db.open_connection()

    # Also check legacy ExchangeApiKeys table
    try:
        keys = list(ExchangeApiKeys.select().where(ExchangeApiKeys.user_id == user_id))
        extra_names = [k.exchange_name for k in keys if k.exchange_name not in stats.get('broker_names', [])]
        if extra_names:
            stats['broker_names'] = stats.get('broker_names', []) + list(set(extra_names))
            stats['broker_keys'] = len(stats['broker_names'])
    except Exception:
        pass

    return stats


@router.post("/impersonate")
def impersonate(json_request: ImpersonateRequestJson, current_user: CurrentUser = Depends(require_admin)):
    """
    Admin only: get a JWT that views data as a specific user
    """
    from qengine.models.User import get_user_by_id
    target = get_user_by_id(json_request.user_id)
    if not target:
        return JSONResponse({'message': 'User not found'}, status_code=404)

    token = authenticator.create_jwt(
        current_user.id, current_user.role, current_user.username,
        impersonating_user_id=str(target.id),
        impersonating_username=target.username,
    )
    audit('impersonate', user_id=current_user.id, username=current_user.username,
          target_user_id=str(target.id), detail=f'as {target.username}')
    return JSONResponse({
        'auth_token': token,
        'impersonating': target.to_dict(),
    })


@router.post("/stop-impersonate")
def stop_impersonate(current_user: CurrentUser = Depends(require_admin)):
    """
    Admin only: stop impersonating and return to admin view
    """
    token = authenticator.create_jwt(current_user.id, current_user.role, current_user.username)
    return JSONResponse({'auth_token': token})


# --- Admin user management ---

@router.get("/users")
def list_users(current_user: CurrentUser = Depends(require_admin)):
    """
    Admin only: list all users
    """
    from qengine.models.User import get_all_users
    from qengine.models.UserQuota import get_quotas_for_user

    users = get_all_users()
    result = []
    for u in users:
        d = u.to_dict()

        if u.is_deleted:
            # Use archived stats snapshot for deleted users
            archived = u.get_deletion_stats() or {}
            d['stats'] = {
                'backtest_sessions': archived.get('backtest_sessions', 0),
                'live_sessions': archived.get('live_sessions', 0),
                'optimization_sessions': archived.get('optimization_sessions', 0),
                'monte_carlo_sessions': archived.get('monte_carlo_sessions', 0),
                'strategies': archived.get('strategies', 0),
                'issues': archived.get('issues', 0),
                'broker_keys': archived.get('broker_keys', 0),
                'notification_keys': archived.get('notification_keys', 0),
                'llm_configured': archived.get('llm_configured', False),
                'llm_provider': archived.get('llm_provider'),
                'broker_names': archived.get('broker_names', []),
            }
            d['connections'] = {
                'llm_configured': archived.get('llm_configured', False),
                'llm_provider': archived.get('llm_provider'),
                'broker_keys_count': archived.get('broker_keys', 0),
                'broker_names': archived.get('broker_names', []),
            }
            d['quotas'] = []
        else:
            d['quotas'] = [q.to_dict() for q in get_quotas_for_user(str(u.id))]
            user_stats = _get_user_stats(str(u.id), is_admin=(u.role == 'admin'))
            d['stats'] = {
                'backtest_sessions': user_stats['backtest_sessions'],
                'live_sessions': user_stats['live_sessions'],
                'optimization_sessions': user_stats['optimization_sessions'],
                'monte_carlo_sessions': user_stats['monte_carlo_sessions'],
                'strategies': user_stats['strategies'],
                'issues': user_stats['issues'],
                'broker_keys': user_stats['broker_keys'],
                'notification_keys': user_stats['notification_keys'],
                'llm_configured': user_stats['llm_configured'],
                'llm_provider': user_stats['llm_provider'],
                'broker_names': user_stats['broker_names'],
            }
            d['connections'] = {
                'llm_configured': user_stats['llm_configured'],
                'llm_provider': user_stats['llm_provider'],
                'broker_keys_count': user_stats['broker_keys'],
                'broker_names': user_stats['broker_names'],
            }
        result.append(d)
    return JSONResponse(result)


@router.post("/users/update")
def update_user_endpoint(json_request: UpdateUserRequestJson, current_user: CurrentUser = Depends(require_admin)):
    """
    Admin only: update user (activate/deactivate, change role)
    """
    from qengine.models.User import get_user_by_id, update_user

    target = get_user_by_id(json_request.user_id)
    if not target:
        return JSONResponse({'message': 'User not found'}, status_code=404)

    updates = {}
    if json_request.is_active is not None:
        updates['is_active'] = json_request.is_active
    if json_request.role is not None:
        updates['role'] = json_request.role
    if json_request.allowed_features is not None:
        import json
        from qengine.models.User import ALL_FEATURES
        # Validate feature names
        valid = [f for f in json_request.allowed_features if f in ALL_FEATURES]
        updates['allowed_features'] = json.dumps(valid)

    if updates:
        update_user(json_request.user_id, **updates)

    updated = get_user_by_id(json_request.user_id)
    return JSONResponse(updated.to_dict())


@router.post("/users/quota")
def update_user_quota(json_request: UpdateUserQuotaRequestJson, current_user: CurrentUser = Depends(require_admin)):
    """
    Admin only: update a user's quota for a feature
    """
    from qengine.models.UserQuota import update_quota, get_quota

    quota = get_quota(json_request.user_id, json_request.feature)
    if not quota:
        return JSONResponse({'message': 'Quota not found'}, status_code=404)

    update_quota(json_request.user_id, json_request.feature, max_runs=json_request.max_runs)
    return JSONResponse({'message': 'Quota updated'})


@router.post("/users/create")
def admin_create_user(json_request: AdminCreateUserRequestJson, current_user: CurrentUser = Depends(require_admin)):
    """Admin only: create a new user with specified role and features."""
    from qengine.models.User import get_user_by_username, create_user
    from qengine.models.UserQuota import seed_default_quotas

    if not json_request.username or len(json_request.username) < 3:
        return JSONResponse({'message': 'Username must be at least 3 characters'}, status_code=400)
    if not json_request.password or len(json_request.password) < 6:
        return JSONResponse({'message': 'Password must be at least 6 characters'}, status_code=400)

    existing = get_user_by_username(json_request.username)
    if existing:
        return JSONResponse({'message': 'Username already taken'}, status_code=400)

    user_id = str(uuid.uuid4())
    password_hash = authenticator.hash_password(json_request.password)
    role = json_request.role or 'user'
    user = create_user(user_id, json_request.username, password_hash, role=role)
    seed_default_quotas(user_id)
    audit('admin_create_user', user_id=current_user.id, username=current_user.username,
          target_user_id=user_id, detail=f'{json_request.username} (role={role})')

    return JSONResponse(user.to_dict())


@router.post("/users/delete")
def admin_delete_user(json_request: AdminDeleteUserRequestJson, current_user: CurrentUser = Depends(require_admin)):
    """Admin only: soft-delete a user and optionally their data. User record preserved with stats snapshot."""
    from qengine.models.User import get_user_by_id, soft_delete_user

    target = get_user_by_id(json_request.user_id)
    if not target:
        return JSONResponse({'message': 'User not found'}, status_code=404)
    if target.role == 'admin':
        return JSONResponse({'message': 'Cannot delete admin user'}, status_code=403)
    if target.is_deleted:
        return JSONResponse({'message': 'User already deleted'}, status_code=400)

    # Snapshot stats before deleting data
    stats = _get_user_stats(json_request.user_id)

    deleted = {}
    if json_request.delete_data:
        deleted = _delete_user_data(json_request.user_id)

    # Delete strategies
    try:
        import shutil, os
        from qengine.services.strategy_handler import STRATEGIES_BASE
        user_strat_dir = os.path.join(STRATEGIES_BASE, json_request.user_id)
        if os.path.isdir(user_strat_dir):
            shutil.rmtree(user_strat_dir)
    except Exception:
        pass

    # Soft-delete: keep user record with stats snapshot for history
    soft_delete_user(json_request.user_id, stats=stats)
    audit('admin_delete_user', user_id=current_user.id, username=current_user.username,
          target_user_id=json_request.user_id, detail=f'{target.username}, with_data={json_request.delete_data}')

    return JSONResponse({'message': 'User deleted', 'deleted_data': deleted})


@router.post("/users/reset-password")
def admin_reset_password(json_request: AdminResetPasswordRequestJson, current_user: CurrentUser = Depends(require_admin)):
    """Admin only: reset a user's password."""
    from qengine.models.User import get_user_by_id, update_user

    target = get_user_by_id(json_request.user_id)
    if not target:
        return JSONResponse({'message': 'User not found'}, status_code=404)
    if not json_request.new_password or len(json_request.new_password) < 6:
        return JSONResponse({'message': 'Password must be at least 6 characters'}, status_code=400)

    update_user(json_request.user_id, password_hash=authenticator.hash_password(json_request.new_password))
    audit('admin_reset_password', user_id=current_user.id, username=current_user.username,
          target_user_id=json_request.user_id, detail=target.username)
    return JSONResponse({'message': f'Password reset for {target.username}'})


# --- Quota Requests ---

@router.post("/quota-request")
def submit_quota_request(json_request: QuotaRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """User submits a request for more quota on a feature."""
    from qengine.models.QuotaRequest import create_quota_request, has_pending_request

    valid_features = {'backtest', 'optimization', 'monte_carlo', 'live'}
    if json_request.feature not in valid_features:
        return JSONResponse({'message': f'Invalid feature: {json_request.feature}'}, status_code=400)
    if json_request.requested_runs < 1:
        return JSONResponse({'message': 'Requested runs must be at least 1'}, status_code=400)

    if has_pending_request(current_user.effective_user_id, json_request.feature):
        return JSONResponse({'message': 'You already have a pending request for this feature'}, status_code=409)

    req = create_quota_request(
        current_user.effective_user_id,
        json_request.feature,
        json_request.requested_runs,
        json_request.reason,
    )

    # Notify admins
    try:
        from qengine.services.redis import publish_admin_notification
        publish_admin_notification({
            'type': 'quota_request',
            'username': current_user.username,
            'feature': json_request.feature,
            'requested_runs': json_request.requested_runs,
        })
    except Exception:
        pass

    return JSONResponse({'message': 'Request submitted', 'request': req.to_dict()})


@router.get("/quota-requests")
def get_quota_requests(current_user: CurrentUser = Depends(get_current_user)):
    """Get quota requests. Admin sees all pending; user sees their own."""
    from qengine.models.QuotaRequest import get_pending_requests, get_requests_for_user
    from qengine.models.User import get_users_by_ids

    if current_user.is_admin and not current_user.is_impersonating:
        requests_list = get_pending_requests()
        items = [r.to_dict() for r in requests_list]
        # Enrich with usernames
        user_ids = list(set(r['user_id'] for r in items))
        if user_ids:
            user_map = get_users_by_ids(user_ids)
            for item in items:
                item['username'] = user_map.get(item['user_id'])
        return JSONResponse({'requests': items})
    else:
        requests_list = get_requests_for_user(current_user.effective_user_id)
        return JSONResponse({'requests': [r.to_dict() for r in requests_list]})


@router.post("/quota-requests/review")
def review_quota_request(json_request: ReviewQuotaRequestJson, current_user: CurrentUser = Depends(require_admin)):
    """Admin approves or denies a quota request. On approve, updates the user's quota."""
    from qengine.models.QuotaRequest import review_request, QuotaRequest as QRModel
    from qengine.models.UserQuota import update_quota, get_quota

    if json_request.status not in ('approved', 'denied'):
        return JSONResponse({'message': 'Status must be approved or denied'}, status_code=400)

    try:
        qr = QRModel.get(QRModel.id == json_request.request_id)
    except QRModel.DoesNotExist:
        return JSONResponse({'message': 'Request not found'}, status_code=404)

    if qr.status != 'pending':
        return JSONResponse({'message': 'Request already reviewed'}, status_code=400)

    review_request(json_request.request_id, json_request.status, str(current_user.id), json_request.admin_note)

    if json_request.status == 'approved':
        new_limit = json_request.approved_runs if json_request.approved_runs is not None else qr.requested_runs
        quota = get_quota(str(qr.user_id), qr.feature)
        if quota:
            update_quota(str(qr.user_id), qr.feature, max_runs=new_limit)

    audit('review_quota_request', user_id=str(current_user.id), username=current_user.username,
          detail=f'{json_request.status} {qr.feature} for user {qr.user_id}, runs={json_request.approved_runs or qr.requested_runs}')

    return JSONResponse({'message': f'Request {json_request.status}'})


# --- Legacy endpoints ---

@router.post("/shutdown")
async def shutdown(background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(require_admin)):
    """
    Admin only: shutdown the application
    """
    background_tasks.add_task(jh.terminate_app)
    return JSONResponse({'message': 'Shutting down...'})


@router.post("/marketplace-token")
async def marketplace_token(current_user: CurrentUser = Depends(get_current_user)):
    """
    Exchange LICENSE_API_TOKEN for marketplace bearer token
    """
    if 'LICENSE_API_TOKEN' not in ENV_VALUES or not ENV_VALUES['LICENSE_API_TOKEN']:
        return JSONResponse({
            'status': 'error',
            'message': 'LICENSE_API_TOKEN not found in .env file'
        }, status_code=400)

    license_token = ENV_VALUES['LICENSE_API_TOKEN']

    try:
        response = requests.post(
            f'{QENGINE_API2_URL}/auth/exchange-token',
            json={'license_api_token': license_token},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return JSONResponse({
                'status': 'success',
                'access_token': data.get('access_token'),
                'user': data.get('user')
            })
        else:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to exchange token: {response.text}'
            }, status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to marketplace API: {str(e)}'
        }, status_code=500)
