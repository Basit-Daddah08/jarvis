from datetime import date
from pathlib import Path
from typing import List, Optional

class NoteWriter:
    """Writes structured Markdown notes and updates daily INBOX.md."""

    def __init__(self, notes_dir: Path, inbox_file: Path):
        self.notes_dir = Path(notes_dir)
        self.inbox_file = Path(inbox_file)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_file.parent.mkdir(parents=True, exist_ok=True)

    def write_note(
        self,
        item_id: str,
        creator: str,
        saved_at: str,
        title: str,
        transcript: str,
        note_type: str = "other",
        tools: Optional[List[str]] = None,
        links: Optional[List[str]] = None,
        summary: Optional[str] = None,
        steps: Optional[List[str]] = None,
    ) -> Path:
        """Write a single video note in standard YAML front-matter format."""
        tools = tools or []
        links = links or []
        summary = summary or ""
        steps = steps or []
        saved_at = saved_at or date.today().isoformat()

        # Format front matter YAML
        tools_formatted = "[" + ", ".join(f'"{t}"' for t in tools) + "]"
        links_formatted = "[" + ", ".join(f'"{link}"' for link in links) + "]"

        content_parts = [
            "---",
            f"id: {item_id}",
            f"saved_at: {saved_at}",
            f'creator: "{creator}"',
            f"type: {note_type}",
            f"tools: {tools_formatted}",
            f"links: {links_formatted}",
            "---",
            "",
            f"# {title}",
            "",
        ]

        if note_type in ["tool", "ai"]:
            content_parts.extend([
                "## Summary",
                summary or "(Summary will be generated during Phase 2 classification)",
                "",
                "## Steps",
            ])
            if steps:
                for idx, step in enumerate(steps, 1):
                    content_parts.append(f"{idx}. {step}")
            else:
                content_parts.append("1. See full transcript below.")
            content_parts.append("")

        content_parts.extend([
            "## Transcript",
            transcript.strip(),
            ""
        ])

        note_filename = f"{item_id}.md"
        note_path = self.notes_dir / note_filename
        with open(note_path, "w", encoding="utf-8") as f:
            f.write("\n".join(content_parts))

        # Append entry to daily INBOX.md
        self._append_to_inbox(
            item_id=item_id,
            title=title,
            creator=creator,
            note_type=note_type,
            summary=summary,
            tools=tools,
            note_path=note_path
        )

        return note_path

    def _append_to_inbox(
        self,
        item_id: str,
        title: str,
        creator: str,
        note_type: str,
        summary: str,
        tools: List[str],
        note_path: Path
    ):
        """Append a note summary card to INBOX.md."""
        today_heading = f"## {date.today().isoformat()}"
        
        inbox_content = ""
        if self.inbox_file.exists():
            with open(self.inbox_file, "r", encoding="utf-8") as f:
                inbox_content = f.read()

        entry_lines = [
            f"### [{title}](notes/{item_id}.md)",
            f"- **Creator:** {creator}",
            f"- **Type:** `{note_type}`",
        ]
        if tools:
            entry_lines.append(f"- **Tools:** {', '.join(tools)}")
        if summary:
            entry_lines.append(f"- **Summary:** {summary}")
        entry_lines.append("")

        if today_heading not in inbox_content:
            inbox_content += f"\n{today_heading}\n\n"
        
        inbox_content += "\n".join(entry_lines) + "\n"

        with open(self.inbox_file, "w", encoding="utf-8") as f:
            f.write(inbox_content)
