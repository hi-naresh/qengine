import os
import re
import shutil
from starlette.responses import JSONResponse


STRATEGIES_BASE = 'strategies'
SHARED_DIR = '_shared'
ADMIN_DIR = '_admin'


def _sanitize_strategy_name(name: str) -> str:
    """Sanitize strategy name to prevent path traversal."""
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    if not sanitized:
        raise ValueError('Invalid strategy name')
    return sanitized


def _user_dir(user_id: str) -> str:
    """Return the strategy directory for a given user."""
    return os.path.join(STRATEGIES_BASE, str(user_id))


def _shared_dir() -> str:
    """Return the shared strategy directory (available to all users)."""
    return os.path.join(STRATEGIES_BASE, SHARED_DIR)


def _admin_dir() -> str:
    """Return the admin-only shared strategy directory."""
    return os.path.join(STRATEGIES_BASE, ADMIN_DIR)


def _ensure_dir(path: str) -> None:
    """Create directory if it doesn't exist. Also creates __init__.py for Python imports."""
    os.makedirs(path, exist_ok=True)
    # Ensure __init__.py exists so Python can import strategies from this dir
    init_file = os.path.join(path, '__init__.py')
    if not os.path.isfile(init_file):
        with open(init_file, 'w') as f:
            f.write('')


def _list_strategies_in(directory: str) -> list:
    """List strategy folder names in a directory."""
    if not os.path.isdir(directory):
        return []
    return [
        item for item in os.listdir(directory)
        if os.path.isdir(os.path.join(directory, item))
        and not item.startswith('.')
        and not item.startswith('__')
    ]


def find_strategy_file(name: str) -> str:
    """
    Find a strategy __init__.py anywhere in the strategies tree.
    Searches _shared, _admin, all user dirs. Returns path to __init__.py or empty string.
    Used by backtest/optimize/monte-carlo modes where user context is not available.
    """
    name = _sanitize_strategy_name(name)
    if not os.path.isdir(STRATEGIES_BASE):
        return ''
    # Check shared and admin dirs first
    for special in (_shared_dir(), _admin_dir()):
        candidate = os.path.join(special, name, '__init__.py')
        if os.path.isfile(candidate):
            return candidate
    # Check all user dirs
    for item in os.listdir(STRATEGIES_BASE):
        if item in (SHARED_DIR, ADMIN_DIR) or item.startswith('.') or item.startswith('__'):
            continue
        candidate = os.path.join(STRATEGIES_BASE, item, name, '__init__.py')
        if os.path.isfile(candidate):
            return candidate
    return ''


def resolve_strategy_path(name: str, user_id: str, search_all: bool = False, is_admin: bool = False) -> str:
    """
    Resolve a strategy name to its filesystem path.
    Checks user dir first, then shared dir, then _admin dir (for admins).
    If search_all=True, also searches all other user directories (for admin).
    Returns the path to the strategy directory (not __init__.py).
    Returns empty string if not found.
    """
    name = _sanitize_strategy_name(name)
    # Check user's own directory first
    user_path = os.path.join(_user_dir(user_id), name)
    if os.path.isdir(user_path):
        return user_path
    # Check shared directory
    shared_path = os.path.join(_shared_dir(), name)
    if os.path.isdir(shared_path):
        return shared_path
    # Check admin-only shared directory
    if is_admin or search_all:
        admin_path = os.path.join(_admin_dir(), name)
        if os.path.isdir(admin_path):
            return admin_path
    # Admin fallback: search all user directories
    if search_all and os.path.isdir(STRATEGIES_BASE):
        for item in os.listdir(STRATEGIES_BASE):
            if item in (SHARED_DIR, ADMIN_DIR) or item.startswith('.') or item.startswith('__'):
                continue
            candidate = os.path.join(STRATEGIES_BASE, item, name)
            if os.path.isdir(candidate):
                return candidate
    return ''


def generate(name: str, user_id: str) -> JSONResponse:
    name = _sanitize_strategy_name(name)
    user_path = os.path.join(_user_dir(user_id), name)

    # Check both user dir and shared dir for duplicates
    if os.path.isdir(user_path):
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" already exists.'
        }, status_code=409)

    shared_path = os.path.join(_shared_dir(), name)
    if os.path.isdir(shared_path):
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" already exists (shared).'
        }, status_code=409)

    admin_path = os.path.join(_admin_dir(), name)
    if os.path.isdir(admin_path):
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" already exists (admin).'
        }, status_code=409)

    # Ensure user directory exists
    _ensure_dir(_user_dir(user_id))

    # Generate from ExampleStrategy template
    dirname, filename = os.path.split(os.path.abspath(__file__))
    shutil.copytree(f'{dirname}/ExampleStrategy', user_path)

    # Replace 'ExampleStrategy' with the name of the new strategy
    with open(f"{user_path}/__init__.py", "rt") as fin:
        data = fin.read()
        data = data.replace('ExampleStrategy', name)
    with open(f"{user_path}/__init__.py", "wt") as fin:
        fin.write(data)

    return JSONResponse({
        'status': 'success',
        'message': user_path
    })


