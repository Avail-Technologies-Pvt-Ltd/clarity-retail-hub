# settings_dev_docker.py — retail_hub
# Development inside Docker (uses PostgreSQL from docker-compose.dev.yml with django-tenants)
from .settings import *
from decouple import config

DEBUG = True
SECRET_KEY = config('SECRET_KEY', default='dev-secret-key-retail-hub-12345')

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': config('DB_NAME', default='dev_retail_hub'),
        'USER': config('DB_USER', default='dev_user'),
        'PASSWORD': config('DB_PASSWORD', default='dev_password'),
        'HOST': config('DB_HOST', default='db'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
