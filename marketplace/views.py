from django.shortcuts import render, redirect, get_object_or_404
from decimal import Decimal
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Avg
from django.http import JsonResponse
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from .models import *
from .models import ShoppingTrip, ShoppingRequest  # Import the new models
from .forms import *
from .middleware import business_owner_required
from .recommendations import get_product_recommendations, get_service_recommendations, get_popular_categories


def home(request):
    # Get featured products and services
    featured_products = Product.objects.filter(is_available=True)[:6]
    featured_services = Service.objects.filter(is_available=True)[:6]

    # Get recommendations for logged-in users
    recommended_products = []
    recommended_services = []

    if request.user.is_authenticated:
        recommended_products = get_product_recommendations(request.user)
        recommended_services = get_service_recommendations(request.user)
    else:
        # For anonymous users, show popular items
        recommended_products = Product.objects.filter(
            is_available=True
        ).annotate(
            avg_rating=Avg('reviews__rating')
        ).order_by('-avg_rating', '-id')[:4]

        recommended_services = Service.objects.filter(
            is_available=True
        ).annotate(
            avg_rating=Avg('reviews__rating')
        ).order_by('-avg_rating', '-id')[:4]

    # Get popular categories
    popular_categories = get_popular_categories()

    context = {
        'featured_products': featured_products,
        'featured_services': featured_services,
        'recommended_products': recommended_products,
        'recommended_services': recommended_services,
        'popular_categories': popular_categories,
    }
    return render(request, 'marketplace/home.html', context)


def about(request):
    return render(request, 'marketplace/about.html')


def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            user_type = form.cleaned_data.get('user_type')
            messages.success(request, f'Account created for {username}!')

            # If user registered as business_owner, redirect to business registration
            if user_type == 'business_owner':
                return redirect('marketplace:business_register')
            else:
                # For clients, redirect to login
                return redirect('marketplace:login')
        else:
            # Form is invalid, show errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
            return render(request, 'marketplace/register.html', {'form': form})
    else:
        form = UserRegistrationForm()

        # Pass the next parameter to the template context if it exists
        next_url = request.GET.get('next')
        context = {'form': form}
        if next_url:
            context['next'] = next_url
        return render(request, 'marketplace/register.html', context)


def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            
            # Check if there's a 'next' parameter in the URL
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                # Ensure the next URL is safe to prevent open redirect vulnerabilities
                if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
                else:
                    # If the next URL is not safe, redirect to home
                    return redirect('marketplace:home')
            
            # If no 'next' parameter, redirect based on user type
            if user.is_staff or (hasattr(user, 'userprofile') and user.userprofile.user_type == 'admin'):
                return redirect('marketplace:admin_dashboard')
            elif hasattr(user, 'userprofile') and user.userprofile.user_type == 'business_owner':
                return redirect('marketplace:business_dashboard')
            else:
                # Redirect regular clients to their dashboard
                return redirect('marketplace:client_dashboard')
        else:
            messages.error(request, 'Invalid username or password')
    return render(request, 'marketplace/login.html')


@login_required
def logout_view(request):
    from django.contrib.auth import logout
    logout(request)
    return redirect('marketplace:home')


@login_required
def admin_approve_business(request):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    pending_businesses = UserProfile.objects.filter(
        user_type='business_owner',
        is_approved=False
    ).select_related('user').prefetch_related('user__businesses')

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')  # 'approve' or 'reject'

        try:
            profile = UserProfile.objects.get(id=user_id)
            user = profile.user
            
            if action == 'approve':
                profile.is_approved = True
                profile.save()
                
                # Send approval notification email
                from django.core.mail import send_mail
                from django.template.loader import render_to_string
                from django.conf import settings
                
                subject = 'Your Business Registration Has Been Approved'
                
                # Render email content from template
                email_content = render_to_string('marketplace/emails/business_approved_email.html', {
                    'user': user,
                    'business_name': user.businesses.first().name if user.businesses.first() else 'your business',
                    'site_name': 'Madidi Market',
                })
                
                try:
                    send_mail(
                        subject,
                        '',  # Plain text version (empty since we're using HTML)
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                        html_message=email_content,
                        fail_silently=False,
                    )
                    messages.success(request, f'Approved business owner: {user.username}. Notification email sent.')
                except Exception as e:
                    # If email fails, still approve the business but log the error
                    messages.warning(request, f'Approved business owner: {user.username}, but failed to send notification email: {str(e)}')
                    
            elif action == 'reject':
                # For rejection, we could delete the business or just keep is_approved=False
                messages.info(request, f'Rejected business owner: {user.username}')
        except UserProfile.DoesNotExist:
            messages.error(request, 'User not found.')

        return redirect('marketplace:admin_approve_business')

    context = {
        'pending_businesses': pending_businesses,
    }
    return render(request, 'marketplace/admin_approve_business.html', context)


def business_register(request):
    # Check if user is authenticated
    if not request.user.is_authenticated:
        messages.info(request, 'You need to register or log in first before registering a business.')
        # Redirect to register page with a parameter to redirect to business registration after login
        next_url = request.build_absolute_uri(request.path)
        return redirect(f"{reverse('marketplace:register')}?next={next_url}")

    if request.method == 'POST':
        form = BusinessOwnerRegistrationForm(request.POST)
        if form.is_valid():
            business = form.save(commit=False)
            business.owner = request.user
            business.save()

            # Update user profile to business owner
            user_profile = UserProfile.objects.get(user=request.user)
            user_profile.user_type = 'business_owner'
            user_profile.is_approved = False  # Needs admin approval
            user_profile.save()

            messages.success(request, 'Business registered successfully! Awaiting admin approval.')
            return redirect('marketplace:home')
    else:
        form = BusinessOwnerRegistrationForm()
    return render(request, 'marketplace/business_register.html', {'form': form})


@login_required
@business_owner_required
def business_dashboard(request):
    # Get all businesses for the user
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')
    
    # Get the business ID from the request, or use the first one if not specified
    selected_business_id = request.GET.get('business_id')
    if selected_business_id:
        try:
            business = Business.objects.get(id=selected_business_id, owner=request.user)
        except Business.DoesNotExist:
            business = all_businesses.first() if all_businesses.exists() else None
    else:
        business = all_businesses.first() if all_businesses.exists() else None
    
    if business:
        products = Product.objects.filter(business=business)
        services = Service.objects.filter(business=business)

        # Get total orders for this business
        total_orders = Order.objects.filter(business=business).count()
        
        # Calculate total revenue from completed orders for this business
        completed_orders = Order.objects.filter(
            business=business,
            status__in=['completed', 'delivered']  # Assuming these statuses mean the order is finalized
        )
        
        total_revenue = 0
        for order in completed_orders:
            total_revenue += float(order.total_amount)
        
        # Calculate admin's payment (5% of total revenue)
        admin_payment = total_revenue * 0.05
    else:
        products = []
        services = []
        total_orders = 0
        total_revenue = 0
        admin_payment = 0

    # Get shopping trips and requests for the user
    from datetime import datetime
    from django.db.models import Count
    upcoming_shopping_trips = ShoppingTrip.objects.filter(
        status='available',
        planned_departure_time__gte=datetime.now()
    ).select_related('user').exclude(user=request.user).annotate(
        request_count=Count('requests')
    ).order_by('planned_departure_time')[:5]  # Limit to 5 upcoming trips

    sent_shopping_requests = ShoppingRequest.objects.filter(
        requester=request.user
    ).select_related('shopper', 'shopping_trip__user').order_by('-created_at')[:5]  # Limit to 5 recent requests

    received_shopping_requests = ShoppingRequest.objects.filter(
        shopper=request.user
    ).select_related('requester', 'shopping_trip__user').order_by('-created_at')[:5]  # Limit to 5 recent requests

    context = {
        'business': business,
        'all_businesses': all_businesses,
        'products': products,
        'services': services,
        'total_products': len(products) if isinstance(products, list) else products.count(),
        'total_services': len(services) if isinstance(services, list) else services.count(),
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'admin_payment': admin_payment,
        'upcoming_shopping_trips': upcoming_shopping_trips,
        'sent_shopping_requests': sent_shopping_requests,
        'received_shopping_requests': received_shopping_requests,
    }
    return render(request, 'marketplace/business_dashboard.html', context)


@login_required
@business_owner_required
def pay_admin_fee(request):
    """Page for business owners to pay admin fees"""
    if not request.user.userprofile.is_approved:
        messages.error(request, 'Your business account must be approved to pay admin fees.')
        return redirect('marketplace:business_dashboard')

    # Get all businesses for the user
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')
    business = all_businesses.first() if all_businesses.exists() else None

    if business:
        # Calculate total revenue from completed orders for this business
        completed_orders = Order.objects.filter(
            business=business,
            status__in=['completed', 'delivered']
        )

        total_revenue = 0
        for order in completed_orders:
            total_revenue += float(order.total_amount)

        # Calculate admin's payment (5% of total revenue)
        admin_payment = total_revenue * 0.05
    else:
        total_revenue = 0
        admin_payment = 0

    context = {
        'business': business,
        'total_revenue': total_revenue,
        'admin_payment': admin_payment,
    }
    return render(request, 'marketplace/pay_admin_fee.html', context)


@login_required
@business_owner_required
def admin_fee_credit_card(request):
    """Credit card payment page for admin fees"""
    if not request.user.userprofile.is_approved:
        messages.error(request, 'Your business account must be approved to pay admin fees.')
        return redirect('marketplace:business_dashboard')

    # Get all businesses for the user
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')
    business = all_businesses.first() if all_businesses.exists() else None

    if business:
        completed_orders = Order.objects.filter(
            business=business,
            status__in=['completed', 'delivered']
        )

        total_revenue = 0
        for order in completed_orders:
            total_revenue += float(order.total_amount)

        admin_payment = total_revenue * 0.05
    else:
        total_revenue = 0
        admin_payment = 0

    if request.method == 'POST':
        # Process the credit card payment
        # In a real application, you would integrate with a payment gateway
        # Create a payment record
        from datetime import timedelta
        from django.utils import timezone
        from marketplace.models import BusinessAdminFeePayment
        
        # Check if there's already a pending payment for this period
        period_end = timezone.now()
        period_start = period_end - timedelta(days=30)  # Last 30 days
        
        existing_payment = BusinessAdminFeePayment.objects.filter(
            business=business,
            period_start__lte=period_start,
            period_end__gte=period_end,
            is_paid=False
        ).first()
        
        if not existing_payment and admin_payment > 0:
            BusinessAdminFeePayment.objects.create(
                business=business,
                period_start=period_start,
                period_end=period_end,
                total_revenue=total_revenue,
                admin_fee_amount=admin_payment,
                is_paid=True,
                paid_date=timezone.now(),
                payment_method='credit_card'
            )
        
        messages.success(request, f'Admin fee of R{admin_payment|floatformat:2} paid successfully!')
        return redirect('marketplace:business_dashboard')

    context = {
        'business': business,
        'total_revenue': total_revenue,
        'admin_payment': admin_payment,
    }
    return render(request, 'marketplace/admin_fee_credit_card.html', context)


