from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from qengine.helpers import get_os
from qengine.services.auth_dependency import get_current_user, CurrentUser
from qengine.services.lsp import LSP_DEFAULT_PORT

router = APIRouter(prefix='/lsp-config', tags=['LSP Configuration'])

@router.get("")
def get_lsp_config(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:

    from qengine.services.env import ENV_VALUES

    # Check if formatting is available on the current platform
    # Formatting is only available on non-windows platforms
    isFormattingAvailable = get_os() != 'windows'
    
    return JSONResponse(
        {'ws_port': ENV_VALUES['LSP_PORT'] if 'LSP_PORT' in ENV_VALUES else LSP_DEFAULT_PORT,
         'ws_path':'/lsp',
         'is_formatting_available': isFormattingAvailable}, status_code=200)