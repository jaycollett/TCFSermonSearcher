import os
import sqlite3
import datetime
import re
from flask import g, current_app

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db_path = current_app.config.get('DATABASE')
        db = g._database = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
    return db

def drop_column_if_exists(conn, table, column):
    """
    Check if a column exists in a table. If it does, drop it.
    This function logs actions via current_app.logger.
    """
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]
    if column in columns:
        try:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            conn.commit()
            current_app.logger.info(f"Dropped column '{column}' from table '{table}'.")
        except sqlite3.Error as e:
            current_app.logger.error(f"Error dropping column '{column}' from table '{table}': {e}")

def init_db():
    """
    Ensure the database file exists and create all necessary tables, indexes, and triggers.
    Uses the DATABASE setting from your configuration.
    """
    db_path = current_app.config.get('DATABASE')
    current_app.logger.info("Initializing database...")

    if not os.path.exists(db_path):
        current_app.logger.info(f"Database file '{db_path}' does not exist. Creating it.")
        open(db_path, 'w').close()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Enable WAL mode if not already enabled
        cursor.execute('PRAGMA journal_mode;')
        journal_mode = cursor.fetchone()[0]
        if journal_mode.lower() != 'wal':
            cursor.execute('PRAGMA journal_mode=WAL;')

        try:
            current_app.logger.info("Creating sermons table...")
            cursor.execute('''
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

            # Drop unwanted columns if they exist.
            drop_column_if_exists(conn, "sermons", "ai_summary")
            drop_column_if_exists(conn, "sermons", "ai_identified_books")

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermon_guid ON sermons (sermon_guid)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermons_language ON sermons(language);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermons_categories ON sermons(categories);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sermons_ai_identified_books ON sermons(ai_identified_books);')
            conn.commit()
            current_app.logger.info("Sermons table created successfully.")
        except sqlite3.Error as e:
            current_app.logger.error(f"Error creating sermons table: {e}")

        try:
            current_app.logger.info("Creating stats_for_nerds table...")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stats_for_nerds (
                    id INTEGER PRIMARY KEY,
                    total_sermons INTEGER,
                    average_words_per_sermon INTEGER,
                    largest_sermon_title TEXT,
                    largest_sermon_word_count INTEGER,
                    shortest_sermon_title TEXT,
                    shortest_sermon_word_count INTEGER,
                    top_ten_words TEXT,
                    most_common_category TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            current_app.logger.info("stats_for_nerds table created successfully.")
        except sqlite3.Error as e:
            current_app.logger.error(f"Error creating stats_for_nerds table: {e}")

        try:
            current_app.logger.info("Creating ip_bans table...")
            cursor.execute('''
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

        try:
            current_app.logger.info("Creating ai_sermon_content table...")
            cursor.execute('''
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

        try:
            current_app.logger.info("Creating sermons_fts table...")
            cursor.execute('''
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

        try:
            current_app.logger.info("Creating triggers...")
            cursor.executescript('''
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

    current_app.logger.info("Database initialization complete.")
