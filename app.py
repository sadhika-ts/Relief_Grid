import functools
import os
import sqlite3
from datetime import datetime, timedelta

from flask import (Flask, flash, redirect, render_template, request, session, url_for)
from flask_mail import Mail, Message
from werkzeug.security import check_password_hash, generate_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

import db as database
from allocation import allocate, priority_score

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

# Email configuration
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "True") == "True"
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")  # Your email
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")  # Your app password
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@reliefgrid.org")

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

app.teardown_appcontext(database.close_db)
database.init_db()

ADMIN_NAV = [("Dashboard", "admin_dashboard"), ("Locations", "locations"), ("Inventory", "inventory"),
             ("Requests", "admin_requests"), ("Allocations", "allocations"), ("Deliveries", "admin_deliveries"),
             ("Simulation", "simulation"), ("Reports", "reports"), ("Notifications", "notifications")]
USER_NAV = [("Home", "user_home"), ("My Requests", "my_requests"), ("Allocations", "my_allocations"),
            ("Deliveries", "my_deliveries"), ("Resources", "user_resources"),
            ("Notifications", "notifications"), ("Profile", "profile")]

REQ_SQL = """SELECT q.*, l.name AS location_name, l.severity, rs.name AS resource_name, rs.unit,
                    u.org_name, u.name AS user_name
             FROM requests q JOIN locations l ON l.id = q.location_id
             JOIN resources rs ON rs.id = q.resource_id JOIN users u ON u.id = q.user_id"""


# ---------- helpers ----------
def db():
    return database.get_db()


def q(sql, *args, one=False):
    rows = db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def login_required(role=None):
    def deco(f):
        @functools.wraps(f)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session["role"] != role:
                flash("You don't have access to that page.", "error")
                return redirect(url_for("home_redirect"))
            return f(*a, **kw)
        return wrapper
    return deco


def available_stock():
    """Stock minus units already reserved by deliveries that haven't been dispatched."""
    rows = q("""SELECT r.id, r.quantity - COALESCE((SELECT SUM(d.quantity) FROM deliveries d
                JOIN requests x ON x.id = d.request_id WHERE x.resource_id = r.id AND d.status = 'Assigned'), 0) AS avail
                FROM resources r""")
    return {r["id"]: r["avail"] for r in rows}


def pending_requests():
    return [dict(r) for r in q(REQ_SQL + " WHERE q.status = 'Pending' ORDER BY q.id")]


def notify(user_id, message, kind="info"):
    db().execute("INSERT INTO notifications(user_id, kind, message) VALUES (?,?,?)", (user_id, kind, message))


def finalize_request(req, qty, note):
    status = "Approved" if qty >= req["quantity"] else "Partially Approved" if qty > 0 else "Rejected"
    db().execute("UPDATE requests SET status=?, allocated_qty=?, total_allocated=total_allocated+?, decision_note=? WHERE id=?",
                 (status, qty, qty, note, req["id"]))
    if qty > 0:
        db().execute("INSERT INTO deliveries(request_id, quantity) VALUES (?,?)", (req["id"], qty))
    detail = f"{qty} of {req['quantity']} {req['unit']}" if status == "Partially Approved" else f"{req['quantity']} {req['unit']}"
    notify(req["user_id"], f"Your request for {detail} of {req['resource_name']} was {status.lower()}. {note or ''}".strip(),
           "success" if status == "Approved" else "warning")


def parse_int(name, minimum=0):
    try:
        value = int(request.form[name])
    except (KeyError, ValueError):
        return None
    return value if value >= minimum else None


def validate_password(password):
    """Validates password strength. Returns (is_valid, error_message)."""
    if not password:
        return False, "Password cannot be empty."
    
    errors = []
    
    if len(password) < 8:
        errors.append("at least 8 characters")
    
    if not any(c.isupper() for c in password):
        errors.append("at least one uppercase letter (A-Z)")
    
    if not any(c.islower() for c in password):
        errors.append("at least one lowercase letter (a-z)")
    
    if not any(c.isdigit() for c in password):
        errors.append("at least one number (0-9)")
    
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        errors.append("at least one special character (!@#$%^&*)")
    
    if errors:
        return False, "Password must contain: " + ", ".join(errors) + "."
    
    return True, ""


