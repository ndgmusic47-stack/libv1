# Google OAuth State Mismatch Investigation Report

**Investigation Date:** 2025-01-XX  
**Target Issue:** Google OAuth state mismatch - session cookie not present during callback  
**Goal:** Identify exact breaking point in state persistence between `/api/auth/google/login` and `/api/auth/google/auth`

---

## EXECUTIVE SUMMARY

This report documents the comprehensive investigation into the Google OAuth state mismatch issue. Extensive logging has been added to track cookie flow, session management, and middleware behavior throughout the OAuth flow.

---

## 1. SESSIONMIDDLEWARE CONFIGURATION ANALYSIS

### ✅ Configuration Status: CONFIRMED CORRECT

**Location:** `main.py` lines 140-151

```python
session_config = {
    "secret_key": settings.session_secret_key or DEFAULT_SESSION_SECRET,
    "max_age": None,  # Session expires when browser closes
    "same_site": "none",  # Required for cross-domain OAuth redirects
    "https_only": True,  # Always True for same_site='none' (browser requirement)
}
app.add_middleware(SessionMiddleware, **session_config)
```

**Findings:**
- ✅ `same_site="none"` - **CORRECT** (required for cross-domain OAuth)
- ✅ `https_only=True` - **CORRECT** (required for `same_site="none"`)
- ✅ `max_age=None` - **CORRECT** (session cookie, expires when browser closes)
- ✅ Cookie name: `"session"` (default Starlette behavior, not configurable)
- ✅ Only **ONE** SessionMiddleware instance found in entire codebase
- ✅ No duplicate or conflicting middleware

**Conclusion:** SessionMiddleware is configured **EXACTLY** as required for cross-domain OAuth flows.

---

## 2. MIDDLEWARE ORDER ANALYSIS

**Location:** `main.py` - Middleware registration order

**Actual Middleware Stack (outermost to innermost):**
1. `CookieDiagnosticMiddleware` (NEW - added for investigation)
2. `UncaughtExceptionMiddleware`
3. `SessionMiddleware` ✅ **Correct position** (before routers)
4. `CORSMiddleware`
5. `RateLimiterMiddleware`
6. `EnforceHTTPSMiddleware`
7. `SecurityHeadersMiddleware`

**Findings:**
- ✅ SessionMiddleware is added **BEFORE** routers are included (correct)
- ✅ SessionMiddleware is added **AFTER** diagnostic middleware (correct for tracking)
- ⚠️ None of the middleware should strip cookies, but this will be verified in logs

**Conclusion:** Middleware order is correct. SessionMiddleware runs before route handlers.

---

## 3. LOGGING IMPLEMENTATION

### 3.1 Login Endpoint (`/api/auth/google/login`)

**Location:** `routers/google_auth_router.py` lines 43-85

**Logs Added:**
1. **BEFORE OAuth Redirect:**
   - Session contents before redirect
   - Session cookie in request.cookies
   - Redirect URI configuration

2. **AFTER OAuth Redirect (State Storage):**
   - Session contents after `authorize_redirect()`
   - State key check (`_state_google`)
   - **CRITICAL: Set-Cookie header inspection** in response
   - Full response headers
   - Request forwarding headers (x-forwarded-proto, x-forwarded-for, host)
   - URL scheme verification

3. **Set-Cookie Header Verification:**
   - Count of Set-Cookie headers
   - Presence of "session" cookie in Set-Cookie
   - Cookie attributes verification (SameSite=None, Secure, HttpOnly)

### 3.2 Callback Endpoint (`/api/auth/google/auth`)

**Location:** `routers/google_auth_router.py` lines 93-253

**Logs Added:**
1. **BEFORE State Validation:**
   - Incoming state parameter from Google
   - Stored state in session (`_state_google` key)
   - Full session contents
   - Session cookie in `request.cookies`
   - All cookies in request
   - **Cookie header parsing** (manual split and inspection)
   - Request URL details (scheme, hostname, full URL)
   - Request headers (Referer, Origin, x-forwarded-proto, x-forwarded-for, host)
   - Session attribute existence check
   - Session object type and ID

2. **State Validation Failure:**
   - Detailed error type and message
   - State comparison (incoming vs stored)
   - Empty session detection

3. **SUCCESS Path:**
   - Final session state after callback
   - Redirect target

### 3.3 Diagnostic Middleware

**Location:** `main.py` lines 69-118

**Purpose:** Track cookie presence at middleware layer boundaries

**Logs:**
1. **REQUEST Phase (before route handler):**
   - Path and method
   - Cookies in `request.cookies`
   - Cookie header (raw)
   - Session cookie presence check
   - Session attribute existence
   - Session contents
   - x-forwarded-proto header

2. **RESPONSE Phase (after route handler):**
   - Path and status code
   - Set-Cookie headers in response
   - Session cookie detection in Set-Cookie
   - Other cookies in Set-Cookie

**Scope:** Only logs for `/api/auth/google/*` endpoints to reduce noise

### 3.4 Startup Configuration Logging

**Location:** `main.py` lines 154-206

