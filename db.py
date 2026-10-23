import os
import sqlite3
from flask import g
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "reliefgrid.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, org_name TEXT,
    email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','relief'))
);
CREATE TABLE IF NOT EXISTS disasters (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Active', created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY, disaster_id INTEGER REFERENCES disasters(id),
    name TEXT NOT NULL, type TEXT NOT NULL, severity TEXT NOT NULL,
    people_affected INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Active',
    lat REAL, lng REAL
);
CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, unit TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    low_threshold INTEGER NOT NULL DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
    location_id INTEGER NOT NULL REFERENCES locations(id),
    resource_id INTEGER NOT NULL REFERENCES resources(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0), people_affected INTEGER NOT NULL,
    urgency TEXT NOT NULL, description TEXT,
    status TEXT NOT NULL DEFAULT 'Pending', allocated_qty INTEGER NOT NULL DEFAULT 0,
    total_allocated INTEGER NOT NULL DEFAULT 0,
    total_dispatched INTEGER NOT NULL DEFAULT 0,
    total_received INTEGER NOT NULL DEFAULT 0,
    decision_note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES requests(id),
    quantity INTEGER NOT NULL, origin TEXT NOT NULL DEFAULT 'Main Depot',
    status TEXT NOT NULL DEFAULT 'Assigned', confirmed INTEGER NOT NULL DEFAULT 0,
    issue TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),  -- NULL = all admins
    kind TEXT NOT NULL DEFAULT 'info', message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        seed(conn)
    conn.commit()
    conn.close()


def seed(c):
    h = generate_password_hash
    c.executemany("INSERT INTO users(name,org_name,email,password_hash,role) VALUES (?,?,?,?,?)", [
        ("Admin", "ReliefGrid HQ", "admin@reliefgrid.org", h("admin123"), "admin"),
        ("Riverside Coordinator", "Riverside Camp NGO", "riverside@ngo.org", h("relief123"), "relief"),
        ("East Coordinator", "East Village Relief", "east@ngo.org", h("relief123"), "relief"),
        ("West Coordinator", "West Village Aid", "west@ngo.org", h("relief123"), "relief"),
    ])
    c.execute("INSERT INTO disasters(name,type) VALUES ('Monsoon Flood 2026','Flood')")
    c.executemany("INSERT INTO locations(disaster_id,name,type,severity,people_affected,status,lat,lng) VALUES (1,?,?,?,?,?,?,?)", [
        ("East Village", "Village", "Critical", 300, "Active", 9.62, 76.42),
        ("North Village", "Village", "Critical", 220, "Active", 9.72, 76.36),
        ("West Village", "Village", "High", 180, "Active", 9.60, 76.30),
        ("South Village", "Village", "Medium", 120, "Active", 9.50, 76.40),
        ("Riverside Camp", "Relief Camp", "High", 90, "Active", 9.66, 76.38),
        ("Hilltop Shelter", "Shelter", "Low", 60, "Stabilizing", 9.70, 76.46),
        ("Forest Camp", "Relief Camp", "Low", 40, "Stabilizing", 9.55, 76.34),
        ("Lakeside Shelter", "Shelter", "Low", 30, "Stabilizing", 9.58, 76.48),
    ])
    c.executemany("INSERT INTO resources(name,unit,quantity,low_threshold) VALUES (?,?,?,?)", [
        ("Drinking Water", "Units", 150, 50), ("Food Packets", "Packets", 200, 60),
        ("Medicines", "Boxes", 80, 30), ("Blankets", "Pieces", 100, 40), ("Tents", "Pieces", 25, 10),
    ])
    # user, location, resource, qty, people, urgency
    c.executemany("INSERT INTO requests(user_id,location_id,resource_id,quantity,people_affected,urgency) VALUES (?,?,?,?,?,?)", [
        (3, 1, 1, 100, 300, "Critical"), (2, 5, 1, 80, 90, "High"), (4, 3, 1, 60, 180, "Medium"),
        (3, 1, 2, 80, 300, "Critical"), (4, 3, 2, 60, 180, "High"),
        (2, 5, 3, 60, 90, "High"), (3, 1, 3, 50, 300, "Critical"),
        (2, 5, 4, 40, 90, "Medium"), (4, 3, 5, 40, 180, "Medium"),
    ])
