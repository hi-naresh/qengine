import json
from starlette.responses import JSONResponse
import qengine.helpers as jh
from qengine.services import transformers


def get_notification_api_keys(user_id: str = None) -> JSONResponse:
    from qengine.services.db import database
    database.open_connection()

    from qengine.models.NotificationApiKeys import NotificationApiKeys

    try:
        # fetch notification api keys, filtered by user_id if provided
        query = NotificationApiKeys.select()
        if user_id:
            query = query.where(NotificationApiKeys.user_id == user_id)
        api_keys = query
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    # transform each api_key using transformers.get_notification_api_key()
    api_keys = [transformers.get_notification_api_key(api_key) for api_key in api_keys]

    database.close_connection()

    return JSONResponse({
        'data': api_keys
    }, status_code=200)


def store_notification_api_keys(
        name: str,
        driver: str,
        fields: dict,
        user_id: str = None,
) -> JSONResponse:
    from qengine.services.db import database
    database.open_connection()

    from qengine.models.NotificationApiKeys import NotificationApiKeys

    # check if the api key already exists
    if NotificationApiKeys.select().where(NotificationApiKeys.name == name).exists():
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': f'API key for the name "{name}" already exists. Please choose another driver.'
        }, status_code=400)

    try:
        # create the record
        notification_api_key: NotificationApiKeys = NotificationApiKeys.create(
            id=jh.generate_unique_id(),
            name=name,
            driver=driver,
            fields=json.dumps(fields),
            user_id=user_id,
            created_at=jh.now_to_datetime()
        )
    except ValueError as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=400)
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    database.close_connection()

    return JSONResponse({
        'status': 'success',
        'message': 'Notification API key has been stored successfully.',
        'data': transformers.get_notification_api_key(notification_api_key)
    }, status_code=200)


def delete_notification_api_keys(notification_api_key_id: str, user_id: str = None) -> JSONResponse:
    from qengine.services.db import database
    database.open_connection()

    from qengine.models.NotificationApiKeys import NotificationApiKeys

    try:
        # delete the record, scoped to user if user_id provided
        query = NotificationApiKeys.delete().where(NotificationApiKeys.id == notification_api_key_id)
        if user_id:
            query = query.where(NotificationApiKeys.user_id == user_id)
        query.execute()
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    database.close_connection()

    return JSONResponse({
        'status': 'success',
        'message': 'Notification API key has been deleted successfully.'
    }, status_code=200)
