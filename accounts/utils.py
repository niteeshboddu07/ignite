import random
import string
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import OTP

def generate_otp():
    """Generate a 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=6))

def send_otp_email(user, otp_code, purpose='verification'):
    """Send OTP via email"""
    
    if purpose == 'verification':
        subject = 'Verify Your Email - IGNITE Platform'
        header_title = 'Welcome to IGNITE!'
        header_color = '#4CAF50'
        message_text = f'Your OTP for email verification is: {otp_code}'
    else:
        subject = 'Password Reset OTP - IGNITE Platform'
        header_title = 'Password Reset Request'
        header_color = '#2196F3'
        message_text = f'Your OTP for password reset is: {otp_code}'
    
    html_message = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; }}
            .header {{ background: {header_color}; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .otp-box {{ background: #f5f5f5; padding: 20px; text-align: center; border-radius: 8px; margin: 20px 0; }}
            .otp-code {{ font-size: 32px; font-weight: bold; color: {header_color}; letter-spacing: 5px; }}
            .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>{header_title}</h2>
            </div>
            <div class="content">
                <p>Hello {user.get_full_name() or user.username},</p>
                <p>Your OTP for {purpose.replace('_', ' ')} is:</p>
                <div class="otp-box">
                    <div class="otp-code">{otp_code}</div>
                </div>
                <p>This OTP is valid for 10 minutes.</p>
                <p>If you didn't request this, please ignore this email.</p>
            </div>
            <div class="footer">
                <p>© 2024 IGNITE - Institute Gateway</p>
            </div>
        </div>
    </body>
    </html>
    '''
    
    try:
        email = EmailMultiAlternatives(
            subject,
            message_text,
            settings.DEFAULT_FROM_EMAIL,
            [user.college_email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send()
        return True
    except Exception as e:
        print(f"Email sending failed: {e}")
        return False

def create_otp(user, purpose='verification'):
    """Create and send OTP"""
    # Delete existing unused OTPs for this purpose
    OTP.objects.filter(user=user, purpose=purpose, is_used=False).delete()
    
    # Generate new OTP
    otp_code = generate_otp()
    expires_at = timezone.now() + timedelta(minutes=10)
    
    # Save OTP
    otp = OTP.objects.create(
        user=user,
        otp=otp_code,
        purpose=purpose,
        expires_at=expires_at
    )
    
    # Send email
    send_otp_email(user, otp_code, purpose)
    
    return otp

def verify_otp(user, otp_code, purpose='verification'):
    """Verify OTP"""
    try:
        otp = OTP.objects.get(
            user=user,
            otp=otp_code,
            purpose=purpose,
            is_used=False
        )
        
        if otp.expires_at > timezone.now():
            otp.is_used = True
            otp.save()
            return True
        else:
            return False
    except OTP.DoesNotExist:
        return False