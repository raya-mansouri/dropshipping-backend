## Context

Our current system uses email addresses as the primary user identifier across authentication, notifications, and data storage. The User model has an email field (required, unique) and a phone field (optional). Authentication flows, user lookup methods, and notification systems all rely on email.

We're transitioning to Iranian phone numbers as the primary identifier to better serve local users. Iranian phone numbers follow the 11-digit format starting with 09 (e.g., 09121234567).

Since there are no existing users or deployed systems, we can make this change cleanly without migration concerns.

## Goals / Non-Goals

**Goals:**
- Replace email with Iranian phone numbers (11 digits starting with 09) as primary user identifier
- Maintain existing notification capabilities (SMS, email, in-app, webhook)
- Standardize phone number format validation across all entry points
- Update authentication, registration, and user lookup to use phone numbers

**Non-Goals:**
- Changing notification channel implementations (SMS adapter stays)
- Adding new notification types beyond current ones
- Modifying business logic unrelated to email/phone switch
- Supporting international phone formats beyond Iranian standard

## Decisions

### Decision 1: Phone Number Format
**Choice:** Use Iranian mobile format: `09121234567` (exactly 11 digits, starts with 09)
**Rationale:** This is the standard format for Iranian mobile numbers. Store and validate as 11 digits starting with 09.
**Alternatives considered:**
- +989121234567: Adds unnecessary international prefix complexity
- Multiple formats: Would complicate validation logic

### Decision 2: User Model Changes
**Choice:** Change `User.email` to `User.phone` as the primary unique identifier
**Rationale:** Simplifies to one primary identifier instead of dual fields.
**Alternatives considered:**
- Keep both email and phone as optional: Confusing UX
- Make phone required, email optional: Email still needed for some notifications

### Decision 3: Validation Implementation
**Choice:** Pydantic validator for 11-digit phone format in schemas
**Rationale:** Centralized validation at the API boundary, reusable across endpoints.
**Alternatives considered:**
- Regex in model: Harder to test
- Custom validator class: Overkill for simple format

## Risks / Trade-offs

Since there are no existing users or deployed systems, risks are minimal.

**Trade-off:** Breaking change in API contracts
**Mitigation:** Update API documentation and client code accordingly

**Risk:** Phone number validation might be too strict
**Mitigation:** Test with various Iranian phone number examples

## Migration Plan

No migration needed since no existing users or database.

1. Update database schema (rename email to phone column)
2. Update API schemas with phone validation
3. Update auth endpoints (login/register with phone)
4. Update user lookup methods throughout codebase
5. Test notification system with phone numbers

## Open Questions

- Should we keep email as a secondary field for future use?
- What SMS provider settings need verification for Iranian numbers?
