# NGO Registration and Verification System - Implementation Plan

## Overview

This plan implements a complete NGO Registration and Verification System for the ReliefGrid Flask+SQLite project. The system allows NGOs to register with official documents, undergo admin verification, and gain access to the relief center dashboard only after approval.

## Dependencies Discovered

- **Flask**: Already present, web framework
- **Flask-Mail**: Already configured for password reset
- **itsdangerous**: Already imported for token generation
- **werkzeug**: Already used for password hashing, also provides secure_filename for uploads
- **SQLite**: Database engine, no new dependencies
- **No build step**: Python Flask runs directly

## Implementation Steps

### 1. Database Schema Extension (FEAT-001)

**What:** Add `ngo_registrations` table and `ngo_registration_id` column to `users` table.

**Files:**
- Modify: `/home/sadhika/Downloads/reliefgrid/db.py`

**Details:**
- Add to SCHEMA string: `ngo_registrations` table with columns: id (PK), ngo_id (UNIQUE), org_name, official_reg_number (UNIQUE), registration_type, email (UNIQUE), contact_number, address, password_hash, certificate_filename, email_verified (0/1), verification_token, status (PENDING/APPROVED/REJECTED), rejection_reason, applied_at, reviewed_at, reviewed_by (FK to users.id)
- Migration-safe ALTER TABLE users ADD COLUMN ngo_registration_id INTEGER with try/except to handle existing databases
- Preserve backward compatibility: existing users with NULL ngo_registration_id continue working

**Verify:** Delete reliefgrid.db, run `python app.py`, check schema with `sqlite3 reliefgrid.db '.schema ngo_registrations'` and `'.schema users'`, login as seed users (admin@reliefgrid.org/admin123, riverside@ngo.org/relief123) successfully.

---

### 2. NGO Registration Flow (FEAT-002)

**What:** Registration form with certificate upload, email verification, application status page.

**Files:**
- Modify: `/home/sadhika/Downloads/reliefgrid/app.py` (add routes and helpers)
- Modify: `/home/sadhika/Downloads/reliefgrid/templates/login.html` (add NGO registration link)
- Create: `/home/sadhika/Downloads/reliefgrid/templates/ngo_register.html`
- Create: `/home/sadhika/Downloads/reliefgrid/templates/ngo_application_status.html`
- Create: `/home/sadhika/Downloads/reliefgrid/templates/email/ngo_verification.html`
- Create: `/home/sadhika/Downloads/reliefgrid/uploads/certificates/` directory

**Details:**

**app.py additions:**
- Add `app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024` (5MB file limit)
- Add `generate_ngo_id()` helper: queries max id from ngo_registrations, increments, formats as NGO-1001, NGO-1002, etc.
- Add GET/POST `/ngo/register`: validates all fields, checks password with `validate_password()`, validates file type (pdf/jpg/jpeg/png) and size, uses `secure_filename()` from werkzeug.utils, saves as `{ngo_id}_{timestamp}_{filename}`, generates verification token with `serializer.dumps(email, salt='ngo-email-verify')`, inserts record with status=PENDING, sends email, redirects to status page
- Add GET `/ngo/verify-email/<token>`: loads token with `serializer.loads(token, salt='ngo-email-verify', max_age=86400)`, updates email_verified=1, shows success
- Add GET `/ngo/application-status`: shows NGO details and current status (PENDING/APPROVED/REJECTED) by email query param
- Add GET `/uploads/certificates/<filename>` with `@login_required('admin')`: serves files securely to admins only

**templates/ngo_register.html:**
- Extends base.html with .auth layout (split-screen like login.html)
- Form fields: org_name, official_reg_number, registration_type (dropdown), email, contact_number, address, password (with strength indicator like register.html), confirm_password, certificate file input (accept=".pdf,.jpg,.jpeg,.png"), terms checkbox
- Client-side JS: password strength validation, file type/size validation, password confirmation match

**templates/ngo_application_status.html:**
- Shows NGO ID, org name, applied date, status pill (pending/approved/rejected using pill() macro), email verification badge, rejection reason if rejected

**templates/email/ngo_verification.html:**
- Follows pattern from email/password_reset.html
- ReliefGrid branding, verify button with verification_url, 24-hour expiry notice, inline CSS

**login.html modification:**
- Add link: "NGO? Register as NGO with verification" below existing register link

**Verify:** Visit /ngo/register, fill form, upload certificate, submit, check database for new record with status=PENDING and ngo_id=NGO-1001, verify file in uploads/certificates/, click verification link, check email_verified=1, visit /ngo/application-status?email=test@ngo.org shows status.

---

### 3. Admin Verification Dashboard (FEAT-003)

**What:** Admin panel to review, approve, or reject NGO applications with email notifications.

