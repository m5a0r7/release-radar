from radar.ingest.linking import extract_item_keys, linking_text


def test_extracts_unique_sorted_keys() -> None:
    title = "KAFKA-20: fix (also kafka-3, KAFKA-20 backport)"

    assert extract_item_keys(title, "KAFKA") == ["KAFKA-3", "KAFKA-20"]


def test_ignores_other_projects_and_embedded_matches() -> None:
    assert extract_item_keys("MINOR: bump; FLINK-1; XKAFKA-2", "KAFKA") == []


def test_github_issue_references_come_from_title_and_body() -> None:
    text = linking_text("Fix crash (#12)", "Closes #7, see apache/other#9 and &#39;", "github")

    assert extract_item_keys(text, "acme/widgets", "github") == ["#7", "#12"]


def test_jira_linking_ignores_the_body() -> None:
    assert linking_text("KAFKA-1: fix", "Also KAFKA-2", "jira") == "KAFKA-1: fix"
