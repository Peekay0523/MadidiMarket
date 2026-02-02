from django.shortcuts import render, redirect, get_object_or_404
from decimal import Decimal
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Avg
from django.http import JsonResponse
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
            messages.success(request, f'Account created for {username}!')
            return redirect('marketplace:login')
    else:
        form = UserRegistrationForm()
    return render(request, 'marketplace/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Redirect based on user type
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
            if action == 'approve':
                profile.is_approved = True
                profile.save()
                messages.success(request, f'Approved business owner: {profile.user.username}')
            elif action == 'reject':
                # For rejection, we could delete the business or just keep is_approved=False
                messages.info(request, f'Rejected business owner: {profile.user.username}')
        except UserProfile.DoesNotExist:
            messages.error(request, 'User not found.')

        return redirect('marketplace:admin_approve_business')

    context = {
        'pending_businesses': pending_businesses,
    }
    return render(request, 'marketplace/admin_approve_business.html', context)


def business_register(request):
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
    business = Business.objects.filter(owner=request.user).first()
    products = Product.objects.filter(business=business)
    services = Service.objects.filter(business=business)

    # Get total orders for this business
    total_orders = Order.objects.filter(business=business).count()

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
        'products': products,
        'services': services,
        'total_products': products.count(),
        'total_services': services.count(),
        'total_orders': total_orders,
        'upcoming_shopping_trips': upcoming_shopping_trips,
        'sent_shopping_requests': sent_shopping_requests,
        'received_shopping_requests': received_shopping_requests,
    }
    return render(request, 'marketplace/business_dashboard.html', context)


@login_required
@business_owner_required
def business_products(request):
    """Display products for the logged-in business owner"""
    business = Business.objects.filter(owner=request.user).first()
    if not business:
        messages.error(request, 'You must have a registered business to view products.')
        return redirect('marketplace:business_dashboard')

    products = Product.objects.filter(business=business)

    context = {
        'business': business,
        'products': products,
        'total_products': products.count(),
    }
    return render(request, 'marketplace/business_products.html', context)


@login_required
@business_owner_required
def business_services(request):
    """Display services for the logged-in business owner"""
    business = Business.objects.filter(owner=request.user).first()
    if not business:
        messages.error(request, 'You must have a registered business to view services.')
        return redirect('marketplace:business_dashboard')

    services = Service.objects.filter(business=business)

    context = {
        'business': business,
        'services': services,
        'total_services': services.count(),
    }
    return render(request, 'marketplace/business_services.html', context)


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
    """Display orders for the business owner"""
    # Get the business for the current user
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
        orders = orders.filter(created_at__date__gte=datetime.strptime(date_from, '%Y-%m-%d'))

    if date_to:
        from datetime import datetime
        orders = orders.filter(created_at__date__lte=datetime.strptime(date_to, '%Y-%m-%d'))

    context = {
        'orders': orders,
        'business': business,
    }
    return render(request, 'marketplace/business_orders.html', context)


@login_required
@business_owner_required
def business_order_detail(request, order_id):
    """Display detailed order information for business owner"""
    # Get the business for the current user
    business = Business.objects.filter(owner=request.user).first()

    if not business:
        messages.error(request, 'No business found associated with your account.')
        return redirect('marketplace:business_dashboard')

    # Get the specific order for this business
    order = get_object_or_404(Order, id=order_id, business=business)
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
    return render(request, 'marketplace/business_order_detail.html', context)


@login_required
@business_owner_required
def update_order_status(request, order_id):
    """Update order status"""
    if request.method != 'POST':
        return redirect('marketplace:business_orders')

    # Get the business for the current user
    business = Business.objects.filter(owner=request.user).first()

    if not business:
        messages.error(request, 'No business found associated with your account.')
        return redirect('marketplace:business_dashboard')

    # Get the specific order for this business
    order = get_object_or_404(Order, id=order_id, business=business)

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

    # Get shopping trips and requests statistics for admin
    total_shopping_trips = ShoppingTrip.objects.count()
    active_shopping_trips = ShoppingTrip.objects.filter(status='available').count()
    total_shopping_requests = ShoppingRequest.objects.count()
    pending_shopping_requests = ShoppingRequest.objects.filter(status='pending').count()

    # Get recent shopping trips and requests
    recent_shopping_trips = ShoppingTrip.objects.select_related('user').order_by('-created_at')[:10]
    recent_shopping_requests = ShoppingRequest.objects.select_related('requester', 'shopper', 'shopping_trip__user').order_by('-created_at')[:10]

    context = {
        'total_users': total_users,
        'total_clients': total_clients,
        'total_business_owners': total_business_owners,
        'approved_businesses': approved_businesses,
        'pending_businesses': pending_businesses,
        'total_products': total_products,
        'total_services': total_services,
        'total_orders': total_orders,
        'total_shopping_trips': total_shopping_trips,
        'active_shopping_trips': active_shopping_trips,
        'total_shopping_requests': total_shopping_requests,
        'pending_shopping_requests': pending_shopping_requests,
        'recent_shopping_trips': recent_shopping_trips,
        'recent_shopping_requests': recent_shopping_requests,
    }
    return render(request, 'marketplace/admin/dashboard.html', context)


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

    context = {
        'upcoming_trips': upcoming_trips,
        'user_trips': user_trips,
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
        from .models import CartItem  # Try to import CartItem
        # If CartItem exists, get the user's cart items
        cart_items = CartItem.objects.filter(cart__customer=request.user).select_related('product')
    except ImportError:
        # If CartItem doesn't exist, cart_items remains empty
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
    """Add a new product to the business"""
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
            return redirect('marketplace:business_dashboard')
    else:
        form = ProductForm()

    return render(request, 'marketplace/add_product.html', {'form': form})


@login_required
@business_owner_required
def add_service(request):
    """Add a new service to the business"""
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
            return redirect('marketplace:business_dashboard')
    else:
        form = ServiceForm()

    return render(request, 'marketplace/add_service.html', {'form': form})


@login_required
@business_owner_required
def view_reviews(request):
    """View reviews for the business's products and services"""
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

    context = {
        'business': business,
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
            return redirect('marketplace:business_dashboard')
    else:
        form = ProductForm(instance=product)

    return render(request, 'marketplace/edit_product.html', {'form': form, 'product': product})


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
        product_name = product.name
        product.delete()
        messages.success(request, f'Product "{product_name}" deleted successfully!')
        return redirect('marketplace:business_dashboard')

    return render(request, 'marketplace/delete_product.html', {'product': product})


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
            return redirect('marketplace:business_dashboard')
    else:
        form = ServiceForm(instance=service)

    return render(request, 'marketplace/edit_service.html', {'form': form, 'service': service})


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
        service_name = service.name
        service.delete()
        messages.success(request, f'Service "{service_name}" deleted successfully!')
        return redirect('marketplace:business_dashboard')

    return render(request, 'marketplace/delete_service.html', {'service': service})


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

    context = {
        'businesses': businesses,
        'current_status': status,
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
@business_owner_required
def my_business(request):
    """Display business owner's business profile and information"""
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

    context = {
        'business': business,
        'total_products': total_products,
        'total_services': total_services,
        'total_orders': total_orders,
        'recent_reviews': recent_reviews,
    }
    return render(request, 'marketplace/my_business.html', context)