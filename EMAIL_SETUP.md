# Email Configuration Guide for ReliefGrid

## 🔐 **SECURITY UPDATE**

**⚠️ IMPORTANT:** For security reasons, password reset now **REQUIRES** email configuration. 
The reset link will **ONLY** be sent via email to protect user accounts from unauthorized access.

---

## ⚙️ **Quick Setup (3 Easy Options)**

### **Option 1: Interactive Setup Script (Easiest)**

Run the configuration script:
```bash
cd /home/sadhika/Downloads/reliefgrid
python configure_email.py
```

The script will:
- ✅ Guide you through Gmail or custom SMTP setup
- ✅ Save configuration to `.env` file
- ✅ Start the application automatically

---

### **Option 2: Manual Gmail Setup**

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate an App Password:**
   - Go to: https://myaccount.google.com/apppasswords
   - Select "Mail" and your device
   - Copy the 16-character password

3. **Set Environment Variables:**

```bash
export MAIL_USERNAME="your-email@gmail.com"
export MAIL_PASSWORD="your-16-char-app-password"
export MAIL_DEFAULT_SENDER="ReliefGrid <your-email@gmail.com>"
```

4. **Run the application:**

```bash
cd /home/sadhika/Downloads/reliefgrid
source venv/bin/activate
python app.py
```

---

### **Option 3: Custom SMTP Server**

Set these environment variables:

```bash
export MAIL_SERVER="smtp.yourserver.com"
export MAIL_PORT="587"
export MAIL_USE_TLS="True"
export MAIL_USERNAME="your-email@yourserver.com"
export MAIL_PASSWORD="your-password"
export MAIL_DEFAULT_SENDER="ReliefGrid <noreply@reliefgrid.org>"
```

---

## 🔒 **Security Features**

1. Configure email using Option 1 or 2 above
2. Start server with environment variables set
3. Go to login page and click "Forgot password?"
4. Enter your email
5. Check your inbox for reset email
6. Click the link in email
7. Set new password
8. Login with new password

---

## 📧 **Email Features**

### **Password Reset Email Includes:**
- ✅ Beautiful HTML design with ReliefGrid branding
- ✅ One-click reset button
- ✅ Plaintext fallback link
- ✅ 1-hour expiration notice
- ✅ Security notes
- ✅ Mobile-responsive design

### **Security Features:**
- 🔒 Reset tokens expire after 1 hour
- 🔒 Tokens are signed and cannot be forged
- 🔒 Password validation enforced (8+ chars, uppercase, lowercase, number, special char)
- 🔒 Passwords must match confirmation
- 🔒 Email existence not revealed (security best practice)

---

## 🚀 **Quick Start Commands**

### **Linux/Mac:**

```bash
# With Gmail
export MAIL_USERNAME="your-email@gmail.com"
export MAIL_PASSWORD="your-app-password"
export MAIL_DEFAULT_SENDER="ReliefGrid <your-email@gmail.com>"
cd /home/sadhika/Downloads/reliefgrid
source venv/bin/activate
python app.py
```

### **Windows (PowerShell):**

```powershell
$env:MAIL_USERNAME="your-email@gmail.com"
$env:MAIL_PASSWORD="your-app-password"
$env:MAIL_DEFAULT_SENDER="ReliefGrid <your-email@gmail.com>"
cd C:\path\to\reliefgrid
venv\Scripts\activate
python app.py
```

---

## 🔍 **Troubleshooting**

### **Problem: "Email not configured" message**
**Solution:** Set MAIL_USERNAME and MAIL_PASSWORD environment variables

### **Problem: "Could not send email"**
**Possible causes:**
- Wrong email credentials
- Gmail: App password not generated or 2FA not enabled
- Firewall blocking SMTP port 587
- SMTP server down

**Solution:** Check credentials, verify 2FA and app password, test SMTP connection

### **Problem: Reset link expired**
**Solution:** Links expire after 1 hour. Request a new reset link.

### **Problem: Invalid reset link**
**Solution:** 
- Token may be corrupted (copied incorrectly)
- Token may have expired
- Request a new reset link

---

## 📱 **User Flow**

```
Login Page
    ↓
Click "Forgot password?"
    ↓
Enter email address
    ↓
Receive email with reset link
    ↓
Click link (valid for 1 hour)
    ↓
Enter new password
    ↓
Confirm password
    ↓
See requirements turn green ✓
    ↓
Submit form
    ↓
Password reset successful!
    ↓
Login with new password
```

---

## 🎯 **Production Recommendations**

For production deployment:

1. **Use a dedicated email service:**
   - SendGrid
   - Mailgun
   - AWS SES (Amazon Simple Email Service)
   - Postmark

2. **Store credentials securely:**
   - Use environment variables
   - Never commit credentials to git
   - Use secrets management (AWS Secrets Manager, Azure Key Vault)

3. **Set up proper DNS:**
   - Configure SPF records
   - Configure DKIM
   - Set up DMARC policy

4. **Monitor email delivery:**
   - Track bounce rates
   - Monitor spam complaints
   - Check delivery rates

---

## ✅ **What's Included**

- ✅ Forgot password link on login page
- ✅ Email input page with validation
- ✅ Password reset page with live validation
- ✅ Beautiful HTML email template
- ✅ Secure token generation (1-hour expiration)
- ✅ Password strength requirements
- ✅ Password confirmation matching
- ✅ Development mode (shows link without email)
- ✅ Production-ready email sending

---

## 📄 **Files Added/Modified**

**New Files:**
- `templates/forgot_password.html` - Forgot password page
- `templates/reset_password.html` - Password reset form
- `templates/email/password_reset.html` - Email template
- `EMAIL_SETUP.md` - This guide

**Modified Files:**
- `app.py` - Added email config and routes
- `templates/login.html` - Added "Forgot password?" link
- `requirements.txt` - Added Flask-Mail dependency

---

## 🎓 **Testing Credentials**

Use existing demo accounts to test:

**Admin:**
- Email: `admin@reliefgrid.org`
- Old Password: `admin123`

**Relief Center:**
- Email: `riverside@ngo.org`
- Old Password: `relief123`

Test the forgot password feature with these emails!

---

**Last Updated:** October 23, 2026
