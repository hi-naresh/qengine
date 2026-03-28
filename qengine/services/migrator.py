import uuid

from qengine.services.db import database
from playhouse.migrate import *
from qengine.enums import migration_actions


def run():
    """
    Runs migrations per each table and adds new fields in case they have not been added yet.

    Accepted action types: add, drop, rename, modify_type, allow_null, deny_null
    If actions type is 'rename', you must add new field with 'old_name' key.
    To make column to not nullable, you must clean all null value of columns.
    """
    print('Checking for new database migrations...\n')

    database.open_connection()

    # create migrator
    migrator = PostgresqlMigrator(database.db)
    # run migrations
    _candle(migrator)
    _completed_trade(migrator)
    _closed_trade(migrator)
    _log(migrator)
    _order(migrator)
    _orderbook(migrator)
    _ticker(migrator)
    _trade(migrator)
    _exchange_api_keys(migrator)
    _optimization_session(migrator)
    _monte_carlo_session(migrator)

    # create initial tables
    from qengine.models import Candle, ClosedTrade, Log, Order, OpenTab, LiveEquitySnapshot
    database.db.create_tables([Candle, ClosedTrade, Log, Order, OpenTab, LiveEquitySnapshot])

    # User system migration
    _user_system_migration(migrator)

    database.close_connection()


def _candle(migrator):
    fields = [
        {'action': migration_actions.ADD, 'name': 'timeframe', 'type': CharField(index=False, null=True)},
        {'action': migration_actions.DROP_INDEX, 'indexes': ('exchange', 'symbol', 'timestamp')},
        {'action': migration_actions.ADD_INDEX, 'indexes': ('exchange', 'symbol', 'timeframe', 'timestamp'), 'is_unique': True},
    ]

    if 'candle' in database.db.get_tables():
        candle_columns = database.db.get_columns('candle')
        _migrate(migrator, fields, candle_columns, 'candle')


def _completed_trade(migrator):
    fields = []

    if 'completedtrade' in database.db.get_tables():
        completedtrade_columns = database.db.get_columns('completedtrade')
        _migrate(migrator, fields, completedtrade_columns, 'completedtrade')


def _closed_trade(migrator):
    fields = [
        {'action': migration_actions.ADD, 'name': 'session_id', 'type': UUIDField(null=True)},
        {'action': migration_actions.ADD, 'name': 'created_at', 'type': BigIntegerField(null=True)},
        {'action': migration_actions.ADD, 'name': 'updated_at', 'type': BigIntegerField(null=True)},
        {'action': migration_actions.ADD, 'name': 'session_mode', 'type': CharField(null=True)},
        {'action': migration_actions.ADD, 'name': 'soft_deleted_at', 'type': BigIntegerField(null=True)},
        {'action': migration_actions.ALLOW_NULL, 'name': 'closed_at', 'type': BigIntegerField(null=True)},
        {'action': migration_actions.ADD_INDEX, 'indexes': ('session_id',), 'is_unique': False},
    ]

    if 'closedtrade' in database.db.get_tables():
        closedtrade_columns = database.db.get_columns('closedtrade')
        _migrate(migrator, fields, closedtrade_columns, 'closedtrade')


def _log(migrator):
    fields = []

    if 'log' in database.db.get_tables():
        log_columns = database.db.get_columns('log')
        _migrate(migrator, fields, log_columns, 'log')


def _order(migrator):
    fields = [
        {'action': migration_actions.ADD, 'name': 'updated_at', 'type': BigIntegerField(null=True)},
        {'action': migration_actions.ADD, 'name': 'session_mode', 'type': CharField(null=True)},
        {'action': migration_actions.ADD, 'name': 'engine_submitted', 'type': BooleanField(default=True)},
        {'action': migration_actions.ADD, 'name': 'submitted_via', 'type': CharField(null=True)},
        {'action': migration_actions.ADD, 'name': 'order_exist_in_exchange', 'type': BooleanField(default=True)},
        {'action': migration_actions.ADD, 'name': 'fee', 'type': FloatField(null=True)},
        {'action': migration_actions.ADD_INDEX, 'indexes': ('session_id',), 'is_unique': False},
    ]

    if 'order' in database.db.get_tables():
        order_columns = database.db.get_columns('order')
        _migrate(migrator, fields, order_columns, 'order')


