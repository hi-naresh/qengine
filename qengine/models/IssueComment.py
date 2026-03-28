import peewee
import uuid
from qengine.services.db import database

if database.is_closed():
    database.open_connection()


class IssueComment(peewee.Model):
    id = peewee.UUIDField(primary_key=True, default=uuid.uuid4)
    issue_id = peewee.UUIDField(index=True)
    parent_id = peewee.UUIDField(null=True)  # null = top-level comment, set = reply
    author = peewee.CharField(max_length=255, null=True)
    body = peewee.TextField()
    # User ownership
    user_id = peewee.UUIDField(null=True)
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        from qengine.services.db import database

        database = database.db
        indexes = (
            (('id',), True),
            (('issue_id',), False),
            (('parent_id',), False),
            (('created_at',), False),
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
            'issue_id': str(self.issue_id),
            'parent_id': str(self.parent_id) if self.parent_id else None,
            'author': self.author,
            'body': self.body,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


# Create table if it doesn't exist
if database.is_open():
    IssueComment.create_table(safe=True)
