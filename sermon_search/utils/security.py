"""
Security utilities for the sermon search application.

This module contains functions for IP ban management and API authentication.
"""

import os
import datetime
from typing import Tuple, Optional
from flask import request, current_app
from sermon_search.database.models import get_db


def get_client_ip() -> str:
    """
    Extract the real client IP behind a reverse proxy.
    
    Returns:
        str: The client's IP address
    """
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr


def is_ip_banned(ip: str) -> bool:
    """
    Check if the IP is banned and reset ban if expired.
    
    Args:
        ip: The IP address to check
        
    Returns:
        bool: True if the IP is currently banned
    """
    db = get_db()
    cur = db.execute("SELECT failed_attempts, banned_until FROM ip_bans WHERE ip_address = ?", (ip,))
    row = cur.fetchone()
    if row:
        failed_attempts, banned_until = row["failed_attempts"], row["banned_until"]
        if banned_until:
            current_time = int(datetime.datetime.utcnow().timestamp())
            if banned_until > current_time:
                return True
            db.execute("UPDATE ip_bans SET failed_attempts = 0, banned_until = NULL WHERE ip_address = ?", (ip,))
            db.commit()
    return False


def verify_api_token() -> Tuple[bool, Optional[str]]:
    """
    Verify the API token from request headers.
    
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    ip = get_client_ip()
    db = get_db()
    
    if is_ip_banned(ip):
        return False, "Too many failed attempts. Try again later."
    
    api_token = request.headers.get("X-API-Token")
    expected_token = os.environ.get("SERMON_API_TOKEN", "")
    
    if not api_token or api_token != expected_token:
        # Track failed attempts
        cur = db.execute("SELECT failed_attempts FROM ip_bans WHERE ip_address = ?", (ip,))
        row = cur.fetchone()
        attempts = row["failed_attempts"] + 1 if row else 1
        
        if attempts >= 3:
            # Ban for 24 hours
            banned_until = int(datetime.datetime.utcnow().timestamp()) + 86400
            db.execute(
                "REPLACE INTO ip_bans (ip_address, failed_attempts, banned_until) VALUES (?, ?, ?)",
                (ip, attempts, banned_until)
            )
        else:
            db.execute(
                "REPLACE INTO ip_bans (ip_address, failed_attempts, banned_until) VALUES (?, ?, NULL)",
                (ip, attempts)
            )
        db.commit()
        return False, "Unauthorized"
    
    # Clear any previous failed attempts
    db.execute("DELETE FROM ip_bans WHERE ip_address = ?", (ip,))
    db.commit()
    return True, None