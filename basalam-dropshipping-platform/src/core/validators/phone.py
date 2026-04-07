"""
Iranian Phone Number Validator
=============================
Validates Iranian mobile phone numbers (11 digits starting with 09)
"""
import re
from typing import Optional, Annotated

from pydantic import BeforeValidator


# Error messages
ERROR_INVALID_FORMAT = "Phone number must be exactly 11 digits starting with 09"
ERROR_INVALID_LENGTH = "Phone number must be exactly 11 digits"
ERROR_INVALID_PREFIX = "Phone number must start with 09"
ERROR_NON_NUMERIC = "Phone number must contain only digits"


def validate_iranian_phone(phone: Optional[str]) -> tuple[bool, str]:
    """
    Validate an Iranian phone number.
    
    Args:
        phone: The phone number string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        If valid, error_message is empty string
    """
    if not phone:
        return False, "Phone number is required"
    
    # Check for non-numeric characters (excluding the + prefix for international format)
    phone_clean = phone.replace('+98', '0').replace('+', '')
    
    if not phone_clean.isdigit():
        return False, ERROR_NON_NUMERIC
    
    # Check length
    if len(phone_clean) != 11:
        return False, ERROR_INVALID_LENGTH
    
    # Check prefix
    if not phone_clean.startswith('09'):
        return False, ERROR_INVALID_PREFIX
    
    return True, ""


def normalize_iranian_phone(phone: Optional[str]) -> Optional[str]:
    """
    Normalize an Iranian phone number to the standard format.
    
    Converts:
    - +98 912 345 6789 -> 09123456789
    - 0989123456789 -> 09123456789
    - 9123456789 -> 09123456789
    - 09123456789 -> 09123456789
    
    Args:
        phone: The phone number to normalize
        
    Returns:
        Normalized phone number or None if invalid
    """
    if not phone:
        return None
    
    # Remove all non-digit characters
    phone_clean = re.sub(r'\D', '', phone)
    
    # Handle +98 prefix (Iran country code)
    if phone_clean.startswith('98'):
        phone_clean = '0' + phone_clean[2:]
    
    # Validate the result
    is_valid, _ = validate_iranian_phone(phone_clean)
    if is_valid:
        return phone_clean
    
    return None


def _validate_phone_pydantic(value):
    """Pydantic v2 validator function for Iranian phone numbers."""
    if value is None:
        return value
    is_valid, error = validate_iranian_phone(value)
    if not is_valid:
        raise ValueError(error)
    return value


# Pydantic v2 compatible type: use as Annotated[str, IranianPhoneType]
IranianPhoneType = Annotated[str, BeforeValidator(_validate_phone_pydantic)]


# Legacy class kept for backward compatibility
class IranianPhoneValidator:
    """Pydantic v2 compatible validator for Iranian phone numbers.

    Usage with Pydantic v2:
        phone: Annotated[str, BeforeValidator(IranianPhoneValidator.validate)]
    """

    @classmethod
    def validate(cls, v):
        """Validate phone number"""
        if v is None:
            return v
        is_valid, error = validate_iranian_phone(v)
        if not is_valid:
            raise ValueError(error)
        return v


# Export for easy importing
__all__ = [
    'validate_iranian_phone',
    'normalize_iranian_phone',
    'IranianPhoneValidator',
    'IranianPhoneType',
    'ERROR_INVALID_FORMAT',
    'ERROR_INVALID_LENGTH',
    'ERROR_INVALID_PREFIX',
    'ERROR_NON_NUMERIC',
]
