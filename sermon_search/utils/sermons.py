"""
Sermon utility functions for the TCF Sermon Searcher.

This module contains functions for retrieving and processing sermon data.
"""

from typing import List, Dict, Any, Optional
from collections import Counter
from flask import current_app
from sermon_search.database.models import get_db
from sermon_search.database.init_metrics_db import get_metrics_db


def get_omitted_categories(language: str = 'en') -> List[str]:
    """
    Get the list of categories that should be omitted from display.
    
    Args:
        language: Language code (e.g., 'en', 'es')
        
    Returns:
        List[str]: List of categories to omit
    """
    db = get_db()
    cur = db.execute(
        "SELECT category FROM omitted_categories WHERE language = ?",
        (language,)
    )
    rows = cur.fetchall()
    
    return [row["category"] for row in rows]


def add_omitted_category(category: str, language: str = 'en') -> bool:
    """
    Add a category to the omitted list.
    
    Args:
        category: Category name to omit
        language: Language code (e.g., 'en', 'es')
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO omitted_categories (category, language) VALUES (?, ?)",
            (category, language)
        )
        db.commit()
        return True
    except Exception as e:
        current_app.logger.error(f"Error adding omitted category: {str(e)}")
        return False


def remove_omitted_category(category: str, language: str = 'en') -> bool:
    """
    Remove a category from the omitted list.
    
    Args:
        category: Category name to remove from omitted list
        language: Language code (e.g., 'en', 'es')
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        db = get_db()
        db.execute(
            "DELETE FROM omitted_categories WHERE category = ? AND language = ?",
            (category, language)
        )
        db.commit()
        return True
    except Exception as e:
        current_app.logger.error(f"Error removing omitted category: {str(e)}")
        return False