def _orderbook(migrator):
    fields = []

    if 'orderbook' in database.db.get_tables():
        orderbook_columns = database.db.get_columns('orderbook')
        _migrate(migrator, fields, orderbook_columns, 'orderbook')


def _ticker(migrator):
    fields = []

    if 'ticker' in database.db.get_tables():
        ticker_columns = database.db.get_columns('ticker')
        _migrate(migrator, fields, ticker_columns, 'ticker')


def _trade(migrator):
    fields = []

    if 'trade' in database.db.get_tables():
        trade_columns = database.db.get_columns('trade')
        _migrate(migrator, fields, trade_columns, 'trade')


def _exchange_api_keys(migrator):
    fields = []

    if 'exchange_api_keys' in database.db.get_tables():
        exchange_api_keys_columns = database.db.get_columns('exchange_api_keys')
        _migrate(migrator, fields, exchange_api_keys_columns, 'exchange_api_keys')


def _optimization_session(migrator):
    fields = [
        {'action': migration_actions.ADD, 'name': 'title', 'type': CharField(max_length=255, null=True)},
        {'action': migration_actions.ADD, 'name': 'description', 'type': TextField(null=True)},
        {'action': migration_actions.ADD, 'name': 'strategy_codes', 'type': TextField(null=True)},
    ]

    if 'optimizationsession' in database.db.get_tables():
        optimization_session_columns = database.db.get_columns('optimizationsession')
        _migrate(migrator, fields, optimization_session_columns, 'optimizationsession')


def _monte_carlo_session(migrator):
    fields = [
        {'action': migration_actions.ADD, 'name': 'strategy_codes', 'type': TextField(null=True)},
    ]

    if 'montecarlosession' in database.db.get_tables():
        monte_carlo_session_columns = database.db.get_columns('montecarlosession')
        _migrate(migrator, fields, monte_carlo_session_columns, 'montecarlosession')


def _migrate(migrator, fields, columns, table):
    for field in fields:
        if field['action'] in [migration_actions.ADD_INDEX, migration_actions.DROP_INDEX]:
            indexes: list = database.db.get_indexes(table)
            to_migrate_indexes: list = field['indexes']
            to_migrate_indexes_str = f'{table}_'
            for t in to_migrate_indexes:
                to_migrate_indexes_str += f'{t}_'
            to_migrate_indexes_str = to_migrate_indexes_str[:-1]
            already_exists = False
            for index in indexes:
                existing_indexes_str: list = index.name
                if to_migrate_indexes_str == existing_indexes_str:
                    already_exists = True
                    break
            if field['action'] == migration_actions.ADD_INDEX:
                if not already_exists:
                    migrate(
                        migrator.add_index(table, field['indexes'], field['is_unique'])
                    )
                    print(f'Added index {field["indexes"]} to {table}')
            if field['action'] == migration_actions.DROP_INDEX:
                if already_exists:
                    migrate(
                        migrator.drop_index(table, to_migrate_indexes_str)
                    )
                    print(f'Dropped index {field["indexes"]} from the "{table}" table')
        else: # else, fist check if the field exists
            column_name_exist = any(field['name'] == item.name for item in columns)
            if column_name_exist:
                if field['action'] == migration_actions.ADD:
                    pass
                elif field['action'] == migration_actions.DROP:
                    migrate(
                        migrator.drop_column(table, field['name'])
                    )
                    print(f"Successfully dropped '{field['name']}' column from the "'{table}'" table.")
                elif field['action'] == migration_actions.RENAME:
                    migrate(
                        migrator.rename_column(table, field['name'], field['new_name'])
                    )
                    print(f"'{field['name']}' column successfully changed to {field['new_name']} in the '{table}' table.")
                elif field['action'] == migration_actions.MODIFY_TYPE:
                    migrate(
                        migrator.alter_column_type(table, field['name'], field['type'])
                    )
                    print(
                        f"'{field['name']}' field's type was successfully changed to {field['type']} in the '{table}' table.")
                elif field['action'] == migration_actions.ALLOW_NULL:
                    # Check if column is already nullable
                    column = next(item for item in columns if item.name == field['name'])
                    if not column.null:
                        migrate(
                            migrator.drop_not_null(table, field['name'])
                        )
                        print(f"'{field['name']}' column successfully updated to accept nullable values in the '{table}' table.")
                elif field['action'] == migration_actions.DENY_NULL:
                    # Check if column is already non-nullable
                    column = next(item for item in columns if item.name == field['name'])
                    if column.null:
                        migrate(
                            migrator.add_not_null(table, field['name'])
                        )
                        print(
                            f"'{field['name']}' column successfully updated to accept to reject nullable values in the '{table}' table.")
            # if column name doesn't not already exist
            else:
                if field['action'] == migration_actions.ADD:
                    migrate(
                        migrator.add_column(table, field['name'], field['type'])
                    )
                    print(f"'{field['name']}' column successfully added to '{table}' table.")
                else:
                    print(f"'{field['name']}' field does not exist in '{table}' table.")