@login_required
@business_owner_required
def admin_fee_bank_transfer(request):
    """Bank transfer payment page for admin fees"""
    if not request.user.userprofile.is_approved:
        messages.error(request, 'Your business account must be approved to pay admin fees.')
        return redirect('marketplace:business_dashboard')

    # Get all businesses for the user
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')
    business = all_businesses.first() if all_businesses.exists() else None

    if business:
        completed_orders = Order.objects.filter(
            business=business,
            status__in=['completed', 'delivered']
        )

        total_revenue = 0
        for order in completed_orders:
            total_revenue += float(order.total_amount)

        admin_payment = total_revenue * 0.05
    else:
        total_revenue = 0
        admin_payment = 0

    if request.method == 'POST':
        # Process the bank transfer payment confirmation
        from datetime import timedelta
        from django.utils import timezone
        from marketplace.models import BusinessAdminFeePayment
        
        transfer_reference = request.POST.get('transfer_reference', '')
        proof_of_payment = request.FILES.get('proof_of_payment')
        
        # Create a pending payment record
        period_end = timezone.now()
        period_start = period_end - timedelta(days=30)  # Last 30 days
        
        if admin_payment > 0:
            payment = BusinessAdminFeePayment.objects.create(
                business=business,
                period_start=period_start,
                period_end=period_end,
                total_revenue=total_revenue,
                admin_fee_amount=admin_payment,
                is_paid=False,
                payment_method='bank_transfer'
            )
            
            # Save proof of payment if uploaded
            if proof_of_payment:
                payment.proof_of_payment = proof_of_payment
                payment.save()
        
        messages.success(request, f'Bank transfer for admin fee of R{admin_payment|floatformat:2} initiated. Please complete the transfer.')
        return redirect('marketplace:business_dashboard')

    context = {
        'business': business,
        'total_revenue': total_revenue,
        'admin_payment': admin_payment,
    }
    return render(request, 'marketplace/admin_fee_bank_transfer.html', context)


@login_required
@business_owner_required
def business_products(request):
    """Display products for the selected business of the logged-in business owner"""
    # Get the business ID from the request, or use the first one if not specified
    selected_business_id = request.GET.get('business_id')
    if selected_business_id:
        try:
            business = Business.objects.get(id=selected_business_id, owner=request.user)
        except Business.DoesNotExist:
            messages.error(request, 'Selected business not found.')
            return redirect('marketplace:business_dashboard')
    else:
        business = Business.objects.filter(owner=request.user).first()
        if not business:
            messages.error(request, 'You must have a registered business to view products.')
            return redirect('marketplace:business_dashboard')

    products = Product.objects.filter(business=business)

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    context = {
        'business': business,
        'all_businesses': all_businesses,
        'products': products,
        'total_products': products.count(),
    }
    return render(request, 'marketplace/business_products.html', context)


@login_required
@business_owner_required
def business_services(request):
    """Display services for the selected business of the logged-in business owner"""
    # Get the business ID from the request, or use the first one if not specified
    selected_business_id = request.GET.get('business_id')
    if selected_business_id:
        try:
            business = Business.objects.get(id=selected_business_id, owner=request.user)
        except Business.DoesNotExist:
            messages.error(request, 'Selected business not found.')
            return redirect('marketplace:business_dashboard')
    else:
        business = Business.objects.filter(owner=request.user).first()
        if not business:
            messages.error(request, 'You must have a registered business to view services.')
            return redirect('marketplace:business_dashboard')

    services = Service.objects.filter(business=business)

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    context = {
        'business': business,
        'all_businesses': all_businesses,
        'services': services,
        'total_services': services.count(),
    }
    return render(request, 'marketplace/business_services.html', context)


@login_required
@business_owner_required
def delete_business(request, business_id):
    """
    Allow business owner to delete their business if it has no pending orders
    """
    from django.shortcuts import get_object_or_404
    from django.db import transaction
    
    # Get the specific business to delete, ensuring it belongs to the current user
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    
    # Check if the business has any pending orders
    pending_orders = Order.objects.filter(
        business=business,
        status__in=['pending', 'confirmed', 'in_progress']
    )
    
    if pending_orders.exists():
        # Cancel pending orders and notify the user
        canceled_count = 0
        for order in pending_orders:
            order.status = 'cancelled'
            order.save()
            canceled_count += 1
        
        messages.warning(
            request, 
            f'Business cannot be deleted because it had pending orders. '
            f'{canceled_count} order(s) have been automatically cancelled.'
        )
        return redirect('marketplace:business_dashboard')
    
    # If no pending orders, delete the business
    business_name = business.name
    business.delete()
    
    messages.success(request, f'Business "{business_name}" has been successfully deleted.')
    return redirect('marketplace:business_dashboard')


@login_required
@business_owner_required
def demand_analytics(request):
    """
    Dashboard showing demand analytics for entrepreneurs
    """
    from django.db.models import Count, Sum
    from datetime import timedelta
    from django.utils import timezone

    # Get the business for the current user
    business = Business.objects.filter(owner=request.user).first()

    # Get product request trends
    recent_product_requests = ProductRequest.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=30)
    ).values('category__name').annotate(
        count=Count('id')
    ).order_by('-count')

    # Get service request trends
    recent_service_requests = ServiceRequest.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=30)
    ).values('category__name').annotate(
        count=Count('id')
    ).order_by('-count')

    # Get most requested products/services
    top_requested_products = ProductRequest.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=30)
    ).values('title').annotate(
        count=Count('id')
    ).order_by('-count')[:5]

    top_requested_services = ServiceRequest.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=30)
    ).values('title').annotate(
        count=Count('id')
    ).order_by('-count')[:5]

    context = {
        'business': business,
        'recent_product_requests': recent_product_requests,
        'recent_service_requests': recent_service_requests,
        'top_requested_products': top_requested_products,
        'top_requested_services': top_requested_services,
    }
    return render(request, 'marketplace/demand_analytics.html', context)


def product_list(request):
    products = Product.objects.filter(is_available=True)
    categories = Category.objects.all()

    # Filter by category if specified
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)

    context = {
        'products': products,
        'categories': categories,
    }
    return render(request, 'marketplace/product_list.html', context)


def service_list(request):
    services = Service.objects.filter(is_available=True)
    categories = Category.objects.all()

    # Filter by category if specified
    category_id = request.GET.get('category')
    if category_id:
        services = services.filter(category_id=category_id)

    context = {
        'services': services,
        'categories': categories,
    }
    return render(request, 'marketplace/service_list.html', context)


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, is_available=True)
    related_products = Product.objects.filter(
        category=product.category,
        is_available=True
    ).exclude(pk=pk)[:4]

    # Get average rating
    avg_rating = 0
    reviews = Review.objects.filter(product=product)
    if reviews.exists():
        avg_rating = sum([review.rating for review in reviews]) / reviews.count()

    context = {
        'product': product,
        'related_products': related_products,
        'avg_rating': avg_rating,
        'reviews': reviews,
    }
    return render(request, 'marketplace/product_detail.html', context)


def service_detail(request, pk):
    service = get_object_or_404(Service, pk=pk, is_available=True)
    related_services = Service.objects.filter(
        category=service.category,
        is_available=True
    ).exclude(pk=pk)[:4]

    # Get average rating
    avg_rating = 0
    reviews = Review.objects.filter(service=service)
    if reviews.exists():
        avg_rating = sum([review.rating for review in reviews]) / reviews.count()

    context = {
        'service': service,
        'related_services': related_services,
        'avg_rating': avg_rating,
        'reviews': reviews,
    }
    return render(request, 'marketplace/service_detail.html', context)


@login_required
def add_to_cart(request, pk):
    """Add a product to the user's cart"""
    product = get_object_or_404(Product, pk=pk, is_available=True)

    # Get or create the user's cart
    cart, created = Cart.objects.get_or_create(customer=request.user)

    # Check if the product is already in the cart
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={'quantity': 1}
    )

    if not created:
        # If the item already exists, increment the quantity
        cart_item.quantity += 1
        cart_item.save()

    messages.success(request, f'{product.name} added to cart successfully!')
    return redirect('marketplace:product_detail', pk=pk)


@login_required
def view_cart(request):
    """View the user's cart"""
    try:
        cart = Cart.objects.get(customer=request.user)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product')
        subtotal = cart.get_total_price()
        tax_rate = Decimal('0.15')  # Use Decimal instead of float
        tax = subtotal * tax_rate
        total = subtotal + tax
    except Cart.DoesNotExist:
        cart = None
        cart_items = []
        subtotal = Decimal('0')
        tax = Decimal('0')
        total = Decimal('0')

    context = {
        'cart': cart,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
    }
    return render(request, 'marketplace/cart.html', context)


@login_required
def update_cart(request):
    """Update cart item quantities"""
    if request.method == 'POST':
        cart_id = request.POST.get('cart_id')
        item_id = request.POST.get('item_id')
        action = request.POST.get('action')  # 'add' or 'remove'

        try:
            cart = Cart.objects.get(id=cart_id, customer=request.user)
            cart_item = CartItem.objects.get(id=item_id, cart=cart)

            if action == 'increment':
                cart_item.quantity += 1
                cart_item.save()
            elif action == 'decrement':
                if cart_item.quantity > 1:
                    cart_item.quantity -= 1
                    cart_item.save()
                else:
                    cart_item.delete()
            elif action == 'remove':
                cart_item.delete()

            messages.success(request, 'Cart updated successfully!')
        except (Cart.DoesNotExist, CartItem.DoesNotExist):
            messages.error(request, 'Cart item not found.')

    return redirect('marketplace:view_cart')


@login_required
def remove_from_cart(request, item_id):
    """Remove an item from the cart"""
    try:
        cart_item = CartItem.objects.get(id=item_id, cart__customer=request.user)
        product_name = cart_item.product.name
        cart_item.delete()
        messages.success(request, f'{product_name} removed from cart.')
    except CartItem.DoesNotExist:
        messages.error(request, 'Cart item not found.')

    return redirect('marketplace:view_cart')


