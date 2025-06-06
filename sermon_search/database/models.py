"""
Database models and operations for the sermon search application.

This module handles database connections, table creation, and database operations.
"""

import os
import sqlite3
import datetime
from typing import Optional, Dict, Any, List, Union
from flask import g, current_app


def get_db() -> sqlite3.Connection:
    """
    Get a connection to the SQLite database.
    
    Returns:
        sqlite3.Connection: Database connection with row factory set
    """
    db = getattr(g, '_database', None)
    if db is None:
        db_path = current_app.config.get('DATABASE')
        db = g._database = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA cache_size = 4000")
    return db


def drop_column_if_exists(conn: sqlite3.Connection, table: str, column: str) -> None:
    """
    Check if a column exists in a table. If it does, drop it.
    First attempts to drop any indexes on the column to avoid constraints.
    
    Args:
        conn: SQLite connection
        table: Table name
        column: Column name to drop
    """
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]
    if column in columns:
        try:
            # Get all indexes for the table
            indexes_cursor = conn.execute(f"PRAGMA index_list({table})")
            indexes = indexes_cursor.fetchall()
            
            # Check each index to see if it includes our column
            for idx in indexes:
                index_name = idx["name"]
                index_info_cursor = conn.execute(f"PRAGMA index_info({index_name})")
                index_columns = [col["name"] for col in index_info_cursor.fetchall()]
                
                # If the column is part of this index, drop the index
                if column in index_columns:
                    try:
                        conn.execute(f"DROP INDEX {index_name}")
                        current_app.logger.info(f"Dropped index '{index_name}' on table '{table}'.")
                    except sqlite3.Error as e:
                        current_app.logger.error(f"Error dropping index '{index_name}': {e}")
            
            # Now drop the column
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            conn.commit()
            current_app.logger.info(f"Dropped column '{column}' from table '{table}'.")
        except sqlite3.Error as e:
            current_app.logger.error(f"Error dropping column '{column}' from table '{table}': {e}")


def _migrate_stats_table(conn: sqlite3.Connection) -> None:
    """
    Migrate stats_for_nerds table to add new columns.
    
    Args:
        conn: SQLite connection
    """
    try:
        current_app.logger.info("Checking stats_for_nerds table for needed migrations...")
        
        # Check if largest_sermon_guid column exists
        cursor = conn.execute("PRAGMA table_info(stats_for_nerds)")
        columns = [row["name"] for row in cursor.fetchall()]
        
        # Add largest_sermon_guid column if it doesn't exist
        if "largest_sermon_guid" not in columns:
            current_app.logger.info("Adding largest_sermon_guid column to stats_for_nerds table")
            conn.execute("ALTER TABLE stats_for_nerds ADD COLUMN largest_sermon_guid TEXT")
            conn.commit()
            current_app.logger.info("Added largest_sermon_guid column")
        
        # Add shortest_sermon_guid column if it doesn't exist
        if "shortest_sermon_guid" not in columns:
            current_app.logger.info("Adding shortest_sermon_guid column to stats_for_nerds table")
            conn.execute("ALTER TABLE stats_for_nerds ADD COLUMN shortest_sermon_guid TEXT")
            conn.commit()
            current_app.logger.info("Added shortest_sermon_guid column")
            
        # If we added new columns, populate them from sermons table if possible
        if "largest_sermon_guid" not in columns or "shortest_sermon_guid" not in columns:
            current_app.logger.info("Populating new sermon GUID columns in stats_for_nerds table")
            
            # Get the stats record
            stats_cursor = conn.execute("SELECT * FROM stats_for_nerds WHERE id = 1")
            stats_row = stats_cursor.fetchone()
            
            if stats_row:
                largest_title = stats_row["largest_sermon_title"]
                shortest_title = stats_row["shortest_sermon_title"]
                
                # Find GUIDs for largest sermon
                largest_cursor = conn.execute(
                    "SELECT sermon_guid FROM sermons WHERE sermon_title = ? AND language = 'en' LIMIT 1", 
                    (largest_title,)
                )
                largest_result = largest_cursor.fetchone()
                largest_guid = largest_result["sermon_guid"] if largest_result else None
                
                # Find GUIDs for shortest sermon
                shortest_cursor = conn.execute(
                    "SELECT sermon_guid FROM sermons WHERE sermon_title = ? AND language = 'en' LIMIT 1", 
                    (shortest_title,)
                )
                shortest_result = shortest_cursor.fetchone()
                shortest_guid = shortest_result["sermon_guid"] if shortest_result else None
                
                # Update the stats table with the GUIDs
                if largest_guid or shortest_guid:
                    update_sql = "UPDATE stats_for_nerds SET "
                    params = []
                    
                    if largest_guid:
                        update_sql += "largest_sermon_guid = ?"
                        params.append(largest_guid)
                    
                    if shortest_guid:
                        if largest_guid:
                            update_sql += ", "
                        update_sql += "shortest_sermon_guid = ?"
                        params.append(shortest_guid)
                    
                    update_sql += " WHERE id = 1"
                    
                    conn.execute(update_sql, params)
                    conn.commit()
                    current_app.logger.info("Updated sermon GUIDs in stats_for_nerds table")
        
        current_app.logger.info("Completed stats_for_nerds table migrations")
    except sqlite3.Error as e:
        current_app.logger.error(f"Error migrating stats_for_nerds table: {e}")


