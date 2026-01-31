from django.shortcuts import redirect
from django.contrib import messages
from .models import UserProfile


def business_owner_required(view_func):
    """
    Decorator to ensure that only approved business owners can access certain views
    """
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'You need to log in to access this page.')
            return redirect('login')

        try:
            user_profile = UserProfile.objects.get(user=request.user)
            if user_profile.user_type != 'business_owner' or not user_profile.is_approved:
                messages.error(request, 'Access denied. Business owner privileges required.')
                return redirect('marketplace:home')
        except UserProfile.DoesNotExist:
            messages.error(request, 'User profile not found.')
            return redirect('marketplace:home')

        return view_func(request, *args, **kwargs)

    return wrapper


def admin_required(view_func):
    """
    Decorator to ensure that only admin users can access certain views
    """
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'You need to log in to access this page.')
            return redirect('login')

        if not request.user.is_staff:
            messages.error(request, 'Access denied. Admin privileges required.')
            return redirect('marketplace:home')

        return view_func(request, *args, **kwargs)

    return wrapper