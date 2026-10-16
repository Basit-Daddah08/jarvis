import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.skills.queue_manager import SkillQueueManager

def main():
    manager = SkillQueueManager(approvals_dir=PROJECT_ROOT / "vault" / "approvals")

    parser = argparse.ArgumentParser(description="Manage JARVIS skill approvals")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("list", help="List all skills awaiting owner approval")

    approve_parser = subparsers.add_parser("approve", help="Approve and install a skill")
    approve_parser.add_argument("skill_name", help="Name of skill to approve")

    reject_parser = subparsers.add_parser("reject", help="Reject and delete a skill")
    reject_parser.add_argument("skill_name", help="Name of skill to reject")

    args = parser.parse_args()

    if args.command == "list" or not args.command:
        pending = manager.list_pending()
        if not pending:
            print("No skills awaiting approval. Queue is empty!")
            return
        print(f"\nSkills Awaiting Your Approval ({len(pending)}):")
        print("-" * 40)
        for s in pending:
            print(f"- {s}  --> (inspect at vault/approvals/{s}/APPROVAL_REQUEST.md)")
        print("\nTo approve: python src/skills/approve.py approve <skill_name>")
        print("To reject:  python src/skills/approve.py reject <skill_name>\n")

    elif args.command == "approve":
        if manager.approve_skill(args.skill_name):
            print(f"Successfully approved and installed skill: {args.skill_name}")
        else:
            print(f"Skill '{args.skill_name}' not found in approval queue.")

    elif args.command == "reject":
        if manager.reject_skill(args.skill_name):
            print(f"Rejected and removed skill: {args.skill_name}")
        else:
            print(f"Skill '{args.skill_name}' not found in approval queue.")

if __name__ == "__main__":
    main()