**Logs Added:**
1. Session configuration details
2. Middleware stack order
3. **Worker configuration check:**
   - `WEB_CONCURRENCY` / `UVICORN_WORKERS` environment variables
   - Warning about multiple workers breaking in-memory sessions
4. Hostname and process ID (for multi-instance detection)

---

## 4. KEY INVESTIGATION POINTS TO VERIFY

### 4.1 Cookie Set in Login Response ✅

**Question:** Does the Set-Cookie header with "session" cookie appear in the `/login` response?

**Verification:** Logs will show:
- Set-Cookie headers count
- Whether "session" cookie is present
- Cookie attributes (SameSite=None, Secure, HttpOnly)

**Expected:** ✅ YES - SessionMiddleware should automatically set cookie when session is modified

### 4.2 Cookie Received in Browser ✅

**Question:** Does the browser actually receive and store the session cookie?

**Verification:** 
- Browser DevTools → Application → Cookies → Check for "session" cookie
- Domain should match backend domain
- Attributes should match (SameSite=None, Secure, HttpOnly)

**Note:** Cannot be verified via backend logs alone. Requires browser inspection.

### 4.3 Cookie Sent in Callback Request ✅

**Question:** Does the browser send the "session" cookie in the `/auth` callback request?

**Verification:** Logs will show:
- `request.cookies.get('session')` - Should NOT be "NOT FOUND"
- Cookie header parsing - Should contain "session=" cookie
- Session attribute existence

**Expected:** ✅ YES if browser stored and sent the cookie

### 4.4 Multiple Workers on Render ⚠️

**Question:** Are multiple workers running, causing in-memory session loss?

**Verification:** 
- Logs will show `WEB_CONCURRENCY` / `UVICORN_WORKERS` environment variables
- Hostname and process ID logged for each request
- If different process IDs for `/login` vs `/auth`, sessions won't work

**Expected Behavior:**
- **Single worker:** Sessions stored in memory, accessible across requests ✅
- **Multiple workers:** Sessions stored in memory PER WORKER, lost when request hits different worker ❌

**Solution if multiple workers detected:**
- Use Redis-backed sessions
- Or ensure single worker: `startCommand: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1`

### 4.5 HTTPS Forwarding on Render ✅

**Question:** Is `x-forwarded-proto="https"` correctly forwarded from Render's load balancer?

**Verification:** Logs will show:
- `x-forwarded-proto` header value
- Request URL scheme
- `EnforceHTTPSMiddleware` behavior

**Expected:** ✅ `x-forwarded-proto: https` on Render

**Impact:** 
- If missing or incorrect, `https_only=True` cookies might be rejected
- Starlette SessionMiddleware uses request URL scheme to determine Secure flag

### 4.6 Domain/Cookie Scope Mismatch ⚠️

**Question:** Are the frontend domain and redirect URI compatible with cookie rules?

**Verification:**
- `settings.frontend_url` logged
- `settings.google_redirect_uri` logged
- Cookie domain scope (if set explicitly)

**Expected:**
- Frontend and backend on same domain OR
- Proper CORS configuration with `allow_credentials=True` ✅ (already configured)
- Cookie domain not overly restrictive

### 4.7 State Key Storage ✅

**Question:** Is the state stored correctly as `_state_google`?

**Verification:** Logs will show:
- Session contents after `authorize_redirect()`
- Presence of `_state_google` key
- Value of stored state

**Expected:** ✅ YES - Authlib automatically stores state with pattern `_state_{provider_name}`

**Note:** Code already logs this extensively.

---

## 5. DIAGNOSTIC WORKFLOW

### Step 1: Deploy with Enhanced Logging
Deploy the updated code with all diagnostic logging enabled.

### Step 2: Trigger OAuth Flow
1. Navigate to frontend
2. Click "Sign in with Google"
3. Complete Google OAuth consent
4. Observe callback

### Step 3: Analyze Logs

**In Render Logs, search for:**

1. **"SESSION MIDDLEWARE CONFIGURATION"** - Verify startup config
2. **"WORKER CONFIGURATION CHECK"** - Check for multiple workers
3. **"GOOGLE LOGIN - BEFORE REDIRECT"** - Initial state
4. **"GOOGLE LOGIN - AFTER REDIRECT"** - State storage verification
5. **"RESPONSE HEADERS - SET-COOKIE"** - ✅ **CRITICAL:** Cookie set verification
6. **"COOKIE DIAGNOSTIC MIDDLEWARE - REQUEST"** (for /auth) - Cookie reception
7. **"GOOGLE CALLBACK - BEFORE STATE VALIDATION"** - Session retrieval verification

### Step 4: Root Cause Identification

**Checklist:**

- [ ] **Set-Cookie header present in /login response?**
  - ✅ YES → Cookie was sent to browser
  - ❌ NO → **ROOT CAUSE:** SessionMiddleware not setting cookie

- [ ] **Cookie present in /auth request?**
  - ✅ YES → Cookie was received from browser
  - ❌ NO → **ROOT CAUSE:** Browser not storing/sending cookie
  
  **Sub-issues:**
  - Domain mismatch?
  - Secure flag issue (http vs https)?
  - SameSite=None blocked by browser?
  - CORS issue?

