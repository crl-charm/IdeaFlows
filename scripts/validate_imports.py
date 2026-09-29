#!/usr/bin/env python
"""
Import Validation Script
Runs all critical imports to catch errors before production deployment.
Run this in CI/CD pipeline to ensure all imports are correct.
"""

import sys
import traceback
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_model_imports():
    """Test that all models can be imported correctly."""
    print("Testing model imports...")
    try:
        from app.models import (
            User, SpaceType, SpacePriceHistory, CustomerSession,
            MenuItem, Order, OrderItem, Transaction, CheckoutVoidRequest, BoardroomBooking,
            LoungeBooking, StaffAttendance, InventoryItem, InventoryLog,
            Receivable, Expense, StaffPerformanceLog, DailySalesReport,
            SoftBalanceEntry, BaseModel, UserRole,
            FinanceBudget, FinanceTransaction
        )
        print("[OK] All models imported successfully")
        return True
    except ImportError as e:
        print(f"[FAIL] Model import failed: {e}")
        traceback.print_exc()
        return False

def test_repository_imports():
    """Test that all repositories can be imported."""
    print("\nTesting repository imports...")
    repositories = [
        'app.repositories.admin_repository',
        'app.repositories.analytics_repository',
        'app.repositories.booking_repository',
        'app.repositories.expense_repository',
        'app.repositories.inventory_repository',
        'app.repositories.menu_repository',
        'app.repositories.order_repository',
        'app.repositories.receivable_repository',
        'app.repositories.sales_repository',
        'app.repositories.session_repository',
        'app.repositories.staff_repository',
    ]
    
    all_passed = True
    for repo_path in repositories:
        try:
            __import__(repo_path)
            print(f"  [OK] {repo_path}")
        except ImportError as e:
            print(f"  [FAIL] {repo_path}: {e}")
            traceback.print_exc()
            all_passed = False
    
    return all_passed

def test_service_imports():
    """Test that all services can be imported."""
    print("\nTesting service imports...")
    services = [
        'app.services.admin_service',
        'app.services.analytics_oop_service',
        'app.services.analytics_service',
        'app.services.daily_balance_export_service',
        'app.services.booking_service',
        'app.services.expense_service',
        'app.services.inventory_service',
        'app.services.menu_service',
        'app.services.order_service',
        'app.services.receivable_service',
        'app.services.sales_service',
        'app.services.session_service',
        'app.services.staff_performance_service',
    ]
    
    all_passed = True
    for service_path in services:
        try:
            __import__(service_path)
            print(f"  [OK] {service_path}")
        except ImportError as e:
            print(f"  [FAIL] {service_path}: {e}")
            traceback.print_exc()
            all_passed = False
    
    return all_passed

def test_route_imports():
    """Test that all routes can be imported."""
    print("\nTesting route imports...")
    try:
        from app import create_app
        app = create_app()
        print("[OK] App created successfully (all routes imported)")
        return True
    except ImportError as e:
        print(f"[FAIL] Route import failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all validation tests."""
    print("=" * 60)
    print("IMPORT VALIDATION - Pre-Production Check")
    print("=" * 60)
    
    results = {
        'Models': test_model_imports(),
        'Repositories': test_repository_imports(),
        'Services': test_service_imports(),
        'Routes': test_route_imports(),
    }
    
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{test_name:.<40} {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n[OK] All imports validated successfully - Safe for deployment")
        return 0
    else:
        print("\n[FAIL] Import validation failed - Do NOT deploy to production")
        return 1

if __name__ == '__main__':
    sys.exit(main())
