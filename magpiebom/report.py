# magpiebom/report.py
import base64
from pathlib import Path


def _image_to_data_uri(image_path: str) -> str:
    """Convert an image file to a base64 data URI."""
    path = Path(image_path)
    suffix = path.suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    mime = mime_types.get(suffix, "image/jpeg")
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _escape(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def generate_report(results: list[dict], output_dir: str) -> str:
    """Generate a self-contained HTML report from pipeline results."""
    found = sum(1 for r in results if r["image_path"])
    not_found = len(results) - found
    total = len(results)

    rows = []
    for r in results:
        pn = _escape(r["part_number"])
        has_image = r["image_path"] is not None

        # Status
        if has_image:
            status = '<span class="found">Found</span>'
        else:
            status = '<span class="not-found">Not Found</span>'

        # Image thumbnail
        if has_image:
            data_uri = _image_to_data_uri(r["image_path"])
            img_cell = f'<img src="{data_uri}" alt="{pn}">'
        else:
            img_cell = '<span class="no-image">—</span>'

        # Description
        desc = _escape(r.get("description", "") or "")

        # Source (clickable if source_url available)
        source = _escape(r.get("source", "") or "")
        source_url = r.get("source_url")
        if source_url:
            source_cell = f'<a href="{_escape(source_url)}" target="_blank">{source}</a>'
        else:
            source_cell = source

        # Datasheet link
        ds_url = r.get("datasheet_url")
        if ds_url:
            ds_cell = f'<a href="{_escape(ds_url)}" target="_blank">PDF</a>'
        else:
            ds_cell = "—"

        rows.append(
            f"<tr>"
            f"<td>{pn}</td>"
            f"<td>{status}</td>"
            f"<td class=\"img-cell\">{img_cell}</td>"
            f"<td>{desc}</td>"
            f"<td>{source_cell}</td>"
            f"<td>{ds_cell}</td>"
            f"</tr>"
        )

    table_rows = "\n".join(rows)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MagpieBOM Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2em; color: #222; }}
  h1 {{ margin-bottom: 0.2em; }}
  .summary {{ color: #555; margin-bottom: 1.5em; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; vertical-align: middle; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  tr:hover {{ background: #fafafa; }}
  .found {{ color: #2e7d32; font-weight: 600; }}
  .not-found {{ color: #c62828; font-weight: 600; }}
  .img-cell img {{ height: 150px; width: auto; display: block; }}
  .no-image {{ color: #999; }}
  a {{ color: #1565c0; }}
</style>
</head>
<body>
<h1>MagpieBOM Report</h1>
<p class="summary">{found} found, {not_found} not found, {total} total</p>
<table>
<thead>
<tr>
  <th>Part Number</th>
  <th>Status</th>
  <th>Image</th>
  <th>Description</th>
  <th>Source</th>
  <th>Datasheet</th>
</tr>
</thead>
<tbody>
{table_rows}
</tbody>
</table>
</body>
</html>"""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.html"
    report_path.write_text(html)
    return str(report_path)
