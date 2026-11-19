# settings.py — retail_hub
# Multi-tenant cloud platform for retail companies

from decouple import config
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Security ─────────────────────────────────────────────────────────────────
SECRET_KEY = config('SECRET_KEY', default='dev-insecure-key-retail-hub-12345')
DEBUG = config('DEBUG', default=False, cast=bool)
allowed_hosts_raw = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,host.docker.internal,web').split(',')
ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_raw if h.strip()] + ['.localhost', '.local']


# ─── django-tenants ───────────────────────────────────────────────────────────
TENANT_MODEL = 'tenants.Company'
TENANT_DOMAIN_MODEL = 'tenants.Domain'
DATABASE_ROUTERS = ['django_tenants.routers.TenantSyncRouter']
PUBLIC_SCHEMA_URLCONF = 'retail_hub.urls_public'

SHARED_APPS = [
    'django_tenants',
    'tenants',
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'subscriptions',
    'identity_client',
]

TENANT_APPS = [
    'rest_framework',
    'django_filters',
    'fontawesomefree',
    'accounts_hub',
    'branches',
    'sync_gateway',
    'dashboard',
    'reports',
    'notifications',
    'marketplace',
]

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]


MIDDLEWARE = [
    'retail_hub.middleware.RetailHubTenantMiddleware',
    'retail_hub.middleware.HostNormalizationMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'retail_hub.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'retail_hub.context_processors.platform_port_context',
                'retail_hub.context_processors.branch_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'retail_hub.wsgi.application'

# ─── Database ─────────────────────────────────────────────────────────────────
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

# ─── Auth ─────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = [
    'retail_hub.backends.EmailOrUsernameModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]


# ─── Internationalisation ─────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Harare'
USE_I18N = True
USE_TZ = True

# ─── Static & Media ───────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Email ────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@clarityretail.com')

# ─── REST Framework ───────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# ─── Redis / Celery ───────────────────────────────────────────────────────────
REDIS_URL = config('REDIS_URL', default='redis://redis:6379/0')
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {'hosts': [REDIS_URL]},
    }
}

# ─── Multi-Tenant Session & Authentication Cookie Settings ───────────────────
# In local development, browsers (Chrome/Edge) strictly reject cookies with Domain=.localhost
# according to RFC 6265 because localhost has no public suffix.
# Setting SESSION_COOKIE_DOMAIN = None produces host-specific cookies that browsers accept 100%.
_cookie_domain_cfg = config('SESSION_COOKIE_DOMAIN', default='')
SESSION_COOKIE_DOMAIN = _cookie_domain_cfg if _cookie_domain_cfg and _cookie_domain_cfg != 'None' else None
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 86400 * 7  # 7 days

# ─── Platform Port (Single Point of Configuration) ───────────────────────────
# If running behind non-standard ports (e.g. 8003 in docker dev), set PLATFORM_PORT in .env.
# If running on standard 80 or 443 in production, leave default or empty.
PLATFORM_PORT = config('PLATFORM_PORT', default=None)
PLATFORM_DOMAIN = config('PLATFORM_DOMAIN', default='localhost')


