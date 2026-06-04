"""src.cli.prompts_cli — CLI for prompt label management (PLAN-F-014 TASK-006).

Usage:
    stokai prompts status
    stokai prompts promote <role_id> --label production
    stokai prompts rollback <role_id> --to-version <sha>

The CLI reads LANGFUSE_HOST and DATABASE_URL from the environment. When
DATABASE_URL is not set the commands that require DB access will fail with
a clear error message.

Commands are implemented with argparse to avoid adding an extra dependency
(click is not in pyproject.toml).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"

CANONICAL_ROLE_IDS: list[str] = [
    "exposure_analyst",
    "historical_context",
    "anomaly_detector",
    "recommendation",
    "narrative_writer",
    "morning_brief_analyst",
    "watchlist_analyst",
    "earnings_analyst",
    "qa_analyst",
    "recommendation_judge",
    "factuality_judge",
    "calibration_judge",
    "event_classifier",
    "ticker_extractor",
    "sentiment_analyzer",
]


def _build_services():
    """Construct GitPromptLoader and PromptLabelService from environment."""
    from src.ai.prompts.prompt_loader import GitPromptLoader
    from src.ai.prompts.label_service import PromptLabel, PromptLabelService

    loader = GitPromptLoader(prompts_root=PROMPTS_ROOT)
    return loader, PromptLabel, PromptLabelService


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_status(_args: argparse.Namespace) -> int:
    """Print the current git SHA and production label for all 15 prompts."""
    loader, PromptLabel, PromptLabelService = _build_services()

    rows = []
    for role_id in CANONICAL_ROLE_IDS:
        try:
            sha = loader.get_sha(role_id)
        except FileNotFoundError:
            sha = "MISSING"
        rows.append({"role_id": role_id, "git_sha": sha})

    print(json.dumps(rows, indent=2))
    return 0


async def _async_promote(role_id: str, label_str: str) -> int:
    """Async implementation for promote command."""
    from src.ai.prompts.prompt_loader import GitPromptLoader
    from src.ai.prompts.label_service import PromptLabel, PromptLabelService
    from src.storage.repositories.prompt_publication_repository import (
        PromptPublicationRepository,
    )
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    try:
        label = PromptLabel(label_str)
    except ValueError:
        print(
            f"ERROR: Invalid label {label_str!r}. "
            "Must be one of: production, staging, canary, experimental",
            file=sys.stderr,
        )
        return 1

    loader = GitPromptLoader(prompts_root=PROMPTS_ROOT)

    try:
        version_sha = loader.get_sha(role_id)
    except FileNotFoundError:
        print(f"ERROR: No prompt file found for role_id={role_id!r}.", file=sys.stderr)
        return 1

    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        repo = PromptPublicationRepository(session)
        service = PromptLabelService(repo)
        await service.apply_label(role_id=role_id, version_sha=version_sha, label=label)
        await session.commit()

    print(
        json.dumps(
            {
                "action": "promote",
                "role_id": role_id,
                "label": label_str,
                "version_sha": version_sha,
            },
            indent=2,
        )
    )
    await engine.dispose()
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    """Promote a prompt to the given label."""
    return asyncio.run(_async_promote(args.role_id, args.label))


async def _async_rollback(role_id: str, to_version: str) -> int:
    """Async implementation for rollback command."""
    from src.ai.prompts.label_service import PromptLabelService
    from src.storage.repositories.prompt_publication_repository import (
        PromptPublicationRepository,
    )
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        repo = PromptPublicationRepository(session)
        service = PromptLabelService(repo)
        result = await service.rollback(role_id=role_id, to_version=to_version)
        await session.commit()

    print(
        json.dumps(
            {
                "action": "rollback",
                "role_id": result.role_id,
                "previous_version": result.previous_version,
                "rolled_back_to": result.rolled_back_to,
                "effective_at": result.effective_at.isoformat(),
            },
            indent=2,
        )
    )
    await engine.dispose()
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    """Roll back a prompt's production label to a previous version."""
    return asyncio.run(_async_rollback(args.role_id, args.to_version))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="stokai prompts",
        description="StokAI prompt label management CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    subparsers.add_parser(
        "status",
        help="Show current git SHA for all 15 canonical prompts",
    )

    # promote
    promote_parser = subparsers.add_parser(
        "promote",
        help="Assign a label to the current git SHA of a prompt",
    )
    promote_parser.add_argument("role_id", help="Prompt role identifier")
    promote_parser.add_argument(
        "--label",
        required=True,
        choices=["production", "staging", "canary", "experimental"],
        help="Label to assign",
    )

    # rollback
    rollback_parser = subparsers.add_parser(
        "rollback",
        help="Roll back production label to a specific version SHA",
    )
    rollback_parser.add_argument("role_id", help="Prompt role identifier")
    rollback_parser.add_argument(
        "--to-version",
        required=True,
        dest="to_version",
        help="Target version SHA to roll back to",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the prompts CLI."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)

    command_map = {
        "status": cmd_status,
        "promote": cmd_promote,
        "rollback": cmd_rollback,
    }

    handler = command_map.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    exit_code = handler(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
