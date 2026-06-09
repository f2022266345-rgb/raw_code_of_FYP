# 🔐 Clerk Authentication Setup & Reference Guide

This document is the unified, single-source reference for Clerk authentication in the LUMINA tutoring system. It consolidates all setup instructions, configuration details, architectural overviews, and troubleshooting guides.

---

## 📋 Table of Contents
1. [Overview](#1-overview)
2. [Clerk Dashboard Configuration](#2-clerk-dashboard-configuration)
3. [Environment Variables Reference](#3-environment-variables-reference)
4. [Installation & Local Setup](#4-installation--local-setup)
5. [How Authentication Works (Flows)](#5-how-authentication-works-flows)
6. [Database Schema & Synchronization](#6-database-schema--synchronization)
7. [API Endpoints Reference](#7-api-endpoints-reference)
8. [Frontend Components & Route Protection](#8-frontend-components--route-protection)
9. [Testing & Verification Checklist](#9-testing--verification-checklist)
10. [Troubleshooting & Common Pitfalls](#10-troubleshooting--common-pitfalls)
11. [Production Deployment](#11-production-deployment)

---

## 1. Overview

LUMINA uses **Clerk** as its sole identity and authentication provider. All legacy custom JWT/password logic has been deprecated and removed. 

The architecture is divided into three key layers:
- **Frontend (Next.js)**: Wrapped in `<ClerkProvider>` to render auth screens, manage active sessions, expose hooks (`useUser()`, `useClerk()`), and automatically attach auth tokens to API calls via the `fetchWithClerkAuth()` helper.
- **Backend (Express)**: Exposes a webhook listener (`/api/webhooks/clerk`) for user provisioning, uses Clerk's middleware for route protection, and exposes endpoint checks.
- **Database (PostgreSQL)**: Holds mirroring `users` table synced via Svix webhooks.

---

## 2. Clerk Dashboard Configuration

Follow these steps to configure your Clerk instance:

1. **Access the Dashboard**: Go to [Clerk Dashboard](https://dashboard.clerk.com) and log in.
2. **Find Your Application**:
   - Development App ID: `app_3EoOonhE5BnePYG28DrtiHXBmok`
3. **Get Your API Keys**:
   - Go to **API Keys** in the left sidebar.
   - Copy the **Publishable Key** (`pk_test_...` or `pk_live_...`).
   - Copy the **Secret Key** (`sk_test_...` or `sk_live_...`).
4. **Create a Webhook Endpoint**:
   - Go to **Webhooks** in the left sidebar and click **Add Endpoint**.
   - **Endpoint URL**: `http://localhost:4000/api/webhooks/clerk` (For production: your backend domain).
   - **Subscribe to Events**:
     - `user.created`
     - `user.updated`
     - `user.deleted`
   - Click **Create** and copy the **Signing Secret** (`whsec_...`).

---

## 3. Environment Variables Reference

Ensure the following configurations are added to your local environment files. These files should **never** be committed to Git.

### Frontend: `frontend/.env.local`
```env
# Clerk Frontend Configuration
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_REPLACE_WITH_YOUR_KEY
CLERK_SECRET_KEY=sk_test_REPLACE_WITH_YOUR_SECRET

# Clerk Routes Configuration
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/onboarding

# API Configuration
NEXT_PUBLIC_EXPRESS_API_BASE=http://localhost:4000
```

### Backend Express: `backend-express/.env`
```env
PORT=4000
NODE_ENV=development
FRONTEND_URL=http://localhost:3000
FASTAPI_BASE_URL=http://localhost:8080

# PostgreSQL Connection
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/lumina_db

# Webhook Signing Secret (from Clerk Webhooks Dashboard)
CLERK_WEBHOOK_SECRET=whsec_REPLACE_WITH_YOUR_WEBHOOK_SECRET

# Secret key for legacy/fallback encryption
JWT_SECRET=your_jwt_secret_key_here
```

---

## 4. Installation & Local Setup

### 1. Backend Express Setup
```bash
cd backend-express
npm install
npm run dev
```
Starts backend on port `4000` listening for requests.

### 2. Frontend Next.js Setup
```bash
cd frontend
npm install
npm run dev
```
Starts development server on `http://localhost:3000`.

---

## 5. How Authentication Works (Flows)

### Authentication Flow Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    LUMINA AUTH FLOW                         │
└─────────────────────────────────────────────────────────────┘

[Unauthenticated User]
        │
        ├─ Visits http://localhost:3000
        ├─ Next.js Middleware detects no Clerk session
        └─ Redirects to /sign-in
                │
                ├─ User signs up/in via Clerk UI Component
                ├─ Clerk validates credentials & creates session
                └─ Webhook Fires: user.created (to Express)
                        │
                        ├─ POST /api/webhooks/clerk (Svix verified)
                        └─ Express inserts user into PostgreSQL DB

[Authenticated User]
        │
        ├─ Visits /dashboard (Access allowed by middleware)
        └─ Component fetches data via fetchWithClerkAuth()
                │
                ├─ Automatically retrieves Clerk JWT & appends bearer header
                ├─ Express requireAuth middleware validates JWT
                └─ Express route processes request using req.auth.userId
```

---

## 6. Database Schema & Synchronization

When a user signs up on Clerk, the Webhook Controller extracts their user information and populates the database dynamically.

### PostgreSQL User Model Definition
```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_id VARCHAR(255) NOT NULL UNIQUE,
  email VARCHAR(255) NOT NULL UNIQUE,
  full_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 7. API Endpoints Reference

### Webhooks
* **`POST /api/webhooks/clerk`**
  * **Headers**: `svix-id`, `svix-timestamp`, `svix-signature`
  * **Payload**: Contains event type (`user.created`, `user.updated`, `user.deleted`) and user fields.
  * **Action**: Provisions, updates, or soft-deletes users in the local PostgreSQL database.

### Auth Management (Express)
* **`POST /api/auth/clerk/sync`**
  * **Authorization**: `Bearer <clerk_token>`
  * **Body**: `{ clerkId, email, fullName }`
  * **Action**: Fallback endpoint to sync user if webhooks are delayed.
* **`GET /api/auth/clerk/me`**
  * **Authorization**: `Bearer <clerk_token>`
  * **Action**: Returns active DB user record matching the authenticated Clerk ID.

---

## 8. Frontend Components & Route Protection

### Route Middleware (`middleware.ts`)
Next.js middleware protects all dashboard pages (`/dashboard/*`, `/chat/*`) and api calls (`/api/*`), while leaving public routes (`/`, `/sign-in`, `/sign-up`, `/about`, `/services`) open.

### Custom API Fetcher (`lib/api.ts`)
Always use `fetchWithClerkAuth(url, options)` instead of raw `fetch()`. It automatically resolves the JWT token from Clerk and injects it into the headers:
```javascript
const response = await fetchWithClerkAuth(buildApiUrl("/api/dashboard/summary"));
```

---

## 9. Testing & Verification Checklist

- [ ] Access http://localhost:3000 while logged out -> redirected to `/sign-in`.
- [ ] Sign up using the Clerk Form -> redirected to `/onboarding`.
- [ ] Verify database record created: `SELECT * FROM users;` has your email and `clerk_id`.
- [ ] Fill onboarding form -> redirected to `/dashboard` upon completion.
- [ ] Log out via `<UserButton>` -> redirected back to landing page/sign-in.
- [ ] Attempt to access `/dashboard` directly -> blocked and redirected.

---

## 10. Troubleshooting & Common Pitfalls

| Symptom | Probable Cause | Action |
| :--- | :--- | :--- |
| `"Missing secretKey"` in console | `CLERK_SECRET_KEY` is not defined in `.env.local` | Add key to `FYP_Project/.env.local` and restart. |
| Webhook signature verification fails | Incorrect `CLERK_WEBHOOK_SECRET` | Verify secret matches key from Clerk Dashboard Webhooks tab. |
| Webhook does not hit local endpoint | Localhost is blocked/not public | Run standard webhook forwarding using ngrok, or use Clerk CLI: `clerk listen`. |
| API requests return `401 Unauthorized` | Clerk token expired or missing | Verify API calls are wrapped in `fetchWithClerkAuth`. Check that backend has matching `CLERK_SECRET_KEY`. |

---

## 11. Production Deployment

In production, Clerk environment variables must be changed to production mode:

1. **Keys**: Switch to Production in Clerk Dashboard. Copy the `pk_live_...` and `sk_live_...` credentials.
2. **Webhooks**: Create a production webhook endpoint pointing to `https://api.yourdomain.com/api/webhooks/clerk`.
3. **Frontend Settings**: Ensure `NEXT_PUBLIC_CLERK_SIGN_IN_URL` etc. are configured correctly on your hosting provider.
4. **Environment Verification**: Keep `.env` files secure in your deployment pipeline.
