# settings_prod.py — retail_hub
# Production settings for Clarity Retail Hub Multi-Tenant Cloud Platform
from .settings import *
from decouple import config

DEBUG = config('DEBUG', default=False, cast=bool)
SECRET_KEY = config('SECRET_KEY')

raw_allowed = config('ALLOWED_HOSTS', default='*')
if raw_allowed == '*':
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = [h.strip() for h in raw_allowed.split(',') if h.strip()]

# Multi-Tenancy Database Backend: MUST use django_tenants.postgresql_backend
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': config('DB_NAME', default='clarity_retail_hub_prod'),
        'USER': config('DB_USER', default='hub_prod_user'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='db'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# CSRF Trusted Origins for Multi-Tenant subdomains and main domain
raw_csrf = config('CSRF_TRUSTED_ORIGINS', default='')
if raw_csrf:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in raw_csrf.split(',') if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = []

# Security headers & SSL Cookies
# Default to False initially to allow smooth setup before SSL/TLS certificate is bound;
# Enable in .env.prod once HTTPS is active.
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)

# Production Static and Media Files
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
