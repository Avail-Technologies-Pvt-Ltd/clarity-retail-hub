from django.db import models


class Notification(models.Model):
    """
    In-app alert notification model for Clarity Retail Hub.
    Broadcasts operational alerts, sync warnings, and B2B activity to store managers.
    """
    LEVEL_CHOICES = [
        ('INFO', 'Information'),
        ('SUCCESS', 'Success'),
        ('WARNING', 'Warning'),
        ('DANGER', 'Critical'),
    ]

    title = models.CharField(max_length=200)
    message = models.TextField()
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='INFO')
    is_read = models.BooleanField(default=False)
    link_url = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.level}] {self.title} (Read: {self.is_read})"
