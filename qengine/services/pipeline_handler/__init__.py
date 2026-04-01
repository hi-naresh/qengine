"""
Pipeline handler — manages pipeline directories with the same three-tier
ownership model as strategies: _shared/, _admin/, {user_id}/.

Each pipeline is a directory containing at minimum an __init__.py with a class
that extends Pipeline. Pipelines can also contain models, data files, configs,
and any other supporting files.
"""
import os
import re
import shutil
from starlette.responses import JSONResponse


PIPELINES_BASE = 'pipelines'
SHARED_DIR = '_shared'
ADMIN_DIR = '_admin'


def _sanitize_name(name: str) -> str:
    """Sanitize pipeline name to prevent path traversal."""
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    if not sanitized:
        raise ValueError('Invalid pipeline name')
    return sanitized


def _user_dir(user_id: str) -> str:
    return os.path.join(PIPELINES_BASE, str(user_id))


def _shared_dir() -> str:
    return os.path.join(PIPELINES_BASE, SHARED_DIR)


def _admin_dir() -> str:
    return os.path.join(PIPELINES_BASE, ADMIN_DIR)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    init_file = os.path.join(path, '__init__.py')
    if not os.path.isfile(init_file):
        with open(init_file, 'w') as f:
            f.write('')


def _list_pipelines_in(directory: str) -> list:
    if not os.path.isdir(directory):
        return []
    return [
        item for item in os.listdir(directory)
        if os.path.isdir(os.path.join(directory, item))
        and not item.startswith('.')
        and not item.startswith('__')
    ]


def find_pipeline_file(name: str) -> str:
    """
    Find a pipeline __init__.py anywhere in the pipelines tree.
    Used by backtest/live modes where user context is not available.
    """
    name = _sanitize_name(name)
    if not os.path.isdir(PIPELINES_BASE):
        return ''
    for special in (_shared_dir(), _admin_dir()):
        candidate = os.path.join(special, name, '__init__.py')
        if os.path.isfile(candidate):
            return candidate
    for item in os.listdir(PIPELINES_BASE):
        if item in (SHARED_DIR, ADMIN_DIR) or item.startswith('.') or item.startswith('__'):
            continue
        candidate = os.path.join(PIPELINES_BASE, item, name, '__init__.py')
        if os.path.isfile(candidate):
            return candidate
    return ''


def resolve_pipeline_path(name: str, user_id: str, search_all: bool = False, is_admin: bool = False) -> str:
    """
    Resolve a pipeline name to its filesystem path.
    Priority: user dir → shared → admin → other users (admin only).
    """
    name = _sanitize_name(name)
    user_path = os.path.join(_user_dir(user_id), name)
    if os.path.isdir(user_path):
        return user_path
    shared_path = os.path.join(_shared_dir(), name)
    if os.path.isdir(shared_path):
        return shared_path
    if is_admin or search_all:
        admin_path = os.path.join(_admin_dir(), name)
        if os.path.isdir(admin_path):
            return admin_path
    if search_all and os.path.isdir(PIPELINES_BASE):
        for item in os.listdir(PIPELINES_BASE):
            if item in (SHARED_DIR, ADMIN_DIR) or item.startswith('.') or item.startswith('__'):
                continue
            candidate = os.path.join(PIPELINES_BASE, item, name)
            if os.path.isdir(candidate):
                return candidate
    return ''


def _find_pipeline_subdir(pipeline_name: str) -> str:
    """
    Find the subdirectory (user_id or _shared/_admin) that contains a pipeline.
    Returns the subdirectory name, or empty string if using legacy flat layout.
    """
    if not os.path.isdir(PIPELINES_BASE):
        return ''
    # Check legacy flat path
    if os.path.isfile(os.path.join(PIPELINES_BASE, pipeline_name, '__init__.py')):
        return ''
    # Search subdirectories
    for item in os.listdir(PIPELINES_BASE):
        item_path = os.path.join(PIPELINES_BASE, item)
        if os.path.isdir(item_path):
            candidate = os.path.join(item_path, pipeline_name, '__init__.py')
            if os.path.isfile(candidate):
                return item
    return ''


def generate(name: str, user_id: str) -> JSONResponse:
    """Create a new pipeline from the ExamplePipeline template."""
    name = _sanitize_name(name)
    user_path = os.path.join(_user_dir(user_id), name)

    for check_path, label in [
        (user_path, ''),
        (os.path.join(_shared_dir(), name), ' (shared)'),
        (os.path.join(_admin_dir(), name), ' (admin)'),
    ]:
        if os.path.isdir(check_path):
            return JSONResponse({
                'status': 'error',
                'message': f'Pipeline "{name}" already exists{label}.'
            }, status_code=409)

    _ensure_dir(_user_dir(user_id))

    dirname = os.path.dirname(os.path.abspath(__file__))
    shutil.copytree(os.path.join(dirname, 'ExamplePipeline'), user_path)

    # Replace 'ExamplePipeline' with the new pipeline name
    init_path = os.path.join(user_path, '__init__.py')
    with open(init_path, 'rt') as f:
        data = f.read()
    data = data.replace('ExamplePipeline', name)
    with open(init_path, 'wt') as f:
        f.write(data)

    return JSONResponse({
        'status': 'success',
        'message': user_path
    })


