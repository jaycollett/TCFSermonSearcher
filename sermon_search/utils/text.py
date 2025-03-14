"""
Text processing utilities for the sermon search application.

This module contains functions for text formatting, search, and highlighting.
"""

import re
import random
from typing import List, Optional


def extract_relevant_snippets(transcript: str, query: str, max_snippets: int = 3, context_words: int = 8) -> List[str]:
    """
    Extract snippets of text surrounding the query.
    
    Args:
        transcript: The full transcript text
        query: The search query to find
        max_snippets: Maximum number of snippets to return
        context_words: Number of words around the matched term for context
        
    Returns:
        List[str]: A list of text snippets
    """
    matched_snippets = []
    escaped_query = re.escape(query)
    matches = list(re.finditer(escaped_query, transcript, re.IGNORECASE))
    
    if not matches:
        return ["(No exact match found)"]
    
    last_end = 0
    for match in matches:
        raw_start = max(0, match.start() - context_words * 5)
        raw_end = min(len(transcript), match.end() + context_words * 5)
        
        if raw_start > 0:
            adjusted_start = transcript.rfind(" ", 0, raw_start)
            start = adjusted_start + 1 if adjusted_start != -1 else raw_start
        else:
            start = raw_start
            
        if raw_end < len(transcript):
            adjusted_end = transcript.find(" ", raw_end)
            end = adjusted_end if adjusted_end != -1 else raw_end
        else:
            end = raw_end
            
        if start < last_end:
            continue
            
        snippet = transcript[start:end].strip()
        matched_snippets.append(snippet)
        last_end = end
        
        if len(matched_snippets) >= max_snippets:
            break
            
    return matched_snippets


def format_text_into_paragraphs(text: str, min_length: int = 665) -> str:
    """
    Break long text into paragraphs for better readability.
    
    Args:
        text: The text to format
        min_length: Minimum length for each paragraph
        
    Returns:
        str: HTML formatted text with paragraph tags
    """
    if "\n\n" in text:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return ''.join(f"<p>{p}</p>" for p in paragraphs)
    else:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        paragraphs = []
        current_para = ""
        
        for sentence in sentences:
            candidate = current_para + " " + sentence if current_para else sentence
            if len(candidate) < min_length:
                current_para = candidate
            else:
                paragraphs.append(current_para.strip())
                current_para = ""
                
        if current_para:
            paragraphs.append(current_para.strip())
            
        return ''.join(f"<p>{p}</p>" for p in paragraphs)


def highlight_search_terms(text: str, query: Optional[str]) -> str:
    """
    Highlight search terms in the given text with HTML spans.
    
    Args:
        text: The text to process
        query: The search query to highlight
        
    Returns:
        str: Text with highlighted search terms
    """
    if not query or query.strip() == "":
        return text
        
    escaped_query = re.escape(query)
    regex = re.compile(rf'({escaped_query})', re.IGNORECASE)
    highlighted_text = regex.sub(r'<span class="highlight">\1</span>', text)
    return highlighted_text


def sanitize_search_term(term: str) -> str:
    """
    Sanitize and prepare search term for FTS query.
    
    Args:
        term: The search term to sanitize
        
    Returns:
        str: Sanitized search term ready for SQLite FTS
    """
    term = term.strip()
    term = re.sub(r'[^\w\s\-]', '', term)
    words = term.split()
    
    if len(words) == 1:
        return f'{term}*'
    return f'"{term}"'


def extract_first_sentences(text: str, min_sentences: int = 3, max_sentences: int = 4) -> str:
    """
    Extract the first few sentences from a text.
    
    Args:
        text: The text to process
        min_sentences: Minimum number of sentences to extract
        max_sentences: Maximum number of sentences to extract
        
    Returns:
        str: A string containing the first few sentences
    """
    if not text:
        return "(No transcription available)"
        
    sentences = re.split(r'(?<=[.!?])\s+', text)
    num_sentences = random.randint(min_sentences, max_sentences)
    snippet = " ".join(sentences[:num_sentences])
    return snippet