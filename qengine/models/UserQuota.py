import peewee
import uuid
from qengine.services.db import database
import qengine.helpers as jh


if database.is_closed():
    database.open_connection()


# Default quotas for newly registered users
DEFAULT_USER_QUOTAS = {
    'backtest': {'max_runs': 5, 'period': 'weekly'},
    'optimization': {'max_runs': 5, 'period': 'weekly'},
    'monte_carlo': {'max_runs': 5, 'period': 'weekly'},
    'live': {'max_runs': 5, 'period': 'weekly'},
}


class UserQuota(peewee.Model):
    id = peewee.UUIDField(primary_key=True, default=uuid.uuid4)
    user_id = peewee.UUIDField(index=True)
    feature = peewee.CharField()  # 'backtest', 'optimization', 'monte_carlo', 'live'
    max_runs = peewee.IntegerField(default=-1)  # -1 = unlimited
    used_runs = peewee.IntegerField(default=0)
    period = peewee.CharField(default='monthly')  # 'monthly', 'daily', 'lifetime'
    period_reset_at = peewee.BigIntegerField(null=True)
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        from qengine.services.db import database

        database = database.db
        indexes = (
            (('user_id', 'feature'), True),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)

    def to_dict(self):
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'feature': self.feature,
            'max_runs': self.max_runs,
            'used_runs': self.used_runs,
            'period': self.period,
            'period_reset_at': self.period_reset_at,
        }


# if database is open, create the table
if database.is_open():
    UserQuota.create_table(safe=True)


# # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # #

def seed_default_quotas(user_id: str):
    now = jh.now_to_timestamp(True)
    for feature, config in DEFAULT_USER_QUOTAS.items():
        # Calculate next month reset for monthly quotas
        period_reset_at = None
        if config['period'] == 'weekly':
            period_reset_at = now + (7 * 24 * 60 * 60 * 1000)
        elif config['period'] == 'monthly':
            period_reset_at = now + (30 * 24 * 60 * 60 * 1000)

        try:
            UserQuota.insert(
                id=uuid.uuid4(),
                user_id=user_id,
                feature=feature,
                max_runs=config['max_runs'],
                used_runs=0,
                period=config['period'],
                period_reset_at=period_reset_at,
                created_at=now,
                updated_at=now,
            ).execute()
        except peewee.IntegrityError:
            # Quota already exists for this user/feature
            pass


def get_quotas_for_user(user_id: str):
    return list(UserQuota.select().where(UserQuota.user_id == user_id))


def get_quota(user_id: str, feature: str):
    try:
        return UserQuota.get(
            UserQuota.user_id == user_id,
            UserQuota.feature == feature
        )
    except UserQuota.DoesNotExist:
        return None


def update_quota(user_id: str, feature: str, **kwargs):
    kwargs['updated_at'] = jh.now_to_timestamp(True)
    UserQuota.update(**kwargs).where(
        UserQuota.user_id == user_id,
        UserQuota.feature == feature
    ).execute()
