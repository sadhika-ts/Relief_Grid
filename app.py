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
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB file upload limit
app.config["UPLOAD_FOLDER"] = "uploads/certificates"

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
             ("Requests", "admin_requests"), ("NGO Verifications", "admin_ngo_verifications"), ("Allocations", "allocations"), ("Deliveries", "admin_deliveries"),
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


def get_ngo_status(user_id):
    """Get NGO approval status for a user. Returns status or None if not an NGO user."""
    user = q("SELECT ngo_registration_id FROM users WHERE id=?", user_id, one=True)
    if not user or not user["ngo_registration_id"]:
        return None
    ngo = q("SELECT status FROM ngo_registrations WHERE id=?", user["ngo_registration_id"], one=True)
    return ngo["status"] if ngo else None


def ngo_approved_required():
    """Decorator to ensure NGO users are approved before accessing relief routes."""
    def deco(f):
        @functools.wraps(f)
        def wrapper(*a, **kw):
            if session.get("role") == "relief":
                user = q("SELECT ngo_registration_id FROM users WHERE id=?", session["user_id"], one=True)
                # If user has ngo_registration_id, check approval status
                if user and user["ngo_registration_id"]:
                    ngo = q("SELECT status FROM ngo_registrations WHERE id=?", user["ngo_registration_id"], one=True)
                    if not ngo or ngo["status"] != "APPROVED":
                        flash("Your NGO application must be approved before accessing this page.", "error")
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


def generate_ngo_id():
    """Generate unique NGO ID in format NGO-1001, NGO-1002, etc."""
    last = q("SELECT ngo_id FROM ngo_registrations ORDER BY id DESC LIMIT 1", one=True)
    if last and last["ngo_id"]:
        # Parse NGO-NNNN format
        num = int(last["ngo_id"].split("-")[1]) + 1
    else:
        num = 1001
    return f"NGO-{num:04d}"


@app.context_processor
def inject_nav():
    if "user_id" not in session:
        return {}
    admin = session["role"] == "admin"
    unread = q("SELECT COUNT(*) c FROM notifications WHERE is_read=0 AND " + ("user_id IS NULL" if admin else "user_id=?"),
               *([] if admin else [session["user_id"]]), one=True)["c"]
    ngo_pending = q("SELECT COUNT(*) c FROM ngo_registrations WHERE status='PENDING'", one=True)["c"] if admin else 0
    return {"nav": ADMIN_NAV if admin else USER_NAV, "unread": unread, "ngo_pending": ngo_pending}


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
            # Check NGO approval status before allowing login
            if user["ngo_registration_id"]:
                ngo = q("SELECT status, rejection_reason FROM ngo_registrations WHERE id=?", user["ngo_registration_id"], one=True)
                if ngo:
                    if ngo["status"] == "PENDING":
                        flash("Your NGO application is pending admin approval. You will be notified when approved.", "warning")
                        return redirect(url_for("login"))
                    elif ngo["status"] == "REJECTED":
                        flash(f"Your NGO application was rejected. Reason: {ngo['rejection_reason']}. Please contact support.", "error")
                        return redirect(url_for("login"))
                    # If APPROVED, continue with login
            
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
            
            # Send email - REQUIRE email configuration for security
            try:
                if not app.config.get("MAIL_USERNAME"):
                    # Email MUST be configured for security reasons
                    flash("Password reset is currently unavailable. Please contact your administrator.", "error")
                    return render_template("forgot_password.html")
                
                msg = Message(
                    subject="Reset Your ReliefGrid Password",
                    recipients=[email],
                    html=render_template("email/password_reset.html", 
                                       user=user, 
                                       reset_url=reset_url)
                )
                
                mail.send(msg)
                flash("Password reset instructions have been sent to your email. Please check your inbox.", "success")
                    
            except Exception as e:
                # Log error but don't reveal details to user
                print(f"Email sending failed: {str(e)}")
                flash("Unable to send password reset email. Please contact your administrator.", "error")
                return render_template("forgot_password.html")
        else:
            # Don't reveal if email exists (security best practice)
            # Show same success message even if email doesn't exist
            flash("If that email exists, password reset instructions have been sent. Please check your inbox.", "success")
        
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
            # Show all resources, not just those with allocations
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
@ngo_approved_required()
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
@ngo_approved_required()
def my_requests():
    return render_template("my_requests.html", title="My Requests", sub="Track every request you've submitted.",
                           rows=q(REQ_SQL + " WHERE q.user_id=? ORDER BY q.id DESC", session["user_id"]))