@login_required
def checkout(request):
    """Show checkout page with payment options"""
    try:
        cart = Cart.objects.get(customer=request.user)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product')

        if not cart_items:
            messages.error(request, 'Your cart is empty.')
            return redirect('marketplace:view_cart')

        # Calculate total amount
        total_amount = sum(item.get_total_price() for item in cart_items)
        tax_rate = Decimal('0.15')
        tax = total_amount * tax_rate
        total_with_tax = total_amount + tax

        context = {
            'cart': cart,
            'cart_items': cart_items,
            'total_amount': total_amount,
            'tax': tax,
            'total_with_tax': total_with_tax,
        }
        return render(request, 'marketplace/checkout.html', context)

    except Cart.DoesNotExist:
        messages.error(request, 'Your cart is empty.')
        return redirect('marketplace:view_cart')


@login_required
def process_payment(request):
    """Process payment and create orders"""
    if request.method != 'POST':
        return redirect('marketplace:checkout')

    try:
        cart = Cart.objects.get(customer=request.user)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product')

        if not cart_items:
            messages.error(request, 'Your cart is empty.')
            return redirect('marketplace:view_cart')

        # Get payment method from form
        payment_method = request.POST.get('payment_method')
        if not payment_method:
            messages.error(request, 'Please select a payment method.')
            return redirect('marketplace:checkout')

        # Get delivery option and address information
        delivery_option = request.POST.get('delivery_option', 'pickup')
        street_address = request.POST.get('street_address', '')
        city = request.POST.get('city', '')
        postal_code = request.POST.get('postal_code', '')
        phone = request.POST.get('phone', '')

        # Store delivery information in session or create a delivery record
        delivery_details = {
            'option': delivery_option,
            'street_address': street_address,
            'city': city,
            'postal_code': postal_code,
            'phone': phone
        }

        # Group cart items by business
        from collections import defaultdict
        business_groups = defaultdict(list)

        for cart_item in cart_items:
            business_groups[cart_item.product.business].append(cart_item)

        # Create an order for each business
        for business, items in business_groups.items():
            total_amount = sum(item.get_total_price() for item in items)

            # Create order with delivery information
            order = Order.objects.create(
                customer=request.user,
                business=business,
                total_amount=total_amount,
                delivery_option=delivery_option
            )

            # Add delivery address if delivery option is selected
            if delivery_option == 'delivery':
                order.delivery_address = f"{street_address}, {city} {postal_code}"
                order.delivery_phone = phone
            order.save()

            # Create order items
            for cart_item in items:
                OrderItem.objects.create(
                    order=order,
                    product=cart_item.product,
                    quantity=cart_item.quantity,
                    price=cart_item.product.price
                )

        # Handle payment method selection
        if payment_method == 'credit_card':
            # Redirect to credit card payment page
            # Store order info in session temporarily
            request.session['payment_method'] = payment_method
            request.session['delivery_details'] = delivery_details

            # Calculate total amount for the session
            total_amount = sum(item.get_total_price() for item in cart_items)
            tax_rate = Decimal('0.15')
            tax = total_amount * tax_rate
            total_with_tax = total_amount + tax

            request.session['payment_amount'] = float(total_with_tax)

            return redirect('marketplace:credit_card_payment')
        elif payment_method == 'bank_transfer':
            # Redirect to bank transfer page
            request.session['payment_method'] = payment_method
            request.session['delivery_details'] = delivery_details

            # Calculate total amount for the session
            total_amount = sum(item.get_total_price() for item in cart_items)
            tax_rate = Decimal('0.15')
            tax = total_amount * tax_rate
            total_with_tax = total_amount + tax

            request.session['payment_amount'] = float(total_with_tax)

            return redirect('marketplace:bank_transfer_payment')
        elif payment_method == 'cash_on_delivery':
            # For cash on delivery, create payments and mark orders as pending
            for business, items in business_groups.items():
                total_amount = sum(item.get_total_price() for item in items)

                # Find the order for this business
                order = Order.objects.get(
                    customer=request.user,
                    business=business,
                    total_amount=total_amount,
                    status='pending'
                )

                # Create payment record
                Payment.objects.create(
                    order=order,
                    payment_method='cash_on_delivery',
                    amount=total_amount,
                    status='pending'
                )

            # Clear the cart
            cart_items.delete()

            messages.success(request, 'Your order(s) have been created successfully! Payment will be collected on delivery.')
            return redirect('marketplace:client_dashboard')
        else:
            # For other payment methods (if any), create payments and mark orders as pending
            for business, items in business_groups.items():
                total_amount = sum(item.get_total_price() for item in items)

                # Find the order for this business
                order = Order.objects.get(
                    customer=request.user,
                    business=business,
                    total_amount=total_amount,
                    status='pending'
                )

                # Create payment record
                Payment.objects.create(
                    order=order,
                    payment_method=payment_method,
                    amount=total_amount,
                    status='pending'
                )

            # Clear the cart
            cart_items.delete()

            messages.success(request, 'Your order(s) have been created successfully!')
            return redirect('marketplace:client_dashboard')

    except Cart.DoesNotExist:
        messages.error(request, 'Your cart is empty.')
        return redirect('marketplace:view_cart')


@login_required
def credit_card_payment(request):
    """Display credit card payment form"""
    amount = request.session.get('payment_amount', 0)

    if not amount:
        messages.error(request, 'No payment amount found. Please go through checkout again.')
        return redirect('marketplace:checkout')

    context = {
        'amount': amount
    }
    return render(request, 'marketplace/credit_card_payment.html', context)


@login_required
def process_credit_card_payment(request):
    """Process credit card payment"""
    if request.method != 'POST':
        return redirect('marketplace:checkout')

    # Get payment details from form
    card_number = request.POST.get('card_number', '')
    card_holder_name = request.POST.get('card_holder_name', '')
    expiry_date = request.POST.get('expiry_date', '')
    cvv = request.POST.get('cvv', '')

    # Validate required fields
    if not all([card_number, card_holder_name, expiry_date, cvv]):
        messages.error(request, 'Please fill in all required card details.')
        return redirect('marketplace:credit_card_payment')

    # Basic validation for card number (remove spaces)
    card_number_clean = card_number.replace(' ', '')
    if len(card_number_clean) != 16 or not card_number_clean.isdigit():
        messages.error(request, 'Invalid card number. Please enter a valid 16-digit card number.')
        return redirect('marketplace:credit_card_payment')

    # Get cart to recreate orders
    try:
        cart = Cart.objects.get(customer=request.user)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product')

        if not cart_items:
            messages.error(request, 'Your cart is empty.')
            return redirect('marketplace:checkout')

        # Get stored delivery details from session
        delivery_details = request.session.get('delivery_details', {})
        delivery_option = delivery_details.get('option', 'pickup')
        street_address = delivery_details.get('street_address', '')
        city = delivery_details.get('city', '')
        postal_code = delivery_details.get('postal_code', '')
        phone = delivery_details.get('phone', '')

        # Group cart items by business (similar to original process)
        from collections import defaultdict
        business_groups = defaultdict(list)

        for cart_item in cart_items:
            business_groups[cart_item.product.business].append(cart_item)

        # Create an order for each business
        for business, items in business_groups.items():
            total_amount = sum(item.get_total_price() for item in items)

            # Create order with delivery information
            order = Order.objects.create(
                customer=request.user,
                business=business,
                total_amount=total_amount,
                delivery_option=delivery_option
            )

            # Add delivery address if delivery option is selected
            if delivery_option == 'delivery':
                order.delivery_address = f"{street_address}, {city} {postal_code}"
                order.delivery_phone = phone
            order.save()

            # Create order items
            for cart_item in items:
                OrderItem.objects.create(
                    order=order,
                    product=cart_item.product,
                    quantity=cart_item.quantity,
                    price=cart_item.product.price
                )

            # Create payment record with last 4 digits of card
            last_four = card_number_clean[-4:]
            Payment.objects.create(
                order=order,
                payment_method='credit_card',
                amount=total_amount,
                status='completed',  # In a real app, this would be 'processing' until verified
                card_last_four=last_four
            )

        # Clear the cart
        cart_items.delete()

        # Clear session data
        if 'payment_amount' in request.session:
            del request.session['payment_amount']
        if 'payment_method' in request.session:
            del request.session['payment_method']
        if 'delivery_details' in request.session:
            del request.session['delivery_details']

        messages.success(request, 'Your payment has been processed successfully! Your order(s) are confirmed.')
        return redirect('marketplace:client_dashboard')

    except Cart.DoesNotExist:
        messages.error(request, 'Your cart is empty.')
        return redirect('marketplace:checkout')


@login_required
def bank_transfer_payment(request):
    """Display bank transfer payment form"""
    amount = request.session.get('payment_amount', 0)

    if not amount:
        messages.error(request, 'No payment amount found. Please go through checkout again.')
        return redirect('marketplace:checkout')

    # Generate a reference code for the bank transfer
    import random
    import string
    reference_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

    context = {
        'amount': amount,
        'reference_code': reference_code
    }
    return render(request, 'marketplace/bank_transfer_payment.html', context)