def init_main_db() -> None:
    """
    Initialize the database with all required tables and indexes.
    
    This function ensures the database file exists and creates all 
    necessary tables, indexes, and triggers.
    """
    db_path = current_app.config.get('DATABASE')
    current_app.logger.info("Initializing database...")

    if not os.path.exists(db_path):
        current_app.logger.info(f"Database file '{db_path}' does not exist. Creating it.")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        open(db_path, 'w').close()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Enable WAL mode for better performance
        cursor.execute('PRAGMA journal_mode;')
        journal_mode = cursor.fetchone()[0]
        if journal_mode.lower() != 'wal':
            cursor.execute('PRAGMA journal_mode=WAL;')

        # Create tables
        _create_sermons_table(conn)
        _create_stats_table(conn)
        _create_ip_bans_table(conn)
        _create_ai_sermon_content_table(conn)
        _create_omitted_categories_table(conn)
        _create_fulltext_search_table(conn)
        _create_triggers(conn)
        
        # Apply migrations for existing tables
        _migrate_stats_table(conn)

    current_app.logger.info("Database initialization complete.")


def _create_sermons_table(conn: sqlite3.Connection) -> None:
    """
    Create the sermons table and related indexes.
    
    Args:
        conn: SQLite connection
    """
    try:
        current_app.logger.info("Creating sermons table...")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sermons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sermon_title TEXT NOT NULL,
                transcription TEXT NOT NULL,
                transcription_timings TEXT,
                audiofilename TEXT,
                sermon_guid VARCHAR(40) NOT NULL,
                language VARCHAR(2) NOT NULL DEFAULT 'en',
                categories TEXT,
                insert_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                church NVARCHAR(10),
                UNIQUE (sermon_guid, language)
            )
        ''')
        conn.commit()

        # Drop unwanted columns if they exist
        drop_column_if_exists(conn, "sermons", "ai_summary")
        drop_column_if_exists(conn, "sermons", "ai_identified_books")

        # Create indexes
        conn.execute('CREATE INDEX IF NOT EXISTS idx_sermon_guid ON sermons (sermon_guid)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_sermons_language ON sermons(language);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_sermons_categories ON sermons(categories);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_language_sermon_title ON sermons (language, sermon_title);')
        conn.commit()
        current_app.logger.info("Sermons table created successfully.")
    except sqlite3.Error as e:
        current_app.logger.error(f"Error creating sermons table: {e}")


def _create_stats_table(conn: sqlite3.Connection) -> None:
    """
    Create the stats_for_nerds table.
    
    Args:
        conn: SQLite connection
    """
    try:
        current_app.logger.info("Creating stats_for_nerds table...")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS stats_for_nerds (
                id INTEGER PRIMARY KEY,
                total_sermons INTEGER,
                average_words_per_sermon INTEGER,
                largest_sermon_title TEXT,
                largest_sermon_word_count INTEGER,
                largest_sermon_guid TEXT,
                shortest_sermon_title TEXT,
                shortest_sermon_word_count INTEGER,
                shortest_sermon_guid TEXT,
                top_ten_words TEXT,
                most_common_category TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        current_app.logger.info("stats_for_nerds table created successfully.")
    except sqlite3.Error as e:
        current_app.logger.error(f"Error creating stats_for_nerds table: {e}")


def _create_ip_bans_table(conn: sqlite3.Connection) -> None:
    """
    Create the ip_bans table for security.
    
    Args:
        conn: SQLite connection
    """
    try:
        current_app.logger.info("Creating ip_bans table...")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ip_bans (
                ip_address TEXT PRIMARY KEY,
                failed_attempts INTEGER DEFAULT 0,
                banned_until INTEGER
            )
        ''')
        conn.commit()
        current_app.logger.info("ip_bans table created successfully.")
    except sqlite3.Error as e:
        current_app.logger.error(f"Error creating ip_bans table: {e}")


