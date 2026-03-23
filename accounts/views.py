from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from datetime import timedelta
from .models import User, OTP
from .forms import RegisterForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from .utils import create_otp, verify_otp
from .utils import send_otp_email

from django.db import transaction


import random

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data

            otp = str(random.randint(100000, 999999))

            # ✅ store in session (NOT DB)
            request.session['register_data'] = data
            request.session['register_otp'] = otp

            # ✅ send OTP (no DB user)
            send_otp_email(
                user=type('obj', (object,), {
                    'username': data['username'],
                    'college_email': data['college_email'],
                    'get_full_name': lambda: data['username']
                }),
                otp_code=otp,
                purpose='verification'
            )

            messages.success(request, "OTP sent to your email")
            return redirect('accounts:verify_otp')

    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})



def verify_otp_view(request):
    data = request.session.get('register_data')
    session_otp = request.session.get('register_otp')

    if not data or not session_otp:
        messages.error(request, 'Session expired. Please register again.')
        return redirect('accounts:register')

    # ✅ RESEND OTP LOGIC
    if request.GET.get('resend'):
        new_otp = str(random.randint(100000, 999999))
        request.session['register_otp'] = new_otp

        send_otp_email(
            user=type('obj', (object,), {
                'username': data['username'],
                'college_email': data['college_email'],
                'get_full_name': lambda: data['username']
            }),
            otp_code=new_otp,
            purpose='verification'
        )

        messages.success(request, 'New OTP sent to your email.')

    if request.method == 'POST':
        otp_code = request.POST.get('otp', '').strip()

        if otp_code == session_otp:
            # ✅ create user AFTER OTP success
            user = User.objects.create_user(
                username=data['username'],
                password=data['password1'],
                college_email=data['college_email'],
                phone=data['phone'],
                department=data['department'],
                year=data['year'],
                user_type=data['user_type']
            )

            user.is_verified = True
            user.save()

            # clear session
            request.session.pop('register_data', None)
            request.session.pop('register_otp', None)

            messages.success(request, 'Registration successful. Please login.')
            return redirect('accounts:login')

        else:
            messages.error(request, 'Invalid OTP. Try again.')

    return render(request, 'accounts/verify_otp.html', {
        'email': data.get('college_email')
    })


def login_view(request):
    """Handle user login"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            
            try:
                user = User.objects.get(college_email=email)
                
                if user.check_password(password):
                    if user.is_verified:
                        login(request, user)
                        messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
                        
                        # Redirect to next parameter if exists
                        next_url = request.GET.get('next')
                        if next_url:
                            return redirect(next_url)
                        return redirect('accounts:dashboard')
                    else:
                        messages.error(request, 'Please verify your email first. Check your inbox for OTP.')
                        request.session['temp_user_id'] = str(user.id)
                        return redirect('accounts:verify_otp')
                else:
                    messages.error(request, 'Invalid password. Please try again.')
            except User.DoesNotExist:
                messages.error(request, 'No account found with this email. Please register first.')
    else:
        form = LoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})


def forgot_password_view(request):
    """Handle forgot password - send OTP"""
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            
            try:
                user = User.objects.get(college_email=email)
                
                if not user.is_verified:
                    messages.error(request, 'Your email is not verified. Please register first.')
                    return redirect('accounts:register')
                
                # Create and send OTP for password reset
                create_otp(user, 'password_reset')
                request.session['reset_user_id'] = str(user.id)
                messages.success(request, 'OTP sent to your email for password reset.')
                return redirect('accounts:reset_password')
                
            except User.DoesNotExist:
                messages.error(request, 'No account found with this email.')
    else:
        form = ForgotPasswordForm()
    
    return render(request, 'accounts/forgot_password.html', {'form': form})


def reset_password_view(request):
    """Handle password reset with OTP"""
    user_id = request.session.get('reset_user_id')
    
    if not user_id:
        messages.error(request, 'Session expired. Please request password reset again.')
        return redirect('accounts:forgot_password')
    
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            otp_code = form.cleaned_data['otp']
            new_password = form.cleaned_data['new_password']
            
            if verify_otp(user, otp_code, 'password_reset'):
                user.set_password(new_password)
                user.save()
                
                # Clear session
                if 'reset_user_id' in request.session:
                    del request.session['reset_user_id']
                
                messages.success(request, 'Password reset successfully! Please login with your new password.')
                return redirect('accounts:login')
            else:
                messages.error(request, 'Invalid or expired OTP. Please try again.')
    else:
        form = ResetPasswordForm()
    
    return render(request, 'accounts/reset_password.html', {'form': form})


@login_required
def dashboard_view(request):
    """User dashboard after login"""
    context = {
        'user': request.user,
        'is_teacher': request.user.user_type in ['teacher', 'club_coordinator', 'admin'],
        'is_student': request.user.user_type == 'student',
        'is_admin': request.user.user_type == 'admin',
        'today': timezone.now().date(),
    }
    return render(request, 'accounts/dashboard.html', context)


@login_required
def logout_view(request):
    """Handle user logout"""
    logout(request)
    messages.success(request, 'Logged out successfully.')
    return redirect('accounts:login')


@login_required
def profile_view(request):
    """View and edit user profile"""
    if request.method == 'POST':
        # Update profile logic
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.phone = request.POST.get('phone', user.phone)
        user.department = request.POST.get('department', user.department)
        
        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']
        
        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('accounts:profile')
    
    return render(request, 'accounts/profile.html', {'user': request.user})


@login_required
def resend_verification_view(request):
    """Resend verification email"""
    user = request.user
    
    if user.is_verified:
        messages.info(request, 'Your email is already verified.')
        return redirect('accounts:dashboard')
    
    # Delete old OTPs
    OTP.objects.filter(user=user, purpose='verification', is_used=False).delete()
    
    # Create and send new OTP
    create_otp(user, 'verification')
    request.session['temp_user_id'] = str(user.id)
    
    messages.success(request, 'Verification OTP resent to your email.')
    return redirect('accounts:verify_otp')


def cleanup_unverified_users():
    """Delete unverified users older than 1 hour"""
    cutoff_time = timezone.now() - timedelta(hours=1)
    unverified_users = User.objects.filter(is_verified=False, date_joined__lt=cutoff_time)
    count = unverified_users.count()
    unverified_users.delete()
    return count