@app.route("/my/allocations")
@login_required("relief")
@ngo_approved_required()
def my_allocations():
    return render_template("my_requests.html", title="Allocations", sub="What was allocated to your requests, and why.",
                           rows=q(REQ_SQL + " WHERE q.user_id=? AND q.status!='Pending' ORDER BY q.id DESC", session["user_id"]))


@app.route("/my/requests/new", methods=["GET", "POST"])
@login_required("relief")
@ngo_approved_required()
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
@ngo_approved_required()
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
@ngo_approved_required()
def user_resources():
    avail = available_stock()
    return render_template("user_resources.html", resources=q("SELECT * FROM resources ORDER BY name"), avail=avail)


# ---------- NGO registration and verification ----------
@app.route("/ngo/register", methods=["GET", "POST"])
def ngo_register():
    if request.method == "POST":
        # Import here to avoid dependency issues
        from werkzeug.utils import secure_filename
        import time
        
        # Collect form data
        f = {k: request.form.get(k, "").strip() for k in ("org_name", "official_reg_number", "registration_type", "email", "contact_number", "address")}
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        # Validate all fields present
        if not all([f["org_name"], f["official_reg_number"], f["registration_type"], f["email"], f["contact_number"], f["address"], password, confirm_password]):
            flash("All fields are required. Please fill in every field.", "error")
            return render_template("ngo_register.html")
        
        # Validate email format
        if "@" not in f["email"] or "." not in f["email"].split("@")[-1]:
            flash("Please enter a valid email address.", "error")
            return render_template("ngo_register.html")
        
        # Validate password strength
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            flash(error_msg, "error")
            return render_template("ngo_register.html")
        
        # Validate password confirmation
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("ngo_register.html")
        
        # Validate certificate upload
        if "certificate" not in request.files:
            flash("Please upload your registration certificate.", "error")
            return render_template("ngo_register.html")
        
        cert_file = request.files["certificate"]
        if cert_file.filename == "":
            flash("Please upload your registration certificate.", "error")
            return render_template("ngo_register.html")
        
        # Check file extension
        allowed_extensions = {"pdf", "jpg", "jpeg", "png"}
        file_ext = cert_file.filename.rsplit(".", 1)[-1].lower() if "." in cert_file.filename else ""
        if file_ext not in allowed_extensions:
            flash("Certificate must be a PDF, JPG, JPEG, or PNG file.", "error")
            return render_template("ngo_register.html")
        
        # Check file size (already limited by MAX_CONTENT_LENGTH, but double-check)
        cert_file.seek(0, 2)  # Seek to end
        file_size = cert_file.tell()
        cert_file.seek(0)  # Reset to beginning
        if file_size > 5 * 1024 * 1024:
            flash("Certificate file must be smaller than 5MB.", "error")
            return render_template("ngo_register.html")
        
        # All validation passed - process registration
        try:
            # Generate NGO ID
            ngo_id = generate_ngo_id()
            
            # Save certificate with secure filename
            timestamp = int(time.time())
            secure_name = secure_filename(cert_file.filename)
            certificate_filename = f"{ngo_id}_{timestamp}_{secure_name}"
            cert_path = os.path.join(app.config["UPLOAD_FOLDER"], certificate_filename)
            cert_file.save(cert_path)
            
            # Hash password
            password_hash = generate_password_hash(password)
            
            # Generate email verification token
            verification_token = serializer.dumps(f["email"], salt="ngo-email-verify")
            
            # Insert into database
            db().execute("""INSERT INTO ngo_registrations 
                           (ngo_id, org_name, official_reg_number, registration_type, email, contact_number, 
                            address, password_hash, certificate_filename, verification_token, status, email_verified)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 0)""",
                        (ngo_id, f["org_name"], f["official_reg_number"], f["registration_type"], 
                         f["email"].lower(), f["contact_number"], f["address"], password_hash, 
                         certificate_filename, verification_token))
            db().commit()
            
            # Send verification email
            verification_url = url_for("ngo_verify_email", token=verification_token, _external=True)
            try:
                if app.config.get("MAIL_USERNAME"):
                    msg = Message(
                        subject="Verify Your Email - ReliefGrid NGO Registration",
                        recipients=[f["email"]],
                        html=render_template("email/ngo_verification.html",
                                           org_name=f["org_name"],
                                           verification_url=verification_url)
                    )
                    mail.send(msg)
            except Exception as e:
                print(f"Email sending failed: {str(e)}")
                # Continue even if email fails - user can check status
            
            # Store email in session for status page
            session["ngo_email"] = f["email"]
            
            flash("Registration submitted successfully! Please check your email to verify your address.", "success")
            return redirect(url_for("ngo_application_status"))
            
        except sqlite3.IntegrityError as e:
            # Duplicate email or registration number
            if "email" in str(e).lower():
                flash("An NGO with that email address is already registered.", "error")
            elif "official_reg_number" in str(e).lower():
                flash("An NGO with that registration number is already registered.", "error")
            else:
                flash("Registration failed. Please check your information and try again.", "error")
            return render_template("ngo_register.html")
    
    return render_template("ngo_register.html")


