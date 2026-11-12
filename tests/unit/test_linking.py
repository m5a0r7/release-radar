from radar.ingest.linking import extract_item_keys


def test_extracts_unique_sorted_keys() -> None:
    title = "KAFKA-20: fix (also kafka-3, KAFKA-20 backport)"

    assert extract_item_keys(title, "KAFKA") == ["KAFKA-3", "KAFKA-20"]


def test_ignores_other_projects_and_embedded_matches() -> None:
    assert extract_item_keys("MINOR: bump; FLINK-1; XKAFKA-2", "KAFKA") == []