@login_required
def process_bank_transfer(request):
    """Process bank transfer payment with proof of payment"""
    if request.method != 'POST':
        return redirect('marketplace:checkout')

    # Get uploaded proof of payment
    proof_of_payment = request.FILES.get('proof_of_payment')

    if not proof_of_payment:
        messages.error(request, 'Please upload proof of payment.')
        return redirect('marketplace:bank_transfer_payment')

    # Validate file type
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    file_extension = '.' + proof_of_payment.name.lower().split('.')[-1]

    if file_extension not in allowed_extensions:
        messages.error(request, 'Invalid file type. Please upload a PDF, JPG, or PNG file.')
        return redirect('marketplace:bank_transfer_payment')

    # Check file size (max 5MB)
    max_size = 5 * 1024 * 1024  # 5MB in bytes
    if proof_of_payment.size > max_size:
        messages.error(request, 'File too large. Please upload a file smaller than 5MB.')
        return redirect('marketplace:bank_transfer_payment')

    # Get cart to recreate orders
    try:
        cart = Cart.objects.get(customer=request.user)
        cart_items = CartItem.objects.filter(cart=cart).select_related('product')

        if not cart_items:
            messages.error(request, 'Your cart is empty.')
            return redirect('marketplace:checkout')

        # Get stored delivery details from session
        delivery_details = request.session.get('delivery_details', {})
        delivery_option = delivery_details.get('option', 'pickup')
        street_address = delivery_details.get('street_address', '')
        city = delivery_details.get('city', '')
        postal_code = delivery_details.get('postal_code', '')
        phone = delivery_details.get('phone', '')

        # Group cart items by business (similar to original process)
        from collections import defaultdict
        business_groups = defaultdict(list)

        for cart_item in cart_items:
            business_groups[cart_item.product.business].append(cart_item)

        # Create an order for each business
        for business, items in business_groups.items():
            total_amount = sum(item.get_total_price() for item in items)

            # Create order with delivery information
            order = Order.objects.create(
                customer=request.user,
                business=business,
                total_amount=total_amount,
                delivery_option=delivery_option,
                status='pending'  # Status remains pending until payment is verified
            )

            # Add delivery address if delivery option is selected
            if delivery_option == 'delivery':
                order.delivery_address = f"{street_address}, {city} {postal_code}"
                order.delivery_phone = phone
            order.save()

            # Create order items
            for cart_item in items:
                OrderItem.objects.create(
                    order=order,
                    product=cart_item.product,
                    quantity=cart_item.quantity,
                    price=cart_item.product.price
                )

            # Create payment record with proof of payment
            Payment.objects.create(
                order=order,
                payment_method='bank_transfer',
                amount=total_amount,
                status='pending',  # Status is pending until verified by admin
                proof_of_payment=proof_of_payment
            )

        # Clear the cart
        cart_items.delete()

        # Clear session data
        if 'payment_amount' in request.session:
            del request.session['payment_amount']
        if 'payment_method' in request.session:
            del request.session['payment_method']
        if 'delivery_details' in request.session:
            del request.session['delivery_details']

        messages.success(request, 'Your proof of payment has been submitted successfully! Our team will verify it shortly. Your order(s) will be processed once payment is confirmed.')
        return redirect('marketplace:client_dashboard')

    except Cart.DoesNotExist:
        messages.error(request, 'Your cart is empty.')
        return redirect('marketplace:checkout')


@login_required
def order_detail(request, pk):
    """View order details"""
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    order_items = order.items.all()

    # Calculate tax and total
    subtotal = order.total_amount
    tax_rate = Decimal('0.15')
    tax = subtotal * tax_rate
    total_with_tax = subtotal + tax

    context = {
        'order': order,
        'order_items': order_items,
        'subtotal': subtotal,
        'tax': tax,
        'total_with_tax': total_with_tax,
    }
    return render(request, 'marketplace/order_detail.html', context)


