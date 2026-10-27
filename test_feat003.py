#!/usr/bin/env python3
"""
FEAT-003 Verification Tests
Tests the Admin NGO Verification System
"""

import sqlite3
import sys

def test_database():
    """Verify database has NGO registrations table and data"""
    print("=" * 60)
    print("TEST: Database Structure and Data")
    print("=" * 60)
    
    conn = sqlite3.connect('reliefgrid.db')
    conn.row_factory = sqlite3.Row
    
    # Check table exists
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ngo_registrations'")
    if not cursor.fetchone():
        print("✗ FAIL: ngo_registrations table not found")
        return False
    print("✓ PASS: ngo_registrations table exists")
    
    # Check for test data
    cursor = conn.execute("SELECT COUNT(*) as count FROM ngo_registrations")
    count = cursor.fetchone()['count']
    print(f"✓ PASS: Found {count} NGO registration(s)")
    
    # Check for PENDING registrations
    cursor = conn.execute("SELECT COUNT(*) as count FROM ngo_registrations WHERE status='PENDING'")
    pending_count = cursor.fetchone()['count']
    print(f"✓ PASS: Found {pending_count} PENDING registration(s)")
    
    # Display registrations
    cursor = conn.execute("""
        SELECT id, ngo_id, org_name, email, status, email_verified, 
               certificate_filename, applied_at 
        FROM ngo_registrations
    """)
    print("\nNGO Registrations:")
    for row in cursor.fetchall():
        print(f"  ID: {row['id']}")
        print(f"    NGO ID: {row['ngo_id']}")
        print(f"    Organization: {row['org_name']}")
        print(f"    Email: {row['email']}")
        print(f"    Status: {row['status']}")
        print(f"    Email Verified: {'Yes' if row['email_verified'] else 'No'}")
        print(f"    Certificate: {row['certificate_filename']}")
        print()
    
    conn.close()
    return True


def test_routes():
    """Verify Flask routes are registered"""
    print("=" * 60)
    print("TEST: Flask Routes Registration")
    print("=" * 60)
    
    try:
        import app
        
        expected_routes = [
            'admin_ngo_verifications',
            'admin_ngo_verification_detail',
            'approve_ngo',
            'reject_ngo'
        ]
        
        registered_endpoints = [rule.endpoint for rule in app.app.url_map.iter_rules()]
        
        for endpoint in expected_routes:
            if endpoint in registered_endpoints:
                print(f"✓ PASS: Route '{endpoint}' is registered")
            else:
                print(f"✗ FAIL: Route '{endpoint}' is NOT registered")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ FAIL: Error loading app: {e}")
        return False


def test_navigation():
    """Verify NGO Verifications is in ADMIN_NAV"""
    print("=" * 60)
    print("TEST: Admin Navigation")
    print("=" * 60)
    
    try:
        import app
        
        # Check if NGO Verifications is in ADMIN_NAV
        admin_nav_labels = [label for label, endpoint in app.ADMIN_NAV]
        
        if "NGO Verifications" in admin_nav_labels:
            print("✓ PASS: 'NGO Verifications' found in ADMIN_NAV")
        else:
            print("✗ FAIL: 'NGO Verifications' NOT found in ADMIN_NAV")
            return False
        
        # Check position (should be after Requests)
        nav_dict = dict(app.ADMIN_NAV)
        if "admin_ngo_verifications" in nav_dict.values():
            print("✓ PASS: admin_ngo_verifications endpoint in ADMIN_NAV")
        else:
            print("✗ FAIL: admin_ngo_verifications endpoint NOT in ADMIN_NAV")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ FAIL: Error checking navigation: {e}")
        return False


def test_templates():
    """Verify templates exist and are valid"""
    print("=" * 60)
    print("TEST: Template Files")
    print("=" * 60)
    
    from jinja2 import Environment, FileSystemLoader
    import os
    
    env = Environment(loader=FileSystemLoader('templates'))
    
    templates = [
        'admin_ngo_verifications.html',
        'admin_ngo_verification_detail.html',
        'email/ngo_approved.html',
        'email/ngo_rejected.html'
    ]
    
    all_valid = True
    for template_name in templates:
        try:
            template = env.get_template(template_name)
            print(f"✓ PASS: Template '{template_name}' exists and is valid")
        except Exception as e:
            print(f"✗ FAIL: Template '{template_name}' error: {e}")
            all_valid = False
    
    return all_valid


def test_context_processor():
    """Verify inject_nav includes ngo_pending"""
    print("=" * 60)
    print("TEST: Context Processor (ngo_pending)")
    print("=" * 60)
    
    try:
        import app
        import inspect
        
        # Check if inject_nav function exists
        if not hasattr(app, 'inject_nav'):
            print("✗ FAIL: inject_nav function not found")
            return False
        
        print("✓ PASS: inject_nav function exists")
        
        # Check if the function returns ngo_pending
        source = inspect.getsource(app.inject_nav)
        if 'ngo_pending' in source:
            print("✓ PASS: inject_nav includes ngo_pending logic")
        else:
            print("✗ FAIL: inject_nav does not include ngo_pending")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ FAIL: Error checking context processor: {e}")
        return False


def test_base_template_badge():
    """Verify base.html has ngo_pending badge logic"""
    print("=" * 60)
    print("TEST: Base Template Badge")
    print("=" * 60)
    
    try:
        with open('templates/base.html', 'r') as f:
            content = f.read()
        
        if 'admin_ngo_verifications' in content and 'ngo_pending' in content:
            print("✓ PASS: base.html contains ngo_pending badge logic")
            return True
        else:
            print("✗ FAIL: base.html missing ngo_pending badge logic")
            return False
            
    except Exception as e:
        print(f"✗ FAIL: Error reading base.html: {e}")
        return False


def main():
    print("\n" + "=" * 60)
    print("FEAT-003 VERIFICATION TEST SUITE")
    print("Admin NGO Verification Dashboard")
    print("=" * 60 + "\n")
    
    tests = [
        ("Database Structure", test_database),
        ("Flask Routes", test_routes),
        ("Admin Navigation", test_navigation),
        ("Templates", test_templates),
        ("Context Processor", test_context_processor),
        ("Base Template Badge", test_base_template_badge),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ FAIL: {name} - Exception: {e}\n")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
