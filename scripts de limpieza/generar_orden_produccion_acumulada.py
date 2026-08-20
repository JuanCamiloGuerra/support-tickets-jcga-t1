import importlib.util
import math
from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import legal, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output" / "pdf"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BASE_SCRIPT = PROJECT_ROOT / "scripts de limpieza" / "generar_orden_produccion.py"
TARGET_MONTHS = {8: "Agosto", 9: "Septiembre"}


def load_base_module():
    spec = importlib.util.spec_from_file_location("orden_produccion_base", BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_base_module()


def round_up_to_5(value):
    if value <= 0:
        return 0
    return int(math.ceil(value / 5) * 5)


def month_forecast(monthly, key, month):
    subset = monthly[
        (monthly["month"] == month)
        & (monthly["school_norm"] == key["school_norm"])
        & (monthly["product_norm"] == key["product_norm"])
        & (monthly["size_norm"] == key["size_norm"])
    ]["qty"]

    if subset.empty:
        avg_qty = p75_qty = std_qty = recent_qty = 0.0
    else:
        avg_qty = float(subset.mean())
        p75_qty = float(subset.quantile(0.75))
        std_qty = float(subset.std(ddof=0))
        recent = monthly[
            (monthly["month"] == month)
            & (monthly["year"] == base.TARGET_YEAR - 1)
            & (monthly["school_norm"] == key["school_norm"])
            & (monthly["product_norm"] == key["product_norm"])
            & (monthly["size_norm"] == key["size_norm"])
        ]["qty"]
        recent_qty = float(recent.iloc[0]) if not recent.empty else 0.0

    weighted_recent = (recent_qty * 0.6) + (avg_qty * 0.4)
    forecast = math.ceil(max(avg_qty, p75_qty, weighted_recent))
    safety = math.ceil(max(forecast * 0.2, std_qty)) if forecast else 0
    return forecast, safety


def build_combined_plan():
    ventas, inventario = base.load_data()
    history = ventas[(ventas["year"] < base.TARGET_YEAR) & (ventas["month"].isin(TARGET_MONTHS))]
    monthly = (
        history.groupby(["month", "year", "school_norm", "product_norm", "size_norm"], dropna=False)["qty"]
        .sum()
        .reset_index()
    )

    current_year = (
        ventas[(ventas["year"] == base.TARGET_YEAR) & (ventas["month"].isin(TARGET_MONTHS))]
        .groupby(["month", "school_norm", "product_norm", "size_norm"], dropna=False)["qty"]
        .sum()
        .reset_index(name="current_qty")
    )

    inv_group = (
        inventario.groupby(["school_norm", "product_norm", "size_norm"], dropna=False)["stock"]
        .sum()
        .reset_index()
    )

    keys = pd.concat(
        [
            monthly[["school_norm", "product_norm", "size_norm"]],
            current_year[["school_norm", "product_norm", "size_norm"]],
            inv_group[["school_norm", "product_norm", "size_norm"]],
        ],
        ignore_index=True,
    ).drop_duplicates()

    rows = []
    for _, key in keys.iterrows():
        forecast_total = 0
        safety_total = 0
        current_total = 0

        for month in TARGET_MONTHS:
            forecast, safety = month_forecast(monthly, key, month)
            current_match = current_year[
                (current_year["month"] == month)
                & (current_year["school_norm"] == key["school_norm"])
                & (current_year["product_norm"] == key["product_norm"])
                & (current_year["size_norm"] == key["size_norm"])
            ]["current_qty"]
            current_qty = float(current_match.iloc[0]) if not current_match.empty else 0.0
            forecast_total += max(forecast, math.ceil(current_qty))
            safety_total += safety
            current_total += current_qty

        stock_match = inv_group[
            (inv_group["school_norm"] == key["school_norm"])
            & (inv_group["product_norm"] == key["product_norm"])
            & (inv_group["size_norm"] == key["size_norm"])
        ]["stock"]
        stock = float(stock_match.iloc[0]) if not stock_match.empty else 0.0
        raw_order = max(0, forecast_total + safety_total - stock)
        production = round_up_to_5(raw_order)

        if production > 0:
            rows.append(
                {
                    "colegio": key["school_norm"],
                    "articulo": key["product_norm"],
                    "producto_colegio": f"{key['product_norm']}_{key['school_norm']}",
                    "talla": str(key["size_norm"]),
                    "inventario": int(round(stock)),
                    "pronostico_agosto_septiembre": int(forecast_total),
                    "stock_minimo": int(safety_total),
                    "orden_sin_redondeo": int(math.ceil(raw_order)),
                    "orden_produccion": production,
                }
            )

    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, pd.DataFrame()

    detail = detail.sort_values(["colegio", "articulo", "talla"], key=lambda col: col.astype(str))
    pivot = detail.pivot_table(
        index=["colegio", "producto_colegio"],
        columns="talla",
        values="orden_produccion",
        aggfunc="sum",
        fill_value=0,
    )
    pivot["_orden_colegio"] = [idx[0] for idx in pivot.index]
    pivot = pivot.sort_values(["_orden_colegio"], kind="stable").drop(columns=["_orden_colegio"])
    pivot = pivot[[col for col in sorted(pivot.columns, key=base.sort_size)]]
    pivot.insert(0, "producto_articulo_colegio", [idx[1] for idx in pivot.index])
    return detail, pivot.reset_index(drop=True)


def page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(doc.pagesize[0] - 1.2 * cm, 0.8 * cm, f"Pagina {doc.page}")
    canvas.restoreState()


def p(text, style):
    return Paragraph(str(text), style)


def chunks(df, rows_per_page=28):
    for start in range(0, len(df), rows_per_page):
        yield df.iloc[start : start + rows_per_page]


def build_pdf(detail, pivot):
    output = OUTPUT_DIR / "orden_produccion_agosto_septiembre_2026_acumulada_redondeada.pdf"
    doc = BaseDocTemplate(
        str(output),
        pagesize=landscape(legal),
        leftMargin=0.8 * cm,
        rightMargin=0.8 * cm,
        topMargin=0.8 * cm,
        bottomMargin=1.0 * cm,
        title="Orden de produccion acumulada agosto septiembre 2026",
    )
    doc.addPageTemplates([PageTemplate(id="page", frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height)], onPage=page_number)])

    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleDYUNIC", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#1f2933"), alignment=TA_LEFT)
    h2 = ParagraphStyle("H2DYUNIC", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#1f2933"), spaceBefore=8, spaceAfter=6)
    body = ParagraphStyle("BodyDYUNIC", parent=styles["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("SmallDYUNIC", parent=styles["BodyText"], fontSize=7.5, leading=9)
    left_cell = ParagraphStyle("LeftCellDYUNIC", parent=small, alignment=TA_LEFT)
    cell = ParagraphStyle("CellDYUNIC", parent=small, alignment=TA_RIGHT)
    header = ParagraphStyle("HeaderCellDYUNIC", parent=small, alignment=TA_CENTER, fontName="Helvetica-Bold", textColor=colors.white)

    story = []

    columns = list(pivot.columns)
    for page_idx, chunk in enumerate(chunks(pivot), start=1):
        story.append(p("Orden de produccion acumulada - Agosto + septiembre" + (" (continuacion)" if page_idx > 1 else ""), title))
        story.append(p(f"Generado el {datetime.now():%Y-%m-%d %H:%M}", body))
        story.append(Spacer(1, 0.15 * cm))
        data = [[p(col.replace("_", " "), header) for col in columns]]
        for _, row in chunk.iterrows():
            data.append([p(row[columns[0]], left_cell), *[p("" if int(row[col]) == 0 else f"{int(row[col]):,}", cell) for col in columns[1:]]])

        first_width = 8.4 * cm
        remaining_width = doc.width - first_width
        size_width = max(1.05 * cm, remaining_width / max(1, len(columns) - 1))
        table = Table(data, repeatRows=1, colWidths=[first_width] + [size_width] * (len(columns) - 1))
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243b53")),
            ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#cbd2d9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
        for row_idx, (_, row) in enumerate(chunk.iterrows(), start=1):
            for col_idx, col in enumerate(columns[1:], start=1):
                value = int(row[col])
                if value > 15:
                    commands.append(("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.HexColor("#f8d7da")))
                    commands.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), colors.HexColor("#8a1f2d")))
                elif value > 10:
                    commands.append(("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.HexColor("#fff3cd")))
                    commands.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), colors.HexColor("#664d03")))
        table.setStyle(TableStyle(commands))
        story.append(table)
        if page_idx < math.ceil(len(pivot) / 28):
            story.append(PageBreak())

    doc.build(story)
    return output


def main():
    detail, pivot = build_combined_plan()
    output = build_pdf(detail, pivot)
    detail.to_csv(OUTPUT_DIR / "orden_produccion_agosto_septiembre_2026_acumulada_redondeada_detalle.csv", index=False, encoding="utf-8-sig")
    print(output)
    print(f"unidades={int(detail['orden_produccion'].sum()) if not detail.empty else 0}")
    print(f"skus={len(detail)}")


if __name__ == "__main__":
    main()