@login_required
@business_owner_required
def business_orders(request):
    """Display orders for the selected business of the business owner"""
    # Get the business ID from the request, or use the first one if not specified
    selected_business_id = request.GET.get('business_id')
    if selected_business_id:
        try:
            business = Business.objects.get(id=selected_business_id, owner=request.user)
        except Business.DoesNotExist:
            messages.error(request, 'Selected business not found.')
            return redirect('marketplace:business_dashboard')
    else:
        business = Business.objects.filter(owner=request.user).first()

    if not business:
        messages.error(request, 'No business found associated with your account.')
        return redirect('marketplace:business_dashboard')

    # Get orders for this business
    orders = Order.objects.filter(business=business).order_by('-created_at')

    # Apply filters if present
    status_filter = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if status_filter:
        orders = orders.filter(status=status_filter)

    if date_from:
        from datetime import datetime
        try:
            orders = orders.filter(created_at__date__gte=datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass  # Ignore invalid date format

    if date_to:
        from datetime import datetime
        try:
            orders = orders.filter(created_at__date__lte=datetime.strptime(date_to, '%Y-%m-%d'))
        except ValueError:
            pass  # Ignore invalid date format

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    context = {
        'orders': orders,
        'business': business,
        'all_businesses': all_businesses,
    }
    return render(request, 'marketplace/business_orders.html', context)


@login_required
@business_owner_required
def business_order_detail(request, order_id):
    """Display detailed order information for business owner"""
    # Get the specific order for this business, ensuring it belongs to a business owned by the user
    order = get_object_or_404(Order, id=order_id, business__owner=request.user)
    order_items = order.items.all()

    # Calculate tax and total
    subtotal = order.total_amount
    tax_rate = Decimal('0.15')
    tax = subtotal * tax_rate
    total_with_tax = subtotal + tax

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    context = {
        'order': order,
        'order_items': order_items,
        'subtotal': subtotal,
        'tax': tax,
        'total_with_tax': total_with_tax,
        'all_businesses': all_businesses,
    }
    return render(request, 'marketplace/business_order_detail.html', context)


@login_required
@business_owner_required
def update_order_status(request, order_id):
    """Update order status"""
    if request.method != 'POST':
        return redirect('marketplace:business_orders')

    # Get the specific order for this business, ensuring it belongs to a business owned by the user
    order = get_object_or_404(Order, id=order_id, business__owner=request.user)

    action = request.POST.get('action')

    if action == 'confirm':
        order.status = 'confirmed'
        messages.success(request, f'Order #{order.id} has been confirmed.')
    elif action == 'cancel':
        order.status = 'cancelled'
        messages.success(request, f'Order #{order.id} has been cancelled.')
    elif action == 'start_processing':
        order.status = 'in_progress'
        messages.success(request, f'Order #{order.id} status updated to in progress.')
    elif action == 'complete':
        order.status = 'completed'
        # Reduce stock for each item in the order
        for item in order.items.all():
            if item.product:
                # Reduce the product's stock quantity
                item.product.stock_quantity -= item.quantity
                # Ensure stock doesn't go below 0
                if item.product.stock_quantity < 0:
                    item.product.stock_quantity = 0
                item.product.save()
        messages.success(request, f'Order #{order.id} has been marked as completed.')

    order.save()

    # If this is an AJAX request, return JSON response
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.http import JsonResponse
        return JsonResponse({'status': 'success', 'message': f'Order #{order.id} status updated to {order.get_status_display()}'})

    return redirect('marketplace:business_order_detail', order_id=order.id)


@login_required
def request_product(request):
    if request.method == 'POST':
        form = ProductRequestForm(request.POST)
        if form.is_valid():
            req = form.save(commit=False)
            req.requester = request.user
            req.save()
            messages.success(request, 'Product request submitted successfully!')
            return redirect('marketplace:home')
    else:
        form = ProductRequestForm()
    return render(request, 'marketplace/request_product.html', {'form': form})


@login_required
def request_service(request):
    if request.method == 'POST':
        form = ServiceRequestForm(request.POST)
        if form.is_valid():
            req = form.save(commit=False)
            req.requester = request.user
            req.save()
            messages.success(request, 'Service request submitted successfully!')
            return redirect('marketplace:home')
    else:
        form = ServiceRequestForm()
    return render(request, 'marketplace/request_service.html', {'form': form})


@login_required
def rate_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment', '')
        
        # Check if user already reviewed this product
        existing_review = Review.objects.filter(
            reviewer=request.user, 
            product=product
        ).first()
        
        if existing_review:
            existing_review.rating = rating
            existing_review.comment = comment
            existing_review.save()
        else:
            Review.objects.create(
                reviewer=request.user,
                product=product,
                rating=rating,
                comment=comment
            )
        
        messages.success(request, 'Thank you for your review!')
        return redirect('product_detail', pk=pk)
    
    return redirect('product_detail', pk=pk)


@login_required
def rate_service(request, pk):
    service = get_object_or_404(Service, pk=pk)
    
    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment', '')
        
        # Check if user already reviewed this service
        existing_review = Review.objects.filter(
            reviewer=request.user, 
            service=service
        ).first()
        
        if existing_review:
            existing_review.rating = rating
            existing_review.comment = comment
            existing_review.save()
        else:
            Review.objects.create(
                reviewer=request.user,
                service=service,
                rating=rating,
                comment=comment
            )
        
        messages.success(request, 'Thank you for your review!')
        return redirect('service_detail', pk=pk)


@login_required
def admin_dashboard(request):
    """Main admin dashboard to manage users, businesses, and other admin tasks"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    # Get statistics for the dashboard
    total_users = User.objects.count()
    total_clients = UserProfile.objects.filter(user_type='client').count()
    total_business_owners = UserProfile.objects.filter(user_type='business_owner').count()
    approved_businesses = UserProfile.objects.filter(user_type='business_owner', is_approved=True).count()
    pending_businesses = UserProfile.objects.filter(user_type='business_owner', is_approved=False).count()
    total_products = Product.objects.count()
    total_services = Service.objects.count()
    total_orders = Order.objects.count()

    # Calculate total revenue and admin's payment from all businesses
    completed_orders = Order.objects.filter(
        status__in=['completed', 'delivered']  # Assuming these statuses mean the order is finalized
    )
    
    total_revenue = 0
    for order in completed_orders:
        total_revenue += float(order.total_amount)
    
    # Calculate admin's payment (5% of total revenue)
    admin_payment = total_revenue * 0.05

    # Get shopping trips and requests statistics for admin
    total_shopping_trips = ShoppingTrip.objects.count()
    active_shopping_trips = ShoppingTrip.objects.filter(status='available').count()
    total_shopping_requests = ShoppingRequest.objects.count()
    pending_shopping_requests = ShoppingRequest.objects.filter(status='pending').count()

    # Get recent shopping trips and requests
    recent_shopping_trips = ShoppingTrip.objects.select_related('user').order_by('-created_at')[:10]
    recent_shopping_requests = ShoppingRequest.objects.select_related('requester', 'shopper', 'shopping_trip__user').order_by('-created_at')[:10]

    # Get admin banking details
    banking_details = AdminBankingDetails.objects.first()

    context = {
        'total_users': total_users,
        'total_clients': total_clients,
        'total_business_owners': total_business_owners,
        'approved_businesses': approved_businesses,
        'pending_businesses': pending_businesses,
        'total_products': total_products,
        'total_services': total_services,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'admin_payment': admin_payment,
        'total_shopping_trips': total_shopping_trips,
        'active_shopping_trips': active_shopping_trips,
        'total_shopping_requests': total_shopping_requests,
        'pending_shopping_requests': pending_shopping_requests,
        'recent_shopping_trips': recent_shopping_trips,
        'recent_shopping_requests': recent_shopping_requests,
        'banking_details': banking_details,
    }
    return render(request, 'marketplace/admin/dashboard.html', context)


@login_required
def update_admin_banking_details(request):
    """Allow admin to update banking details for receiving payments"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    # Get existing banking details or create new instance
    banking_details = AdminBankingDetails.objects.first()

    if request.method == 'POST':
        form = AdminBankingDetailsForm(request.POST, instance=banking_details)
        if form.is_valid():
            form.save()
            messages.success(request, 'Banking details updated successfully!')
            return redirect('marketplace:admin_dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = AdminBankingDetailsForm(instance=banking_details)

    context = {
        'form': form,
        'banking_details': banking_details,
    }
    return render(request, 'marketplace/admin/update_banking_details.html', context)


@login_required
def admin_business_revenue(request):
    """Display business revenue details for admin"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    # Handle form submission to update paid status
    if request.method == 'POST':
        business_id = request.POST.get('business_id')
        paid_status = request.POST.get('paid_status')
        
        try:
            from datetime import datetime
            business = Business.objects.get(id=business_id)
            
            # Get the latest admin fee payment record for this business
            # In a real scenario, you might want to create records for specific periods
            # For now, we'll create or update a record for the current period
            from django.utils import timezone
            now = timezone.now()
            
            # Get the latest payment record or create a new one
            payment_record, created = BusinessAdminFeePayment.objects.get_or_create(
                business=business,
                period_start__year=now.year,
                period_end__year=now.year,
                defaults={
                    'period_start': now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
                    'period_end': now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999),
                    'total_revenue': Decimal('0'),
                    'admin_fee_amount': Decimal('0'),
                    'is_paid': paid_status == 'paid'
                }
            )
            
            # Update the payment status
            payment_record.is_paid = paid_status == 'paid'
            if paid_status == 'paid':
                payment_record.paid_date = now
            else:
                payment_record.paid_date = None
            payment_record.save()
            
            if paid_status == 'paid':
                messages.success(request, f'Marked business "{business.name}" as paid.')
            else:
                messages.info(request, f'Marked business "{business.name}" as not paid.')
        except Business.DoesNotExist:
            messages.error(request, 'Business not found.')
        
        return redirect('marketplace:admin_business_revenue')

    # Get all businesses with their revenue
    from django.db.models import Sum, F
    from django.db import models
    from django.utils import timezone
    
    now = timezone.now()
    businesses_with_revenue = Business.objects.annotate(
        total_revenue=Sum(
            'orders__total_amount',
            filter=models.Q(orders__status__in=['completed', 'delivered'])
        )
    ).annotate(
        admin_fee=F('total_revenue') * Decimal('0.05'),  # 5% admin fee - using Decimal
        completed_orders_count=Sum(
            'orders__id',
            filter=models.Q(orders__status__in=['completed', 'delivered']),
            distinct=True
        )
    ).exclude(total_revenue=None).order_by('-total_revenue')

    # Add payment status to each business
    for business in businesses_with_revenue:
        # Get the payment record for the current year
        payment_record, created = BusinessAdminFeePayment.objects.get_or_create(
            business=business,
            period_start__year=now.year,
            period_end__year=now.year,
            defaults={
                'period_start': now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
                'period_end': now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999),
                'total_revenue': business.total_revenue or Decimal('0'),
                'admin_fee_amount': (business.total_revenue or Decimal('0')) * Decimal('0.05'),
                'is_paid': False
            }
        )
        # Update the payment record with current values if they've changed
        if not created:
            payment_record.total_revenue = business.total_revenue or Decimal('0')
            payment_record.admin_fee_amount = (business.total_revenue or Decimal('0')) * Decimal('0.05')
            payment_record.save()
        
        business.payment_status = payment_record.is_paid
        business.payment_record_id = payment_record.id

    # Calculate overall totals
    overall_total_revenue = sum(business.total_revenue or Decimal('0') for business in businesses_with_revenue)
    overall_admin_fee = overall_total_revenue * Decimal('0.05')

    context = {
        'businesses_with_revenue': businesses_with_revenue,
        'overall_total_revenue': overall_total_revenue,
        'overall_admin_fee': overall_admin_fee,
    }
    return render(request, 'marketplace/admin/business_revenue.html', context)


@login_required
def admin_manage_products(request):
    """Manage all products in the system"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    products = Product.objects.select_related('business', 'category').all()

    # Handle product updates
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        product_action = request.POST.get('action')  # 'delete', 'toggle_availability', etc.

        try:
            product = Product.objects.get(id=product_id)
            if product_action == 'delete':
                product.delete()
                messages.success(request, f'Product {product.name} deleted successfully.')
            elif product_action == 'toggle_availability':
                product.is_available = not product.is_available
                product.save()
                status = "available" if product.is_available else "unavailable"
                messages.success(request, f'Product {product.name} is now {status}.')
        except Product.DoesNotExist:
            messages.error(request, 'Product not found.')

        return redirect('marketplace:admin_manage_products')

    context = {
        'products': products,
    }
    return render(request, 'marketplace/admin/manage_products.html', context)


@login_required
def admin_manage_services(request):
    """Manage all services in the system"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    services = Service.objects.select_related('business', 'category').all()

    # Handle service updates
    if request.method == 'POST':
        service_id = request.POST.get('service_id')
        service_action = request.POST.get('action')  # 'delete', 'toggle_availability', etc.

        try:
            service = Service.objects.get(id=service_id)
            if service_action == 'delete':
                service.delete()
                messages.success(request, f'Service {service.name} deleted successfully.')
            elif service_action == 'toggle_availability':
                service.is_available = not service.is_available
                service.save()
                status = "available" if service.is_available else "unavailable"
                messages.success(request, f'Service {service.name} is now {status}.')
        except Service.DoesNotExist:
            messages.error(request, 'Service not found.')

        return redirect('marketplace:admin_manage_services')

    context = {
        'services': services,
    }
    return render(request, 'marketplace/admin/manage_services.html', context)


@login_required
def admin_manage_orders(request):
    """Manage all orders in the system"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    orders = Order.objects.select_related('customer', 'business').prefetch_related('items').all()

    # Handle order updates
    if request.method == 'POST':
        order_id = request.POST.get('order_id')
        order_action = request.POST.get('action')  # 'cancel', 'complete', etc.

        try:
            order = Order.objects.get(id=order_id)
            if order_action == 'cancel':
                order.status = 'cancelled'
                order.save()
                messages.success(request, f'Order #{order.id} has been cancelled.')
            elif order_action == 'complete':
                order.status = 'completed'
                order.save()
                messages.success(request, f'Order #{order.id} has been marked as completed.')
        except Order.DoesNotExist:
            messages.error(request, 'Order not found.')

        return redirect('marketplace:admin_manage_orders')

    context = {
        'orders': orders,
    }
    return render(request, 'marketplace/admin/manage_orders.html', context)


@login_required
def rate_business(request, business_id):
    """Allow customers to leave reviews for businesses"""
    if request.method != 'POST':
        return redirect('marketplace:home')

    business = get_object_or_404(Business, id=business_id)

    # Get rating and comment from form
    rating = request.POST.get('rating')
    comment = request.POST.get('comment', '')

    if not rating:
        messages.error(request, 'Please select a rating.')
        return redirect('marketplace:business_detail', pk=business_id)

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError
    except ValueError:
        messages.error(request, 'Invalid rating. Please select a rating between 1 and 5.')
        return redirect('marketplace:business_detail', pk=business_id)

    # Create the review
    Review.objects.create(
        reviewer=request.user,
        business=business,
        rating=rating,
        comment=comment
    )

    messages.success(request, 'Thank you for your review!')
    return redirect('marketplace:business_detail', pk=business_id)


def business_list(request):
    """Display a list of all businesses"""
    businesses = Business.objects.filter(is_active=True).select_related('owner__userprofile')

    # Add average rating to each business
    for business in businesses:
        reviews = business.reviews.all()
        if reviews.exists():
            business.avg_rating = sum(review.rating for review in reviews) / reviews.count()
        else:
            business.avg_rating = 0

    context = {
        'businesses': businesses,
    }
    return render(request, 'marketplace/business_list.html', context)


def business_map(request, business_id):
    """Display business location on a map"""
    business = get_object_or_404(Business, id=business_id)
    
    # Default to Namibia coordinates if no location set
    default_lat = -22.957689  # Windhoek, Namibia
    default_lng = 18.490417
    
    context = {
        'business': business,
        'latitude': float(business.latitude) if business.latitude else default_lat,
        'longitude': float(business.longitude) if business.longitude else default_lng,
        'has_location': bool(business.latitude and business.longitude),
    }
    return render(request, 'marketplace/business_map.html', context)


def business_detail(request, pk):
    """Display business details and allow reviews"""
    business = get_object_or_404(Business, id=pk)

    # Get business reviews with like/dislike counts
    from django.db.models import Count, Q
    reviews = business.reviews.annotate(
        num_likes=Count('review_likes', filter=Q(review_likes__is_like=True)),
        num_dislikes=Count('review_likes', filter=Q(review_likes__is_like=False))
    ).order_by('-created_at')

    # Calculate average rating
    avg_rating = 0
    if reviews.exists():
        avg_rating = sum(review.rating for review in reviews) / reviews.count()

    # Get business products and services
    products = Product.objects.filter(business=business)
    services = Service.objects.filter(business=business)

    context = {
        'business': business,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'products': products,
        'services': services,
    }
    return render(request, 'marketplace/business_detail.html', context)


@login_required
def toggle_review_like(request, review_id):
    """Toggle like/dislike for a review"""
    import json
    from django.http import HttpResponse
    from django.shortcuts import get_object_or_404
    from .models import Review, ReviewLike

    if request.method != 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return HttpResponse(json.dumps({'success': False, 'error': 'Invalid request method'}), content_type='application/json')
        return redirect('marketplace:home')

    try:
        review = get_object_or_404(Review, id=review_id)
        action_param = request.POST.get('action')

        if action_param not in ['like', 'dislike']:
            error_msg = f"Invalid action: {action_param}. Expected 'like' or 'dislike'"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return HttpResponse(json.dumps({'success': False, 'error': error_msg}), content_type='application/json')
            else:
                from django.contrib import messages
                messages.error(request, error_msg)
                return redirect('marketplace:home')

        is_like = action_param == 'like'

        # Check if user already liked/disliked this review
        review_like, created = ReviewLike.objects.get_or_create(
            user=request.user,
            review=review,
            defaults={'is_like': is_like}
        )

        # Store the previous state before any changes
        previous_state = None
        was_deleted = False

        if not created:
            previous_state = review_like.is_like

            if review_like.is_like == is_like:
                # Remove the like/dislike if clicking the same button again
                review_like.delete()
                was_deleted = True
            else:
                # Switch from like to dislike or vice versa
                review_like.is_like = is_like
                review_like.save()

        # Calculate updated counts
        num_likes = review.review_likes.filter(is_like=True).count()
        num_dislikes = review.review_likes.filter(is_like=False).count()

        # Determine user action
        if created:
            user_action = 'liked' if is_like else 'disliked'
        elif was_deleted:  # User clicked the same button again, so it was removed
            user_action = 'removed_like' if is_like else 'removed_dislike'
        elif previous_state is not None and previous_state != is_like:  # User switched
            user_action = 'switched_to_like' if is_like else 'switched_to_dislike'
        else:
            user_action = 'removed_like' if is_like else 'removed_dislike'

        # Return success response for AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response_data = {
                'success': True,
                'likes': num_likes,
                'dislikes': num_dislikes,
                'user_action': user_action
            }
            return HttpResponse(json.dumps(response_data), content_type='application/json')

        # For non-AJAX requests, redirect back
        next_url = request.POST.get('next', '/')
        if not next_url or not next_url.startswith('/'):
            next_url = '/'
        return redirect(next_url)

    except Exception as e:
        import traceback
        print(f"Error in toggle_review_like: {str(e)}")
        print(traceback.format_exc())
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response_data = {'success': False, 'error': str(e)}
            return HttpResponse(json.dumps(response_data), content_type='application/json')
        else:
            from django.contrib import messages
            messages.error(request, f'An error occurred: {str(e)}')
            return redirect('marketplace:home')


@login_required
def go_shopping(request):
    """Page where users can see others going shopping and request items"""
    from django.db.models import Count
    from datetime import datetime, timedelta

    # Get upcoming shopping trips that are still available
    upcoming_trips = ShoppingTrip.objects.filter(
        status='available',
        planned_departure_time__gte=datetime.now()
    ).select_related('user').annotate(
        request_count=Count('requests')
    ).order_by('planned_departure_time')

    # Get current user's shopping trips
    user_trips = ShoppingTrip.objects.filter(user=request.user).order_by('-created_at')

    # Calculate stats
    total_shopping_trips = ShoppingTrip.objects.count()
    active_shopping_trips = ShoppingTrip.objects.filter(status='available').count()
    total_shopping_requests = ShoppingRequest.objects.count()
    pending_shopping_requests = ShoppingRequest.objects.filter(status='pending').count()

    context = {
        'upcoming_trips': upcoming_trips,
        'user_trips': user_trips,
        'total_shopping_trips': total_shopping_trips,
        'active_shopping_trips': active_shopping_trips,
        'total_shopping_requests': total_shopping_requests,
        'pending_shopping_requests': pending_shopping_requests,
    }
    return render(request, 'marketplace/go_shopping.html', context)


@login_required
def create_shopping_trip(request):
    """Allow user to create a new shopping trip"""
    if request.method == 'POST':
        from django.utils.dateparse import parse_datetime

        destination = request.POST.get('destination', '')
        planned_departure_str = request.POST.get('planned_departure_time')
        estimated_return_str = request.POST.get('estimated_return_time')
        notes = request.POST.get('notes', '')

        # Parse datetime strings
        planned_departure = parse_datetime(planned_departure_str)
        estimated_return = parse_datetime(estimated_return_str)

        if planned_departure and estimated_return:
            ShoppingTrip.objects.create(
                user=request.user,
                destination=destination,
                planned_departure_time=planned_departure,
                estimated_return_time=estimated_return,
                notes=notes
            )
            messages.success(request, 'Your shopping trip has been created!')
        else:
            messages.error(request, 'Please provide valid departure and return times.')

        return redirect('marketplace:go_shopping')

    return render(request, 'marketplace/create_shopping_trip.html')


@login_required
def make_shopping_request(request, trip_id):
    """Allow user to make a request to a shopper"""
    trip = get_object_or_404(ShoppingTrip, id=trip_id, status='available')

    if request.user == trip.user:
        messages.error(request, "You can't request items from yourself!")
        return redirect('marketplace:go_shopping')

    if request.method == 'POST':
        items_requested = request.POST.get('items_requested', '')
        estimated_total_cost = request.POST.get('estimated_total_cost', '')
        amount_to_pay_shopper = request.POST.get('amount_to_pay_shopper', '')
        delivery_location = request.POST.get('delivery_location', '')
        contact_details = request.POST.get('contact_details', '')
        notes = request.POST.get('notes', '')

        # Validate required fields
        if items_requested and delivery_location and contact_details:
            # Convert amounts to Decimal if provided
            from decimal import Decimal, InvalidOperation
            try:
                cost_decimal = Decimal(estimated_total_cost) if estimated_total_cost else None
                pay_decimal = Decimal(amount_to_pay_shopper) if amount_to_pay_shopper else None

                # Validate that amount to pay is greater than or equal to estimated cost
                if cost_decimal and pay_decimal and pay_decimal < cost_decimal:
                    messages.error(request, 'Amount to pay shopper must be greater than or equal to the estimated total cost.')
                    context = {'trip': trip}
                    return render(request, 'marketplace/make_shopping_request.html', context)

                ShoppingRequest.objects.create(
                    requester=request.user,
                    shopper=trip.user,
                    shopping_trip=trip,
                    items_requested=items_requested,
                    estimated_total_cost=cost_decimal,
                    amount_to_pay_shopper=pay_decimal,
                    delivery_location=delivery_location,
                    contact_details=contact_details,
                    notes=notes
                )
                messages.success(request, 'Your shopping request has been sent!')
            except InvalidOperation:
                messages.error(request, 'Please enter valid numeric values for costs.')
        else:
            messages.error(request, 'Please fill in all required fields.')

        return redirect('marketplace:go_shopping')

    context = {
        'trip': trip
    }
    return render(request, 'marketplace/make_shopping_request.html', context)


@login_required
def my_shopping_requests(request):
    """Show user's shopping requests (made and received)"""
    sent_requests = ShoppingRequest.objects.filter(requester=request.user).select_related(
        'shopper', 'shopping_trip__user'
    ).order_by('-created_at')

    received_requests = ShoppingRequest.objects.filter(shopper=request.user).select_related(
        'requester', 'shopping_trip__user'
    ).order_by('-created_at')

    context = {
        'sent_requests': sent_requests,
        'received_requests': received_requests,
    }
    return render(request, 'marketplace/my_shopping_requests.html', context)


@login_required
def admin_manage_reviews(request):
    """Manage all reviews in the system"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    reviews = Review.objects.select_related('reviewer', 'business', 'product', 'service').prefetch_related('review_likes').all()

    # Handle review updates
    if request.method == 'POST':
        review_id = request.POST.get('review_id')
        review_action = request.POST.get('action')  # 'delete', etc.

        try:
            review = Review.objects.get(id=review_id)
            if review_action == 'delete':
                review.delete()
                messages.success(request, f'Review by {review.reviewer.username} deleted successfully.')
        except Review.DoesNotExist:
            messages.error(request, 'Review not found.')

        return redirect('marketplace:admin_manage_reviews')

    context = {
        'reviews': reviews,
    }
    return render(request, 'marketplace/admin/manage_reviews.html', context)


@login_required
def admin_order_detail(request, order_id):
    """Display detailed order information for admin"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    # Get the specific order
    order = get_object_or_404(Order, id=order_id)
    order_items = order.items.all()

    # Get payment information
    payments = order.payments.all()

    # Calculate tax and total
    subtotal = order.total_amount
    tax_rate = Decimal('0.15')
    tax = subtotal * tax_rate
    total_with_tax = subtotal + tax

    context = {
        'order': order,
        'order_items': order_items,
        'payments': payments,
        'subtotal': subtotal,
        'tax': tax,
        'total_with_tax': total_with_tax,
    }
    return render(request, 'marketplace/admin/order_detail.html', context)


@login_required
def admin_manage_users(request):
    """Manage all users in the system"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    # Get query parameters for filtering
    user_type = request.GET.get('user_type')
    content = request.GET.get('content')

    # Base queryset
    users = User.objects.select_related('userprofile').prefetch_related('businesses').all()

    # Apply filters based on query parameters
    if user_type:
        if user_type == 'client':
            users = users.filter(userprofile__user_type='client')
        elif user_type == 'business_owner':
            users = users.filter(userprofile__user_type='business_owner')

    # Handle content-based filtering (products, services, orders)
    if content == 'products':
        # Get users who have products
        from django.db.models import Exists, OuterRef
        users = users.annotate(
            has_products=Exists(Product.objects.filter(business__owner=OuterRef('pk')))
        ).filter(has_products=True)
    elif content == 'services':
        # Get users who have services
        from django.db.models import Exists, OuterRef
        users = users.annotate(
            has_services=Exists(Service.objects.filter(business__owner=OuterRef('pk')))
        ).filter(has_services=True)
    elif content == 'orders':
        # Get users who have orders (as customers)
        from django.db.models import Exists, OuterRef
        users = users.annotate(
            has_orders=Exists(Order.objects.filter(customer=OuterRef('pk')))
        ).filter(has_orders=True)

    # Handle user updates
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        user_action = request.POST.get('action')  # 'delete', 'change_type', etc.

        try:
            user = User.objects.get(id=user_id)
            if user_action == 'delete':
                user.delete()
                messages.success(request, f'User {user.username} deleted successfully.')
            elif user_action == 'toggle_approval':
                profile = user.userprofile
                profile.is_approved = not profile.is_approved
                profile.save()
                status = "approved" if profile.is_approved else "unapproved"
                messages.success(request, f'Business owner {user.username} is now {status}.')
        except User.DoesNotExist:
            messages.error(request, 'User not found.')

        return redirect('marketplace:admin_manage_users')

    context = {
        'users': users,
        'current_filter': user_type or content,
    }
    return render(request, 'marketplace/admin/manage_users.html', context)


@login_required
def toggle_dashboard_view(request):
    """Toggle between client and business dashboards"""
    try:
        user_profile = request.user.userprofile
        if user_profile.user_type == 'business_owner' and user_profile.is_approved:
            # Get the referer to determine where the user came from
            referer = request.META.get('HTTP_REFERER', '')

            # Check if the referer contains the business dashboard URL
            if 'business/dashboard' in referer:
                # Came from business dashboard, switch to client dashboard
                return redirect('marketplace:client_dashboard')
            else:
                # Came from client side, switch to business dashboard
                return redirect('marketplace:business_dashboard')
    except AttributeError:
        # UserProfile doesn't exist for this user
        pass

    return redirect('marketplace:home')


@login_required
def client_dashboard(request):
    """Client dashboard showing their orders, cart, and market participation"""
    # Get user's orders
    orders = Order.objects.filter(customer=request.user).select_related('business')

    # Get user's cart items if there's a cart system
    # Check if CartItem model exists
    cart_items = []
    try:
        from .models import CartItem, Cart  # Try to import CartItem and Cart
        # If Cart and CartItem exist, get the user's cart items
        cart_items = CartItem.objects.filter(cart__customer=request.user).select_related('product')
    except ImportError:
        # If Cart or CartItem doesn't exist, cart_items remains empty
        pass

    # Get user's product requests
    product_requests = ProductRequest.objects.filter(requester=request.user)

    # Get user's service requests
    service_requests = ServiceRequest.objects.filter(requester=request.user)

    # Get user's reviews with like/dislike counts
    from django.db.models import Count, Q
    user_reviews = Review.objects.filter(reviewer=request.user).select_related('business', 'product', 'service').annotate(
        num_likes=Count('review_likes', filter=Q(review_likes__is_like=True)),
        num_dislikes=Count('review_likes', filter=Q(review_likes__is_like=False))
    ).order_by('-created_at')

    # Calculate market participation metrics
    total_spent = sum(float(order.total_amount) for order in orders if order.status != 'cancelled')
    total_orders = orders.count()

    # Get recently viewed items if tracking is implemented
    # For now, we'll get recommended products based on their activity
    recommended_products = get_product_recommendations(request.user)

    # Get top 3 reviews based on likes
    from django.db.models import Count, Q
    top_reviews = Review.objects.select_related('reviewer', 'business').annotate(
        num_likes=Count('review_likes', filter=Q(review_likes__is_like=True)),
        num_dislikes=Count('review_likes', filter=Q(review_likes__is_like=False))
    ).order_by('-num_likes', 'created_at')[:3]

    # Get shopping trips and requests for the user
    from datetime import datetime
    upcoming_shopping_trips = ShoppingTrip.objects.filter(
        status='available',
        planned_departure_time__gte=datetime.now()
    ).select_related('user').exclude(user=request.user).annotate(
        request_count=Count('requests')
    ).order_by('planned_departure_time')[:5]  # Limit to 5 upcoming trips

    sent_shopping_requests = ShoppingRequest.objects.filter(
        requester=request.user
    ).select_related('shopper', 'shopping_trip__user').order_by('-created_at')[:5]  # Limit to 5 recent requests

    received_shopping_requests = ShoppingRequest.objects.filter(
        shopper=request.user
    ).select_related('requester', 'shopping_trip__user').order_by('-created_at')[:5]  # Limit to 5 recent requests

    context = {
        'orders': orders,
        'cart_items': cart_items,
        'product_requests': product_requests,
        'service_requests': service_requests,
        'user_reviews': user_reviews,
        'total_spent': total_spent,
        'total_orders': total_orders,
        'recommended_products': recommended_products,
        'top_reviews': top_reviews,
        'upcoming_shopping_trips': upcoming_shopping_trips,
        'sent_shopping_requests': sent_shopping_requests,
        'received_shopping_requests': received_shopping_requests,
    }
    return render(request, 'marketplace/client_dashboard.html', context)


@login_required
@business_owner_required
def add_product(request):
    """Add a new product to the selected business"""
    # Get the business ID from the request, or use the first one if not specified
    selected_business_id = request.GET.get('business_id')
    if selected_business_id:
        try:
            business = Business.objects.get(id=selected_business_id, owner=request.user)
        except Business.DoesNotExist:
            messages.error(request, 'Selected business not found.')
            return redirect('marketplace:business_dashboard')
    else:
        business = Business.objects.filter(owner=request.user).first()
        if not business:
            messages.error(request, 'You must have a registered business to add products.')
            return redirect('marketplace:business_dashboard')

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.business = business
            product.save()
            messages.success(request, 'Product added successfully!')
            return redirect(f'{request.path}?business_id={business.id}')
    else:
        form = ProductForm()

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    return render(request, 'marketplace/add_product.html', {
        'form': form,
        'business': business,
        'all_businesses': all_businesses
    })


@login_required
@business_owner_required
def add_service(request):
    """Add a new service to the selected business"""
    # Get the business ID from the request, or use the first one if not specified
    selected_business_id = request.GET.get('business_id')
    if selected_business_id:
        try:
            business = Business.objects.get(id=selected_business_id, owner=request.user)
        except Business.DoesNotExist:
            messages.error(request, 'Selected business not found.')
            return redirect('marketplace:business_dashboard')
    else:
        business = Business.objects.filter(owner=request.user).first()
        if not business:
            messages.error(request, 'You must have a registered business to add services.')
            return redirect('marketplace:business_dashboard')

    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES)
        if form.is_valid():
            service = form.save(commit=False)
            service.business = business
            service.save()
            messages.success(request, 'Service added successfully!')
            return redirect(f'{request.path}?business_id={business.id}')
    else:
        form = ServiceForm()

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    return render(request, 'marketplace/add_service.html', {
        'form': form,
        'business': business,
        'all_businesses': all_businesses
    })


@login_required
@business_owner_required
def view_reviews(request):
    """View reviews for the selected business's products and services"""
    # Get the business ID from the request, or use the first one if not specified
    selected_business_id = request.GET.get('business_id')
    if selected_business_id:
        try:
            business = Business.objects.get(id=selected_business_id, owner=request.user)
        except Business.DoesNotExist:
            messages.error(request, 'Selected business not found.')
            return redirect('marketplace:business_dashboard')
    else:
        business = Business.objects.filter(owner=request.user).first()
        if not business:
            messages.error(request, 'You must have a registered business to view reviews.')
            return redirect('marketplace:business_dashboard')

    # Get reviews for all products and services of this business
    product_reviews = Review.objects.filter(product__business=business).select_related('reviewer', 'product')
    service_reviews = Review.objects.filter(service__business=business).select_related('reviewer', 'service')

    # Combine and sort reviews by date (newest first)
    all_reviews = sorted(
        list(product_reviews) + list(service_reviews),
        key=lambda x: x.created_at, reverse=True
    )

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    context = {
        'business': business,
        'all_businesses': all_businesses,
        'reviews': all_reviews,
        'product_reviews': product_reviews,
        'service_reviews': service_reviews,
    }
    return render(request, 'marketplace/view_reviews.html', context)


@login_required
@business_owner_required
def edit_product(request, pk):
    """Edit an existing product"""
    product = get_object_or_404(Product, pk=pk)

    # Ensure the product belongs to the current user's business
    if product.business.owner != request.user:
        messages.error(request, 'You do not have permission to edit this product.')
        return redirect('marketplace:business_dashboard')

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated successfully!')
            return redirect(f'{request.META.get("HTTP_REFERER", "marketplace:business_dashboard")}?business_id={product.business.id}')
    else:
        form = ProductForm(instance=product)

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    return render(request, 'marketplace/edit_product.html', {
        'form': form, 
        'product': product,
        'business': product.business,
        'all_businesses': all_businesses
    })


@login_required
@business_owner_required
def delete_product(request, pk):
    """Delete a product"""
    product = get_object_or_404(Product, pk=pk)

    # Ensure the product belongs to the current user's business
    if product.business.owner != request.user:
        messages.error(request, 'You do not have permission to delete this product.')
        return redirect('marketplace:business_dashboard')

    if request.method == 'POST':
        business_id = product.business.id
        product_name = product.name
        product.delete()
        messages.success(request, f'Product "{product_name}" deleted successfully!')
        return redirect(f'{request.META.get("HTTP_REFERER", "marketplace:business_dashboard")}?business_id={business_id}')

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    return render(request, 'marketplace/delete_product.html', {
        'product': product,
        'business': product.business,
        'all_businesses': all_businesses
    })


@login_required
@business_owner_required
def edit_service(request, pk):
    """Edit an existing service"""
    service = get_object_or_404(Service, pk=pk)

    # Ensure the service belongs to the current user's business
    if service.business.owner != request.user:
        messages.error(request, 'You do not have permission to edit this service.')
        return redirect('marketplace:business_dashboard')

    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, 'Service updated successfully!')
            return redirect(f'{request.META.get("HTTP_REFERER", "marketplace:business_dashboard")}?business_id={service.business.id}')
    else:
        form = ServiceForm(instance=service)

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    return render(request, 'marketplace/edit_service.html', {
        'form': form, 
        'service': service,
        'business': service.business,
        'all_businesses': all_businesses
    })