def get_strategies(user_id: str = None, is_admin: bool = False) -> JSONResponse:
    strategies = []

    if is_admin and not user_id:
        # Admin (not impersonating): show ALL users' strategies with owner labels
        if os.path.isdir(STRATEGIES_BASE):
            for item in sorted(os.listdir(STRATEGIES_BASE)):
                item_path = os.path.join(STRATEGIES_BASE, item)
                if not os.path.isdir(item_path) or item.startswith('.') or item.startswith('__'):
                    continue
                if item == SHARED_DIR:
                    for s in _list_strategies_in(item_path):
                        strategies.append({'name': s, 'owner': 'shared'})
                elif item == ADMIN_DIR:
                    for s in _list_strategies_in(item_path):
                        strategies.append({'name': s, 'owner': 'admin'})
                else:
                    # User directory - item is the user_id
                    for s in _list_strategies_in(item_path):
                        strategies.append({'name': s, 'owner': item})
    else:
        if user_id:
            # User's own strategies
            for s in _list_strategies_in(_user_dir(user_id)):
                strategies.append({'name': s, 'owner': user_id})
            # Shared strategies (available to all)
            for s in _list_strategies_in(_shared_dir()):
                strategies.append({'name': s, 'owner': 'shared'})
            # Admin-only strategies
            if is_admin:
                for s in _list_strategies_in(_admin_dir()):
                    strategies.append({'name': s, 'owner': 'admin'})

    # Resolve user_id owners to usernames
    special_owners = {'shared', 'admin'}
    owner_ids = set(s['owner'] for s in strategies if s['owner'] and s['owner'] not in special_owners)
    if owner_ids:
        from qengine.models.User import get_users_by_ids
        user_map = get_users_by_ids(list(owner_ids))
        for s in strategies:
            if s['owner'] and s['owner'] not in special_owners:
                s['owner_username'] = user_map.get(s['owner'])

    return JSONResponse({
        'status': 'success',
        'strategies': strategies
    })


def get_strategy(name: str, user_id: str, is_admin: bool = False) -> JSONResponse:
    name = _sanitize_strategy_name(name)
    path = resolve_strategy_path(name, user_id, search_all=is_admin, is_admin=is_admin)

    if not path:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" does not exist.'
        }, status_code=404)

    with open(f"{path}/__init__.py", "rt") as fin:
        content = fin.read()

    # Determine if this is a shared or admin-shared strategy
    is_shared = path.startswith(_shared_dir())
    is_admin_shared = path.startswith(_admin_dir())
    owner = 'shared' if is_shared else 'admin' if is_admin_shared else user_id
    # Shared = readonly for everyone; admin-shared = editable by admin only
    readonly = is_shared or (is_admin_shared and not is_admin)

    return JSONResponse({
        'status': 'success',
        'content': content,
        'owner': owner,
        'readonly': readonly,
    })


def save_strategy(name: str, content: str, user_id: str, is_admin: bool = False) -> JSONResponse:
    name = _sanitize_strategy_name(name)

    # Cannot save to shared (read-only for everyone)
    shared_path = os.path.join(_shared_dir(), name)
    if os.path.isdir(shared_path):
        user_path = os.path.join(_user_dir(user_id), name)
        if not os.path.isdir(user_path):
            return JSONResponse({
                'status': 'error',
                'message': f'Strategy "{name}" is shared and read-only. Fork it first.'
            }, status_code=403)

    # Admin-shared: only admin can save
    admin_path = os.path.join(_admin_dir(), name)
    if os.path.isdir(admin_path) and not is_admin:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" is admin-only and read-only.'
        }, status_code=403)

    # Resolve the actual path (admin can edit admin-shared and other users' strategies)
    path = resolve_strategy_path(name, user_id, search_all=is_admin, is_admin=is_admin)
    if not path:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" does not exist.'
        }, status_code=404)

    with open(f"{path}/__init__.py", "wt") as fin:
        fin.write(content)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{name}" has been saved.'
    })


