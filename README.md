# ReliefGrid: Smart Disaster Relief Allocation and Rescue Coordination

Flask + SQLite + plain HTML/CSS/JS.

## Run
    pip install -r requirements.txt
    python app.py          # http://127.0.0.1:5000  (creates reliefgrid.db with demo data on first run)

Demo logins: `admin@reliefgrid.org` / `admin123` (Admin tab) and `riverside@ngo.org` / `relief123` (Relief center user tab).
Set `SECRET_KEY` in the environment for anything beyond local demos. Delete `reliefgrid.db` to reset the data.

## Layout
| File | Purpose |
|---|---|
| `app.py` | All routes, grouped by module |
| `allocation.py` | Priority score + stock-limited allocation (the core algorithm) |
| `db.py` | Schema and demo seed data |
| `templates/`, `static/style.css` | UI matching the mockup |

## Module map
1. Auth: `/login`, `/register`, `/profile`, role-based redirects
2. Locations: `/admin/locations` (disasters, locations, severity, status)
3. Inventory: `/admin/inventory` (add, receive, set stock, low-stock flags, reserved stock)
4. Requests: `/my/requests/new`, `/admin/requests` (manual approve / partial / reject with reason)
5. Smart allocation: `/admin/allocations` (preview, explain, apply)
6. Deliveries: `/admin/deliveries`, `/my/deliveries` (dispatch deducts stock; confirm receipt / report issue)
7. Simulation: `/admin/simulation` (demand change, stock cut, blocked route; compares to current plan)
8. Reports and notifications: `/admin/reports`, `/notifications`

## How allocation works
Score = 45% request urgency + 30% location severity + 25% people affected (relative to the largest request).
Requests are served in score order per resource until available stock is used up. Available stock excludes units
already reserved by deliveries that are assigned but not yet dispatched.

## Not yet built
CSRF protection, vehicle capacity, depot-to-location route distances, CSV/PDF report export.