def _user_system_migration(migrator):
    """Create User/UserQuota tables and add user_id to all user-scoped tables."""
    from qengine.models.User import User
    from qengine.models.UserQuota import UserQuota
    from qengine.models.QuotaRequest import QuotaRequest

    # Create new tables
    database.db.create_tables([User, UserQuota, QuotaRequest], safe=True)
    print('User system tables created (if not existing).')

    # Add user_id column to all user-scoped tables
    tables_needing_user_id = [
        'backtestsession', 'livesession', 'optimizationsession',
        'montecarlosession', 'exchange_api_keys', 'notificationapikeys',
        'issue', 'issuecomment', 'opentab', 'option',
        'closedtrade', 'order', 'liveequitysnapshot'
    ]

    for table_name in tables_needing_user_id:
        if table_name in database.db.get_tables():
            columns = database.db.get_columns(table_name)
            if not any(c.name == 'user_id' for c in columns):
                try:
                    migrate(migrator.add_column(table_name, 'user_id', UUIDField(null=True)))
                    print(f"'user_id' column added to '{table_name}' table.")
                except Exception as e:
                    print(f"Could not add user_id to {table_name}: {e}")

                # Add index on user_id
                try:
                    migrate(migrator.add_index(table_name, ('user_id',), False))
                    print(f"Index on user_id added to '{table_name}' table.")
                except Exception:
                    pass

    # Add name column to user table if missing
    if 'user' in database.db.get_tables():
        user_columns = database.db.get_columns('user')
        if not any(c.name == 'name' for c in user_columns):
            try:
                migrate(migrator.add_column('user', 'name', CharField(max_length=255, default='')))
                print("'name' column added to 'user' table.")
            except Exception as e:
                print(f"Could not add name to user: {e}")

    # Add allowed_features column to user table if missing
    if 'user' in database.db.get_tables():
        user_columns = database.db.get_columns('user')
        if not any(c.name == 'allowed_features' for c in user_columns):
            try:
                migrate(migrator.add_column('user', 'allowed_features', TextField(null=True)))
                print("'allowed_features' column added to 'user' table.")
            except Exception as e:
                print(f"Could not add allowed_features to user: {e}")

    # Add deleted_at and deletion_stats columns to user table if missing
    if 'user' in database.db.get_tables():
        user_columns = database.db.get_columns('user')
        if not any(c.name == 'deleted_at' for c in user_columns):
            try:
                migrate(migrator.add_column('user', 'deleted_at', BigIntegerField(null=True)))
                print("'deleted_at' column added to 'user' table.")
            except Exception as e:
                print(f"Could not add deleted_at to user: {e}")
        if not any(c.name == 'deletion_stats' for c in user_columns):
            try:
                migrate(migrator.add_column('user', 'deletion_stats', TextField(null=True)))
                print("'deletion_stats' column added to 'user' table.")
            except Exception as e:
                print(f"Could not add deletion_stats to user: {e}")

    # Auto-create admin user and backfill existing data
    _create_admin_and_backfill()

    # Migrate admin settings to shared ADMIN_SETTINGS_ID
    try:
        _migrate_admin_settings_to_shared()
    except Exception as e:
        print(f"Could not migrate admin settings to shared ID: {e}")