def import_strategy(name: str, code: str, user_id: str) -> JSONResponse:
    # Sanitize strategy name
    sanitized_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    sanitized_name = re.sub(r'_+', '_', sanitized_name)
    sanitized_name = sanitized_name.strip('_')

    if not sanitized_name:
        return JSONResponse({
            'status': 'error',
            'message': 'Invalid strategy name'
        }, status_code=400)

    # Ensure user directory exists
    _ensure_dir(_user_dir(user_id))

    user_path = os.path.join(_user_dir(user_id), sanitized_name)

    # Check if strategy already exists in user dir or shared
    if os.path.isdir(user_path):
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{sanitized_name}" already exists.'
        }, status_code=409)

    shared_path = os.path.join(_shared_dir(), sanitized_name)
    if os.path.isdir(shared_path):
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{sanitized_name}" already exists (shared).'
        }, status_code=409)

    admin_path = os.path.join(_admin_dir(), sanitized_name)
    if os.path.isdir(admin_path):
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{sanitized_name}" already exists (admin).'
        }, status_code=409)

    # Create strategy directory
    os.makedirs(user_path, exist_ok=True)

    # Write the strategy code
    with open(f"{user_path}/__init__.py", "wt") as f:
        f.write(code)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{sanitized_name}" has been imported.',
        'path': user_path,
        'name': sanitized_name
    })


def delete_strategy(name: str, user_id: str, is_admin: bool = False) -> JSONResponse:
    name = _sanitize_strategy_name(name)

    # Cannot delete shared strategies (unless admin)
    shared_path = os.path.join(_shared_dir(), name)
    if os.path.isdir(shared_path) and not is_admin:
        user_path = os.path.join(_user_dir(user_id), name)
        if not os.path.isdir(user_path):
            return JSONResponse({
                'status': 'error',
                'message': f'Strategy "{name}" is shared and cannot be deleted.'
            }, status_code=403)

    # Cannot delete admin-shared strategies (unless admin)
    admin_path = os.path.join(_admin_dir(), name)
    if os.path.isdir(admin_path) and not is_admin:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" is admin-only and cannot be deleted.'
        }, status_code=403)

    # Resolve path (admin can delete other users' strategies)
    path = resolve_strategy_path(name, user_id, search_all=is_admin, is_admin=is_admin)
    if not path:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" does not exist.'
        }, status_code=404)

    shutil.rmtree(path)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{name}" has been deleted.'
    })


def ensure_shared_example() -> None:
    """
    Ensure the Example strategy exists in _shared/ so all users have access.
    Creates it from the ExampleStrategy template if missing.
    """
    shared_dir = _shared_dir()
    example_path = os.path.join(shared_dir, 'Example')
    if os.path.isdir(example_path):
        return  # Already exists

    _ensure_dir(shared_dir)
    dirname = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(dirname, 'ExampleStrategy')
    if os.path.isdir(template_path):
        shutil.copytree(template_path, example_path)


def migrate_existing_strategies() -> None:
    """
    One-time migration: move existing flat strategies into user-scoped directories.
    - Known example strategies go to _shared/
    - Other strategies go to the first admin user's directory
    """
    shared_dir = _shared_dir()
    example_strategies = {'Example'}

    if not os.path.isdir(STRATEGIES_BASE):
        return

    items = os.listdir(STRATEGIES_BASE)
    # Check if migration is needed: are there any strategy dirs at the top level
    # that aren't user dirs or _shared?
    flat_strategies = []
    for item in items:
        item_path = os.path.join(STRATEGIES_BASE, item)
        if not os.path.isdir(item_path):
            continue
        if item.startswith('.') or item.startswith('__') or item in (SHARED_DIR, ADMIN_DIR):
            continue
        # Check if this looks like a strategy (has __init__.py) vs a user dir
        # User dirs contain subdirectories that have __init__.py
        init_path = os.path.join(item_path, '__init__.py')
        if os.path.isfile(init_path):
            flat_strategies.append(item)

    if not flat_strategies:
        return  # Already migrated or nothing to migrate

    # Ensure strategies base has __init__.py for Python imports
    base_init = os.path.join(STRATEGIES_BASE, '__init__.py')
    if not os.path.isfile(base_init):
        with open(base_init, 'w') as f:
            f.write('')

    # Get admin user ID for non-example strategies
    admin_user_id = None
    try:
        from qengine.models.User import get_admin_user
        admin = get_admin_user()
        if admin:
            admin_user_id = str(admin.id)
    except Exception:
        pass

    if not admin_user_id:
        admin_user_id = 'legacy'

    for strategy_name in flat_strategies:
        src = os.path.join(STRATEGIES_BASE, strategy_name)
        if strategy_name in example_strategies:
            # Move to shared
            _ensure_dir(shared_dir)
            dst = os.path.join(shared_dir, strategy_name)
        else:
            # Move to admin user's directory
            _ensure_dir(_user_dir(admin_user_id))
            dst = os.path.join(_user_dir(admin_user_id), strategy_name)

        if not os.path.exists(dst):
            shutil.move(src, dst)
