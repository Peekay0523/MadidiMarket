"""
URLs for the marketplace app
"""
from django.urls import path
from . import views

app_name = 'marketplace'

urlpatterns = [
    # Main pages
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    
    # User authentication
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Business owner related
    path('business/register/', views.business_register, name='business_register'),
    path('business/dashboard/', views.business_dashboard, name='business_dashboard'),
    path('business/<int:pk>/', views.business_detail, name='business_detail'),
    path('businesses/', views.business_list, name='business_list'),
    path('business/<int:business_id>/delete/', views.delete_business, name='delete_business'),
    
    # Product and service listings
    path('products/', views.product_list, name='product_list'),
    path('services/', views.service_list, name='service_list'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),
    path('product/<int:pk>/add-to-cart/', views.add_to_cart, name='add_to_cart'),
    path('service/<int:pk>/', views.service_detail, name='service_detail'),
    path('cart/', views.view_cart, name='view_cart'),
    path('cart/update/', views.update_cart, name='update_cart'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('process-payment/', views.process_payment, name='process_payment'),
    path('credit-card-payment/', views.credit_card_payment, name='credit_card_payment'),
    path('process-credit-card-payment/', views.process_credit_card_payment, name='process_credit_card_payment'),
    path('bank-transfer-payment/', views.bank_transfer_payment, name='bank_transfer_payment'),
    path('process-bank-transfer/', views.process_bank_transfer, name='process_bank_transfer'),
    path('order/<int:pk>/', views.order_detail, name='order_detail'),
    
    # Requests for products/services
    path('request/product/', views.request_product, name='request_product'),
    path('request/service/', views.request_service, name='request_service'),
    
    # Ratings and reviews
    path('rate/product/<int:pk>/', views.rate_product, name='rate_product'),
    path('rate/service/<int:pk>/', views.rate_service, name='rate_service'),

    # Business dashboard and analytics
    path('business/demand-analytics/', views.demand_analytics, name='demand_analytics'),
    path('business/products/', views.business_products, name='business_products'),
    path('business/services/', views.business_services, name='business_services'),
    path('business/my-business/', views.my_business, name='my_business'),
    path('business/add-product/', views.add_product, name='add_product'),
    path('business/add-service/', views.add_service, name='add_service'),
    path('business/view-reviews/', views.view_reviews, name='view_reviews'),
    path('business/edit-product/<int:pk>/', views.edit_product, name='edit_product'),
    path('business/delete-product/<int:pk>/', views.delete_product, name='delete_product'),
    path('business/edit-service/<int:pk>/', views.edit_service, name='edit_service'),
    path('business/delete-service/<int:pk>/', views.delete_service, name='delete_service'),
    path('client/dashboard/', views.client_dashboard, name='client_dashboard'),

    # Dashboard toggle
    path('toggle-dashboard/', views.toggle_dashboard_view, name='toggle_dashboard_view'),

    # Custom admin pages (changed from 'admin/' to 'admin-panel/' to avoid conflicts)
    path('admin-panel/approve-business/', views.admin_approve_business, name='admin_approve_business'),
    path('admin-panel/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/users/', views.admin_manage_users, name='admin_manage_users'),
    path('admin-panel/businesses/', views.admin_manage_businesses, name='admin_manage_businesses'),

    # Business owner order management
    path('business/orders/', views.business_orders, name='business_orders'),
    path('business/order/<int:order_id>/', views.business_order_detail, name='business_order_detail'),
    path('business/order/<int:order_id>/update-status/', views.update_order_status, name='update_order_status'),

    # Admin management pages
    path('admin-panel/orders/<int:order_id>/', views.admin_order_detail, name='admin_order_detail'),
    path('admin-panel/orders/', views.admin_manage_orders, name='admin_manage_orders'),
    path('admin-panel/products/', views.admin_manage_products, name='admin_manage_products'),
    path('admin-panel/services/', views.admin_manage_services, name='admin_manage_services'),
    path('admin-panel/reviews/', views.admin_manage_reviews, name='admin_manage_reviews'),
    path('admin-panel/shopping-trips/', views.admin_manage_shopping_trips, name='admin_manage_shopping_trips'),
    path('admin-panel/shopping-requests/', views.admin_manage_shopping_requests, name='admin_manage_shopping_requests'),

    # Review functionality
    path('business/<int:business_id>/rate/', views.rate_business, name='rate_business'),
    path('review/<int:review_id>/toggle-like/', views.toggle_review_like, name='toggle_review_like'),

    # Shopping functionality
    path('go-shopping/', views.go_shopping, name='go_shopping'),
    path('create-shopping-trip/', views.create_shopping_trip, name='create_shopping_trip'),
    path('make-shopping-request/<int:trip_id>/', views.make_shopping_request, name='make_shopping_request'),
    path('my-shopping-requests/', views.my_shopping_requests, name='my_shopping_requests'),

    # Password reset functionality
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset/done/', views.password_reset_done, name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
    path('password-reset-complete/', views.password_reset_complete, name='password_reset_complete'),
]