@login_required
@business_owner_required
def delete_service(request, pk):
    """Delete a service"""
    service = get_object_or_404(Service, pk=pk)

    # Ensure the service belongs to the current user's business
    if service.business.owner != request.user:
        messages.error(request, 'You do not have permission to delete this service.')
        return redirect('marketplace:business_dashboard')

    if request.method == 'POST':
        business_id = service.business.id
        service_name = service.name
        service.delete()
        messages.success(request, f'Service "{service_name}" deleted successfully!')
        return redirect(f'{request.META.get("HTTP_REFERER", "marketplace:business_dashboard")}?business_id={business_id}')

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    return render(request, 'marketplace/delete_service.html', {
        'service': service,
        'business': service.business,
        'all_businesses': all_businesses
    })


@login_required
def admin_manage_businesses(request):
    """Manage all businesses in the system"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    # Get query parameter for filtering
    status = request.GET.get('status')

    businesses = Business.objects.select_related('owner__userprofile').all()

    # Apply filter based on status
    if status == 'approved':
        businesses = businesses.filter(owner__userprofile__is_approved=True)
    elif status == 'pending':
        businesses = businesses.filter(owner__userprofile__is_approved=False)

    # Get statistics for the page
    total_business_owners = UserProfile.objects.filter(user_type='business_owner').count()
    approved_businesses_count = UserProfile.objects.filter(user_type='business_owner', is_approved=True).count()

    context = {
        'businesses': businesses,
        'current_status': status,
        'total_business_owners': total_business_owners,
        'approved_businesses': approved_businesses_count,
    }
    return render(request, 'marketplace/admin/manage_businesses.html', context)


@login_required
def admin_manage_shopping_trips(request):
    """Manage all shopping trips in the system"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    # Get query parameter for filtering
    status = request.GET.get('status', 'all')

    shopping_trips = ShoppingTrip.objects.select_related('user').all()

    # Apply filter based on status
    if status != 'all':
        shopping_trips = shopping_trips.filter(status=status)

    # Calculate stats
    total_shopping_trips = ShoppingTrip.objects.count()
    active_trips = ShoppingTrip.objects.filter(status='available').count()
    completed_trips = ShoppingTrip.objects.filter(status='completed').count()
    cancelled_trips = ShoppingTrip.objects.filter(status='cancelled').count()

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(shopping_trips, 10)  # Show 10 trips per page
    page_number = request.GET.get('page')
    shopping_trips = paginator.get_page(page_number)

    context = {
        'shopping_trips': shopping_trips,
        'total_shopping_trips': total_shopping_trips,
        'active_trips': active_trips,
        'completed_trips': completed_trips,
        'cancelled_trips': cancelled_trips,
        'current_status': status,
    }
    return render(request, 'marketplace/admin/manage_shopping_trips.html', context)


