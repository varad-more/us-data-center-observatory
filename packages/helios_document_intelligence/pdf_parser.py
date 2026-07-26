"""PDF parsing utility for document intelligence."""

from __future__ import annotations

import fitz


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF document.

    Args:
        pdf_bytes: The raw bytes of the PDF document.

    Returns:
        The extracted text as a single string.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    
    return text.strip()


def find_keywords_in_text(text: str, keywords: list[str], window_size: int = 150) -> list[str]:
    """Find occurrences of keywords in text and return snippets around them.
    
    Args:
        text: The full text to search.
        keywords: A list of keywords (case-insensitive) to search for.
        window_size: Number of characters to include before and after the keyword.
        
    Returns:
        A list of snippets containing the keywords.
    """
    snippets = []
    text_lower = text.lower()
    
    for keyword in keywords:
        kw_lower = keyword.lower()
        start = 0
        while True:
            idx = text_lower.find(kw_lower, start)
            if idx == -1:
                break
                
            snippet_start = max(0, idx - window_size)
            snippet_end = min(len(text), idx + len(kw_lower) + window_size)
            
            # Try to snap to word boundaries
            if snippet_start > 0:
                space_idx = text.rfind(" ", 0, snippet_start)
                if space_idx != -1:
                    snippet_start = space_idx + 1
                    
            if snippet_end < len(text):
                space_idx = text.find(" ", snippet_end)
                if space_idx != -1:
                    snippet_end = space_idx
                    
            snippet = text[snippet_start:snippet_end].strip()
            # Replace newlines with spaces for a cleaner snippet
            snippet = " ".join(snippet.split())
            
            snippets.append(snippet)
            start = idx + len(kw_lower)
            
    return snippets
