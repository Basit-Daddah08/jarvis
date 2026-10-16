import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VAULT_DIR = PROJECT_ROOT / "vault"
NOTES_DIR = VAULT_DIR / "notes"
INBOX_FILE = VAULT_DIR / "INBOX.md"
APPROVALS_DIR = VAULT_DIR / "approvals"

def parse_note(file_path: Path) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    front_matter = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2]
            for line in fm_text.strip().split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    k = key.strip()
                    v = val.strip().strip('"').strip("'")
                    if v.startswith("[") and v.endswith("]"):
                        # Parse list
                        items = [i.strip().strip('"').strip("'") for i in v[1:-1].split(",") if i.strip()]
                        front_matter[k] = items
                    else:
                        front_matter[k] = v

    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else file_path.stem

    summary_match = re.search(r"##\s+Summary\s*\n([\s\S]*?)(?=##|$)", body)
    summary = summary_match.group(1).strip() if summary_match else ""

    return {
        "id": front_matter.get("id", file_path.stem),
        "title": title,
        "creator": front_matter.get("creator", "@unknown"),
        "type": front_matter.get("type", "other"),
        "saved_at": front_matter.get("saved_at", ""),
        "tools": front_matter.get("tools", []),
        "links": front_matter.get("links", []),
        "summary": summary,
        "body": body.strip(),
        "path": str(file_path.relative_to(PROJECT_ROOT))
    }

def list_saved_notes(days: int = 7, category: str = "all") -> List[Dict[str, Any]]:
    results = []
    if not NOTES_DIR.exists():
        return results

    cutoff_date = (date.today() - timedelta(days=days)).isoformat()
    for note_path in sorted(NOTES_DIR.glob("*.md")):
        note = parse_note(note_path)
        if category != "all" and note.get("type", "").lower() != category.lower():
            continue
        saved_at = note.get("saved_at", "")
        if saved_at and saved_at < cutoff_date:
            continue
        results.append(note)
    return results

def search_vault_notes(query: str) -> List[Dict[str, Any]]:
    q = query.lower()
    results = []
    if not NOTES_DIR.exists():
        return results

    for note_path in sorted(NOTES_DIR.glob("*.md")):
        note = parse_note(note_path)
        match_score = 0
        if q in note.get("title", "").lower():
            match_score += 10
        if any(q in t.lower() for t in note.get("tools", [])):
            match_score += 8
        if q in note.get("summary", "").lower():
            match_score += 5
        if q in note.get("body", "").lower():
            match_score += 2

        if match_score > 0:
            note["match_score"] = match_score
            results.append(note)

    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results

# MCP JSON-RPC Stdio Server
def run_mcp_server():
    """Lightweight Model Context Protocol (MCP) server for Claude Code and AI agents."""
    sys.stderr.write("JARVIS MCP server started on stdio.\n")
    sys.stderr.flush()

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "jarvis-vault-mcp",
                            "version": "1.0.0"
                        }
                    }
                }
            elif method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "list_saved",
                                "description": "List recently saved video notes with tools and summaries.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "days": {"type": "integer", "description": "Days to look back (default 7)", "default": 7},
                                        "category": {"type": "string", "description": "Filter: 'all', 'tool', 'ai', 'other'", "default": "all"}
                                    }
                                }
                            },
                            {
                                "name": "search_vault",
                                "description": "Search saved notes by keyword, tool name, or topic.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string", "description": "Search terms"}
                                    },
                                    "required": ["query"]
                                }
                            },
                            {
                                "name": "get_note",
                                "description": "Retrieve full markdown content of a specific saved note.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "note_id": {"type": "string", "description": "Video note ID"}
                                    },
                                    "required": ["note_id"]
                                }
                            },
                            {
                                "name": "get_inbox",
                                "description": "Retrieve today's INBOX.md digest.",
                                "inputSchema": {"type": "object"}
                            }
                        ]
                    }
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                args = params.get("arguments", {})

                if tool_name == "list_saved":
                    days = int(args.get("days", 7))
                    cat = args.get("category", "all")
                    notes = list_saved_notes(days=days, category=cat)
                    resp_content = json.dumps(notes, indent=2)
                elif tool_name == "search_vault":
                    q = args.get("query", "")
                    notes = search_vault_notes(q)
                    resp_content = json.dumps(notes, indent=2)
                elif tool_name == "get_note":
                    note_id = args.get("note_id")
                    note_p = NOTES_DIR / f"{note_id}.md"
                    if note_p.exists():
                        with open(note_p, "r", encoding="utf-8") as f:
                            resp_content = f.read()
                    else:
                        resp_content = f"Note '{note_id}' not found."
                elif tool_name == "get_inbox":
                    if INBOX_FILE.exists():
                        with open(INBOX_FILE, "r", encoding="utf-8") as f:
                            resp_content = f.read()
                    else:
                        resp_content = "INBOX.md is empty."
                else:
                    resp_content = f"Unknown tool: {tool_name}"

                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": resp_content}
                        ]
                    }
                }
            else:
                resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        except Exception as e:
            sys.stderr.write(f"Error handling request: {e}\n")
            sys.stderr.flush()

if __name__ == "__main__":
    run_mcp_server()