@login_required
def admin_manage_shopping_requests(request):
    """Manage all shopping requests in the system"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    # Get query parameter for filtering
    status = request.GET.get('status', 'all')

    shopping_requests = ShoppingRequest.objects.select_related('requester', 'shopper', 'shopping_trip__user').all()

    # Apply filter based on status
    if status != 'all':
        shopping_requests = shopping_requests.filter(status=status)

    # Calculate stats
    total_shopping_requests = ShoppingRequest.objects.count()
    pending_requests = ShoppingRequest.objects.filter(status='pending').count()
    accepted_requests = ShoppingRequest.objects.filter(status='accepted').count()
    completed_requests = ShoppingRequest.objects.filter(status='completed').count()
    rejected_requests = ShoppingRequest.objects.filter(status='rejected').count()

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(shopping_requests, 10)  # Show 10 requests per page
    page_number = request.GET.get('page')
    shopping_requests = paginator.get_page(page_number)

    context = {
        'shopping_requests': shopping_requests,
        'total_shopping_requests': total_shopping_requests,
        'pending_requests': pending_requests,
        'accepted_requests': accepted_requests,
        'completed_requests': completed_requests,
        'rejected_requests': rejected_requests,
        'current_status': status,
    }
    return render(request, 'marketplace/admin/manage_shopping_requests.html', context)


@login_required
def admin_manage_payments(request):
    """Manage all admin fee payments in the system"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    # Get query parameter for filtering
    status = request.GET.get('status', 'all')

    payments = BusinessAdminFeePayment.objects.select_related('business__owner').all()

    # Apply filter based on status
    if status == 'paid':
        payments = payments.filter(is_paid=True)
    elif status == 'pending':
        payments = payments.filter(is_paid=False)

    # Calculate stats
    total_payments = BusinessAdminFeePayment.objects.count()
    paid_payments = BusinessAdminFeePayment.objects.filter(is_paid=True).count()
    pending_payments = BusinessAdminFeePayment.objects.filter(is_paid=False).count()
    total_revenue = sum(p.admin_fee_amount for p in BusinessAdminFeePayment.objects.filter(is_paid=True))
    pending_revenue = sum(p.admin_fee_amount for p in BusinessAdminFeePayment.objects.filter(is_paid=False))

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(payments, 10)  # Show 10 payments per page
    page_number = request.GET.get('page')
    payments = paginator.get_page(page_number)

    context = {
        'payments': payments,
        'total_payments': total_payments,
        'paid_payments': paid_payments,
        'pending_payments': pending_payments,
        'total_revenue': total_revenue,
        'pending_revenue': pending_revenue,
        'current_status': status,
    }
    return render(request, 'marketplace/admin/manage_payments.html', context)


