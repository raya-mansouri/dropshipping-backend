## 1. Database Schema Changes

- [x] 1.1 Update User model: change email column to phone column
- [x] 1.2 Update database migration script for phone field
- [x] 1.3 Update unique constraints and indexes for phone

## 2. API Schema Updates

- [x] 2.1 Update UserBase schema: replace EmailStr with phone validation
- [x] 2.2 Update UserCreate schema for phone registration
- [x] 2.3 Update UserUpdate schema for phone updates
- [x] 2.4 Update LoginRequest schema to use phone instead of email
- [x] 2.5 Add Iranian phone number validator (11 digits starting with 09)

## 3. Authentication Endpoints

- [x] 3.1 Update /auth/register endpoint to accept phone instead of email
- [x] 3.2 Update /auth/login endpoint to authenticate with phone
- [x] 3.3 Update password reset endpoint to send SMS instead of email
- [x] 3.4 Update user lookup methods to use phone instead of email

## 4. User Services

- [x] 4.1 Update UserService.create_user to validate phone format
- [x] 4.2 Update UserService.get_user_by_email to get_user_by_phone
- [x] 4.3 Update AccountService to work with phone-based users

## 5. Notification System

- [x] 5.1 Update notification manager to use phone as recipient identifier
- [x] 5.2 Verify SMS adapter works with Iranian phone numbers
- [x] 5.3 Update notification templates to reference phone numbers

## 6. Data Export Updates

- [x] 6.1 Update data export to include phone numbers instead of emails
- [x] 6.2 Update export schemas to handle phone field

## 7. Test Updates

- [x] 7.1 Update all test data to use phone numbers instead of emails
- [x] 7.2 Update auth integration tests for phone-based login
- [x] 7.3 Add phone validation tests
- [x] 7.4 Run full test suite to ensure no regressions
