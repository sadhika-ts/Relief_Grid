#!/usr/bin/env python3
"""Test NGO registration feature (FEAT-002)"""

import os
import sys
import sqlite3
from io import BytesIO

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, generate_ngo_id

def test_generate_ngo_id():
    """Test NGO ID generation"""
    with app.app_context():
        ngo_id = generate_ngo_id()
        print(f"✓ Generated NGO ID: {ngo_id}")
        assert ngo_id.startswith("NGO-"), "NGO ID should start with 'NGO-'"
        assert len(ngo_id) == 8, "NGO ID should be 8 characters (NGO-NNNN)"

def test_routes():
    """Test that all NGO routes are registered"""
    routes = {rule.endpoint: rule.rule for rule in app.url_map.iter_rules()}
    
    required_routes = [
        ('ngo_register', '/ngo/register'),
        ('ngo_verify_email', '/ngo/verify-email/<token>'),
        ('ngo_application_status', '/ngo/application-status'),
        ('serve_certificate', '/uploads/certificates/<filename>'),
    ]
    
    for endpoint, path in required_routes:
        assert endpoint in routes, f"Route {endpoint} not found"
        print(f"✓ Route {endpoint}: {routes[endpoint]}")

def test_templates():
    """Test that all templates exist and can be loaded"""
    from jinja2 import Environment, FileSystemLoader
    
    env = Environment(loader=FileSystemLoader('templates'))
    
    templates = [
        'ngo_register.html',
        'ngo_application_status.html',
        'ngo_email_verified.html',
        'email/ngo_verification.html'
    ]
    
    for tmpl in templates:
        env.get_template(tmpl)
        print(f"✓ Template {tmpl} exists and is valid")

def test_database_schema():
    """Test that ngo_registrations table has required columns"""
    conn = sqlite3.connect('reliefgrid.db')
    cursor = conn.execute("PRAGMA table_info(ngo_registrations)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    required_columns = [
        'id', 'ngo_id', 'org_name', 'official_reg_number', 'registration_type',
        'email', 'contact_number', 'address', 'password_hash', 'certificate_filename',
        'email_verified', 'verification_token', 'status', 'rejection_reason',
        'applied_at', 'reviewed_at', 'reviewed_by'
    ]
    
    for col in required_columns:
        assert col in columns, f"Column {col} not found in ngo_registrations table"
    
    print(f"✓ Database schema has all {len(required_columns)} required columns")
    conn.close()

def test_uploads_directory():
    """Test that uploads/certificates directory exists"""
    upload_dir = os.path.join(os.path.dirname(__file__), 'uploads', 'certificates')
    assert os.path.exists(upload_dir), "uploads/certificates directory not found"
    assert os.path.isdir(upload_dir), "uploads/certificates is not a directory"
    print(f"✓ Upload directory exists: {upload_dir}")

def test_config():
    """Test Flask configuration"""
    assert app.config.get('MAX_CONTENT_LENGTH') == 5 * 1024 * 1024, "MAX_CONTENT_LENGTH should be 5MB"
    assert app.config.get('UPLOAD_FOLDER') == 'uploads/certificates', "UPLOAD_FOLDER not configured correctly"
    print("✓ Flask configuration correct")

def test_registration_form_validation():
    """Test registration form with test client"""
    with app.test_client() as client:
        # Test GET request
        response = client.get('/ngo/register')
        assert response.status_code == 200, "GET /ngo/register should return 200"
        assert b'NGO Registration' in response.data or b'ngo' in response.data.lower(), "Page should mention NGO"
        print("✓ GET /ngo/register returns valid page")
        
        # Test POST with missing fields
        response = client.post('/ngo/register', data={})
        assert response.status_code == 200, "POST with empty data should return form with errors"
        print("✓ POST /ngo/register validates required fields")

def test_application_status_route():
    """Test application status page"""
    with app.test_client() as client:
        # Test without email
        response = client.get('/ngo/application-status')
        assert response.status_code in [200, 302], "Should handle missing email gracefully"
        print("✓ GET /ngo/application-status handles missing email")
        
        # Test with non-existent email
        response = client.get('/ngo/application-status?email=nonexistent@test.com')
        assert response.status_code == 200, "Should show 'not found' for non-existent email"
        print("✓ GET /ngo/application-status handles non-existent email")

def test_login_page_has_ngo_link():
    """Test that login page has NGO registration link"""
    with app.test_client() as client:
        response = client.get('/login')
        assert response.status_code == 200, "Login page should load"
        assert b'ngo' in response.data.lower(), "Login page should mention NGO registration"
        print("✓ Login page includes NGO registration link")

if __name__ == '__main__':
    print("=" * 60)
    print("Testing FEAT-002: NGO Registration Frontend and Backend")
    print("=" * 60)
    
    tests = [
        test_config,
        test_uploads_directory,
        test_database_schema,
        test_generate_ngo_id,
        test_routes,
        test_templates,
        test_registration_form_validation,
        test_application_status_route,
        test_login_page_has_ngo_link,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            print(f"\n{test.__name__}:")
            test()
            passed += 1
        except Exception as e:
            print(f"✗ FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Tests: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 60)
    
    sys.exit(0 if failed == 0 else 1)
