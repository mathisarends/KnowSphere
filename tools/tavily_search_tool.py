from typing import Optional, List
from langchain.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults

@tool
def tavily_search(
    query: str, 
    max_results: Optional[int] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    search_depth: str = "basic"
) -> str:
    """Suche im Internet nach aktuellen Informationen zu einem Thema.
    
    Args:
        query: Die Suchanfrage
        max_results: Maximale Anzahl an Ergebnissen
        include_domains: Liste von Domains, die bevorzugt werden sollen (z.B. ["github.com"])
        exclude_domains: Liste von Domains, die ausgeschlossen werden sollen
        search_depth: Suchtiefe ("basic" oder "advanced")
    
    Returns:
        Suchergebnisse als Text
    """
    tavily_params = {
        "max_results": max_results or 2,
        "search_depth": search_depth
    }
    
    if include_domains:
        tavily_params["include_domains"] = include_domains
        
    if exclude_domains:
        tavily_params["exclude_domains"] = exclude_domains
        
    tavily_tool = TavilySearchResults(**tavily_params)
    return tavily_tool.invoke(query)