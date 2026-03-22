import peewee
import uuid
from qengine.services.db import database

if database.is_closed():
    database.open_connection()


class Issue(peewee.Model):
    id = peewee.UUIDField(primary_key=True, default=uuid.uuid4)
    title = peewee.CharField(max_length=500)
    description = peewee.TextField(null=True)
    status = peewee.CharField(default='todo')  # todo, in-progress, in-review, done
    author = peewee.CharField(max_length=255, null=True)
    priority = peewee.CharField(default='medium')  # low, medium, high, critical
    labels = peewee.TextField(null=True)  # comma-separated labels
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        from qengine.services.db import database

        database = database.db
        indexes = (
            (('id',), True),
            (('created_at',), False),
            (('status',), False),
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
            'title': self.title,
            'description': self.description,
            'status': self.status,
            'author': self.author,
            'priority': self.priority,
            'labels': self.labels.split(',') if self.labels else [],
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


# Create table if it doesn't exist
if database.is_open():
    Issue.create_table(safe=True)
