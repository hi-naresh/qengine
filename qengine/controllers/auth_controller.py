from typing import Optional
from fastapi import APIRouter, Header, BackgroundTasks
from fastapi.responses import JSONResponse
import requests
from qengine.services.env import ENV_VALUES
from qengine.services import auth as authenticator
from qengine.services.multiprocessing import process_manager
from qengine.services.web import LoginRequestJson
import qengine.helpers as jh
from qengine.info import QENGINE_API2_URL

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
def login(json_request: LoginRequestJson):
    """
    Authenticate user with password and return a token
    """
    return authenticator.password_to_token(json_request.password)


@router.post("/user-validation")
def login(json_request: LoginRequestJson):
    """
    Authenticate user with password and return a token
    """
    return authenticator.user_validation(json_request.password)


@router.post("")
def auth(json_request: LoginRequestJson):
    """
    Authenticate user with password and return a token
    """
    return authenticator.password_to_token(json_request.password)


@router.post("/shutdown")
async def shutdown(background_tasks: BackgroundTasks, authorization: Optional[str] = Header(None)):
    """
    Shutdown the application
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    background_tasks.add_task(jh.terminate_app)
    return JSONResponse({'message': 'Shutting down...'})


@router.post("/marketplace-token")
async def marketplace_token(authorization: Optional[str] = Header(None)):
    """
    Exchange LICENSE_API_TOKEN for marketplace bearer token
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

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
