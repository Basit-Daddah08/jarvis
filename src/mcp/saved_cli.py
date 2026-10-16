import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.mcp.server import list_saved_notes, search_vault_notes

def handle_query(query: str):
    q = query.lower()
    print(f"\n[JARVIS /saved] Query: '{query}'")
    print("-" * 50)

    if any(k in q for k in ["tool", "tools"]):
        notes = list_saved_notes(days=7, category="tool") + list_saved_notes(days=7, category="ai")
        # Deduplicate
        seen = set()
        unique_notes = []
        for n in notes:
            if n["id"] not in seen:
                seen.add(n["id"])
                unique_notes.append(n)
        
        all_tools = []
        for n in unique_notes:
            all_tools.extend(n.get("tools", []))
        
        print(f"Found {len(unique_notes)} tool/AI video note(s) saved this week:\n")
        for n in unique_notes:
            tools_str = f" [Tools: {', '.join(n['tools'])}]" if n.get("tools") else ""
            print(f"- {n['title']} (by {n['creator']}){tools_str}")
            if n.get("summary"):
                print(f"  Summary: {n['summary']}")
            print(f"  Note: {n['path']}")
            print()
        return

    # General search
    results = search_vault_notes(query)
    if not results:
        print("No matching notes found.")
        return

    print(f"Found {len(results)} matching note(s):\n")
    for r in results[:5]:
        print(f"- [{r['type'].upper()}] {r['title']} (by {r['creator']})")
        if r.get("summary"):
            print(f"  Summary: {r['summary']}")
        print(f"  Note: {r['path']}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query saved notes like Claude Code /saved")
    parser.add_argument("query", nargs="?", default="what tools did we save this week?", help="Search or question")
    parser.add_argument("--tools", action="store_true", help="List all saved tools")
    args = parser.parse_args()

    q = "what tools did we save this week?" if args.tools else args.query
    handle_query(q)