@login_required
def admin_payment_detail(request, payment_id):
    """Detail view for a specific admin fee payment"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    payment = get_object_or_404(BusinessAdminFeePayment.objects.select_related('business__owner'), id=payment_id)

    if request.method == 'POST':
        # Admin can mark payment as paid
        action = request.POST.get('action')
        if action == 'mark_paid':
            payment.is_paid = True
            payment.paid_date = timezone.now()
            payment.save()
            messages.success(request, 'Payment marked as paid.')
        elif action == 'remove_proof':
            if payment.proof_of_payment:
                payment.proof_of_payment.delete()
                payment.proof_of_payment = None
                payment.save()
            messages.success(request, 'Proof of payment removed.')
        return redirect('marketplace:admin_payment_detail', payment_id=payment.id)

    context = {
        'payment': payment,
    }
    return render(request, 'marketplace/admin/payment_detail.html', context)


@login_required
def download_proof_of_payment(request, payment_id):
    """Download proof of payment file"""
    if not request.user.is_staff and request.user.userprofile.user_type != 'admin':
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('marketplace:home')

    payment = get_object_or_404(BusinessAdminFeePayment, id=payment_id)

    if not payment.proof_of_payment:
        messages.error(request, 'No proof of payment uploaded for this payment.')
        return redirect('marketplace:admin_payment_detail', payment_id=payment.id)

    from django.http import FileResponse
    import os

    file_path = payment.proof_of_payment.path
    filename = os.path.basename(file_path)

    response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@business_owner_required
def my_business(request):
    """Display business owner's business profile and information"""
    # Get the business ID from the request, or use the first one if not specified
    selected_business_id = request.GET.get('business_id')
    if selected_business_id:
        try:
            business = Business.objects.get(id=selected_business_id, owner=request.user)
        except Business.DoesNotExist:
            messages.error(request, 'Selected business not found.')
            return redirect('marketplace:business_dashboard')
    else:
        business = Business.objects.filter(owner=request.user).first()

    if not business:
        messages.error(request, 'You must have a registered business to view business details.')
        return redirect('marketplace:business_register')

    # Get business statistics
    total_products = Product.objects.filter(business=business).count()
    total_services = Service.objects.filter(business=business).count()
    total_orders = Order.objects.filter(business=business).count()

    # Get recent reviews for the business
    recent_reviews = business.reviews.select_related('reviewer').order_by('-created_at')[:5]

    # Get all businesses for the user to allow switching
    all_businesses = Business.objects.filter(owner=request.user).order_by('-created_at')

    context = {
        'business': business,
        'all_businesses': all_businesses,
        'total_products': total_products,
        'total_services': total_services,
        'total_orders': total_orders,
        'recent_reviews': recent_reviews,
    }
    return render(request, 'marketplace/my_business.html', context)


@login_required
@business_owner_required
def delete_my_business(request):
    """Allow business owner to delete their business from the my_business page"""
    if request.method != 'POST':
        return redirect('marketplace:my_business')
    
    # Get the business ID from the request, or use the first one if not specified
    selected_business_id = request.GET.get('business_id')
    if selected_business_id:
        try:
            business = Business.objects.get(id=selected_business_id, owner=request.user)
        except Business.DoesNotExist:
            messages.error(request, 'Selected business not found.')
            return redirect('marketplace:business_dashboard')
    else:
        business = Business.objects.filter(owner=request.user).first()

    if not business:
        messages.error(request, 'No business found to delete.')
        return redirect('marketplace:business_register')

    # Check if the business has any pending orders
    pending_orders = Order.objects.filter(
        business=business,
        status__in=['pending', 'confirmed', 'in_progress']
    )

    if pending_orders.exists():
        # Cancel pending orders and notify the user
        canceled_count = 0
        for order in pending_orders:
            order.status = 'cancelled'
            order.save()
            canceled_count += 1

        messages.warning(
            request,
            f'Business cannot be deleted because it had pending orders. '
            f'{canceled_count} order(s) have been automatically cancelled.'
        )
        return redirect('marketplace:my_business')

    # If no pending orders, delete the business
    business_name = business.name
    business.delete()

    messages.success(request, f'Business "{business_name}" has been successfully deleted.')
    return redirect('marketplace:business_register')


@login_required
@business_owner_required
def update_business_location(request):
    """Allow business owner to update their business location"""
    if request.method != 'POST':
        return redirect('marketplace:my_business')

    # Get the business ID from the request, or use the first one if not specified
    selected_business_id = request.GET.get('business_id')
    if selected_business_id:
        try:
            business = Business.objects.get(id=selected_business_id, owner=request.user)
        except Business.DoesNotExist:
            messages.error(request, 'Selected business not found.')
            return redirect('marketplace:business_dashboard')
    else:
        business = Business.objects.filter(owner=request.user).first()

    if not business:
        messages.error(request, 'No business found to update.')
        return redirect('marketplace:business_register')

    form = BusinessLocationUpdateForm(request.POST, instance=business)
    if form.is_valid():
        form.save()
        messages.success(request, 'Business location updated successfully!')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')

    return redirect('marketplace:my_business')


def password_reset_request(request):
    """
    Display the password reset form and handle form submission.
    """
    if request.method == 'POST':
        email = request.POST.get('email')
        
        # Find user by email
        user = User.objects.filter(email=email).first()
        
        if user:
            # Use Django's built-in password reset functionality
            from django.contrib.auth.tokens import default_token_generator
            from django.utils.http import urlsafe_base64_encode
            from django.utils.encoding import force_bytes
            from django.template.loader import render_to_string
            from django.core.mail import send_mail
            from django.contrib.sites.shortcuts import get_current_site
            from django.conf import settings
            
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            
            # Create password reset link
            current_site = get_current_site(request)
            reset_url = f"http://{current_site.domain}/password-reset-confirm/{uid}/{token}/"
            
            # Prepare email content
            subject = 'Password Reset Request'
            message = render_to_string('marketplace/password_reset_email.html', {
                'user': user,
                'reset_url': reset_url,
                'site_name': 'Madidi Market',
            })
            
            # Try to send email
            try:
                send_mail(
                    subject,
                    message,
                    getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@madidimarket.com'),
                    [user.email],
                    fail_silently=False,
                )
                # Log successful email sending
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Password reset email sent successfully to {user.email}")
            except Exception as e:
                # Log the error
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Could not send password reset email to {user.email}: {str(e)}")
                # In production, you might want to notify admins of email failures
                # For now, we'll continue as if the email was sent for security reasons

            return redirect('marketplace:password_reset_done')
        else:
            # Even if email doesn't exist, show the same message for security
            return redirect('marketplace:password_reset_done')
    
    return render(request, 'marketplace/password_reset.html')


def password_reset_done(request):
    """
    Display a success message after password reset email has been sent.
    """
    return render(request, 'marketplace/password_reset_done.html')


def password_reset_confirm(request, uidb64, token):
    """
    Display the password reset form for entering a new password.
    """
    try:
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_decode
        from django.utils.encoding import force_str
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            password1 = request.POST.get('new_password1')
            password2 = request.POST.get('new_password2')
            
            if password1 and password2 and password1 == password2:
                user.set_password(password1)
                user.save()
                from django.contrib import messages
                messages.success(request, 'Your password has been reset successfully. You can now log in with your new password.')
                return redirect('marketplace:password_reset_complete')
            else:
                # Passwords don't match or are empty
                from django.contrib import messages
                messages.error(request, 'Passwords do not match or are empty.')
        return render(request, 'marketplace/password_reset_confirm.html', {'valid_token': True})
    else:
        # Invalid token
        return render(request, 'marketplace/password_reset_confirm.html', {'valid_token': False})


def password_reset_complete(request):
    """
    Display a success message after password has been reset.
    """
    return render(request, 'marketplace/password_reset_complete.html')