def _create_ai_sermon_content_table(conn: sqlite3.Connection) -> None:
    """
    Create the ai_sermon_content table for AI-generated content.
    
    Args:
        conn: SQLite connection
    """
    try:
        current_app.logger.info("Creating ai_sermon_content table...")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ai_sermon_content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sermon_guid VARCHAR(40) NOT NULL,
                ai_summary TEXT,
                ai_summary_es TEXT,
                bible_books TEXT,
                bible_books_es TEXT,
                created_at DATETIME,
                key_quotes TEXT,
                key_quotes_es TEXT,
                sentiment TEXT,
                sentiment_es TEXT,
                sermon_style TEXT,
                sermon_style_es TEXT,
                status VARCHAR(50),
                topics TEXT,
                topics_es TEXT,
                updated_at DATETIME,
                FOREIGN KEY (sermon_guid) REFERENCES sermons(sermon_guid)
            )
        ''')
        conn.commit()
        
        current_app.logger.info("ai_sermon_content table created successfully.")
    except sqlite3.Error as e:
        current_app.logger.error(f"Error creating ai_sermon_content table: {e}")


def _create_omitted_categories_table(conn: sqlite3.Connection) -> None:
    """
    Create the omitted_categories table to store categories that should be
    omitted from display in the UI.
    
    Args:
        conn: SQLite connection
    """
    try:
        current_app.logger.info("Creating omitted_categories table...")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS omitted_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'en',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(category, language)
            )
        ''')
        
        # Create index for faster lookups
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_omitted_categories_language 
            ON omitted_categories(language)
        ''')
        
        current_app.logger.info("omitted_categories table created successfully.")
    except sqlite3.Error as e:
        current_app.logger.error(f"Error creating omitted_categories table: {e}")


def _create_fulltext_search_table(conn: sqlite3.Connection) -> None:
    """
    Create the full-text search virtual table.
    
    Args:
        conn: SQLite connection
    """
    try:
        current_app.logger.info("Creating sermons_fts table...")
        conn.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS sermons_fts USING fts5(
                sermon_guid, sermon_title, transcription, 
                audiofilename UNINDEXED, language UNINDEXED, 
                categories, church UNINDEXED,
                content='sermons', content_rowid='id',
                tokenize='unicode61',  
                prefix='2,3'
            )
        ''')
        conn.commit()
        current_app.logger.info("sermons_fts table created successfully.")
    except sqlite3.Error as e:
        current_app.logger.error(f"Error creating sermons_fts table: {e}")


