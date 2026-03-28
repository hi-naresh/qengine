import peewee
import uuid
from qengine.services.db import database
import qengine.helpers as jh


if database.is_closed():
    database.open_connection()


class QuotaRequest(peewee.Model):
    id = peewee.UUIDField(primary_key=True, default=uuid.uuid4)
    user_id = peewee.UUIDField(index=True)
    feature = peewee.CharField()  # 'backtest', 'optimization', 'monte_carlo', 'live'
    requested_runs = peewee.IntegerField()  # how many runs they want
    reason = peewee.TextField(default='')
    status = peewee.CharField(default='pending')  # 'pending', 'approved', 'denied'
    admin_note = peewee.TextField(default='')
    reviewed_by = peewee.UUIDField(null=True)
    reviewed_at = peewee.BigIntegerField(null=True)
    created_at = peewee.BigIntegerField()

    class Meta:
        from qengine.services.db import database

        database = database.db

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
            'requested_runs': self.requested_runs,
            'reason': self.reason,
            'status': self.status,
            'admin_note': self.admin_note,
            'reviewed_by': str(self.reviewed_by) if self.reviewed_by else None,
            'reviewed_at': self.reviewed_at,
            'created_at': self.created_at,
        }


# if database is open, create the table
if database.is_open():
    QuotaRequest.create_table(safe=True)


# # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # #

def create_quota_request(user_id: str, feature: str, requested_runs: int, reason: str = '') -> QuotaRequest:
    now = jh.now_to_timestamp(True)
    req_id = uuid.uuid4()
    QuotaRequest.insert(
        id=req_id,
        user_id=user_id,
        feature=feature,
        requested_runs=requested_runs,
        reason=reason,
        status='pending',
        created_at=now,
    ).execute()
    return QuotaRequest.get(QuotaRequest.id == req_id)


def get_pending_requests():
    return list(QuotaRequest.select().where(
        QuotaRequest.status == 'pending'
    ).order_by(QuotaRequest.created_at.desc()))


def get_requests_for_user(user_id: str):
    return list(QuotaRequest.select().where(
        QuotaRequest.user_id == user_id
    ).order_by(QuotaRequest.created_at.desc()).limit(20))


def review_request(request_id: str, status: str, admin_id: str, admin_note: str = ''):
    now = jh.now_to_timestamp(True)
    QuotaRequest.update(
        status=status,
        reviewed_by=admin_id,
        reviewed_at=now,
        admin_note=admin_note,
    ).where(QuotaRequest.id == request_id).execute()
    try:
        return QuotaRequest.get(QuotaRequest.id == request_id)
    except QuotaRequest.DoesNotExist:
        return None


def has_pending_request(user_id: str, feature: str) -> bool:
    return QuotaRequest.select().where(
        QuotaRequest.user_id == user_id,
        QuotaRequest.feature == feature,
        QuotaRequest.status == 'pending'
    ).exists()
