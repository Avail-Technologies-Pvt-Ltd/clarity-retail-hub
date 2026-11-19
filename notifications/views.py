from django.shortcuts import render
from django.http import JsonResponse
from .models import Notification
from retail_hub.decorators import staff_required


def _ok(title, message, **extra):
    return JsonResponse({'type': 'success', 'title': title, 'message': message, **extra})


@staff_required
def notifications_list(request):
    """Lists operational notifications and system alerts."""
    tenant = getattr(request, 'tenant', None)
    notifs = Notification.objects.all().order_by('-created_at')

    context = {
        'page_title': 'Notifications & Alerts',
        'tenant': tenant,
        'notifications': notifs,
        'unread_count': notifs.filter(is_read=False).count(),
    }
    return render(request, 'notifications/notifications_list.html', context)


@staff_required
def ajax_mark_all_read(request):
    """Marks all unread notifications as read."""
    if request.method == 'POST':
        Notification.objects.filter(is_read=False).update(is_read=True)
        return _ok('Notifications Cleared', 'All alerts have been marked as read.')
    return JsonResponse({'status': 'ok'})


@staff_required
def ajax_unread_count(request):
    """Returns unread notification badge count."""
    count = Notification.objects.filter(is_read=False).count()
    return JsonResponse({'unread_count': count})