@app.route("/ngo/verify-email/<token>")
def ngo_verify_email(token):
    try:
        # Verify token (expires after 24 hours)
        email = serializer.loads(token, salt="ngo-email-verify", max_age=86400)
        
        # Update email_verified flag
        db().execute("UPDATE ngo_registrations SET email_verified=1 WHERE email=?", (email,))
        db().commit()
        
        flash("Email verified successfully! Your application is now pending admin review.", "success")
        return render_template("ngo_email_verified.html", email=email)
        
    except SignatureExpired:
        flash("This verification link has expired. Please contact support.", "error")
        return redirect(url_for("login"))
    except BadSignature:
        flash("Invalid verification link.", "error")
        return redirect(url_for("login"))


@app.route("/ngo/application-status")
def ngo_application_status():
    email = request.args.get("email") or session.get("ngo_email")
    
    if not email:
        flash("Please provide your email address to check your application status.", "error")
        return redirect(url_for("login"))
    
    ngo = q("SELECT * FROM ngo_registrations WHERE email=?", email.lower(), one=True)
    
    if not ngo:
        return render_template("ngo_application_status.html", ngo=None, email=email)
    
    # Check if user is logged in and this is their application
    is_logged_in = False
    if "user_id" in session:
        user = q("SELECT ngo_registration_id FROM users WHERE id=?", session["user_id"], one=True)
        if user and user["ngo_registration_id"] == ngo["id"]:
            is_logged_in = True
    
    return render_template("ngo_application_status.html", ngo=dict(ngo), email=email, is_logged_in=is_logged_in)


@app.route("/uploads/certificates/<filename>")
@login_required("admin")
def serve_certificate(filename):
    from flask import send_from_directory
    try:
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)
    except FileNotFoundError:
        flash("Certificate file not found.", "error")
        return redirect(url_for("admin_dashboard"))


# ---------- Admin NGO Verification ----------
@app.route("/admin/ngo-verifications")
@login_required("admin")
def admin_ngo_verifications():
    status_filter = request.args.get("status", "")
    
    # Build query with optional status filter
    sql = """SELECT ngo_registrations.*, users.name AS reviewer_name 
             FROM ngo_registrations 
             LEFT JOIN users ON users.id = ngo_registrations.reviewed_by"""
    
    if status_filter:
        sql += " WHERE status=?"
        rows = q(sql + " ORDER BY applied_at DESC", status_filter)
    else:
        rows = q(sql + " ORDER BY applied_at DESC")
    
    # Count pending applications
    pending_count = q("SELECT COUNT(*) c FROM ngo_registrations WHERE status='PENDING'", one=True)["c"]
    
    return render_template("admin_ngo_verifications.html", rows=rows, status=status_filter, pending_count=pending_count)


