"""Unit tests for StdoutCollector."""
from uuid import uuid4

from src.pipeline.stdout_collector import StdoutCollector


class TestStdoutCollector:
    """Tests for StdoutCollector."""

    def test_capture_and_retrieve(self) -> None:
        collector = StdoutCollector()
        sid = uuid4()
        collector.capture(sid, "line 1\nline 2\nline 3")
        output = collector.get_output(sid)
        assert output == ["line 1", "line 2", "line 3"]

    def test_capture_empty_text(self) -> None:
        collector = StdoutCollector()
        sid = uuid4()
        collector.capture(sid, "")
        assert collector.get_output(sid) == []

    def test_capture_multiple_times(self) -> None:
        collector = StdoutCollector()
        sid = uuid4()
        collector.capture(sid, "first")
        collector.capture(sid, "second")
        collector.capture(sid, "third")
        output = collector.get_output(sid)
        assert output == ["first", "second", "third"]

    def test_get_output_limit(self) -> None:
        collector = StdoutCollector()
        sid = uuid4()
        for i in range(10):
            collector.capture(sid, f"line {i}")
        output = collector.get_output(sid, limit=3)
        assert output == ["line 7", "line 8", "line 9"]

    def test_get_output_nonexistent_strategy(self) -> None:
        collector = StdoutCollector()
        assert collector.get_output(uuid4()) == []

    def test_clear_buffer(self) -> None:
        collector = StdoutCollector()
        sid = uuid4()
        collector.capture(sid, "line 1\nline 2")
        collector.clear(sid)
        assert collector.get_output(sid) == []

    def test_clear_nonexistent_strategy(self) -> None:
        collector = StdoutCollector()
        collector.clear(uuid4())  # Should not raise

    def test_clear_all(self) -> None:
        collector = StdoutCollector()
        sid1 = uuid4()
        sid2 = uuid4()
        collector.capture(sid1, "strategy 1")
        collector.capture(sid2, "strategy 2")
        collector.clear_all()
        assert collector.get_output(sid1) == []
        assert collector.get_output(sid2) == []

    def test_line_count(self) -> None:
        collector = StdoutCollector()
        sid = uuid4()
        collector.capture(sid, "a\nb\nc")
        assert collector.get_line_count(sid) == 3

    def test_line_count_nonexistent(self) -> None:
        collector = StdoutCollector()
        assert collector.get_line_count(uuid4()) == 0

    def test_buffer_size(self) -> None:
        collector = StdoutCollector()
        sid = uuid4()
        collector.capture(sid, "hello")
        assert collector.get_buffer_size(sid) == 5

    def test_buffer_size_nonexistent(self) -> None:
        collector = StdoutCollector()
        assert collector.get_buffer_size(uuid4()) == 0

    def test_all_strategy_ids(self) -> None:
        collector = StdoutCollector()
        sid1 = uuid4()
        sid2 = uuid4()
        collector.capture(sid1, "test")
        collector.capture(sid2, "test")
        ids = collector.get_all_strategy_ids()
        assert set(ids) == {sid1, sid2}

    def test_to_dict(self) -> None:
        collector = StdoutCollector()
        sid = uuid4()
        collector.capture(sid, "line 1\nline 2")
        result = collector.to_dict(sid)
        assert result["strategy_id"] == str(sid)
        assert result["line_count"] == 2
        assert result["buffer_size"] == 12  # "line 1" (6) + "line 2" (6)

    def test_buffer_size_limit(self) -> None:
        collector = StdoutCollector(max_buffer_size=20)
        sid = uuid4()
        collector.capture(sid, "a" * 15)
        collector.capture(sid, "b" * 10)
        # Oldest lines should be removed to fit new data
        assert collector.get_buffer_size(sid) <= 20

    def test_max_lines_limit(self) -> None:
        collector = StdoutCollector(max_lines=5)
        sid = uuid4()
        for i in range(10):
            collector.capture(sid, f"line {i}")
        output = collector.get_output(sid)
        assert len(output) == 5
        assert output[0] == "line 5"

    def test_concurrent_capture(self) -> None:
        import threading

        collector = StdoutCollector()
        sid = uuid4()

        def capture_lines(start: int) -> None:
            for i in range(start, start + 100):
                collector.capture(sid, f"line {i}")

        threads = [threading.Thread(target=capture_lines, args=(i * 100,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert collector.get_line_count(sid) == 500
