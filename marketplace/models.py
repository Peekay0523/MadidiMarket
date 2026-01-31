from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator


class UserProfile(models.Model):
    USER_TYPE_CHOICES = [
        ('client', 'Client'),
        ('business_owner', 'Business Owner'),
        ('admin', 'Admin'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='client')
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False)  # For business owners
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.user_type}"


class Business(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='businesses')
    name = models.CharField(max_length=200)
    description = models.TextField()
    address = models.TextField()
    phone_number = models.CharField(max_length=15)
    email = models.EmailField()
    logo = models.ImageField(upload_to='business_logos/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)  # For CSS classes or emoji
    
    def __str__(self):
        return self.name


class Product(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class Service(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)  # Optional for services
    duration = models.CharField(max_length=100, blank=True)  # e.g., "2 hours", "per day"
    image = models.ImageField(upload_to='service_images/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class ProductRequest(models.Model):
    """Requests from clients for specific products"""
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_requests')
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    contact_info = models.CharField(max_length=100)  # Phone or email
    is_fulfilled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.title


class ServiceRequest(models.Model):
    """Requests from clients for specific services"""
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='service_requests')
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    contact_info = models.CharField(max_length=100)  # Phone or email
    is_fulfilled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.title


class Order(models.Model):
    ORDER_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    DELIVERY_OPTION_CHOICES = [
        ('pickup', 'Pickup at Seller\'s Place'),
        ('delivery', 'Delivery to Address'),
    ]

    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='orders')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='pending')
    delivery_option = models.CharField(max_length=20, choices=DELIVERY_OPTION_CHOICES, default='pickup')
    delivery_address = models.TextField(blank=True, null=True)
    delivery_phone = models.CharField(max_length=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id} - {self.customer.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Price at time of order
    
    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


class Cart(models.Model):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='carts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.customer.username}"

    def get_total_price(self):
        return sum(item.get_total_price() for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    def get_total_price(self):
        return self.quantity * self.product.price


class Review(models.Model):
    RATING_CHOICES = [(i, i) for i in range(1, 6)]  # 1 to 5 stars

    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_given')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='reviews', null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews', null=True, blank=True)
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='reviews', null=True, blank=True)
    rating = models.IntegerField(choices=RATING_CHOICES, validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review by {self.reviewer.username} for {self.business or self.product or self.service}"

    @property
    def like_count(self):
        return self.review_likes.filter(is_like=True).count()

    @property
    def dislike_count(self):
        return self.review_likes.filter(is_like=False).count()


class ReviewLike(models.Model):
    """Model to track likes and dislikes for reviews"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='review_likes')
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='review_likes')
    is_like = models.BooleanField()  # True for like, False for dislike
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'review')  # One like/dislike per user per review

    def __str__(self):
        action = "liked" if self.is_like else "disliked"
        return f"{self.user.username} {action} review {self.review.id}"


class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('credit_card', 'Credit Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash_on_delivery', 'Cash on Delivery'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=100, blank=True)
    proof_of_payment = models.FileField(upload_to='proof_of_payments/', blank=True, null=True)
    card_last_four = models.CharField(max_length=4, blank=True, null=True)  # For credit card payments
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment for Order #{self.order.id} - {self.payment_method} - {self.status}"


class ShoppingTrip(models.Model):
    """Model to track users who are going shopping"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shopping_trips')
    destination = models.CharField(max_length=200, blank=True)
    planned_departure_time = models.DateTimeField()
    estimated_return_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=[
        ('available', 'Available'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ], default='available')
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.username} - Shopping Trip ({self.planned_departure_time.strftime('%Y-%m-%d %H:%M')})"


class ShoppingRequest(models.Model):
    """Model to track requests from users to shoppers"""
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shopping_requests_made')
    shopper = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shopping_requests_received')
    shopping_trip = models.ForeignKey(ShoppingTrip, on_delete=models.CASCADE, related_name='requests')
    items_requested = models.TextField()
    estimated_total_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amount_to_pay_shopper = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    delivery_location = models.CharField(max_length=200)
    contact_details = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.requester.username} -> {self.shopper.username} - {self.shopping_trip.id}"