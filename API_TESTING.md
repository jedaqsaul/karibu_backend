# Quick API testing reference (Postman)

Base URL: `http://localhost:8000/api`

All authenticated requests need header: `Authorization: Bearer <access_token>`

---

## 1. Register attendee
`POST /auth/register/`
```json
{
  "email": "attendee@test.com",
  "first_name": "Amara",
  "last_name": "Otieno",
  "phone_number": "+254712345678",
  "password": "TestPass123!",
  "password_confirm": "TestPass123!"
}
```

## 2. Register organizer
`POST /auth/register/organizer/`
```json
{
  "email": "organizer@test.com",
  "first_name": "Kevin",
  "last_name": "Mwangi",
  "phone_number": "+254798765432",
  "password": "TestPass123!",
  "password_confirm": "TestPass123!",
  "organization_name": "Nairobi Events Co.",
  "bio": "We run live music events.",
  "website": "https://example.com"
}
```
No tokens returned — organizer needs admin approval before it matters (they can still log in and create draft events).

## 3. Register admin
No public endpoint. Use:
```bash
python manage.py createsuperuser
```

## 4. Login
`POST /auth/login/`
```json
{ "email": "attendee@test.com", "password": "TestPass123!" }
```
Returns `{ access, refresh, user }`. Copy `access` into your Postman env/Authorization header for everything below. Copy `refresh` for step 5.

## 5. Refresh token
`POST /auth/token/refresh/`
```json
{ "refresh": "<refresh_token_from_login>" }
```

## 6. Get my profile
`GET /auth/me/` — auth required, no body

## 7. Update my profile
`PATCH /auth/me/`
```json
{ "first_name": "Amara", "phone_number": "+254700000000" }
```

## 8. Change password
`POST /auth/me/change-password/`
```json
{
  "current_password": "TestPass123!",
  "new_password": "NewPass456!",
  "new_password_confirm": "NewPass456!"
}
```

---

## 9. Admin: approve the organizer
Log in as your superuser first, use that `access` token.

`GET /admin/organizers/pending/` — find the organizer's `id` (this is the **OrganizerProfile id**, not the user id)

`POST /admin/organizers/<id>/approval/`
```json
{ "action": "approve" }
```
or
```json
{ "action": "reject", "rejection_reason": "Incomplete info" }
```

---

## 10. Organizer: create an event
Log in as the organizer. First get a category id:
`GET /events/categories/`

`POST /organizer/events/create/`
```json
{
  "title": "Nairobi Jazz Festival",
  "description": "A night of live jazz.",
  "category_id": "<uuid from categories list>",
  "venue": "Carnivore Grounds",
  "address": "Langata Road",
  "city": "Nairobi",
  "country": "Kenya",
  "start_datetime": "2026-12-01T18:00:00Z",
  "end_datetime": "2026-12-01T23:00:00Z",
  "is_free": false,
  "ticket_price": 2500,
  "total_capacity": 200
}
```
Save the returned `id`.

## 11. Organizer: submit event for review
`POST /organizer/events/<id>/submit/` — no body

## 12. Admin: approve the event
`GET /admin/events/pending/` to find it, then:
`POST /admin/events/<id>/approval/`
```json
{ "action": "approve" }
```

---

## 13. Attendee: browse + buy a ticket
`GET /events/` — find the event's `id`

`POST /tickets/purchase/`
```json
{ "event_id": "<event id>", "quantity": 2 }
```

`GET /tickets/` — list your tickets

---

## Notes
- No cookies — always send the JWT as `Authorization: Bearer <token>`.
- Access tokens expire fast; re-run step 5 (or log in again) if you get 401s.
- IDs are UUIDs — copy them from the previous response, don't guess.
