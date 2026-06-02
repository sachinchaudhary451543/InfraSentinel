#!/usr/bin/env python
"""
Quick validation script to verify all fixes are in place
"""
import os
import sys
import sqlite3

def check_files():
    """Verify all modified files exist and compile"""
    print("=" * 60)
    print("CHECKING FILES")
    print("=" * 60)
    
    files_to_check = [
        ('web/models.py', 'Model definitions'),
        ('web/routes/api.py', 'API endpoints'),
        ('fix_employee_activity_schema.py', 'Database migration'),
    ]
    
    for filepath, description in files_to_check:
        if os.path.exists(filepath):
            print(f"✓ {filepath}: {description}")
            # Try to compile
            try:
                import py_compile
                py_compile.compile(filepath, doraise=True)
                print(f"  ✓ Python syntax valid")
            except Exception as e:
                print(f"  ✗ Syntax error: {e}")
                return False
        else:
            print(f"✗ {filepath}: NOT FOUND")
            return False
    
    return True


def check_database():
    """Verify database schema changes"""
    print("\n" + "=" * 60)
    print("CHECKING DATABASE SCHEMA")
    print("=" * 60)
    
    db_path = 'data/central.db'
    if not os.path.exists(db_path):
        print(f"✗ Database not found at {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check employee_activity columns
        cursor.execute("PRAGMA table_info(employee_activity)")
        columns = {row[1] for row in cursor.fetchall()}
        
        print(f"employee_activity columns: {sorted(columns)}")
        
        required_columns = {'tenant_id', 'employee_id', 'server_id', 'user', 'app', 'window_title', 'idle_time', 'timestamp', 'id'}
        missing = required_columns - columns
        
        if missing:
            print(f"✗ Missing columns: {missing}")
            return False
        else:
            print(f"✓ All required columns present")
        
        # Check for indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='employee_activity'")
        indexes = {row[0] for row in cursor.fetchall()}
        print(f"Indexes: {indexes}")
        
        required_indexes = {
            'idx_employee_activity_tenant_server_user',
            'idx_employee_activity_tenant_timestamp', 
            'idx_employee_activity_employee_timestamp'
        }
        missing_indexes = required_indexes - indexes
        
        if missing_indexes:
            print(f"⚠ Missing indexes (not critical): {missing_indexes}")
        else:
            print(f"✓ All performance indexes present")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Database error: {e}")
        return False


def check_api_code():
    """Verify API code changes"""
    print("\n" + "=" * 60)
    print("CHECKING API CODE CHANGES")
    print("=" * 60)
    
    try:
        with open('web/routes/api.py', 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        checks = [
            ('_as_local exception handling', 'except Exception as e:' in content and 'logger.warning(f"Timezone conversion' in content),
            ('Activity tenant_id assignment', 'activity.tenant_id = server.tenant_id' in content),
            ('Activity employee_id linking', 'activity.employee_id = assignment.employee_id' in content),
            ('Screenshots dates exception handling', 'except Exception as e:' in content and 'logger.warning(f"Failed to process screenshot' in content),
        ]
        
        all_ok = True
        for check_name, check_result in checks:
            status = "✓" if check_result else "✗"
            print(f"{status} {check_name}")
            all_ok = all_ok and check_result
        
        return all_ok
        
    except Exception as e:
        print(f"✗ Error reading api.py: {e}")
        return False


def check_models():
    """Verify model changes"""
    print("\n" + "=" * 60)
    print("CHECKING MODEL DEFINITIONS")
    print("=" * 60)
    
    try:
        with open('web/models.py', 'r') as f:
            content = f.read()
        
        # Find EmployeeActivity class
        if 'class EmployeeActivity' not in content:
            print("✗ EmployeeActivity class not found")
            return False
        
        # Check for new fields
        in_class = False
        checks = [
            ('tenant_id field', 'tenant_id = db.Column'),
            ('employee_id field', 'employee_id = db.Column'),
            ('Indexes definition', '__table_args__'),
        ]
        
        all_ok = True
        for check_name, check_pattern in checks:
            if check_pattern in content:
                print(f"✓ {check_name}")
            else:
                print(f"✗ {check_name}")
                all_ok = False
        
        return all_ok
        
    except Exception as e:
        print(f"✗ Error reading models.py: {e}")
        return False


if __name__ == '__main__':
    print("\n🔍 ServerMonitor Production Fixes Validation\n")
    
    results = []
    results.append(('Files Check', check_files()))
    results.append(('Database Schema', check_database()))
    results.append(('API Code', check_api_code()))
    results.append(('Model Definitions', check_models()))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for check_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {check_name}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n✅ All fixes verified successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some checks failed. Review the output above.")
        sys.exit(1)
