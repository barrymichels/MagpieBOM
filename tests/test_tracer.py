import json
from magpiebom.tracer import Tracer


def test_step_writes_jsonl_event(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    t.step("Trying Mouser API")
    t.close()
    lines = (tmp_path / t.filename).read_text().strip().split("\n")
    event = json.loads(lines[0])
    assert event["type"] == "step"
    assert event["message"] == "Trying Mouser API"
    assert "ts" in event


def test_detail_writes_with_extra_data(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    t.detail("Found 3 images", urls=["a.jpg", "b.jpg", "c.jpg"])
    t.close()
    lines = (tmp_path / t.filename).read_text().strip().split("\n")
    event = json.loads(lines[0])
    assert event["type"] == "detail"
    assert event["urls"] == ["a.jpg", "b.jpg", "c.jpg"]


def test_http_truncates_body_at_2kb(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    long_body = "x" * 5000
    t.http(url="https://api.mouser.com/search", method="POST", status=200,
           headers={"content-type": "application/json"}, body=long_body, duration_ms=150.5)
    t.close()
    lines = (tmp_path / t.filename).read_text().strip().split("\n")
    event = json.loads(lines[0])
    assert event["type"] == "http"
    assert len(event["body"]) == 2048
    assert event["duration_ms"] == 150.5


def test_http_handles_none_body(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    t.http(url="https://example.com", method="GET", status=200, headers={}, body=None, duration_ms=50)
    t.close()
    lines = (tmp_path / t.filename).read_text().strip().split("\n")
    event = json.loads(lines[0])
    assert event["body"] is None


def test_llm_writes_full_prompt_and_response(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    t.llm(purpose="validate_image", prompt="Is this a resistor?",
           response='{"match": true}', tokens={"prompt": 100, "completion": 20}, duration_ms=500)
    t.close()
    lines = (tmp_path / t.filename).read_text().strip().split("\n")
    event = json.loads(lines[0])
    assert event["type"] == "llm"
    assert event["purpose"] == "validate_image"
    assert event["prompt"] == "Is this a resistor?"
    assert event["response"] == '{"match": true}'
    assert event["tokens"] == {"prompt": 100, "completion": 20}


def test_image_writes_metadata(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    t.image(url="https://example.com/part.jpg", path="/tmp/part.jpg",
            width=640, height=480, size_bytes=48000, format="JPEG")
    t.close()
    lines = (tmp_path / t.filename).read_text().strip().split("\n")
    event = json.loads(lines[0])
    assert event["type"] == "image"
    assert event["width"] == 640
    assert event["size_bytes"] == 48000


def test_error_writes_exception_info(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    try:
        raise ConnectionError("timeout")
    except ConnectionError as e:
        t.error("Download failed", exception=e, url="https://example.com")
    t.close()
    lines = (tmp_path / t.filename).read_text().strip().split("\n")
    event = json.loads(lines[0])
    assert event["type"] == "error"
    assert event["message"] == "Download failed"
    assert "ConnectionError" in event["exception"]
    assert event["url"] == "https://example.com"


def test_result_writes_closing_event(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    t.result({"part_number": "LM7805", "image_path": "./parts/LM7805.jpg"})
    t.close()
    lines = (tmp_path / t.filename).read_text().strip().split("\n")
    event = json.loads(lines[0])
    assert event["type"] == "result"
    assert event["data"]["image_path"] == "./parts/LM7805.jpg"


def test_multiple_events_produce_multiple_lines(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    t.step("Step 1")
    t.step("Step 2")
    t.detail("Detail 1")
    t.close()
    lines = (tmp_path / t.filename).read_text().strip().split("\n")
    assert len(lines) == 3


def test_filename_contains_part_number(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    assert "LM7805" in t.filename
    assert t.filename.endswith(".jsonl")
    t.close()


def test_step_prints_to_stderr(tmp_path, capsys):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    t.step("Trying Mouser API")
    t.close()
    assert "Trying Mouser API" in capsys.readouterr().err


def test_detail_hidden_from_stderr_when_not_verbose(tmp_path, capsys):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    t.detail("Internal detail")
    t.close()
    assert "Internal detail" not in capsys.readouterr().err


def test_detail_shown_on_stderr_when_verbose(tmp_path, capsys):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=True)
    t.detail("Verbose detail")
    t.close()
    assert "Verbose detail" in capsys.readouterr().err


def test_error_always_prints_to_stderr(tmp_path, capsys):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    t.error("Something broke")
    t.close()
    assert "Something broke" in capsys.readouterr().err


def test_context_manager_closes_file(tmp_path):
    with Tracer("LM7805", trace_dir=str(tmp_path), verbose=False) as t:
        t.step("Hello")
    assert t._file.closed


def test_trace_path_property(tmp_path):
    t = Tracer("LM7805", trace_dir=str(tmp_path), verbose=False)
    assert str(tmp_path) in t.trace_path
    assert t.trace_path.endswith(".jsonl")
    t.close()
