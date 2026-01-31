from django.db.models import Count, Avg
from .models import Product, Service, Review, Category


def get_product_recommendations(user, limit=4):
    """
    Get product recommendations for a user based on their review history and popular items
    """
    recommended_products = []
    
    # If user has reviewed products, recommend similar products from same categories
    user_reviews = Review.objects.filter(reviewer=user, product__isnull=False).select_related('product__category')
    
    if user_reviews.exists():
        # Get categories of products the user has reviewed
        reviewed_categories = user_reviews.values_list('product__category', flat=True).distinct()
        
        # Recommend products from those categories that the user hasn't reviewed
        reviewed_product_ids = user_reviews.values_list('product_id', flat=True)
        recommended_products = Product.objects.filter(
            category_id__in=reviewed_categories,
            is_available=True
        ).exclude(
            id__in=reviewed_product_ids
        ).distinct()[:limit]
    
    # If no personalized recommendations, get popular products
    if not recommended_products:
        recommended_products = Product.objects.filter(
            is_available=True
        ).annotate(
            avg_rating=Avg('reviews__rating')
        ).order_by('-avg_rating', '-id')[:limit]
    
    return recommended_products


def get_service_recommendations(user, limit=4):
    """
    Get service recommendations for a user based on their review history and popular items
    """
    recommended_services = []
    
    # If user has reviewed services, recommend similar services from same categories
    user_reviews = Review.objects.filter(reviewer=user, service__isnull=False).select_related('service__category')
    
    if user_reviews.exists():
        # Get categories of services the user has reviewed
        reviewed_categories = user_reviews.values_list('service__category', flat=True).distinct()
        
        # Recommend services from those categories that the user hasn't reviewed
        reviewed_service_ids = user_reviews.values_list('service_id', flat=True)
        recommended_services = Service.objects.filter(
            category_id__in=reviewed_categories,
            is_available=True
        ).exclude(
            id__in=reviewed_service_ids
        ).distinct()[:limit]
    
    # If no personalized recommendations, get popular services
    if not recommended_services:
        recommended_services = Service.objects.filter(
            is_available=True
        ).annotate(
            avg_rating=Avg('reviews__rating')
        ).order_by('-avg_rating', '-id')[:limit]
    
    return recommended_services


def get_popular_categories(limit=5):
    """
    Get the most popular categories based on number of products/services
    """
    # Combine product and service counts for each category
    from django.db import connection
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.id, c.name, c.description, 
                   COALESCE(p_count.p_count, 0) + COALESCE(s_count.s_count, 0) as total_count
            FROM marketplace_category c
            LEFT JOIN (
                SELECT category_id, COUNT(*) as p_count
                FROM marketplace_product
                WHERE is_available = 1
                GROUP BY category_id
            ) p_count ON c.id = p_count.category_id
            LEFT JOIN (
                SELECT category_id, COUNT(*) as s_count
                FROM marketplace_service
                WHERE is_available = 1
                GROUP BY category_id
            ) s_count ON c.id = s_count.category_id
            ORDER BY total_count DESC
            LIMIT %s
        """, [limit])
        
        columns = [col[0] for col in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        return results