def _create_triggers(conn: sqlite3.Connection) -> None:
    """
    Create database triggers for FTS synchronization.
    
    Args:
        conn: SQLite connection
    """
    try:
        current_app.logger.info("Creating triggers...")
        conn.executescript('''
            CREATE TRIGGER IF NOT EXISTS sermons_ai AFTER INSERT ON sermons BEGIN
                INSERT INTO sermons_fts(rowid, sermon_guid, sermon_title, transcription, audiofilename, categories, language, church)
                VALUES (new.id, new.sermon_guid, new.sermon_title, new.transcription, new.audiofilename, new.categories, new.language, new.church);
            END;
            CREATE TRIGGER IF NOT EXISTS sermons_ad AFTER DELETE ON sermons BEGIN
                DELETE FROM sermons_fts WHERE rowid = old.id;
            END;
            CREATE TRIGGER IF NOT EXISTS sermons_au AFTER UPDATE ON sermons BEGIN
                DELETE FROM sermons_fts WHERE rowid = old.id;
                INSERT INTO sermons_fts(rowid, sermon_guid, sermon_title, transcription, audiofilename, language, categories, church)
                VALUES (new.id, new.sermon_guid, new.sermon_title, new.transcription, new.audiofilename, new.language, new.categories, new.church);
            END;
        ''')
        conn.commit()
        current_app.logger.info("Triggers created successfully.")
    except sqlite3.Error as e:
        current_app.logger.error(f"Error creating triggers: {e}")


def query_db(query: str, args=(), one: bool = False) -> Union[List[Dict[str, Any]], Dict[str, Any], None]:
    """
    Execute a database query and fetch the results.
    
    Args:
        query: SQL query to execute
        args: Parameters for the query
        one: If True, return only one result or None
        
    Returns:
        Query results as a list of dictionaries, a single dictionary, or None
    """
    try:
        cur = get_db().execute(query, args)
        rv = cur.fetchall()
        cur.close()
        return (dict(rv[0]) if rv else None) if one else [dict(r) for r in rv]
    except sqlite3.Error as e:
        current_app.logger.error(f"Database error in query: {e}")
        raise


def get_sermon_by_guid(sermon_guid: str, language: str = 'en') -> Optional[Dict[str, Any]]:
    """
    Get a sermon by its GUID and language.
    
    Args:
        sermon_guid: The sermon's unique identifier
        language: Language code (default: 'en')
        
    Returns:
        Sermon data as a dictionary or None if not found
    """
    try:
        db = get_db()
        cur = db.execute(
            "SELECT * FROM sermons WHERE sermon_guid = ? AND language = ?",
            (sermon_guid, language)
        )
        sermon = cur.fetchone()
        if not sermon and language != 'en':
            # Fallback to English if the requested language isn't available
            cur = db.execute(
                "SELECT * FROM sermons WHERE sermon_guid = ? AND language = 'en'",
                (sermon_guid,)
            )
            sermon = cur.fetchone()
        
        return dict(sermon) if sermon else None
    except sqlite3.Error as e:
        current_app.logger.error(f"Error fetching sermon {sermon_guid}: {e}")
        return None


def get_ai_content_by_guid(sermon_guid: str) -> Optional[Dict[str, Any]]:
    """
    Get AI-generated content for a sermon by its GUID.
    
    Args:
        sermon_guid: The sermon's unique identifier
        
    Returns:
        AI content as a dictionary or None if not found
    """
    try:
        db = get_db()
        cur = db.execute(
            "SELECT * FROM ai_sermon_content WHERE sermon_guid = ?",
            (sermon_guid,)
        )
        content = cur.fetchone()
        return dict(content) if content else None
    except sqlite3.Error as e:
        current_app.logger.error(f"Error fetching AI content for sermon {sermon_guid}: {e}")
        return None