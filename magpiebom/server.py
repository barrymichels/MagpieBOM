# magpiebom/server.py
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, redirect, render_template, request, send_from_directory, stream_with_context, url_for

from magpiebom.cli import run_pipeline

app = Flask(__name__)

PARTS_DIR = Path(os.environ.get("MAGPIEBOM_PARTS_DIR", "./parts")).resolve()


def _load_results(batch_id: str) -> dict:
    path = PARTS_DIR / batch_id / "results.json"
    return json.loads(path.read_text())


def _save_results(batch_id: str, data: dict):
    path = PARTS_DIR / batch_id / "results.json"
    path.write_text(json.dumps(data, indent=2))


def _result_to_part(part_number: str, result: dict) -> dict:
    """Convert a run_pipeline result to a JSON-safe part dict with relative paths."""
    image_path = result.get("image_path")
    if image_path:
        image_path = os.path.basename(image_path)

    datasheet_path = result.get("datasheet_path")
    if datasheet_path:
        datasheet_path = os.path.basename(datasheet_path)

    return {
        "part_number": part_number,
        "image_path": image_path,
        "datasheet_url": result.get("datasheet_url"),
        "datasheet_path": datasheet_path,
        "description": result.get("description", ""),
        "source": result.get("source") or "not_found",
        "source_url": result.get("source_url", ""),
    }


@app.route("/")
def home():
    batches = []
    if PARTS_DIR.exists():
        for d in sorted(PARTS_DIR.iterdir(), reverse=True):
            results_file = d / "results.json"
            if d.is_dir() and results_file.exists():
                try:
                    data = json.loads(results_file.read_text())
                except (json.JSONDecodeError, OSError):
                    continue
                parts = data.get("parts", [])
                found = sum(1 for p in parts if p.get("image_path"))
                pending = sum(1 for p in parts if p.get("image_path") is None)
                batches.append({
                    "id": d.name,
                    "created": data.get("created", ""),
                    "total": len(parts),
                    "found": found,
                    "not_found": len(parts) - found - pending,
                    "pending": pending,
                })
    return render_template("home.html", batches=batches)


@app.route("/batch/new", methods=["POST"])
def batch_new():
    raw = request.form.get("parts", "")
    part_numbers = [p.strip() for p in raw.splitlines() if p.strip()]
    if not part_numbers:
        return redirect(url_for("home"))

    batch_id = f"batch_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    batch_dir = PARTS_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "parts": [
            {
                "part_number": pn,
                "image_path": None,
                "datasheet_url": None,
                "datasheet_path": None,
                "description": "",
                "source": "",
                "source_url": "",
            }
            for pn in part_numbers
        ],
    }
    _save_results(batch_id, data)
    return redirect(url_for("batch_view", batch_id=batch_id))


@app.route("/batch/<batch_id>")
def batch_view(batch_id: str):
    data = _load_results(batch_id)
    parts = data["parts"]
    found = sum(1 for p in parts if p.get("image_path"))
    pending = sum(1 for p in parts if p.get("image_path") is None and not p.get("source"))
    not_found = sum(1 for p in parts if p.get("image_path") is None and p.get("source") == "not_found")
    return render_template(
        "batch.html",
        batch_id=batch_id,
        parts=parts,
        found=found,
        not_found=not_found,
        pending=pending,
        total=len(parts),
    )


@app.route("/batch/<batch_id>/stream")
def batch_stream(batch_id: str):
    def generate():
        data = _load_results(batch_id)
        batch_dir = str(PARTS_DIR / batch_id)

        for i, part in enumerate(data["parts"]):
            if part.get("image_path") is not None or part.get("source") == "not_found":
                continue

            pn = part["part_number"]
            yield f"event: status\ndata: {json.dumps({'part_number': pn, 'index': i, 'status': 'searching'})}\n\n"

            try:
                result = run_pipeline(
                    part_number=pn,
                    output_dir=batch_dir,
                    no_open=True,
                    verbose=False,
                )
            except Exception as e:
                print(f"Pipeline error for {pn}: {e}", file=sys.stderr)
                result = {"part_number": pn, "image_path": None, "source": "", "source_url": "", "description": "", "datasheet_url": None, "datasheet_path": None}

            data["parts"][i] = _result_to_part(pn, result)
            _save_results(batch_id, data)

            yield f"event: result\ndata: {json.dumps(data['parts'][i] | {'index': i})}\n\n"

        yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/batch/<batch_id>/retry/<part_number>", methods=["GET", "POST"])
def batch_retry(batch_id: str, part_number: str):
    def generate():
        data = _load_results(batch_id)
        batch_dir = PARTS_DIR / batch_id

        # Find the part index
        idx = None
        for i, p in enumerate(data["parts"]):
            if p["part_number"] == part_number:
                idx = i
                break

        if idx is None:
            yield f"event: error\ndata: {json.dumps({'error': 'part not found'})}\n\n"
            return

        # Delete old files
        old = data["parts"][idx]
        if old.get("image_path"):
            (batch_dir / old["image_path"]).unlink(missing_ok=True)
        if old.get("datasheet_path"):
            (batch_dir / old["datasheet_path"]).unlink(missing_ok=True)

        yield f"event: status\ndata: {json.dumps({'part_number': part_number, 'index': idx, 'status': 'searching'})}\n\n"

        try:
            result = run_pipeline(
                part_number=part_number,
                output_dir=str(batch_dir),
                no_open=True,
                verbose=False,
            )
        except Exception as e:
            print(f"Pipeline error for {part_number}: {e}", file=sys.stderr)
            result = {"part_number": part_number, "image_path": None, "source": "", "source_url": "", "description": "", "datasheet_url": None, "datasheet_path": None}

        data["parts"][idx] = _result_to_part(part_number, result)
        _save_results(batch_id, data)

        yield f"event: result\ndata: {json.dumps(data['parts'][idx] | {'index': idx})}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/batch/<batch_id>/images/<filename>")
def batch_image(batch_id: str, filename: str):
    return send_from_directory(PARTS_DIR / batch_id, filename)


def server_main(args):
    app.run(host=args.host, port=args.port, debug=True, threaded=True)


