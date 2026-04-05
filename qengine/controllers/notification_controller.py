from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from qengine.services import auth as authenticator
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
from qengine.services.web import StoreNotificationApiKeyRequestJson, DeleteNotificationApiKeyRequestJson

router = APIRouter(prefix="/notification", tags=["Notification"])


@router.get("/api-keys")
def get_notification_api_keys(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Get all notification API keys.
    Admins see all keys (shared). Regular users see only their own.
    """

    if current_user.is_admin and not current_user.is_impersonating:
        user_id = None  # admins see all
    else:
        user_id = current_user.effective_user_id

    from qengine.modes.notification_api_keys import get_notification_api_keys

    return get_notification_api_keys(user_id=user_id)


@router.post("/api-keys/store")
def store_notification_api_keys(
        json_request: StoreNotificationApiKeyRequestJson,
        current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Store a new notification API key
    """

    from qengine.modes.notification_api_keys import store_notification_api_keys

    return store_notification_api_keys(
        json_request.name, json_request.driver, json_request.fields,
        user_id=current_user.effective_user_id
    )


@router.post("/api-keys/delete")
def delete_notification_api_keys(
        json_request: DeleteNotificationApiKeyRequestJson,
        current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Delete a notification API key
    """

    user_id = current_user.effective_user_id if not current_user.is_admin or current_user.is_impersonating else None

    from qengine.modes.notification_api_keys import delete_notification_api_keys

    return delete_notification_api_keys(json_request.id, user_id=user_id)
