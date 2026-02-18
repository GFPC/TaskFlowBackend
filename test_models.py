#!/usr/bin/env python3
"""Test script to verify models import correctly"""
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.db import User, UserRole
from core.db.main import BaseModel

print("All models imported successfully!")
print(f"User class: {User}")
print(f"UserRole class: {UserRole}")
print(f"BaseModel class: {BaseModel}")

# Test creating a user instance (without saving to database)
try:
    user = User(first_name="Test", last_name="User", username="testuser")
    print(f"User instance created: {user.full_name}")
except Exception as e:
    print(f"Error creating user: {e}")
