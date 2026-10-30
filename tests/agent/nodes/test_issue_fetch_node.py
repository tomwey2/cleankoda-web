"""
Tests for the issue fetch node.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cleankoda.agent.nodes.issue_fetch_node import create_issue_fetch_node
from cleankoda.core.extern.its.issue_tracking_system import Issue
from cleankoda.core.extern.vcs.version_control_system import PRReview, PullRequest
from cleankoda.core.types import IssueStateType


@pytest.fixture(name="mock_its")
def fixture_mock_its():
    """Fixture for an issue tracking system with one issue in "In Progress"."""
    its = MagicMock()
    its.get_issue_by_id = AsyncMock(
        return_value=Issue(
            id="card1",
            name="Test Issue",
            description="Test Description",
            state_type=IssueStateType.IN_PROGRESS,
            state_id="list2",
            state_name="In Progress",
        )
    )
    its.get_comments_from_issue = AsyncMock(return_value=[])
    return its


@pytest.fixture(name="mock_vcs")
def fixture_mock_vcs():
    """Fixture for a version control system with an open PR that has requested changes."""
    vcs = MagicMock()
    vcs.get_pr = AsyncMock(
        return_value=PullRequest(
            number=12,
            title="Test Issue",
            body="",
            html_url="https://github.com/owner/repo/pull/12",
            state="open",
            head_branch="feature/card1",
            base_branch="master",
            created_at="2026-01-01T12:00:00Z",
            updated_at="2026-01-01T13:00:00Z",
        )
    )
    vcs.get_pr_review_status = AsyncMock(
        return_value=(
            False,
            [
                PRReview(
                    id="review1",
                    reviewer="reviewer",
                    state="CHANGES_REQUESTED",
                    body="Please rename the method",
                    submitted_at="2026-01-01T14:00:00Z",
                )
            ],
            [],
        )
    )
    vcs.format_pr_review_status = MagicMock(return_value="PULL REQUEST REVIEW FEEDBACK")
    return vcs


@pytest.mark.asyncio
async def test_issue_fetch_node_with_pr_review(mock_its, mock_vcs):
    """Test issue fetch with PR review feedback when the issue is back in In Progress."""
    issue_fetch = create_issue_fetch_node(MagicMock(its=mock_its, vcs=mock_vcs))
    result = await issue_fetch(
        {
            "current_node": None,
            "issue_id": "card1",
            "issue_read_comments_at": None,
            "repo_pr_number": 12,
        }
    )

    assert result["issue_id"] == "card1"
    assert result["pr_review_message"] == "PULL REQUEST REVIEW FEEDBACK"
    mock_vcs.get_pr.assert_awaited_once_with(12)
    mock_vcs.get_pr_review_status.assert_awaited_once_with(12)
