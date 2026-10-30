"""
Issue fetch node.

Fetches issues from an issue tracking system (Trello, GitHub, Jira, etc.),
preparing them for processing by the agent.
"""

import logging
from datetime import datetime

from cleankoda.agent.runtime import RuntimeSettings
from cleankoda.agent.state import AgentState
from cleankoda.core.extern.its.issue_tracking_system import Issue, IssueTrackingSystem
from cleankoda.core.extern.vcs.version_control_system import VersionControlSystem
from cleankoda.core.services.issues_service import fetch_comments_since
from cleankoda.core.types import IssueStateType, WorkingState

logger = logging.getLogger(__name__)


def create_issue_fetch_node(runtime: RuntimeSettings):
    """Creates an issue fetch node for the agent graph."""
    its: IssueTrackingSystem = runtime.its
    vcs: VersionControlSystem = runtime.vcs

    async def issue_fetch(state: AgentState) -> dict:  # pylint: disable=unused-argument
        """
        Fetches the first issue from the issue tracking system in a specified list.
        """
        if state["current_node"] != "issue_fetch":
            logger.info("--- ISSUE FETCH node ---")

        try:
            issue = await _resolve_issue(state["issue_id"], its)

            # if no issue is found, return
            if not issue:
                logger.info("There is no current issue to work on.")
                return {"issue_id": None}

            # if issue is found, determine if it is active, i.e. in todo, in progress or in review
            issue_is_active = issue.state_type in [
                IssueStateType.TODO,
                IssueStateType.IN_PROGRESS,
                IssueStateType.IN_REVIEW,
            ]
            issue_from_todo = issue.state_type == IssueStateType.TODO

            comments = []
            issue_read_comments_at = state["issue_read_comments_at"]
            pr_review_message = ""
            if issue_is_active and issue.state_type == IssueStateType.IN_PROGRESS:
                # otherwise fetch review comments from issue tracking system and pr, in order
                # to give further information from user
                comments = await fetch_comments_since(
                    its,
                    issue.id,
                    issue_read_comments_at,
                )
                issue_read_comments_at = datetime.now()
                pr_review_message = await _fetch_pr_review_info(vcs, state, issue.id)

            if issue_is_active and issue_from_todo:
                # if the issue is new and has the state "todo" then move it to "in progress"
                await its.move_issue_to_state(
                    issue_id=issue.id, target_state_type=IssueStateType.IN_PROGRESS
                )

            return {
                "current_node": "issue_fetch",
                "issue_id": issue.id,
                "issue_name": issue.name,
                "issue_description": issue.description,
                "issue_state": IssueStateType.IN_PROGRESS
                if issue_is_active
                else IssueStateType.UNKNOWN,
                "issue_comments": comments,
                "issue_is_active": issue_is_active,
                "issue_read_comments_at": issue_read_comments_at,
                "issue_from_todo": issue_from_todo,
                "issue_url": issue.url,
                "pr_review_message": pr_review_message,
                "working_state": WorkingState.WORKING.value,
            }

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error fetching issue: %s", e)
            return {"issue_id": None}

    return issue_fetch


async def _resolve_issue(issue_id: str | None, its: IssueTrackingSystem) -> Issue | None:
    """
    Get the last issue (with issue_id) or create a new issue.
    See specification in issue-management.md.
    Returns: the issue
    """

    if issue_id:
        logger.info("Fetching issue from issue tracking system: %s", issue_id)

        try:
            issue = await its.get_issue_by_id(issue_id)
        except Exception:  # pylint: disable=broad-exception-caught
            issue = None

        if issue:
            # check if issue in review or in progress
            if issue.state_type == IssueStateType.IN_REVIEW:
                logger.info("Issue is in review. Wait for user action.")
                return None

            if issue.state_type == IssueStateType.IN_PROGRESS:
                logger.info("Issue is in progress. Add review comments.")
                return issue

            logger.info("Last issue found but it is not in review or in progress.")
            return issue

    # Get a new issue from todo
    logger.info("Fetching new issue from todo.")
    issue = await its.get_next_issue_from_state(IssueStateType.TODO)
    return issue


async def _fetch_pr_review_info(vcs: VersionControlSystem, state: AgentState, issue_id: str) -> str:
    """
    Fetch PR review info if a PR exists for the issue.

    Args:
        issue_id: The issue ID to check

    Returns:
        Tuple of (is_approved, formatted_review_message)
        - is_approved: True if PR is approved or no PR exists
        - formatted_review_message: Formatted message for SystemMessage, empty if approved
    """
    repo_pr_number = state.get("repo_pr_number")
    pr = None
    if repo_pr_number:
        pr = await vcs.get_pr(repo_pr_number)

    if not pr or pr.state in ["APPROVED", "MERGED", "CLOSED"]:
        return ""  # besser: wenn Approved dann issue auf done schieben!

    is_approved, rejection_reviews, code_comments = await vcs.get_pr_review_status(pr.number)

    if is_approved:
        logger.info("PR #%d for issue %s is approved", pr.number, issue_id)
        return ""

    logger.info(
        "PR #%d for issue %s has %d rejections and %d code comments",
        pr.number,
        issue_id,
        len(rejection_reviews),
        len(code_comments),
    )

    return vcs.format_pr_review_status(pr.html_url or "", rejection_reviews, code_comments)
