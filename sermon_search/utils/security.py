"""
Security utilities for the sermon search application.

This module contains functions for IP ban management and API authentication.
"""

import os
import uuid
import datetime
from typing import Tuple, Optional
from flask import request, current_app, make_response, Response
from sermon_search.database.models import get_db


def get_client_ip() -> str:
    """
    Extract the real client IP behind a reverse proxy.
    
    If request.remote_addr is a 10.x internal IP, it falls back to the X-Forwarded-For header.
    
    Returns:
        str: The client's IP address.
    """
    remote_ip = request.remote_addr
    # Check if remote_addr is an internal (10.x) IP
    if remote_ip.startswith("10."):
        # Get the X-Forwarded-For header value (if available)
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # The first IP in the X-Forwarded-For header is the original client IP
            return xff.split(",")[0].strip()
    return remote_ip


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
            current_time = int(datetime.datetime.now(datetime.UTC).timestamp())
            if banned_until > current_time:
                return True
            db.execute("UPDATE ip_bans SET failed_attempts = 0, banned_until = NULL WHERE ip_address = ?", (ip,))
            db.commit()
    return False


def get_or_create_visitor_id() -> str:
    """
    Get the visitor ID from cookie or create a new one.
    
    Returns:
        str: A unique visitor ID
    """
    visitor_id = request.cookies.get('visitor_id')
    
    if not visitor_id:
        # Generate a new visitor ID if none exists
        visitor_id = str(uuid.uuid4())
        current_app.logger.debug(f"Generated new visitor ID: {visitor_id}")
    
    return visitor_id


def set_visitor_id_cookie(response: Response) -> Response:
    """
    Set or update the visitor ID cookie on the response.
    
    Args:
        response: The Flask response object
        
    Returns:
        Response: The updated response with the visitor ID cookie
    """
    visitor_id = get_or_create_visitor_id()
    
    # Set the cookie to expire in 2 years
    expires = datetime.datetime.now() + datetime.timedelta(days=365*2)
    
    response.set_cookie(
        'visitor_id',
        visitor_id,
        expires=expires,
        httponly=True,
        samesite='Lax',
        path='/'
    )
    
    return response


def verify_api_token(f):
    """
    Decorator to verify the API token from request headers.
    
    Args:
        f: The function to decorate
        
    Returns:
        The decorated function that checks for a valid API token
    """
    from functools import wraps
    from flask import jsonify
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip = get_client_ip()
        db = get_db()
        
        if is_ip_banned(ip):
            return jsonify({
                "status": "error",
                "message": "Too many failed attempts. Try again later."
            }), 429
        
        api_token = request.headers.get("Authorization")
        if api_token and api_token.startswith("Bearer "):
            api_token = api_token[7:]  # Remove 'Bearer ' prefix
        else:
            api_token = request.headers.get("X-API-Token")  # Fallback to X-API-Token for backward compatibility
            
        expected_token = os.environ.get("SERMON_API_TOKEN", "")
        
        if not api_token or api_token != expected_token:
            # Track failed attempts
            cur = db.execute("SELECT failed_attempts FROM ip_bans WHERE ip_address = ?", (ip,))
            row = cur.fetchone()
            attempts = row["failed_attempts"] + 1 if row else 1
            
            if attempts >= 3:
                # Ban for 24 hours
                banned_until = int(datetime.datetime.now(datetime.UTC).timestamp()) + 86400
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
            return jsonify({
                "status": "error",
                "message": "Unauthorized"
            }), 401
        
        # Clear any previous failed attempts
        db.execute("DELETE FROM ip_bans WHERE ip_address = ?", (ip,))
        db.commit()
        return f(*args, **kwargs)
    
    return decorated_function
