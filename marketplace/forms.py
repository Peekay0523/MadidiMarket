from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Business, UserProfile, Product, Service, ProductRequest, ServiceRequest


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=15, required=False)
    address = forms.CharField(widget=forms.Textarea, required=False)
    # Restrict user type choices to only client or business_owner - admin registration is restricted
    USER_TYPE_CHOICES_REGISTRATION = [
        ('client', 'Client'),
        ('business_owner', 'Business Owner'),
    ]
    user_type = forms.ChoiceField(choices=USER_TYPE_CHOICES_REGISTRATION, initial='client')

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2", "first_name", "last_name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()

            # Create associated UserProfile
            UserProfile.objects.create(
                user=user,
                user_type=self.cleaned_data.get("user_type", "client"),
                phone_number=self.cleaned_data.get("phone_number", ""),
                address=self.cleaned_data.get("address", "")
            )
        return user


class BusinessOwnerRegistrationForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ['name', 'description', 'address', 'phone_number', 'email']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'category', 'price', 'stock_quantity', 'image', 'is_available']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['name', 'description', 'category', 'price', 'duration', 'image', 'is_available']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class ProductRequestForm(forms.ModelForm):
    class Meta:
        model = ProductRequest
        fields = ['title', 'description', 'category', 'budget', 'contact_info']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class ServiceRequestForm(forms.ModelForm):
    class Meta:
        model = ServiceRequest
        fields = ['title', 'description', 'category', 'budget', 'contact_info']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }