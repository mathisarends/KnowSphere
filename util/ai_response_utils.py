def clean_markdown_code_blocks(content: str) -> str:
    """
    Removes markdown code block markers from the beginning and end of content.
    
    Args:
        content: String that might contain markdown code blocks
        
    Returns:
        Cleaned content without leading/trailing markdown code block markers
    """
    # Remove leading code block markers (```markdown or ``` at the beginning)
    if content.startswith("```"):
        first_newline = content.find("\n")
        if first_newline != -1:
            content = content[first_newline + 1:]
    
    # Remove trailing code block markers (``` at the end)
    if content.rstrip().endswith("```"):
        last_marker = content.rstrip().rfind("```")
        if last_marker != -1:
            content = content[:last_marker].rstrip()
    
    return content