@app.context_processor
def inject_nav():
    if "user_id" not in session:
        return {}
    admin = session["role"] == "admin"
    unread = q("SELECT COUNT(*) c FROM notifications WHERE is_read=0 AND " + ("user_id IS NULL" if admin else "user_id=?"),
               *([] if admin else [session["user_id"]]), one=True)["c"]
    return {"nav": ADMIN_NAV if admin else USER_NAV, "unread": unread}


# ---------- 1. authentication ----------
@app.route("/")
def home_redirect():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("admin_dashboard" if session["role"] == "admin" else "user_home"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "relief")
        user = q("SELECT * FROM users WHERE email=?", email, one=True)
        if user and user["role"] == role and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session.update(user_id=user["id"], role=user["role"], name=user["org_name"] or user["name"])
            return redirect(url_for("home_redirect"))
        flash("The email, password, or account type is incorrect.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in ("name", "org_name", "email")}
        password = request.form.get("password", "")  # Don't strip password
        
        # Validate all fields are filled
        if not all([f["name"], f["org_name"], f["email"], password]):
            flash("All fields are required. Please fill in every field.", "error")
            return render_template("register.html")
        
        # Validate email format
        if "@" not in f["email"] or "." not in f["email"].split("@")[-1]:
            flash("Please enter a valid email address.", "error")
            return render_template("register.html")
        
        # Validate password strength
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            flash(error_msg, "error")
            return render_template("register.html")
        
        # If all validations pass, create account
        try:
            db().execute("INSERT INTO users(name,org_name,email,password_hash,role) VALUES (?,?,?,?, 'relief')",
                         (f["name"], f["org_name"], f["email"].lower(), generate_password_hash(password)))
            db().commit()
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("An account with that email already exists.", "error")
    
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        
        if not email:
            flash("Please enter your email address.", "error")
            return render_template("forgot_password.html")
        
        # Check if user exists
        user = q("SELECT * FROM users WHERE email=?", email, one=True)
        
        if user:
            # Generate password reset token (expires in 1 hour)
            token = serializer.dumps(email, salt="password-reset-salt")
            
            # Create reset link
            reset_url = url_for("reset_password", token=token, _external=True)
            
            # Send email
            try:
                msg = Message(
                    subject="Reset Your ReliefGrid Password",
                    recipients=[email],
                    html=render_template("email/password_reset.html", 
                                       user=user, 
                                       reset_url=reset_url)
                )
                
                # Try to send email
                if app.config.get("MAIL_USERNAME"):
                    mail.send(msg)
                    flash("Password reset instructions have been sent to your email.", "success")
                else:
                    # Development mode - show reset link
                    flash(f"Email not configured. Reset link: {reset_url}", "warning")
                    
            except Exception as e:
                # If email fails, show link in development
                flash(f"Could not send email. Reset link: {reset_url}", "warning")
        else:
            # Don't reveal if email exists (security best practice)
            flash("If that email exists, password reset instructions have been sent.", "success")
        
        return redirect(url_for("login"))
    
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        # Verify token (expires after 1 hour)
        email = serializer.loads(token, salt="password-reset-salt", max_age=3600)
    except SignatureExpired:
        flash("The password reset link has expired. Please request a new one.", "error")
        return redirect(url_for("forgot_password"))
    except BadSignature:
        flash("Invalid password reset link.", "error")
        return redirect(url_for("forgot_password"))
    
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        # Check passwords match
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", token=token)
        
        # Validate password strength
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            flash(error_msg, "error")
            return render_template("reset_password.html", token=token)
        
        # Update password
        db().execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (generate_password_hash(password), email)
        )
        db().commit()
        
        flash("Your password has been reset successfully! Please log in.", "success")
        return redirect(url_for("login"))
    
    return render_template("reset_password.html", token=token)


@app.route("/profile", methods=["GET", "POST"])
@login_required()
def profile():
    user = q("SELECT * FROM users WHERE id=?", session["user_id"], one=True)
    if request.method == "POST":
        org, name = request.form.get("org_name", "").strip(), request.form.get("name", "").strip()
        pw = request.form.get("password", "")  # Don't strip password
        
        if not name:
            flash("Name can't be empty.", "error")
        else:
            db().execute("UPDATE users SET name=?, org_name=? WHERE id=?", (name, org, user["id"]))
            
            # If password is provided, validate and update
            if pw:
                is_valid, error_msg = validate_password(pw)
                if not is_valid:
                    flash(error_msg, "error")
                    return redirect(url_for("profile"))
                db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(pw), user["id"]))
            
            db().commit()
            session["name"] = org or name
            flash("Profile saved.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html", user=user)


