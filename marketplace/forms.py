from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Business, UserProfile, Product, Service, ProductRequest, ServiceRequest, AdminBankingDetails


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
    latitude = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        widget=forms.HiddenInput()
    )
    longitude = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        widget=forms.HiddenInput()
    )
    agree_to_terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'mr-2'})
    )

    class Meta:
        model = Business
        fields = ['name', 'description', 'address', 'phone_number', 'email', 'latitude', 'longitude']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }


class CombinedBusinessOwnerForm(forms.Form):
    """Combined form for non-authenticated users to register user account and business"""
    # User fields
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-input'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-input'}))
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    first_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-input'}))
    last_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-input'}))
    
    # Business fields
    business_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs={'class': 'form-input'}))
    business_description = forms.CharField(widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-textarea'}))
    business_address = forms.CharField(widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-textarea'}))
    business_phone_number = forms.CharField(max_length=15, widget=forms.TextInput(attrs={'class': 'form-input'}))
    business_email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-input'}))
    latitude = forms.DecimalField(max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput())
    longitude = forms.DecimalField(max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput())
    
    # Terms acceptance
    agree_to_terms = forms.BooleanField(required=True, widget=forms.CheckboxInput(attrs={'class': 'mr-2'}))
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match")
        
        email = cleaned_data.get('email')
        business_email = cleaned_data.get('business_email')
        
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists")
        
        username = cleaned_data.get('username')
        if username and User.objects.filter(username=username).exists():
            raise forms.ValidationError("A user with this username already exists")
        
        return cleaned_data


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


class BusinessLocationUpdateForm(forms.ModelForm):
    latitude = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        widget=forms.HiddenInput()
    )
    longitude = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        widget=forms.HiddenInput()
    )

    class Meta:
        model = Business
        fields = ['address', 'latitude', 'longitude']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
        }


class AdminBankingDetailsForm(forms.ModelForm):
    class Meta:
        model = AdminBankingDetails
        fields = ['account_holder_name', 'bank_name', 'account_number', 'branch_code', 'account_type', 'reference']
        widgets = {
            'account_holder_name': forms.TextInput(attrs={'class': 'form-input'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-input'}),
            'account_number': forms.TextInput(attrs={'class': 'form-input'}),
            'branch_code': forms.TextInput(attrs={'class': 'form-input'}),
            'account_type': forms.Select(attrs={'class': 'form-input'}),
            'reference': forms.TextInput(attrs={'class': 'form-input'}),
        }