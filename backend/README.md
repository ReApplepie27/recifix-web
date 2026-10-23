# Recifix backend (Flask + MySQL)

Serves your existing site **and** a JSON API from one server, so the front end and API
share an origin (no CORS, cookies "just work"). Open the site through Flask
(`http://127.0.0.1:5000`), not by double-clicking the HTML files.

## Setup

1. **Create the MySQL database and user** (MySQL 8+ / MariaDB 10.5+):
   ```sql
   CREATE DATABASE recifix CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'recifix'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
   GRANT ALL PRIVILEGES ON recifix.* TO 'recifix'@'localhost';
   ```
2. **Install and configure**
   ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env                                    # Windows: copy .env.example .env
   ```
   Edit `.env`: set `DATABASE_URL`, and a `SECRET_KEY` from
   `python -c "import secrets; print(secrets.token_hex(32))"`.
3. **Create the tables and run**
   ```bash
   python init_db.py
   python wsgi.py          # http://127.0.0.1:5000
   ```

## What it does

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/signup` | Create account, start session |
| `POST /api/auth/login` | Log in (5 failed tries / 15 min per IP+email, then 429) |
| `POST /api/auth/logout` | End session |
| `GET /api/auth/me` | Current user (401 if logged out) |
| `PATCH /api/account` | Update name / email |
| `POST /api/account/password` | Change password (needs current password; signs out other devices) |
| `POST /api/auth/forgot-password` | Request reset: `{email, new_password}`; emails a confirmation link |
| `GET /api/auth/confirm-reset?token=` | Applies the pending password, redirects to the login page |

`/dashboard.html` is only served to logged-in users; everything else in `backend/` is never exposed.

### Forgot password
Your modal asks for an email and a new password. Applying that directly would let anyone
reset anyone's password, so the new password is stored (hashed) as *pending* and only
takes effect when the account owner opens the emailed link (valid 1 hour, single use).
Without `SMTP_*` settings, the link is printed in the server console for local testing.

### Security notes
- Passwords: scrypt hashes (Werkzeug); minimum 8 characters.
- Sessions: signed, HttpOnly, SameSite=Lax cookies, 14 days. Set `SESSION_COOKIE_SECURE=1` behind HTTPS.
- Write requests must be `application/json` (blocks cross-site form posts).
- The login rate limiter lives in process memory; with several gunicorn workers the limit is per worker.

## Recipes

Recipes come from your spreadsheet (exported as CSV). Run these from the `backend` folder with the virtual environment active.

```powershell
pip install -r requirements.txt        # once: adds Pillow for image resizing
python init_db.py                       # once (and after updates): creates the recipe tables
```

**1. Prepare the photos** (optional but recommended). Keep the full-size originals *outside* the project, named after
the recipe (`Adobong Baboy.png`). This writes small web-ready JPEGs into `images/recipes/`:
```powershell
python prepare_images.py --csv "data\RECIFIX_dish_All_Recipes.csv" --source "C:\path\to\originals"
```
It prints which recipes have no photo, which files match no recipe, and near-misses it did *not* apply
(rename the file if the suggestion is right). Recipes without a photo show a placeholder.

**2. Import the recipes:**
```powershell
python import_recipes.py "data\RECIFIX_dish_All_Recipes.csv"
```
It is safe to re-run after editing the sheet: recipes are updated in place, so users' saved recipes survive, and a
running server picks up the changes without a restart. A review report (`import_report.txt`, next to the CSV) lists
everything that needs a human look. Add `--dry-run` to check without touching the database. Run `prepare_images.py`
*before* the import so photos get linked (or re-run the import afterwards).

### How pantry matching works
- Each ingredient line is reduced to a name ("1 medium potato, diced" becomes `potato`); plurals and Tagalog names
  (sibuyas, toyo, patis...) are normalised, so "Tomatoes" matches "1 tomato, diced".
- "Salt, pepper, water and cooking oil" are assumed to be in every kitchen; optional lines ("for serving") never count against a match.
- "A or B" means either works; "A and B" needs both. `pork` matches `pork belly`, but `milk` does not match `coconut milk`.
- Recipes you can cook right now come first, then recipes that use the most of your ingredients while needing the fewest extras.

### Allergens (please read)
The allergy filter is conservative. A recipe is hidden if **any** of these suggests the allergen: the sheet's Allergens
column, conditional notes ("Fish (if fish sauce is used)"), or the ingredient list itself (regular soy sauce
implies wheat, oyster sauce implies shellfish, butter implies dairy). Recipes with an empty Allergens cell are
hidden whenever an allergen filter is on. The ingredient check uses keyword rules and cannot know about brands, so the
site shows "always check labels" wherever allergens appear. Fix the sheet and re-import to make a recipe's allergen list authoritative.

## API (recipes)

| Endpoint | Purpose |
|---|---|
| `GET /api/recipes/search` | `ingredients` (comma list), `meal`, `taste`, `allergens` (comma list), `difficulty`, `max_minutes`, `q`, `limit`, `offset`, `include_unverified` |
| `GET /api/recipes/<id>` | Full recipe: ingredients by section, steps, allergens |
| `GET /api/saved`, `PUT/DELETE /api/saved/<id>` | The logged-in user's saved recipes |
| `GET /api/ingredients/suggest?q=` | Ingredient autocomplete |

## Production
```bash
gunicorn -w 2 -b 127.0.0.1:8000 wsgi:app    # put nginx/Caddy with HTTPS in front; set BASE_URL to the public URL
```

## Tests
```bash
python -m unittest discover -s tests -v
```
Tests run on a temporary SQLite file (same SQL as MySQL), so no MySQL server is needed. Pillow is needed for the image tests.