def clear_omitted_categories(language: str = None) -> bool:
    """
    Clear all omitted categories.
    
    Args:
        language: Optional language code to clear only categories for a specific language.
                 If None, clears all languages.
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        db = get_db()
        if language:
            db.execute("DELETE FROM omitted_categories WHERE language = ?", (language,))
        else:
            db.execute("DELETE FROM omitted_categories")
        db.commit()
        return True
    except Exception as e:
        current_app.logger.error(f"Error clearing omitted categories: {str(e)}")
        return False


def get_all_categories(language: str) -> List[str]:
    """
    Return a sorted list of distinct categories for the given language,
    excluding any categories that have been marked for omission.
    
    Args:
        language: Language code (e.g., 'en', 'es')
        
    Returns:
        List[str]: Sorted list of sermon categories
    """
    db = get_db()
    cur = db.execute("SELECT categories FROM sermons WHERE language = ?", (language,))
    rows = cur.fetchall()
    
    cats_set = set()
    for row in rows:
        if row["categories"]:
            for cat in row["categories"].split(","):
                trimmed = cat.strip()
                if trimmed:
                    cats_set.add(trimmed)
    
    # Get categories to omit and remove them from the set
    omitted = set(get_omitted_categories(language))
    cats_set = cats_set - omitted
                    
    return sorted(list(cats_set))


def search_sermons(
    query: str, 
    language: str, 
    selected_categories: List[str] = None, 
    page: int = 1, 
    per_page: int = 10
) -> Dict[str, Any]:
    """
    Search sermons using full-text search or fallback to LIKE query.
    
    Args:
        query: The search term
        language: Language code
        selected_categories: List of categories to filter by
        page: Page number (1-based)
        per_page: Number of results per page
        
    Returns:
        Dict containing search results, pagination info and total count
    """
    from sermon_search.utils.text import sanitize_search_term
    
    selected_categories = selected_categories or []
    offset = (page - 1) * per_page
    sanitized_term = sanitize_search_term(query)
    results = []
    
    try:
        db = get_db()
        filter_clause = ""
        filter_params = []
        
        if selected_categories:
            conditions = []
            for cat in selected_categories:
                conditions.append("s.categories LIKE ?")
                filter_params.append(f"%{cat}%")
            filter_clause = " AND (" + " OR ".join(conditions) + ")"

        # Try FTS search first
        fts_query_str = f"sermon_title:{sanitized_term} OR transcription:{sanitized_term}"
        fts_sql = (
            "SELECT s.sermon_guid, s.sermon_title, s.audiofilename, s.transcription, s.categories "
            "FROM sermons s "
            "JOIN sermons_fts ON s.id = sermons_fts.rowid "
            "WHERE sermons_fts MATCH ? AND s.language = ? "
            f"{filter_clause} ORDER BY s.insert_date DESC LIMIT ? OFFSET ?"
        )
        params = [fts_query_str, language] + filter_params + [per_page, offset]
        cur = db.execute(fts_sql, params)
        sermons = cur.fetchall()

        count_sql = (
            "SELECT COUNT(*) as total "
            "FROM sermons s "
            "JOIN sermons_fts ON s.id = sermons_fts.rowid "
            "WHERE sermons_fts MATCH ? AND s.language = ? "
            f"{filter_clause}"
        )
        count_params = [fts_query_str, language] + filter_params
        cur = db.execute(count_sql, count_params)
        total_count = cur.fetchone()["total"]

        # If no results with FTS, fallback to LIKE
        if not sermons:
            like_query = f"%{query}%"
            fallback_sql = (
                "SELECT s.sermon_guid, s.sermon_title, s.audiofilename, s.transcription, s.categories "
                "FROM sermons s "
                "WHERE s.transcription LIKE ? AND s.language = ? "
            f"{filter_clause} ORDER BY s.insert_date DESC LIMIT ? OFFSET ?"
            )
            params = [like_query, language] + filter_params + [per_page, offset]
            cur = db.execute(fallback_sql, params)
            sermons = cur.fetchall()
            
            count_sql = (
                "SELECT COUNT(*) as total "
                "FROM sermons s "
                "WHERE s.transcription LIKE ? AND s.language = ? "
                f"{filter_clause}"
            )
            count_params = [like_query, language] + filter_params
            cur = db.execute(count_sql, count_params)
            total_count = cur.fetchone()["total"]

        current_app.logger.debug(f"Total results found: {len(sermons)} out of {total_count}")
        return {
            'sermons': [dict(sermon) for sermon in sermons],
            'total_count': total_count
        }
        
    except Exception as e:
        current_app.logger.error(f"Error during search: {str(e)}", exc_info=True)
        return {'sermons': [], 'total_count': 0}


def get_sermon_statistics() -> Dict[str, Any]:
    """
    Get computed statistics about the sermon database.
    
    Returns:
        Dict containing statistics or default values if none exist
    """
    db = get_db()
    
    # Get basic stats from stats_for_nerds table
    row = db.execute("SELECT * FROM stats_for_nerds WHERE id = 1").fetchone()
    
    # Get top accessed sermons from metrics database
    top_accessed_sermons = []
    try:
        # First, get sermon access counts from metrics database
        metrics_db = get_metrics_db()
        sermon_access_query = """
            SELECT sermon_guid, COUNT(*) as access_count 
            FROM Sermon_Access 
            GROUP BY sermon_guid 
            ORDER BY access_count DESC 
            LIMIT 10
        """
        
        metrics_cursor = metrics_db.execute(sermon_access_query)
        access_results = metrics_cursor.fetchall()
        
        # For each accessed sermon, get its title from the main database
        for access_record in access_results:
            sermon_guid = access_record['sermon_guid']
            main_db_query = """
                SELECT sermon_title FROM sermons 
                WHERE sermon_guid = ? AND language = 'en'
                LIMIT 1
            """
            sermon_cursor = db.execute(main_db_query, (sermon_guid,))
            sermon_result = sermon_cursor.fetchone()
            
            if sermon_result:
                top_accessed_sermons.append({
                    'sermon_guid': sermon_guid,
                    'sermon_title': sermon_result['sermon_title'],
                    'access_count': access_record['access_count']
                })
            else:
                # If sermon not found in main DB (e.g., test data), use the GUID as title
                top_accessed_sermons.append({
                    'sermon_guid': sermon_guid,
                    'sermon_title': f"Unknown sermon ({sermon_guid[:8]}...)",
                    'access_count': access_record['access_count']
                })
    except Exception as e:
        current_app.logger.error(f"Failed to get top accessed sermons: {str(e)}", exc_info=True)
    
    # Get sermon GUIDs directly from stats table
    largest_sermon_guid = None
    shortest_sermon_guid = None
    
    if row:
        try:
            # Use GUIDs directly from the stats_for_nerds table if available
            if "largest_sermon_guid" in row and row["largest_sermon_guid"]:
                largest_sermon_guid = row["largest_sermon_guid"]
            else:
                # Backward compatibility for older database versions
                largest_sermon_query = """
                    SELECT sermon_guid FROM sermons 
                    WHERE sermon_title = ? AND language = 'en'
                    LIMIT 1
                """
                largest_cursor = db.execute(largest_sermon_query, (row["largest_sermon_title"],))
                largest_result = largest_cursor.fetchone()
                if largest_result:
                    largest_sermon_guid = largest_result["sermon_guid"]
                
            if "shortest_sermon_guid" in row and row["shortest_sermon_guid"]:
                shortest_sermon_guid = row["shortest_sermon_guid"]
            else:
                # Backward compatibility for older database versions
                shortest_sermon_query = """
                    SELECT sermon_guid FROM sermons 
                    WHERE sermon_title = ? AND language = 'en'
                    LIMIT 1
                """
                shortest_cursor = db.execute(shortest_sermon_query, (row["shortest_sermon_title"],))
                shortest_result = shortest_cursor.fetchone()
                if shortest_result:
                    shortest_sermon_guid = shortest_result["sermon_guid"]
        except Exception as e:
            current_app.logger.error(f"Failed to get sermon GUIDs: {str(e)}", exc_info=True)
    
    if row:
        import json
        return {
            "total_sermons": row["total_sermons"],
            "average_words_per_sermon": row["average_words_per_sermon"],
            "largest_sermon_title": row["largest_sermon_title"],
            "largest_sermon_word_count": row["largest_sermon_word_count"],
            "largest_sermon_guid": largest_sermon_guid,
            "shortest_sermon_title": row["shortest_sermon_title"],
            "shortest_sermon_word_count": row["shortest_sermon_word_count"],
            "shortest_sermon_guid": shortest_sermon_guid,
            "top_ten_words": json.loads(row["top_ten_words"]) if row["top_ten_words"] else [],
            "most_common_category": row["most_common_category"],
            "updated_at": row["updated_at"],
            "top_accessed_sermons": top_accessed_sermons
        }
    else:
        return {
            "total_sermons": 0,
            "average_words_per_sermon": 0,
            "largest_sermon_title": "No data",
            "largest_sermon_word_count": 0,
            "largest_sermon_guid": None,
            "shortest_sermon_title": "No data",
            "shortest_sermon_word_count": 0,
            "shortest_sermon_guid": None,
            "top_ten_words": [],
            "most_common_category": "N/A",
            "updated_at": "N/A",
            "top_accessed_sermons": []
        }
