"""CSV / JSON / PDF export of a cached run result."""
import io
import json
import os

import pandas as pd

EXPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)


def to_csv_bytes(result: dict) -> bytes:
    buf = io.StringIO()
    buf.write(f"# strategy,{result['strategy']['name']}\n")
    buf.write(f"# run_id,{result['run_id']}\n\n")
    buf.write("# metrics\n")
    for k, v in result["metrics"].items():
        buf.write(f"{k},{v}\n")
    buf.write("\n# success_bar\n")
    if result["success_bar"]:
        sb = pd.DataFrame(result["success_bar"])
        sb.to_csv(buf, index=False)
    buf.write("\n# trades\n")
    if result["trades"]:
        pd.DataFrame(result["trades"]).to_csv(buf, index=False)
    else:
        buf.write("(no discrete trades for this hypothesis)\n")
    return buf.getvalue().encode("utf-8")


def to_json_bytes(result: dict) -> bytes:
    return json.dumps(result, indent=2, default=str).encode("utf-8")


def to_pdf_bytes(result: dict) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter

    y = h - 0.75 * inch
    c.setFont("Helvetica-Bold", 16)
    c.drawString(0.75 * inch, y, f"{result['strategy']['name']}")
    y -= 0.3 * inch
    c.setFont("Helvetica", 9)
    c.drawString(0.75 * inch, y, f"run_id: {result['run_id']}   category: {result['category']}")
    y -= 0.35 * inch

    # equity curve image
    eq = result.get("equity") or []
    if eq:
        xs = list(range(len(eq)))
        ys = [e["equity"] for e in eq]
        fig, ax = plt.subplots(figsize=(6.5, 2.6))
        ax.plot(xs, ys, linewidth=1)
        ax.set_title("Equity curve")
        ax.grid(alpha=0.3)
        img_buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(img_buf, format="png", dpi=150)
        plt.close(fig)
        img_buf.seek(0)
        from reportlab.lib.utils import ImageReader
        img = ImageReader(img_buf)
        c.drawImage(img, 0.75 * inch, y - 2.3 * inch, width=6.5 * inch, height=2.3 * inch)
        y -= 2.5 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.75 * inch, y, "Metrics")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    for k, v in result["metrics"].items():
        if y < 0.75 * inch:
            c.showPage()
            y = h - 0.75 * inch
        c.drawString(0.85 * inch, y, f"{k}: {v}")
        y -= 0.16 * inch

    y -= 0.15 * inch
    if y < 1.5 * inch:
        c.showPage()
        y = h - 0.75 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.75 * inch, y, "Success bar")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    for row in result["success_bar"]:
        if y < 0.75 * inch:
            c.showPage()
            y = h - 0.75 * inch
        c.drawString(0.85 * inch, y,
                     f"{row['metric']}: {row['value']} {row['op']} {row['threshold']} -> {row['pass']}")
        y -= 0.16 * inch

    c.showPage()
    c.save()
    return buf.getvalue()


def save_and_get_path(run_id: str, fmt: str, data: bytes) -> str:
    path = os.path.join(EXPORT_DIR, f"{run_id}.{fmt}")
    with open(path, "wb") as f:
        f.write(data)
    return path