@app.route("/admin/ngo-verifications/<int:ngo_id>")
@login_required("admin")
def admin_ngo_verification_detail(ngo_id):
    # Query full NGO record with reviewer info
    ngo = q("""SELECT ngo_registrations.*, users.name AS reviewer_name 
               FROM ngo_registrations 
               LEFT JOIN users ON users.id = ngo_registrations.reviewed_by 
               WHERE ngo_registrations.id=?""", ngo_id, one=True)
    
    if not ngo:
        flash("NGO registration not found.", "error")
        return redirect(url_for("admin_ngo_verifications"))
    
    return render_template("admin_ngo_verification_detail.html", ngo=dict(ngo))


@app.route("/admin/ngo-verifications/<int:ngo_id>/approve", methods=["POST"])
@login_required("admin")
def approve_ngo(ngo_id):
    # Get NGO registration
    ngo = q("SELECT * FROM ngo_registrations WHERE id=? AND status='PENDING'", ngo_id, one=True)
    
    if not ngo:
        flash("NGO registration not found or already processed.", "error")
        return redirect(url_for("admin_ngo_verifications"))
    
    # Update ngo_registrations status
    db().execute("""UPDATE ngo_registrations 
                    SET status='APPROVED', reviewed_at=CURRENT_TIMESTAMP, reviewed_by=? 
                    WHERE id=?""", (session["user_id"], ngo_id))
    
    # Create user account with role='relief'
    db().execute("""INSERT INTO users (name, org_name, email, password_hash, role, ngo_registration_id)
                    VALUES (?, ?, ?, ?, 'relief', ?)""",
                (ngo["org_name"], ngo["org_name"], ngo["email"], ngo["password_hash"], ngo_id))
    
    db().commit()
    
    # Send approval email
    try:
        if app.config.get("MAIL_USERNAME"):
            msg = Message(
                subject="Your NGO Registration Approved - ReliefGrid",
                recipients=[ngo["email"]],
                html=render_template("email/ngo_approved.html", ngo=dict(ngo))
            )
            mail.send(msg)
    except Exception as e:
        print(f"Email sending failed: {str(e)}")
    
    flash("NGO approved and user account created successfully!", "success")
    return redirect(url_for("admin_ngo_verifications", status="PENDING"))


@app.route("/admin/ngo-verifications/<int:ngo_id>/reject", methods=["POST"])
@login_required("admin")
def reject_ngo(ngo_id):
    rejection_reason = request.form.get("rejection_reason", "").strip()
    
    if not rejection_reason:
        flash("Please provide a reason for rejection.", "error")
        return redirect(url_for("admin_ngo_verification_detail", ngo_id=ngo_id))
    
    # Get NGO registration
    ngo = q("SELECT * FROM ngo_registrations WHERE id=? AND status='PENDING'", ngo_id, one=True)
    
    if not ngo:
        flash("NGO registration not found or already processed.", "error")
        return redirect(url_for("admin_ngo_verifications"))
    
    # Update status with rejection reason
    db().execute("""UPDATE ngo_registrations 
                    SET status='REJECTED', rejection_reason=?, reviewed_at=CURRENT_TIMESTAMP, reviewed_by=? 
                    WHERE id=?""", (rejection_reason, session["user_id"], ngo_id))
    
    db().commit()
    
    # Send rejection email
    try:
        if app.config.get("MAIL_USERNAME"):
            msg = Message(
                subject="NGO Registration Update - ReliefGrid",
                recipients=[ngo["email"]],
                html=render_template("email/ngo_rejected.html", ngo=dict(ngo), rejection_reason=rejection_reason)
            )
            mail.send(msg)
    except Exception as e:
        print(f"Email sending failed: {str(e)}")
    
    flash("NGO application rejected.", "success")
    return redirect(url_for("admin_ngo_verification_detail", ngo_id=ngo_id))


if __name__ == "__main__":
    app.run(debug=True)
