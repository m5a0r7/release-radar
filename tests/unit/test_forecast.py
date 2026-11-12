from datetime import date

from radar.insights.forecast import monte_carlo_completion

START = date(2026, 3, 1)


def test_nothing_remaining_finishes_immediately() -> None:
    result = monte_carlo_completion(0, [3, 4], START, date(2026, 3, 10))

    assert result.p50_date == START
    assert result.on_time_probability == 1.0


def test_zero_throughput_cannot_be_forecast() -> None:
    result = monte_carlo_completion(10, [0, 0, 0], START, date(2026, 3, 10))

    assert result.p50_date is None
    assert result.on_time_probability == 0.0


def test_constant_throughput_gives_an_exact_date() -> None:
    result = monte_carlo_completion(10, [5, 5, 5], START, None)

    assert result.p50_date == date(2026, 3, 15)
    assert result.p85_date == date(2026, 3, 15)
    assert result.on_time_probability is None


def test_forecast_is_deterministic_and_ordered() -> None:
    samples = [2, 9, 4, 0, 7, 5]
    first = monte_carlo_completion(40, samples, START, date(2026, 4, 30))
    second = monte_carlo_completion(40, samples, START, date(2026, 4, 30))

    assert first == second
    assert first.p50_date is not None and first.p85_date is not None
    assert first.p50_date <= first.p85_date
    assert first.on_time_probability is not None and 0 < first.on_time_probability < 1


def test_later_target_is_never_less_likely() -> None:
    samples = [2, 9, 4, 0, 7, 5]
    early = monte_carlo_completion(40, samples, START, date(2026, 4, 1))
    late = monte_carlo_completion(40, samples, START, date(2026, 5, 1))

    assert early.on_time_probability is not None and late.on_time_probability is not None
    assert early.on_time_probability <= late.on_time_probability