# ---------- admin: dashboard, locations, inventory ----------
@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    avail = available_stock()
    demand = {r["resource_id"]: r["t"] for r in q("SELECT resource_id, SUM(quantity) t FROM requests WHERE status='Pending' GROUP BY resource_id")}
    stats = {
        "affected": q("SELECT COALESCE(SUM(people_affected),0) c FROM locations WHERE status!='Resolved'", one=True)["c"],
        "available": sum(avail.values()),
        "pending": q("SELECT COUNT(*) c FROM requests WHERE status='Pending'", one=True)["c"],
        "shortages": sum(1 for rid, d in demand.items() if d > avail.get(rid, 0)),
        "deliveries": q("SELECT COUNT(*) c FROM deliveries WHERE status IN ('Assigned','In Transit')", one=True)["c"],
    }
    locs = [dict(r) for r in q("SELECT * FROM locations WHERE status!='Resolved'")]
    recent = q(REQ_SQL + " ORDER BY q.id DESC LIMIT 8")
    return render_template("admin_dashboard.html", stats=stats, locs=locs, recent=recent)


@app.route("/admin/locations", methods=["GET", "POST"])
@login_required("admin")
def locations():
    if request.method == "POST":
        if request.form.get("action") == "disaster":
            if request.form.get("name", "").strip():
                db().execute("INSERT INTO disasters(name,type) VALUES (?,?)",
                             (request.form["name"].strip(), request.form.get("type", "Flood")))
                flash("Disaster recorded.", "success")
        else:
            people = parse_int("people_affected")
            try:
                lat, lng = float(request.form["lat"]), float(request.form["lng"])
            except (KeyError, ValueError):
                lat = lng = None
            if not request.form.get("name", "").strip() or people is None:
                flash("Enter a location name and a valid number of people affected.", "error")
            else:
                db().execute("""INSERT INTO locations(disaster_id,name,type,severity,people_affected,status,lat,lng)
                                VALUES (?,?,?,?,?,?,?,?)""",
                             (request.form.get("disaster_id") or None, request.form["name"].strip(), request.form["type"],
                              request.form["severity"], people, request.form["status"], lat, lng))
                flash("Location added.", "success")
        db().commit()
        return redirect(url_for("locations"))
    return render_template("locations.html", disasters=q("SELECT * FROM disasters"),
                           locs=q("SELECT l.*, d.name AS disaster FROM locations l LEFT JOIN disasters d ON d.id=l.disaster_id ORDER BY l.id"))


@app.post("/admin/locations/<int:lid>")
@login_required("admin")
def update_location(lid):
    people = parse_int("people_affected")
    if people is None:
        flash("People affected must be a positive number.", "error")
    else:
        db().execute("UPDATE locations SET severity=?, status=?, people_affected=? WHERE id=?",
                     (request.form["severity"], request.form["status"], people, lid))
        db().commit()
        flash("Location updated.", "success")
    return redirect(url_for("locations"))


