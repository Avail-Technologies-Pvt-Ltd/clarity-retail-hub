# settings_dev.py — retail_hub
# Local development without Docker (uses SQLite for quick spin-up)
from .settings import *

DEBUG = True
SECRET_KEY = 'dev-insecure-key-only-for-local-dev'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
