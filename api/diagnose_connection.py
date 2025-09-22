#!/usr/bin/env python3
"""
Connection diagnostics script for delegation program leaderboard API
Run this script to troubleshoot database connectivity issues

Usage:
    python diagnose_connection.py
    
Environment Variables:
    DEBUG=true - Enable verbose debug output
    LOGGING_LEVEL=DEBUG - Set logging level
"""

import os
import sys
import socket
import psycopg2
from datetime import datetime

# Add the minanet_app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'minanet_app'))

from config import BaseConfig
from logger_util import logger
from db_health import DatabaseHealthChecker


def test_network_connectivity():
    """Test basic network connectivity to database host"""
    print(f"\n=== Network Connectivity Test ===")
    print(f"Target: {BaseConfig.SNARK_HOST}:{BaseConfig.SNARK_PORT}")
    
    try:
        # Test TCP connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(BaseConfig.DB_CONNECTION_TIMEOUT)
        
        result = sock.connect_ex((BaseConfig.SNARK_HOST, BaseConfig.SNARK_PORT))
        sock.close()
        
        if result == 0:
            print(f"✅ TCP connection successful to {BaseConfig.SNARK_HOST}:{BaseConfig.SNARK_PORT}")
            return True
        else:
            print(f"❌ TCP connection failed to {BaseConfig.SNARK_HOST}:{BaseConfig.SNARK_PORT}")
            print(f"   Error code: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Network connectivity test failed: {e}")
        return False


def test_dns_resolution():
    """Test DNS resolution for database host"""
    print(f"\n=== DNS Resolution Test ===")
    print(f"Hostname: {BaseConfig.SNARK_HOST}")
    
    try:
        ip_address = socket.gethostbyname(BaseConfig.SNARK_HOST)
        print(f"✅ DNS resolution successful: {BaseConfig.SNARK_HOST} -> {ip_address}")
        return True
    except Exception as e:
        print(f"❌ DNS resolution failed: {e}")
        return False


def test_database_authentication():
    """Test database authentication with provided credentials"""
    print(f"\n=== Database Authentication Test ===")
    print(f"Database: {BaseConfig.SNARK_DB}")
    print(f"Username: {BaseConfig.SNARK_USER}")
    print(f"Password: {'*' * len(BaseConfig.SNARK_PASSWORD)} ({len(BaseConfig.SNARK_PASSWORD)} chars)")
    
    try:
        connection = psycopg2.connect(
            host=BaseConfig.SNARK_HOST,
            port=BaseConfig.SNARK_PORT,
            database=BaseConfig.SNARK_DB,
            user=BaseConfig.SNARK_USER,
            password=BaseConfig.SNARK_PASSWORD,
            connect_timeout=BaseConfig.DB_CONNECTION_TIMEOUT
        )
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT version();")
            db_version = cursor.fetchone()[0]
            print(f"✅ Database authentication successful")
            print(f"   PostgreSQL version: {db_version}")
            
        connection.close()
        return True
        
    except psycopg2.OperationalError as e:
        print(f"❌ Database authentication failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected database error: {e}")
        return False


def run_comprehensive_diagnostics():
    """Run all diagnostic tests"""
    print(f"{'='*60}")
    print(f"DELEGATION PROGRAM LEADERBOARD - CONNECTION DIAGNOSTICS")
    print(f"{'='*60}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Debug Mode: {BaseConfig.DEBUG}")
    print(f"Logging Level: {BaseConfig.LOGGING_LEVEL}")
    
    # Configuration overview
    print(f"\n=== Configuration Overview ===")
    print(f"Database Host: {BaseConfig.SNARK_HOST}")
    print(f"Database Port: {BaseConfig.SNARK_PORT}")
    print(f"Database Name: {BaseConfig.SNARK_DB}")
    print(f"Database User: {BaseConfig.SNARK_USER}")
    print(f"Connection Timeout: {BaseConfig.DB_CONNECTION_TIMEOUT}s")
    print(f"Retry Attempts: {BaseConfig.DB_RETRY_ATTEMPTS}")
    
    # Run tests
    tests = [
        ("DNS Resolution", test_dns_resolution),
        ("Network Connectivity", test_network_connectivity),
        ("Database Authentication", test_database_authentication),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{'='*60}")
    print(f"DIAGNOSTIC RESULTS SUMMARY")
    print(f"{'='*60}")
    
    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        icon = "✅" if result else "❌"
        print(f"{icon} {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(results)} tests")
    
    if passed == len(results):
        print(f"🎉 All tests passed! Database connectivity should be working.")
    else:
        print(f"⚠️  Some tests failed. Please check the errors above.")
        
    print(f"\n{'='*60}")
    
    return passed == len(results)


if __name__ == "__main__":
    success = run_comprehensive_diagnostics()
    sys.exit(0 if success else 1)