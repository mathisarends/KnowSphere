import logging
import asyncio
import json
from typing import Dict, Any

from notion.core.notion_abstract_client import AbstractNotionClient, HttpMethod
from notion.core.notion_pages import NotionPages

class NotionSchemaExplorer(AbstractNotionClient):
    def __init__(self, start_database_name: str = None, start_database_id: str = None):
        super().__init__()
        
        # Entweder direkt die ID verwenden oder den Namen in ID umwandeln
        if start_database_id:
            self.start_database_id = start_database_id
        elif start_database_name:
            self.start_database_id = NotionPages.get_database_id(start_database_name)
        else:
            self.start_database_id = None
            
        # Speichere alle bereits abgerufenen Schemas, um Schleifen zu vermeiden
        self.explored_databases: Dict[str, Dict[str, Any]] = {}
        
    async def explore_schema_recursively(self, database_id: str = None, max_depth: int = 5) -> Dict[str, Any]:
        """
        Erkundet das Schema einer Datenbank und folgt rekursiv allen Relationsbeziehungen 
        bis zur angegebenen Tiefe.
        
        Args:
            database_id: Optional - die zu erkundende Datenbank-ID (verwendet start_database_id wenn nicht angegeben)
            max_depth: Maximale Tiefe der rekursiven Erkundung (um Endlosschleifen zu vermeiden)
            
        Returns:
            Ein Dictionaries mit den vollständigen Schemas aller verknüpften Datenbanken
        """
        if database_id is None:
            database_id = self.start_database_id
            
        if database_id is None:
            self.logger.error("Keine Datenbank-ID angegeben und keine Startdatenbank definiert")
            return {}
            
        # Abbruchbedingungen
        if max_depth <= 0:
            return {}
            
        if database_id in self.explored_databases:
            return {database_id: self.explored_databases[database_id]}
            
        # Hole das primäre Schema der aktuellen Datenbank
        db_info = await self._fetch_database_info(database_id)
        if not db_info:
            return {}
            
        # Speichere Basisinformationen für diese Datenbank
        db_title = self._extract_database_title(db_info)
        properties = db_info.get("properties", {})
        
        schema_info = {
            "title": db_title,
            "properties": properties,
            "related_schemas": {},
        }
        
        # Füge zur Liste der erkundeten Datenbanken hinzu, um Schleifen zu vermeiden
        self.explored_databases[database_id] = schema_info
        
        # Finde alle Relationseigenschaften
        relation_properties = {
            prop_name: prop_info 
            for prop_name, prop_info in properties.items() 
            if prop_info.get("type") == "relation"
        }
        
        # Rekursiv folge jeder Relation
        for prop_name, prop_info in relation_properties.items():
            related_db_id = prop_info.get("relation", {}).get("database_id")
            
            if not related_db_id:
                continue
                
            self.logger.info(f"Folge Relation '{prop_name}' zu Datenbank {related_db_id}")
            
            # Rekursiver Aufruf mit verringerter Tiefe
            related_schema = await self.explore_schema_recursively(related_db_id, max_depth - 1)
            
            if related_schema:
                schema_info["related_schemas"][prop_name] = {
                    "database_id": related_db_id,
                    "schema": related_schema.get(related_db_id, {})
                }
        
        return {database_id: schema_info}
    
    async def _fetch_database_info(self, database_id: str) -> Dict[str, Any]:
        """Ruft die vollständigen Informationen einer Datenbank ab"""
        response = await self._make_request(
            HttpMethod.GET,
            f"databases/{database_id}"
        )
        
        if response is None or "error" in response:
            error_msg = response.get('error', 'Unknown error') if response else 'No response'
            self.logger.error(f"Fehler beim Abrufen der Datenbank {database_id}: {error_msg}")
            return {}
        
        return response
    
    def _extract_database_title(self, db_info: Dict[str, Any]) -> str:
        """Extrahiert den Titel aus den Datenbankinformationen"""
        title = ""
        if "title" in db_info:
            title_objects = db_info.get("title", [])
            if title_objects:
                title = title_objects[0].get("text", {}).get("content", "")
                
        return title
    
    async def print_schema_tree(self, schema: Dict[str, Any] = None, indent: int = 0):
        """
        Gibt eine formatierte Baumansicht des Schemas aus
        
        Args:
            schema: Das zu druckende Schema (wenn None, wird das vollständige Schema verwendet)
            indent: Aktuelle Einrückungsebene
        """
        if schema is None:
            if not self.explored_databases:
                self.logger.warning("Keine Schemas verfügbar. Bitte zuerst explore_schema_recursively aufrufen.")
                return
                
            schema = {self.start_database_id: self.explored_databases.get(self.start_database_id, {})}
        
        # Ein Zeichen für jede Einrückungsebene
        indent_str = "  " * indent
        
        for db_id, db_info in schema.items():
            db_title = db_info.get("title", "Unbenannte Datenbank")
            print(f"{indent_str}📁 Datenbank: {db_title} ({db_id})")
            
            # Eigenschaften ausgeben
            print(f"{indent_str}  Eigenschaften:")
            properties = db_info.get("properties", {})
            
            for prop_name, prop_info in properties.items():
                prop_type = prop_info.get("type", "unknown")
                print(f"{indent_str}    • {prop_name} ({prop_type})")
                
                # Zusätzliche Details je nach Eigenschaftstyp
                if prop_type == "select" and "select" in prop_info:
                    options = prop_info["select"].get("options", [])
                    print(f"{indent_str}      Optionen:")
                    for option in options:
                        color = option.get("color", "default")
                        name = option.get("name", "")
                        print(f"{indent_str}        - {name} (Farbe: {color})")
                
                elif prop_type == "multi_select" and "multi_select" in prop_info:
                    options = prop_info["multi_select"].get("options", [])
                    print(f"{indent_str}      Optionen:")
                    for option in options:
                        color = option.get("color", "default")
                        name = option.get("name", "")
                        print(f"{indent_str}        - {name} (Farbe: {color})")
                
                elif prop_type == "relation" and "relation" in prop_info:
                    related_db = prop_info["relation"].get("database_id", "")
                    print(f"{indent_str}      ↳ Verknüpft mit Datenbank: {related_db}")
            
            # Rekursiv verknüpfte Schemas ausgeben
            if "related_schemas" in db_info and db_info["related_schemas"]:
                print(f"{indent_str}  Verknüpfte Datenbanken:")
                
                for rel_name, rel_info in db_info["related_schemas"].items():
                    rel_id = rel_info.get("database_id", "")
                    print(f"{indent_str}    ↳ {rel_name} -> {rel_id}")
                    
                    # Rekursiver Aufruf mit erhöhter Einrückung
                    rel_schema = {rel_id: rel_info.get("schema", {})}
                    await self.print_schema_tree(rel_schema, indent + 3)
            
            print()  # Leerzeile für bessere Lesbarkeit
            
            
async def main():
    # Konfiguriere Logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Initialisiere den SchemaExplorer mit der WISSEN_NOTIZEN-Datenbank
    explorer = NotionSchemaExplorer(start_database_name="WISSEN_NOTIZEN")
    
    print("🔍 Starte rekursive Schemaanalyse der WISSEN_NOTIZEN-Datenbank...")
    # Max_depth begrenzt die Rekursionstiefe, um Schleifen zu vermeiden
    schema = await explorer.explore_schema_recursively(max_depth=3)
    
    print("\n📊 VOLLSTÄNDIGER DATENBANKSCHEMA-BAUM:\n")
    await explorer.print_schema_tree()
    
    # Schema in eine JSON-Datei schreiben für spätere Analyse
    with open("notion_complete_schema.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Vollständiges Schema wurde in 'notion_complete_schema.json' gespeichert.")

if __name__ == "__main__":
    asyncio.run(main())