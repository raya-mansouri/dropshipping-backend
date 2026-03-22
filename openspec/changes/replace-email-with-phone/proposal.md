## Why

Currently our system requires email addresses for user authentication, notifications, and data tracking. However, many users in Iran prefer using phone numbers as their primary identifier. This change will align with local user preferences and improve accessibility for Iranian customers who may not have reliable email access.

## What Changes

### Key Modifications
- Replace all email field usage with phone number storage/validation
- Remove email as primary user identifier in database
- Update authentication and verification flows to use phone numbers
- Modify notification systems to support phone number communication
- Standardize Iranian phone number format across all touchpoints

### BREAKING Changes
- User data migration script required for existing email users

## Capabilities

### New Capabilities
- `user-auth-by-phone`: New authentication capability using Iranian phone numbers
- `phone-validation`: Validation rules for Iranian phone numbers (11 digits, optional +98 prefix)
- `phone-notifications`: Notification system capable of sending via SMS to phone numbers

### Modified Capabilities
- `user-auth`: Changed requirement from email authentication to phone authentication
- `user-profiles`: Profile fields now use phone numbers instead of email
- `data-export`: Data export capability now needs to handle phone number storage

## Impact

### Code Changes
- User model: email → phone column
- Auth API: login/registration endpoints modified
- Notification adapters: SMS implementation required
- Database: INDEX constraint changes for phone numbers

### Components
- User schema
- Authentication flow
- Notification system
- Data storage

## Success Criteria
- 100% coverage of email → phone conversion in codebase
- Valid Iranian phone number format validation in all entry points
