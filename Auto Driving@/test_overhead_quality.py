from build_raw_session_dataset import overhead_safe


def test_overhead_quality_requires_clearance_through_context():
    times = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    assert overhead_safe(0.3, (times, [True] * len(times)))

    safe = [True] * len(times)
    safe[4] = False
    assert not overhead_safe(0.3, (times, safe))


def test_overhead_quality_rejects_missing_video_and_short_window():
    assert not overhead_safe(1.0, ([0.0, 0.1], [True, True]))
    assert not overhead_safe(0.3, ([0.3], [True]))
