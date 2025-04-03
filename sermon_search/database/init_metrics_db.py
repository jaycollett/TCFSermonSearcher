"""
Metrics Database Initialization Script

This script initializes the SQLite database, configurable via the METRICS_DATABASE environment variable
(or Flask configuration), which stores logging and performance data.
It creates the following two tables:
  - Search_History: Stores search queries entered on the site along with the IP address and timestamp.
  - Sermon_Access: Records sermon access events with the sermon GUID, IP address, and timestamp.
"""

import os
import sqlite3
import datetime
from flask import g, current_app

def get_metrics_db() -> sqlite3.Connection:
    """
    Get a connection to the metrics SQLite database.

    Returns:
        sqlite3.Connection: Metrics database connection with row factory set.
    """
    db = getattr(g, '_metrics_db', None)
    if db is None:
        db_path = current_app.config.get('METRICS_DATABASE')
        if not db_path:
            # Default path if not specified
            db_path = os.path.join(
                os.path.dirname(current_app.config.get('DATABASE', './data/sermons.db')),
                'metrics.db'
            )
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        
        db = g._metrics_db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
    return db

def _check_column_exists(conn, table, column):
    """
    Check if a column exists in a table.
    
    Args:
        conn: SQLite connection
        table: Table name
        column: Column name
        
    Returns:
        bool: True if column exists, False otherwise
    """
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]
    return column in columns


def _migrate_search_history_table(conn):
    """
    Migrate the Search_History table schema if needed.
    
    Args:
        conn: SQLite connection
    """
    # Check if category_filters column exists
    if not _check_column_exists(conn, "Search_History", "category_filters"):
        try:
            current_app.logger.info("Adding category_filters column to Search_History table")
            conn.execute("ALTER TABLE Search_History ADD COLUMN category_filters TEXT")
            conn.commit()
            current_app.logger.info("Successfully added category_filters column")
        except sqlite3.Error as e:
            current_app.logger.error(f"Error adding category_filters column: {e}")
            
    # Check if search_type column exists
    if not _check_column_exists(conn, "Search_History", "search_type"):
        try:
            current_app.logger.info("Adding search_type column to Search_History table")
            conn.execute("ALTER TABLE Search_History ADD COLUMN search_type TEXT DEFAULT 'new_search'")
            conn.commit()
            current_app.logger.info("Successfully added search_type column")
        except sqlite3.Error as e:
            current_app.logger.error(f"Error adding search_type column: {e}")


def init_metrics_db() -> None:
    """
    Initializes the metrics SQLite database with required tables.
    The database path is configurable via the METRICS_DATABASE configuration variable.
    """
    db_path = current_app.config.get('METRICS_DATABASE')
    if not db_path:
        # Default path if not specified
        db_path = os.path.join(
            os.path.dirname(current_app.config.get('DATABASE', './data/sermons.db')),
            'metrics.db'
        )
    
    current_app.logger.info(f"Initializing metrics database: {db_path}")

    # Ensure the directory for the database exists (use '.' if no directory specified)
    os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
    if not os.path.exists(db_path):
        open(db_path, 'w').close()
        current_app.logger.info(f"Created metrics database file: {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Create table for search history logging
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Search_History (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_query TEXT NOT NULL,
                ip TEXT,
                category_filters TEXT,
                search_type TEXT DEFAULT 'new_search',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create table for sermon access logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Sermon_Access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sermon_guid TEXT NOT NULL,
                ip TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        
        # Run migrations for existing tables
        _migrate_search_history_table(conn)
        
    current_app.logger.info("Metrics database initialized with tables: Search_History and Sermon_Access")