def get_pipelines(user_id: str = None, is_admin: bool = False) -> JSONResponse:
    """List all pipelines visible to the user."""
    pipelines = []

    if is_admin and not user_id:
        if os.path.isdir(PIPELINES_BASE):
            for item in sorted(os.listdir(PIPELINES_BASE)):
                item_path = os.path.join(PIPELINES_BASE, item)
                if not os.path.isdir(item_path) or item.startswith('.') or item.startswith('__'):
                    continue
                if item == SHARED_DIR:
                    for p in _list_pipelines_in(item_path):
                        pipelines.append({'name': p, 'owner': 'shared'})
                elif item == ADMIN_DIR:
                    for p in _list_pipelines_in(item_path):
                        pipelines.append({'name': p, 'owner': 'admin'})
                else:
                    for p in _list_pipelines_in(item_path):
                        pipelines.append({'name': p, 'owner': item})
    else:
        if user_id:
            for p in _list_pipelines_in(_user_dir(user_id)):
                pipelines.append({'name': p, 'owner': user_id})
            for p in _list_pipelines_in(_shared_dir()):
                pipelines.append({'name': p, 'owner': 'shared'})
            if is_admin:
                for p in _list_pipelines_in(_admin_dir()):
                    pipelines.append({'name': p, 'owner': 'admin'})

    # Resolve user_id owners to usernames
    special_owners = {'shared', 'admin'}
    owner_ids = set(p['owner'] for p in pipelines if p['owner'] and p['owner'] not in special_owners)
    if owner_ids:
        try:
            from qengine.models.User import get_users_by_ids
            user_map = get_users_by_ids(list(owner_ids))
            for p in pipelines:
                if p['owner'] and p['owner'] not in special_owners:
                    p['owner_username'] = user_map.get(p['owner'])
        except Exception:
            pass

    return JSONResponse({
        'status': 'success',
        'pipelines': pipelines
    })


def get_pipeline(name: str, user_id: str, is_admin: bool = False) -> JSONResponse:
    """Get pipeline source code."""
    name = _sanitize_name(name)
    path = resolve_pipeline_path(name, user_id, search_all=is_admin, is_admin=is_admin)

    if not path:
        return JSONResponse({
            'status': 'error',
            'message': f'Pipeline "{name}" does not exist.'
        }, status_code=404)

    init_path = os.path.join(path, '__init__.py')
    with open(init_path, 'rt') as f:
        content = f.read()

    # List all files in the pipeline directory (for complex pipelines)
    files = []
    for root, dirs, filenames in os.walk(path):
        for fn in filenames:
            if fn.startswith('.') or fn.endswith('.pyc'):
                continue
            rel = os.path.relpath(os.path.join(root, fn), path)
            files.append(rel)

    is_shared = path.startswith(_shared_dir())
    is_admin_shared = path.startswith(_admin_dir())
    owner = 'shared' if is_shared else 'admin' if is_admin_shared else user_id
    readonly = is_shared or (is_admin_shared and not is_admin)

    return JSONResponse({
        'status': 'success',
        'content': content,
        'owner': owner,
        'readonly': readonly,
        'files': files,
    })


def save_pipeline(name: str, content: str, user_id: str, is_admin: bool = False) -> JSONResponse:
    """Save pipeline source code."""
    name = _sanitize_name(name)

    shared_path = os.path.join(_shared_dir(), name)
    if os.path.isdir(shared_path):
        user_path = os.path.join(_user_dir(user_id), name)
        if not os.path.isdir(user_path):
            return JSONResponse({
                'status': 'error',
                'message': f'Pipeline "{name}" is shared and read-only. Fork it first.'
            }, status_code=403)

    admin_path = os.path.join(_admin_dir(), name)
    if os.path.isdir(admin_path) and not is_admin:
        return JSONResponse({
            'status': 'error',
            'message': f'Pipeline "{name}" is admin-only and read-only.'
        }, status_code=403)

    path = resolve_pipeline_path(name, user_id, search_all=is_admin, is_admin=is_admin)
    if not path:
        return JSONResponse({
            'status': 'error',
            'message': f'Pipeline "{name}" does not exist.'
        }, status_code=404)

    with open(os.path.join(path, '__init__.py'), 'wt') as f:
        f.write(content)

    return JSONResponse({
        'status': 'success',
        'message': f'Pipeline "{name}" has been saved.'
    })


def delete_pipeline(name: str, user_id: str, is_admin: bool = False) -> JSONResponse:
    """Delete a pipeline."""
    name = _sanitize_name(name)

    shared_path = os.path.join(_shared_dir(), name)
    if os.path.isdir(shared_path) and not is_admin:
        user_path = os.path.join(_user_dir(user_id), name)
        if not os.path.isdir(user_path):
            return JSONResponse({
                'status': 'error',
                'message': f'Pipeline "{name}" is shared and cannot be deleted.'
            }, status_code=403)

    admin_path = os.path.join(_admin_dir(), name)
    if os.path.isdir(admin_path) and not is_admin:
        return JSONResponse({
            'status': 'error',
            'message': f'Pipeline "{name}" is admin-only and cannot be deleted.'
        }, status_code=403)

    path = resolve_pipeline_path(name, user_id, search_all=is_admin, is_admin=is_admin)
    if not path:
        return JSONResponse({
            'status': 'error',
            'message': f'Pipeline "{name}" does not exist.'
        }, status_code=404)

    shutil.rmtree(path)

    return JSONResponse({
        'status': 'success',
        'message': f'Pipeline "{name}" has been deleted.'
    })


def ensure_shared_example() -> None:
    """Ensure the GridPilot pipeline exists in _shared/."""
    shared_dir = _shared_dir()
    grid_path = os.path.join(shared_dir, 'GridPilot')
    if os.path.isdir(grid_path):
        return
    # GridPilot is shipped with the repo in pipelines/_shared/GridPilot/
    # Nothing to do if it already exists in the filesystem