**Files:**
- Modify: `/home/sadhika/Downloads/reliefgrid/app.py` (add to ADMIN_NAV, add routes)
- Modify: `/home/sadhika/Downloads/reliefgrid/templates/base.html` (show pending badge on nav)
- Create: `/home/sadhika/Downloads/reliefgrid/templates/admin_ngo_verifications.html`
- Create: `/home/sadhika/Downloads/reliefgrid/templates/admin_ngo_verification_detail.html`
- Create: `/home/sadhika/Downloads/reliefgrid/templates/email/ngo_approved.html`
- Create: `/home/sadhika/Downloads/reliefgrid/templates/email/ngo_rejected.html`

**Details:**

**app.py additions:**
- Add to ADMIN_NAV: `('NGO Verifications', 'admin_ngo_verifications')`
- Add GET `/admin/ngo-verifications`: lists all NGOs with optional ?status= filter, shows pending count
- Add GET `/admin/ngo-verifications/<int:id>`: shows full NGO details including certificate
- Add POST `/admin/ngo-verifications/<int:id>/approve`: sets status=APPROVED, creates user account (INSERT INTO users with role='relief', ngo_registration_id=id, copies password_hash), sends approval email, redirects
- Add POST `/admin/ngo-verifications/<int:id>/reject`: requires rejection_reason, sets status=REJECTED, sends rejection email with reason
- Modify `inject_nav()` context processor: query pending count for badge display

**templates/admin_ngo_verifications.html:**
- List view with status filter tabs (All, Pending, Approved, Rejected)
- Table: NGO ID, Org Name, Registration #, Email, Applied Date, Email Verified (✓/✗), Status (pill), Actions
- Pending tab shows badge with count

**templates/admin_ngo_verification_detail.html:**
- Grid layout (.grid .g2): left column shows all NGO details, right column shows certificate preview
- PDF: embed with <embed> tag, JPG/PNG: <img> tag
- If PENDING: show Approve button and Reject form (textarea for reason)
- If APPROVED/REJECTED: show reviewer name, date, reason

**templates/email/ngo_approved.html:**
- Congratulations message, NGO ID, login credentials reminder, link to login page

**templates/email/ngo_rejected.html:**
- Respectful rejection message, reason from admin, contact support invitation

**Verify:** Login as admin, see 'NGO Verifications' in sidebar with pending badge, click it, see list of NGOs, click detail view, see certificate preview, approve one NGO, verify user account created in database (SELECT * FROM users WHERE ngo_registration_id IS NOT NULL), check approval email sent, reject another NGO with reason, verify rejection email sent.

---

### 4. Login Validation and Access Control (FEAT-004)

**What:** Enforce NGO approval status at login and on all relief routes.

**Files:**
- Modify: `/home/sadhika/Downloads/reliefgrid/app.py` (update /login route, add decorator, apply to routes)

**Details:**

**app.py modifications:**
- Modify `/login` POST: after password check, if user.ngo_registration_id not NULL, query ngo_registrations status. If PENDING: flash message, block login. If REJECTED: flash rejection reason, block login. If APPROVED or NULL: allow login.
- Add `ngo_approved_required()` decorator: checks if user is relief role with ngo_registration_id, then verifies status=APPROVED. If NULL (legacy user), allows access. If not approved, blocks with flash and redirect.
- Apply `@ngo_approved_required()` to relief routes: /home, /my/requests, /my/allocations, /my/requests/new, /my/deliveries, /my/resources
- Keep /profile and /logout accessible without approval check (so pending users can still logout)
- Add helper `get_ngo_status(user_id)` to avoid duplicate queries

**Verify:** Create pending NGO, try to login - blocked with message. Approve NGO, login succeeds, access all relief routes. Create rejected NGO, try login - blocked with reason. Test backward compat: login as riverside@ngo.org/relief123 (legacy user with ngo_registration_id=NULL) - works normally, all routes accessible.

---

### 5. Integration Testing and Documentation (FEAT-005)

**What:** End-to-end testing of all workflows, edge cases, security, and comprehensive documentation.

**Files:**
- Create: `/home/sadhika/Downloads/reliefgrid/TESTING.md` (testing guide)

**Details:**

**Testing scenarios:**
1. Happy path: register → verify → approve → login → submit request
2. Rejection path: register → verify → reject → login blocked → reason shown
3. Pending path: register → verify → try login → blocked
4. Backward compat: all seed users work normally
5. Edge cases: duplicates, invalid files, expired tokens, SQL injection, XSS
6. Security: access control, certificate protection, parameterized queries
7. UI/UX: pills, badges, forms, emails, responsive design

**TESTING.md sections:**
- Setup instructions
- Test credentials and scenarios
- Expected outcomes
- Troubleshooting
- Database schema reference
- Security checklist
- Known limitations

**Verify:** Run all test scenarios from TESTING.md, verify all pass without errors. Clean database test: delete reliefgrid.db, run happy path, verify full workflow. Clean database test: seed users work normally. Review console logs - no errors.

---

## Security Checklist

- [x] Passwords hashed with werkzeug (already in use)
- [x] All database queries parameterized (using q() helper)
- [x] File uploads use secure_filename() to prevent path traversal
- [x] File types validated client-side and server-side
- [x] File size limited to 5MB via Flask config
- [x] Certificates only accessible to admins via protected route
- [x] Email verification tokens signed with itsdangerous, expire after 24 hours
- [x] NGO approval required for relief dashboard access (enforced in decorator)
- [x] HTML escaped in templates (Jinja2 auto-escapes)
- [x] Backward compatibility: legacy users with ngo_registration_id=NULL bypass NGO checks

