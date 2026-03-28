from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
from qengine.services.web import ConfigRequestJson
import qengine.helpers as jh

router = APIRouter(prefix="/config", tags=["Configuration"])


@router.post("/get")
def get_config(json_request: ConfigRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """
    Get the current configuration
    """
    from qengine.modes.data_provider import get_config as gc

    return JSONResponse({
        'data': gc(json_request.current_config, has_live=jh.has_live_trade_plugin())
    }, status_code=200)


@router.post("/update")
def update_config(json_request: ConfigRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """
    Update the configuration
    """
    from qengine.modes.data_provider import update_config as uc

    uc(json_request.current_config)

    return JSONResponse({'message': 'Updated configurations successfully'}, status_code=200)
