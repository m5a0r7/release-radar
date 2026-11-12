import re
from functools import lru_cache


@lru_cache(maxsize=64)
def _key_pattern(project_key: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(project_key)}-(\d+)\b", re.IGNORECASE)


def extract_item_keys(text: str, project_key: str) -> list[str]:
    """Work-item keys referenced in free text, e.g. 'KAFKA-123: fix ...' -> ['KAFKA-123']."""
    numbers = {int(match) for match in _key_pattern(project_key).findall(text)}
    return [f"{project_key}-{number}" for number in sorted(numbers)]