## Migration Strategy

**Safe migration for existing databases:**
1. ALTER TABLE in db.py wrapped in try/except to handle column already exists
2. New column ngo_registration_id defaults to NULL
3. All existing users have NULL ngo_registration_id, bypass NGO checks
4. New NGO registrations create separate ngo_registrations record, link via ngo_registration_id
5. Seed users continue working without modification

## Testing Instructions

1. **Setup:** `cd /home/sadhika/Downloads/reliefgrid && python app.py`
2. **Fresh test:** Delete reliefgrid.db before testing to start clean
3. **Seed users:** admin@reliefgrid.org/admin123 (admin), riverside@ngo.org/relief123 (relief)
4. **NGO registration:** Visit http://127.0.0.1:5000/login, click "Register as NGO", fill form, upload test PDF/JPG
5. **Email verification:** Check console for verification link if email not configured, or check email inbox
6. **Admin approval:** Login as admin, go to NGO Verifications, view details, approve or reject
7. **NGO login:** Try to login with NGO credentials, verify behavior based on status
8. **Backward compat:** Login as riverside@ngo.org, verify works normally

## Build/Test Commands

- **Start server:** `python app.py` (runs on http://127.0.0.1:5000)
- **Reset database:** `rm reliefgrid.db` then restart server (recreates with seed data)
- **Check schema:** `sqlite3 reliefgrid.db '.schema ngo_registrations'`
- **Check data:** `sqlite3 reliefgrid.db 'SELECT * FROM ngo_registrations'`
- **Check users:** `sqlite3 reliefgrid.db 'SELECT id, email, role, ngo_registration_id FROM users'`

## Project Patterns to Follow

- **Routes:** Group by module with comment headers (e.g., `# ---------- NGO registration ----------`)
- **Queries:** Use `q(sql, *args, one=False)` helper for all database queries
- **Auth:** Use `@login_required(role)` decorator, add `@ngo_approved_required()` for relief routes
- **Templates:** Extend `base.html`, use macros from `_macros.html` (pill, stat)
- **Styles:** Use existing CSS classes from `static/style.css` (.card, .grid, .btn, .pill, .flash, .auth, .hero, .panel)
- **Emails:** Follow pattern from `templates/email/password_reset.html` (inline CSS, branding, buttons)
- **Validation:** Use `validate_password()` for password strength, flash messages for user feedback

## Known Limitations

- Manual testing only (no automated test framework in project)
- File upload security: validates type by extension only (not MIME type or content inspection)
- No CSRF protection (mentioned in README as "not yet built")
- Email depends on Flask-Mail configuration (degrades gracefully if not configured)
- Certificate preview: PDF embed may not work in all browsers (provide download link fallback)

## Files Modified/Created Summary

**Modified (6 files):**
- db.py (schema)
- app.py (routes, helpers, decorators)
- templates/base.html (nav badge)
- templates/login.html (NGO register link)

**Created (8 files):**
- templates/ngo_register.html
- templates/ngo_application_status.html
- templates/admin_ngo_verifications.html
- templates/admin_ngo_verification_detail.html
- templates/email/ngo_verification.html
- templates/email/ngo_approved.html
- templates/email/ngo_rejected.html
- TESTING.md

**Created (1 directory):**
- uploads/certificates/

**No new dependencies required** (all needed packages already in requirements.txt)

---

## Rationale for Key Decisions

**1. Separate ngo_registrations table instead of adding fields to users:**
- Allows NGO-specific data (official_reg_number, certificate, application status) without cluttering users table
- Enables registration workflow before user account creation
- Admin reviews applications before account creation (security)
- Supports future expansion (multiple NGO types, different approval workflows)

**2. Link via ngo_registration_id in users table:**
- Maintains referential integrity
- Allows lookup in both directions (user → NGO registration, NGO → user)
- Backward compatible: NULL for legacy users

**3. Email verification separate from admin approval:**
- Email proves user owns the email address (prevents typos, spam)
- Admin approval proves NGO legitimacy (reviews official documents)
- Two-step verification: ownership + legitimacy

**4. Certificate upload required during registration:**
- Provides evidence for admin to review
- Prevents incomplete applications
- Secure storage (admin-only access)

**5. Login blocking enforced in /login route AND decorator:**
- Defense in depth: check at entry point (login) and at each protected route (decorator)
- Handles edge cases (expired sessions, manual URL access)
- Graceful degradation for legacy users

**6. Automatic user account creation on approval:**
- Streamlines workflow: no separate account creation step
- Copies password_hash from NGO registration (user keeps same password)
- Links via ngo_registration_id for status tracking

**7. NGO ID format (NGO-1001):**
- Human-readable, unique identifier
- Easier to reference in support, communications
- Auto-incremented, no collisions
- Separate from internal database id