- [ ] **Multiple workers detected?**
  - ✅ YES → **ROOT CAUSE:** Session lost due to worker switching
  - ❌ NO → Not the issue

- [ ] **x-forwarded-proto="https" present?**
  - ✅ YES → HTTPS correctly forwarded
  - ❌ NO → **ROOT CAUSE:** Secure cookies rejected due to HTTP

- [ ] **State key `_state_google` in session?**
  - ✅ YES → State stored correctly
  - ❌ NO → **ROOT CAUSE:** Authlib not storing state

---

## 6. POTENTIAL ROOT CAUSES & FIXES

### 6.1 Multiple Workers (HIGH PROBABILITY)

**Symptoms:**
- Process ID differs between `/login` and `/auth` requests
- Session exists in `/login` but empty in `/auth`
- `WEB_CONCURRENCY > 1` or `UVICORN_WORKERS > 1`

**Fix:**
```yaml
# render.yaml
startCommand: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

OR use Redis-backed sessions (requires Redis configuration).

### 6.2 Cookie Not Set in Response (MEDIUM PROBABILITY)

**Symptoms:**
- Set-Cookie header absent in `/login` response logs
- Session exists but cookie not sent

**Fix:**
- Ensure `request.session` is actually modified (Authlib should do this automatically)
- Check if SessionMiddleware is running (should be in middleware stack)
- Verify session secret key is set

### 6.3 Browser Not Storing Cookie (MEDIUM PROBABILITY)

**Symptoms:**
- Set-Cookie present in response
- Cookie absent in `/auth` request
- Browser DevTools shows no cookie

**Possible Causes:**
- **Domain mismatch:** Cookie domain doesn't match redirect URI domain
- **Secure flag:** Cookie requires HTTPS but request is HTTP (unlikely on Render)
- **SameSite=None blocked:** Browser blocking third-party cookies
- **Cookie path:** Path restriction preventing cookie from being sent

**Fixes:**
- Verify redirect URI domain matches cookie domain
- Check browser console for cookie warnings
- Test with different browsers

### 6.4 HTTPS Forwarding Issue (LOW PROBABILITY)

**Symptoms:**
- `x-forwarded-proto` missing or incorrect
- Request URL scheme is `http` instead of `https`

**Fix:**
- Verify Render proxy configuration
- Ensure `EnforceHTTPSMiddleware` is not interfering

### 6.5 State Key Mismatch (LOW PROBABILITY)

**Symptoms:**
- State key `_state_google` not found in session
- Different key used

**Fix:**
- Verify Authlib version compatibility
- Check if state key pattern changed

---

## 7. NEXT STEPS

1. **Deploy the enhanced logging code** to production/staging
2. **Trigger OAuth flow** and capture logs
3. **Analyze logs** using the checklist in Section 5
4. **Identify root cause** based on log patterns
5. **Apply appropriate fix** from Section 6
6. **Verify fix** with another OAuth flow test

---

## 8. LOG LOCATIONS

All diagnostic logs are written using `logger.error()` to ensure they appear in logs even if log level is set to WARNING or ERROR.

**Log Files:**
- Render: Application logs (dashboard)
- Local: `./logs/app.log` (if running locally)

**Log Format:**
```
================================================================================
[SECTION TITLE]
================================================================================
[Detailed information]
================================================================================
```

**Key Log Markers:**
- `SESSION MIDDLEWARE CONFIGURATION` - Startup config
- `GOOGLE LOGIN - BEFORE REDIRECT` - Pre-redirect state
- `GOOGLE LOGIN - AFTER REDIRECT` - Post-redirect state
- `RESPONSE HEADERS - SET-COOKIE` - **CRITICAL:** Cookie set verification
- `COOKIE DIAGNOSTIC MIDDLEWARE` - Middleware layer tracking
- `GOOGLE CALLBACK - BEFORE STATE VALIDATION` - Callback state

---

## 9. CONCLUSION

All necessary diagnostic logging has been implemented. The logs will reveal:

1. **Whether SessionMiddleware is configured correctly** ✅ (Already verified)
2. **Whether the session cookie is SET in the /login response** (To be verified via logs)
3. **Whether the session cookie is RECEIVED in the /auth request** (To be verified via logs)
4. **Whether multiple workers exist** (To be verified via logs)
5. **Whether HTTPS forwarding is correct** (To be verified via logs)
6. **Whether state keys are stored correctly** (To be verified via logs)

**Once logs are captured from a production OAuth flow, the root cause will be immediately identifiable.**

---

## 10. FILES MODIFIED

1. **`main.py`**
   - Added `CookieDiagnosticMiddleware` for cookie tracking
   - Enhanced startup logging with middleware order and worker check

2. **`routers/google_auth_router.py`**
   - Enhanced `/login` endpoint logging (Set-Cookie header inspection)
   - Enhanced `/auth` endpoint logging (Cookie header parsing and detailed inspection)

---

**END OF REPORT**

