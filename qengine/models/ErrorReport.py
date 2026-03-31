import peewee
import uuid
from qengine.services.db import database

if database.is_closed():
    database.open_connection()


class ErrorReport(peewee.Model):
    id = peewee.UUIDField(primary_key=True, default=uuid.uuid4)
    session_id = peewee.UUIDField(null=True, index=True)
    session_type = peewee.CharField(max_length=50, null=True)  # backtest, live, optimization, monte-carlo, system
    error_type = peewee.CharField(max_length=255, null=True)  # exception class name
    message = peewee.TextField()
    traceback = peewee.TextField(null=True)
    context = peewee.TextField(null=True)  # JSON: strategy, broker, symbol, etc.
    status = peewee.CharField(default='new', max_length=20)  # new, reviewed, submitted
    issue_id = peewee.UUIDField(null=True)  # linked issue if submitted
    user_id = peewee.UUIDField(null=True)
    created_at = peewee.BigIntegerField()

    class Meta:
        from qengine.services.db import database
        database = database.db
        indexes = (
            (('status', 'created_at'), False),
            (('session_type', 'created_at'), False),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)

    def to_dict(self):
        import json
        ctx = None
        if self.context:
            try:
                ctx = json.loads(self.context)
            except (json.JSONDecodeError, TypeError):
                ctx = self.context
        return {
            'id': str(self.id),
            'session_id': str(self.session_id) if self.session_id else None,
            'session_type': self.session_type,
            'error_type': self.error_type,
            'message': self.message,
            'traceback': self.traceback,
            'context': ctx,
            'status': self.status,
            'issue_id': str(self.issue_id) if self.issue_id else None,
            'user_id': str(self.user_id) if self.user_id else None,
            'created_at': self.created_at,
        }


# Create table if it doesn't exist
if database.is_open():
    ErrorReport.create_table(safe=True)