def _create_admin_and_backfill():
    """Create admin user from .env PASSWORD and assign all existing data to admin."""
    from qengine.models.User import User, get_admin_user, create_user
    from qengine.services.env import ENV_VALUES
    from qengine.services.auth import hash_password

    admin = get_admin_user()
    if admin:
        print(f'Admin user already exists: {admin.username}')
        admin_id = str(admin.id)
    else:
        # Create admin from .env
        admin_username = ENV_VALUES.get('ADMIN_USERNAME', 'admin')
        admin_password = ENV_VALUES.get('PASSWORD', 'admin')
        admin_id = str(uuid.uuid4())

        try:
            create_user(
                user_id=admin_id,
                username=admin_username,
                password_hash=hash_password(admin_password),
                role='admin'
            )
            print(f"Admin user '{admin_username}' created successfully.")
        except Exception as e:
            print(f"Could not create admin user: {e}")
            return

    # Backfill user_id on all existing rows that have NULL user_id
    tables_to_backfill = [
        'backtestsession', 'livesession', 'optimizationsession',
        'montecarlosession', 'exchange_api_keys', 'notificationapikeys',
        'issue', 'issuecomment', 'opentab', 'option',
        'closedtrade', 'order', 'liveequitysnapshot'
    ]

    for table_name in tables_to_backfill:
        if table_name in database.db.get_tables():
            columns = database.db.get_columns(table_name)
            if any(c.name == 'user_id' for c in columns):
                try:
                    count = database.db.execute_sql(
                        f'UPDATE "{table_name}" SET user_id = %s WHERE user_id IS NULL',
                        (admin_id,)
                    ).rowcount
                    if count > 0:
                        print(f"Backfilled {count} rows in '{table_name}' with admin user_id.")
                except Exception as e:
                    print(f"Could not backfill {table_name}: {e}")


def _migrate_admin_settings_to_shared():
    """Move admin user's settings to shared __admin__ ID so all admins share one config."""
    from qengine.controllers.settings_controller import ADMIN_SETTINGS_ID
    from qengine.models.User import get_admin_user
    import json

    if 'option' not in database.db.get_tables():
        return

    # Check if shared admin settings already exist
    cursor = database.db.execute_sql(
        "SELECT id FROM option WHERE type = 'app_settings' AND user_id = %s",
        (ADMIN_SETTINGS_ID,)
    )
    if cursor.fetchone():
        return  # Already migrated

    # Find the first admin user's settings and copy them
    admin = get_admin_user()
    if not admin:
        return

    cursor = database.db.execute_sql(
        "SELECT json FROM option WHERE type = 'app_settings' AND user_id = %s",
        (str(admin.id),)
    )
    row = cursor.fetchone()
    if not row:
        return

    # Copy admin's settings to shared row
    from qengine.helpers import generate_unique_id, now
    database.db.execute_sql(
        "INSERT INTO option (id, updated_at, type, json, user_id) VALUES (%s, %s, 'app_settings', %s, %s)",
        (generate_unique_id(), now(True), row[0], ADMIN_SETTINGS_ID)
    )
    print(f"Migrated admin settings to shared '{ADMIN_SETTINGS_ID}' settings ID.")
