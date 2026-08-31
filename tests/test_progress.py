import io

from warehouse_investigator.progress import InvestigationProgress, format_investigation_status


def test_investigation_status_shows_spinner_ticket_and_elapsed() -> None:
    text = format_investigation_status("INC-001", elapsed_s=12.3, frame=0)

    assert "Investigating INC-001" in text
    assert "12.3s" in text
    assert text.startswith("|")


def test_investigation_status_animates_spinner() -> None:
    first = format_investigation_status("INC-001", elapsed_s=1.0, frame=0)
    second = format_investigation_status("INC-001", elapsed_s=1.0, frame=1)

    assert first[0] != second[0]


def test_non_live_progress_prints_one_line_when_work_starts() -> None:
    stream = io.StringIO()
    progress = InvestigationProgress(["INC-001"], stream=stream, live=False)
    progress.start()
    progress.mark_working("INC-001")
    progress.close()

    assert stream.getvalue() == "Investigating INC-001...\n"


def test_live_progress_hides_cursor_and_rewrites_status() -> None:
    stream = io.StringIO()
    progress = InvestigationProgress(["INC-001"], stream=stream, live=True, interval_seconds=0)
    progress.start()
    progress.mark_working("INC-001")
    progress.close()

    output = stream.getvalue()
    assert "\x1b[?25l" in output
    assert "\x1b[?25h" in output
    assert "Investigating INC-001" in output


def test_live_progress_erases_status_on_close() -> None:
    stream = io.StringIO()
    progress = InvestigationProgress(["INC-001"], stream=stream, live=True, interval_seconds=0)
    progress.start()
    progress.mark_working("INC-001")
    progress.close()

    output = stream.getvalue()
    assert "\x1b[2K" in output
    assert output.endswith("\x1b[?25h")
