from .models import Cart, CartItem, Review, ReviewLike

def cart_context(request):
    """
    Context processor to add cart information to all templates
    """
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(customer=request.user)
            cart_items_count = cart.items.count()
        except Cart.DoesNotExist:
            cart = None
            cart_items_count = 0

        return {
            'cart': cart,
            'cart_items_count': cart_items_count,
        }
    else:
        return {
            'cart': None,
            'cart_items_count': 0,
        }


def review_context(request):
    """
    Context processor to add recent reviews to all templates
    """
    from django.db.models import Count, Q

    # Get the 6 most recent reviews with the highest like counts
    recent_reviews = Review.objects.select_related('reviewer', 'business').annotate(
        num_likes=Count('review_likes', filter=Q(review_likes__is_like=True)),
        num_dislikes=Count('review_likes', filter=Q(review_likes__is_like=False))
    ).order_by('-created_at')[:6]

    return {
        'recent_reviews': recent_reviews,
    }


def admin_notification_context(request):
    """
    Context processor to add admin notifications to all templates
    """
    if request.user.is_authenticated and (request.user.is_staff or hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'admin'):
        from .models import UserProfile
        
        # Count pending business approvals
        pending_approvals = UserProfile.objects.filter(
            user_type='business_owner',
            is_approved=False
        ).count()
        
        return {
            'pending_approvals_count': pending_approvals,
        }
    else:
        return {
            'pending_approvals_count': 0,
        }