@app.route("/admin/inventory", methods=["GET", "POST"])
@login_required("admin")
def inventory():
    if request.method == "POST":
        action, amount = request.form.get("action"), parse_int("amount")
        if action == "add":
            if request.form.get("name", "").strip() and amount is not None and request.form.get("unit", "").strip():
                try:
                    db().execute("INSERT INTO resources(name,unit,quantity,low_threshold) VALUES (?,?,?,?)",
                                 (request.form["name"].strip(), request.form["unit"].strip(), amount, parse_int("low_threshold") or 0))
                    flash("Resource added.", "success")
                except sqlite3.IntegrityError:
                    flash("That resource already exists.", "error")
            else:
                flash("Enter a name, unit, and quantity.", "error")
        elif amount is None:
            flash("Enter a valid quantity.", "error")
        else:
            rid = int(request.form["resource_id"])
            cur = q("SELECT quantity FROM resources WHERE id=?", rid, one=True)["quantity"]
            reserved = cur - available_stock()[rid]
            new = cur + amount if action == "receive" else amount
            if new < reserved:
                flash(f"{reserved} units are reserved for assigned deliveries. Stock can't go below that.", "error")
            else:
                db().execute("UPDATE resources SET quantity=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new, rid))
                flash("Stock updated.", "success")
        db().commit()
        return redirect(url_for("inventory"))
    return render_template("inventory.html", resources=q("SELECT * FROM resources ORDER BY id"), avail=available_stock())


# ---------- 4. requests ----------
@app.route("/admin/requests")
@login_required("admin")
def admin_requests():
    status = request.args.get("status", "")
    rows = q(REQ_SQL + (" WHERE q.status=?" if status else "") + " ORDER BY q.id DESC", *([status] if status else []))
    return render_template("admin_requests.html", rows=rows, status=status, avail=available_stock())


@app.post("/admin/requests/<int:rid>/decide")
@login_required("admin")
def decide(rid):
    req = q(REQ_SQL + " WHERE q.id=? AND q.status='Pending'", rid, one=True)
    qty, note = parse_int("qty"), request.form.get("note", "").strip()
    if not req:
        flash("That request has already been decided.", "error")
    elif qty is None or qty > req["quantity"]:
        flash(f"Enter a quantity between 0 and {req['quantity']}.", "error")
    elif qty > available_stock()[req["resource_id"]]:
        flash("That's more than the stock currently available.", "error")
    elif qty < req["quantity"] and not note:
        flash("Add a reason when approving less than requested.", "error")
    else:
        finalize_request(dict(req), qty, note)
        db().commit()
        flash("Decision saved.", "success")
    return redirect(url_for("admin_requests", status="Pending"))


# ---------- 5. smart allocation ----------
@app.route("/admin/allocations", methods=["GET", "POST"])
@login_required("admin")
def allocations():
    reqs = pending_requests()
    plan, _ = allocate(reqs, available_stock())
    if request.method == "POST":
        by_id = {r["id"]: r for r in reqs}
        for p in plan:
            finalize_request(by_id[p["id"]], p["allocated"], p["reason"])
        db().commit()
        flash(f"Allocation applied to {len(plan)} requests. Deliveries are now assigned.", "success")
        return redirect(url_for("admin_deliveries"))
    totals = {"requests": len(plan), "requested": sum(p["quantity"] for p in plan),
              "allocated": sum(p["allocated"] for p in plan), "unmet": sum(p["unmet"] for p in plan)}
    return render_template("allocations.html", plan=plan, totals=totals)


# ---------- 6. deliveries ----------
@app.route("/admin/deliveries")
@login_required("admin")
def admin_deliveries():
    rows = q("""SELECT d.*, q.resource_id, rs.name AS resource_name, rs.unit, l.name AS location_name, u.org_name
                FROM deliveries d JOIN requests q ON q.id=d.request_id JOIN resources rs ON rs.id=q.resource_id
                JOIN locations l ON l.id=q.location_id JOIN users u ON u.id=q.user_id ORDER BY d.id DESC""")
    return render_template("admin_deliveries.html", rows=rows)


@app.post("/admin/deliveries/<int:did>/advance")
@login_required("admin")
def advance_delivery(did):
    d = q("""SELECT d.*, q.resource_id, q.user_id, q.quantity AS req_quantity, q.total_received, rs.name AS resource_name FROM deliveries d
             JOIN requests q ON q.id=d.request_id JOIN resources rs ON rs.id=q.resource_id WHERE d.id=?""", did, one=True)
    nxt = {"Assigned": "In Transit", "In Transit": "Delivered"}.get(d["status"]) if d else None
    if not nxt:
        flash("That delivery can't be advanced.", "error")
    else:
        if nxt == "In Transit":  # dispatch: stock leaves the depot
            cur = db().execute("UPDATE resources SET quantity=quantity-?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND quantity>=?",
                               (d["quantity"], d["resource_id"], d["quantity"]))
            if cur.rowcount == 0:
                flash("Not enough stock in the depot to dispatch this delivery.", "error")
                return redirect(url_for("admin_deliveries"))
            db().execute("UPDATE requests SET total_dispatched=total_dispatched+? WHERE id=?", (d["quantity"], d["request_id"]))
        db().execute("UPDATE deliveries SET status=? WHERE id=?", (nxt, did))
        if nxt == "Delivered":
            new_total_received = d["total_received"] + d["quantity"]
            remaining_demand = max(0, d["req_quantity"] - new_total_received)
            new_status = "Fulfilled" if remaining_demand == 0 else "Partially Fulfilled"
            db().execute("UPDATE requests SET status=?, total_received=? WHERE id=?", (new_status, new_total_received, d["request_id"]))
        notify(d["user_id"], f"Your delivery of {d['quantity']} {d['resource_name']} is now {nxt.lower()}.", "info")
        db().commit()
        flash(f"Delivery marked {nxt}.", "success")
    return redirect(url_for("admin_deliveries"))


# ---------- 7. simulation ----------
@app.route("/admin/simulation", methods=["GET", "POST"])
@login_required("admin")
def simulation():
    resources, locs = q("SELECT * FROM resources"), q("SELECT id, name FROM locations")
    result = None
    if request.method == "POST":
        demand = parse_int("demand_pct", 1) or 100
        cut_res, cut_pct = int(request.form.get("cut_resource") or 0), parse_int("cut_pct") or 0
        blocked = {int(request.form["blocked"])} if request.form.get("blocked") else set()
        reqs, avail = pending_requests(), available_stock()
        base, _ = allocate(reqs, avail)
        scen_reqs = [{**r, "quantity": max(1, round(r["quantity"] * demand / 100))} for r in reqs]
        scen_stock = {k: (v * (100 - cut_pct) // 100 if k == cut_res else v) for k, v in avail.items()}
        scen, _ = allocate(scen_reqs, scen_stock, blocked)
        rows = []
        for res in resources:
            b = sum(p["allocated"] for p in base if p["resource_id"] == res["id"])
            s = sum(p["allocated"] for p in scen if p["resource_id"] == res["id"])
            if b or s:
                rows.append({"name": res["name"], "before": b, "after": s, "change": s - b,
                             "unmet": sum(p["unmet"] for p in scen if p["resource_id"] == res["id"])})
        result = {"rows": rows, "delta": sum(r["change"] for r in rows), "empty": not reqs, "form": request.form}
    return render_template("simulation.html", resources=resources, locs=locs, result=result)


# ---------- 8. reports & notifications ----------
@app.route("/admin/reports")
@login_required("admin")
def reports():
    by_res = q("""SELECT rs.id, rs.name, rs.unit,
                  COALESCE(SUM(CASE WHEN q.status!='Pending' THEN q.quantity END),0) AS requested,
                  COALESCE(SUM(q.allocated_qty),0) AS allocated,
                  COALESCE(SUM(CASE WHEN q.status='Pending' THEN q.quantity END),0) AS pending
                  FROM resources rs LEFT JOIN requests q ON q.resource_id=rs.id GROUP BY rs.id""")
    delivered = {r["resource_id"]: r["t"] for r in q("""SELECT q.resource_id, SUM(d.quantity) t FROM deliveries d
                 JOIN requests q ON q.id=d.request_id WHERE d.status='Delivered' GROUP BY q.resource_id""")}
    return render_template("reports.html", by_res=by_res, delivered=delivered,
                           statuses=q("SELECT status, COUNT(*) c FROM requests GROUP BY status"))


@app.route("/notifications")
@login_required()
def notifications():
    admin = session["role"] == "admin"
    where, args = ("user_id IS NULL", []) if admin else ("user_id=?", [session["user_id"]])
    rows = q(f"SELECT * FROM notifications WHERE {where} ORDER BY id DESC LIMIT 50", *args)
    db().execute(f"UPDATE notifications SET is_read=1 WHERE {where}", args)
    db().commit()
    return render_template("notifications.html", rows=rows)


# ---------- relief center user ----------
@app.route("/home")
@login_required("relief")
def user_home():
    uid = session["user_id"]
    stats = {
        "allocated": q("SELECT COALESCE(SUM(allocated_qty),0) c FROM requests WHERE user_id=?", uid, one=True)["c"],
        "pending_deliveries": q("SELECT COUNT(*) c FROM deliveries d JOIN requests q ON q.id=d.request_id WHERE q.user_id=? AND d.status IN ('Assigned','In Transit')", uid, one=True)["c"],
        "active": q("SELECT COUNT(*) c FROM requests WHERE user_id=? AND status='Pending'", uid, one=True)["c"],
        "completed": q("SELECT COUNT(*) c FROM deliveries d JOIN requests q ON q.id=d.request_id WHERE q.user_id=? AND d.status='Delivered'", uid, one=True)["c"],
    }
    recent = q(REQ_SQL + " WHERE q.user_id=? ORDER BY q.id DESC LIMIT 5", uid)
    return render_template("user_home.html", stats=stats, recent=recent)


@app.route("/my/requests")
@login_required("relief")
def my_requests():
    return render_template("my_requests.html", title="My Requests", sub="Track every request you've submitted.",
                           rows=q(REQ_SQL + " WHERE q.user_id=? ORDER BY q.id DESC", session["user_id"]))


@app.route("/my/allocations")
@login_required("relief")
def my_allocations():
    return render_template("my_requests.html", title="Allocations", sub="What was allocated to your requests, and why.",
                           rows=q(REQ_SQL + " WHERE q.user_id=? AND q.status!='Pending' ORDER BY q.id DESC", session["user_id"]))


@app.route("/my/requests/new", methods=["GET", "POST"])
@login_required("relief")
def new_request():
    if request.method == "POST":
        qty, people = parse_int("quantity", 1), parse_int("people_affected", 1)
        if qty is None or people is None or request.form.get("urgency") not in ("Low", "Medium", "High", "Critical"):
            flash("Enter a quantity, the number of people affected, and an urgency level.", "error")
        else:
            db().execute("""INSERT INTO requests(user_id,location_id,resource_id,quantity,people_affected,urgency,description)
                            VALUES (?,?,?,?,?,?,?)""", (session["user_id"], request.form["location_id"], request.form["resource_id"],
                                                        qty, people, request.form["urgency"], request.form.get("description", "").strip()))
            notify(None, f"New {request.form['urgency'].lower()} request from {session['name']}.", "warning")
            db().commit()
            flash("Request submitted. You'll be notified when it's reviewed.", "success")
            return redirect(url_for("my_requests"))
    return render_template("new_request.html", locs=q("SELECT * FROM locations WHERE status!='Resolved' ORDER BY name"),
                           resources=q("SELECT * FROM resources ORDER BY name"))


@app.route("/my/deliveries")
@login_required("relief")
def my_deliveries():
    rows = q("""SELECT d.*, rs.name AS resource_name, rs.unit, l.name AS location_name FROM deliveries d
                JOIN requests q ON q.id=d.request_id JOIN resources rs ON rs.id=q.resource_id
                JOIN locations l ON l.id=q.location_id WHERE q.user_id=? ORDER BY d.id DESC""", session["user_id"])
    return render_template("my_deliveries.html", rows=rows)


@app.post("/my/deliveries/<int:did>/<action>")
@login_required("relief")
def delivery_feedback(did, action):
    d = q("""SELECT d.* FROM deliveries d JOIN requests q ON q.id=d.request_id WHERE d.id=? AND q.user_id=?""",
          did, session["user_id"], one=True)
    if not d or d["status"] == "Assigned" or action not in ("confirm", "report"):
        flash("That delivery can't be updated yet.", "error")
    elif action == "confirm":
        db().execute("UPDATE deliveries SET confirmed=1 WHERE id=?", (did,))
        notify(None, f"{session['name']} confirmed receipt of delivery #{did}.", "success")
        flash("Receipt confirmed.", "success")
    else:
        issue = request.form.get("issue", "").strip()
        if not issue:
            flash("Describe the problem so the admin can follow up.", "error")
            return redirect(url_for("my_deliveries"))
        db().execute("UPDATE deliveries SET issue=? WHERE id=?", (issue, did))
        notify(None, f"{session['name']} reported a problem with delivery #{did}: {issue}", "warning")
        flash("Problem reported to the admin.", "success")
    db().commit()
    return redirect(url_for("my_deliveries"))


@app.route("/my/resources")
@login_required("relief")
def user_resources():
    avail = available_stock()
    return render_template("user_resources.html", resources=q("SELECT * FROM resources ORDER BY name"), avail=avail)


if __name__ == "__main__":
    app.run(debug=True)
