#!/bin/bash

# ReliefGrid Email Configuration Setup Script
# This script helps you configure email settings for password reset functionality

echo "======================================"
echo "ReliefGrid Email Configuration Setup"
echo "======================================"
echo ""
echo "⚠️  IMPORTANT: Password reset requires email configuration for security."
echo "    Without email, users cannot securely reset their passwords."
echo ""

# Check if already configured
if [ ! -z "$MAIL_USERNAME" ]; then
    echo "✅ Email is already configured!"
    echo "   MAIL_USERNAME: $MAIL_USERNAME"
    echo ""
    read -p "Do you want to reconfigure? (y/n): " reconfigure
    if [ "$reconfigure" != "y" ]; then
        echo "Keeping existing configuration."
        exit 0
    fi
fi

echo "Choose your email provider:"
echo "1) Gmail (Recommended)"
echo "2) Custom SMTP Server"
echo ""
read -p "Enter choice (1 or 2): " choice

if [ "$choice" == "1" ]; then
    echo ""
    echo "📧 Gmail Configuration"
    echo "-------------------------------------"
    echo "Before proceeding, you need to:"
    echo "1. Enable 2-Factor Authentication on your Gmail account"
    echo "2. Generate an App Password:"
    echo "   - Go to: https://myaccount.google.com/apppasswords"
    echo "   - Select 'Mail' and your device"
    echo "   - Copy the 16-character password"
    echo ""
    
    read -p "Enter your Gmail address: " gmail_address
    read -s -p "Enter your Gmail App Password (16 chars): " gmail_password
    echo ""
    
    # Export variables
    export MAIL_SERVER="smtp.gmail.com"
    export MAIL_PORT="587"
    export MAIL_USE_TLS="True"
    export MAIL_USERNAME="$gmail_address"
    export MAIL_PASSWORD="$gmail_password"
    export MAIL_DEFAULT_SENDER="ReliefGrid <$gmail_address>"
    
    echo ""
    echo "✅ Gmail configuration complete!"
    
elif [ "$choice" == "2" ]; then
    echo ""
    echo "📧 Custom SMTP Configuration"
    echo "-------------------------------------"
    
    read -p "SMTP Server (e.g., smtp.yourserver.com): " smtp_server
    read -p "SMTP Port (default 587): " smtp_port
    smtp_port=${smtp_port:-587}
    read -p "Use TLS? (y/n, default y): " use_tls
    use_tls=${use_tls:-y}
    read -p "Email Username: " email_user
    read -s -p "Email Password: " email_pass
    echo ""
    read -p "Sender Name (default 'ReliefGrid'): " sender_name
    sender_name=${sender_name:-ReliefGrid}
    
    # Export variables
    export MAIL_SERVER="$smtp_server"
    export MAIL_PORT="$smtp_port"
    export MAIL_USE_TLS=$([ "$use_tls" == "y" ] && echo "True" || echo "False")
    export MAIL_USERNAME="$email_user"
    export MAIL_PASSWORD="$email_pass"
    export MAIL_DEFAULT_SENDER="$sender_name <$email_user>"
    
    echo ""
    echo "✅ Custom SMTP configuration complete!"
else
    echo "Invalid choice. Exiting."
    exit 1
fi

echo ""
echo "======================================"
echo "Configuration Summary"
echo "======================================"
echo "MAIL_SERVER: $MAIL_SERVER"
echo "MAIL_PORT: $MAIL_PORT"
echo "MAIL_USE_TLS: $MAIL_USE_TLS"
echo "MAIL_USERNAME: $MAIL_USERNAME"
echo "MAIL_PASSWORD: ********"
echo "MAIL_DEFAULT_SENDER: $MAIL_DEFAULT_SENDER"
echo ""
echo "⚠️  These variables are only set for this terminal session."
echo "    To make them permanent, add them to your ~/.bashrc or ~/.zshrc"
echo ""
echo "To save permanently, add these lines to your ~/.bashrc:"
echo "-------------------------------------"
echo "export MAIL_SERVER=\"$MAIL_SERVER\""
echo "export MAIL_PORT=\"$MAIL_PORT\""
echo "export MAIL_USE_TLS=\"$MAIL_USE_TLS\""
echo "export MAIL_USERNAME=\"$MAIL_USERNAME\""
echo "export MAIL_PASSWORD=\"$MAIL_PASSWORD\""
echo "export MAIL_DEFAULT_SENDER=\"$MAIL_DEFAULT_SENDER\""
echo "-------------------------------------"
echo ""
read -p "Start ReliefGrid now? (y/n): " start_app

if [ "$start_app" == "y" ]; then
    echo ""
    echo "🚀 Starting ReliefGrid..."
    cd "$(dirname "$0")"
    source venv/bin/activate
    python app.py
else
    echo ""
    echo "To start ReliefGrid later, run:"
    echo "  cd $(dirname "$0")"
    echo "  source venv/bin/activate"
    echo "  python app.py"
fi
