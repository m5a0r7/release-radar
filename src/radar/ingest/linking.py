import re
from functools import lru_cache

# `#123`, but not `owner/repo#123` (another repository), `&#123;` (an HTML entity) or `abc#1`.
GITHUB_ISSUE_RE = re.compile(r"(?<![\w/&#])#(\d{1,9})\b")


@lru_cache(maxsize=64)
def _key_pattern(project_key: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(project_key)}-(\d+)\b", re.IGNORECASE)


def extract_item_keys(text: str, project_key: str, tracker: str = "jira") -> list[str]:
    """Work-item keys referenced in free text.

    Jira: 'KAFKA-123: fix ...' -> ['KAFKA-123']. GitHub issues: 'Fixes #12' -> ['#12'].
    """
    if tracker == "github":
        return [f"#{n}" for n in sorted({int(m) for m in GITHUB_ISSUE_RE.findall(text)})]
    numbers = {int(match) for match in _key_pattern(project_key).findall(text)}
    return [f"{project_key}-{number}" for number in sorted(numbers)]


def linking_text(title: str, body: str, tracker: str) -> str:
    """GitHub PRs usually reference issues in the body ("Fixes #12"); Jira projects use titles."""
    return f"{title}\n{body}" if tracker == "github" else title
