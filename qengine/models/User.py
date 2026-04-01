import json
import peewee
import uuid
from qengine.services.db import database
import qengine.helpers as jh


ALL_FEATURES = [
    'dashboard', 'strategies', 'backtest', 'optimization',
    'monte_carlo', 'live', 'import_data', 'tools', 'llm_studio',
    'issues', 'settings'
]

DEFAULT_USER_FEATURES = [
    'dashboard', 'strategies', 'backtest',
    'monte_carlo', 'live', 'import_data', 'tools', 'llm_studio',
    'issues', 'settings'
]


if database.is_closed():
    database.open_connection()


class User(peewee.Model):
    id = peewee.UUIDField(primary_key=True, default=uuid.uuid4)
    username = peewee.CharField(max_length=150, unique=True)
    name = peewee.CharField(max_length=255, default='')
    password_hash = peewee.CharField(max_length=255)
    role = peewee.CharField(default='user')  # 'admin' or 'user'
    is_active = peewee.BooleanField(default=True)
    allowed_features = peewee.TextField(null=True)
    deleted_at = peewee.BigIntegerField(null=True)
    deletion_stats = peewee.TextField(null=True)  # JSON snapshot of stats at deletion
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        from qengine.services.db import database

        database = database.db
        indexes = (
            (('username',), True),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)

    def get_features(self):
        """Return list of allowed features. Admin always gets ALL_FEATURES."""
        if self.role == 'admin':
            return ALL_FEATURES
        if self.allowed_features:
            try:
                return json.loads(self.allowed_features)
            except (json.JSONDecodeError, TypeError):
                pass
        return DEFAULT_USER_FEATURES

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def get_deletion_stats(self):
        if self.deletion_stats:
            try:
                return json.loads(self.deletion_stats)
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def to_dict(self):
        d = {
            'id': str(self.id),
            'username': self.username,
            'name': self.name,
            'role': self.role,
            'is_active': self.is_active,
            'allowed_features': self.get_features(),
            'deleted_at': self.deleted_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }
        if self.is_deleted:
            d['deletion_stats'] = self.get_deletion_stats()
        return d


# if database is open, create the table
if database.is_open():
    User.create_table(safe=True)


# # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # #

def get_user_by_id(user_id: str):
    try:
        return User.get(User.id == user_id)
    except User.DoesNotExist:
        return None


def get_user_by_username(username: str, include_deleted: bool = False):
    """Get user by username. By default excludes deleted users."""
    try:
        query = User.username == username
        if not include_deleted:
            query = query & User.deleted_at.is_null()
        return User.get(query)
    except User.DoesNotExist:
        return None


def create_user(user_id: str, username: str, password_hash: str, role: str = 'user', name: str = '') -> User:
    features = ALL_FEATURES if role == 'admin' else DEFAULT_USER_FEATURES
    d = {
        'id': user_id,
        'username': username,
        'name': name,
        'password_hash': password_hash,
        'role': role,
        'is_active': True,
        'allowed_features': json.dumps(features),
        'created_at': jh.now_to_timestamp(True),
        'updated_at': jh.now_to_timestamp(True),
    }
    User.insert(**d).execute()
    return get_user_by_id(user_id)


def get_all_users():
    """Return all users sorted: active first, then deleted, by creation date."""
    return list(User.select().order_by(
        peewee.fn.COALESCE(User.deleted_at, 0).asc(),
        User.created_at.asc()
    ))


def get_admin_user():
    try:
        return User.get(User.role == 'admin')
    except User.DoesNotExist:
        return None


def update_user(user_id: str, **kwargs):
    kwargs['updated_at'] = jh.now_to_timestamp(True)
    User.update(**kwargs).where(User.id == user_id).execute()


def get_users_by_ids(user_ids: list) -> dict:
    """Return a dict mapping user_id (str) -> username for a list of user_ids."""
    if not user_ids:
        return {}
    users = User.select(User.id, User.username).where(User.id.in_(user_ids))
    return {str(u.id): u.username for u in users}


def soft_delete_user(user_id: str, stats: dict = None):
    """Soft-delete: mark user as deleted, store stats snapshot, disable login."""
    updates = {
        'deleted_at': jh.now_to_timestamp(True),
        'is_active': False,
        'updated_at': jh.now_to_timestamp(True),
    }
    if stats:
        updates['deletion_stats'] = json.dumps(stats)
    User.update(**updates).where(User.id == user_id).execute()


def delete_user(user_id: str):
    """Hard delete — only used internally if truly needed."""
    User.delete().where(User.id == user_id).execute()
