# Email Configuration for Madidi Market App

## Setting up Gmail for Password Reset Emails

### Steps to Generate Gmail App Password:

1. **Enable 2-Factor Authentication** on your Google account (if not already enabled):
   - Go to your [Google Account settings](https://myaccount.google.com/)
   - Navigate to Security
   - Under "Signing in to Google," select "2-Step Verification"
   - Follow the prompts to enable 2FA

2. **Generate an App Password**:
   - Go to your [Google Account settings](https://myaccount.google.com/)
   - Navigate to Security
   - Under "Signing in to Google," select "App passwords"
     - If you don't see this option, make sure 2FA is enabled
   - Sign in to your Google Account if prompted
   - Select "Mail" as the app and "Other (Custom name)" as the device
   - Enter a custom name like "MadidiMarketApp" 
   - Click "Generate"
   - A 16-character password will appear (e.g., "abcd efgh ijkl mnop")

3. **Copy the App Password**:
   - Copy the 16-character app password that appears
   - Store it securely as you won't be able to see it again

### Setting Up the Environment Variable:

**Option 1: Windows Command Prompt**
```
set GMAIL_APP_PASSWORD=nuwu zfbp yvct uwjp
```

**Option 2: Windows PowerShell**
```
$env:GMAIL_APP_PASSWORD="nuwu zfbp yvct uwjp"
```

**Option 3: Create a .env file** in the project root directory:
```
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
```

**Option 4: Linux/macOS Terminal**
```
export GMAIL_APP_PASSWORD="abcd efgh ijkl mnop"
```

### Using the Password Reset Feature:

Once configured, users can:
- Click "Forgot your password?" on the login page
- Enter their email address
- Receive a password reset link via email
- Follow the link to reset their password

### Important Notes:

- The email used is: `pontshokganakga863@gmail.com`
- For security reasons, the actual password is stored in an environment variable
- The system will send password reset emails from this account
- Make sure the Gmail account has "Less secure app access" disabled and uses App Passwords instead
- App passwords are safer than using your regular Google password
- Each app password can be revoked individually if needed