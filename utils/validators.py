"""
validators — Input validation functions for Bharat AI OPD App.
PIN, phone, patient name, email validation with Tuple[bool, str] return.
"""

import re
from typing import Tuple


def validate_pin(pin: str) -> Tuple[bool, str]:
    """Validate PIN: must be 4-8 digits."""
    pin = pin.strip()
    if not pin:
        return False, "PIN is required"
    if not pin.isdigit():
        return False, "PIN must contain only digits"
    if len(pin) < 4 or len(pin) > 8:
        return False, "PIN must be 4-8 digits"
    return True, ""


def validate_phone(phone: str) -> Tuple[bool, str]:
    """Validate phone number (optional field)."""
    phone = phone.strip()
    if not phone:
        return True, ""  # phone is optional
    if not phone.isdigit():
        return False, "Phone must contain only digits"
    if len(phone) != 10:
        return False, "Phone must be exactly 10 digits"
    return True, ""


def validate_patient_name(name: str) -> Tuple[bool, str]:
    """Validate patient name."""
    name = name.strip()
    if not name:
        return False, "Patient name is required"
    if len(name) < 2:
        return False, "Name too short"
    return True, ""


def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email address (optional field)."""
    if not email:
        return True, ""  # email is optional
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(pattern, email):
        return True, ""
    return False, "Invalid email format"
