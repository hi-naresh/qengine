from dotenv import load_dotenv, dotenv_values
import qengine.helpers as jh
import os
import sys

# fix directory issue
sys.path.insert(0, os.getcwd())

ENV_VALUES = {}

if jh.is_unit_testing():
    ENV_VALUES['POSTGRES_HOST'] = '127.0.0.1'
    ENV_VALUES['POSTGRES_NAME'] = 'qengine_db'
    ENV_VALUES['POSTGRES_PORT'] = '5432'
    ENV_VALUES['POSTGRES_USERNAME'] = 'qengine_user'
    ENV_VALUES['POSTGRES_PASSWORD'] = 'password'
    ENV_VALUES['REDIS_HOST'] = 'localhost'
    ENV_VALUES['REDIS_PORT'] = '6379'
    ENV_VALUES['REDIS_DB'] = 0
    ENV_VALUES['REDIS_PASSWORD'] = ''
    ENV_VALUES['APP_PORT'] = 3000
    ENV_VALUES['IS_DEV_ENV'] = 'TRUE'
    ENV_VALUES['LSP_PORT'] = 9001

elif jh.is_qengine_project():
    # load env
    load_dotenv()

    # create and expose ENV_VALUES
    ENV_VALUES = dotenv_values('.env')

    # validation for existence of .env file
    # Use print+os._exit instead of jh.error() to avoid a circular import:
    # jh.error() → config → modes.utils → logger → redis → env (partially initialised)
    if len(list(ENV_VALUES.keys())) == 0:
        print(
            '[QEngine] .env file is missing from within your local project. '
            'This usually happens when you\'re in the wrong directory. '
            '\n\nIf you haven\'t created a QEngine project yet, do that by running: \n'
            'qengine make-project {name}\n'
            'And then go into that project, and run the same command.'
        )
        os._exit(1)

    if ENV_VALUES['PASSWORD'] == '':
        raise EnvironmentError('You forgot to set the PASSWORD in your .env file')


def is_dev_env() -> bool:
    return ENV_VALUES.get('IS_DEV_ENV', '').upper() == 'TRUE'
