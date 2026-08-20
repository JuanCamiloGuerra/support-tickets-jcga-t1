import math
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import legal, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLAS_DIR = PROJECT_ROOT / "tablas"
OUTPUT_DIR = PROJECT_ROOT / "output" / "pdf"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_YEAR = 2026
TARGET_MONTHS = {8: "Agosto", 9: "Septiembre"}
TARGET_SCHOOLS = [
    "liceo pupo jimenez",
    "liceo universitario",
    "nuestra señora del carmen",
    "gimnasio plaza feliz",
    "gimnasio vallegrande",
    "colsafa",
    "conalco",
    "la inmaculada",
    "Antonio Narino",
    "hogar",
    "otros",
    "Pantalones Azules",
    "Bermudas Azules",
]

EXCLUDED_PRODUCT_WORDS = ["medias"]


def normalize_text(value):
    text = str(value or "").strip().lower()
    text = text.replace("�", "ñ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_col(value):
    return normalize_text(value).replace(" ", "_")


def money_or_qty(value):
    if pd.isna(value):
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    text = text.replace("$", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def sort_size(value):
    text = str(value).strip()
    lower = text.lower()
    if lower == "unica":
        return (2, 0, lower)
    if lower.isdigit():
        return (0, int(lower), lower)
    alpha_order = {"s": 100, "m": 101, "l": 102, "xl": 103, "xxl": 104}
    return (1, alpha_order.get(lower, 999), lower)


def get_column(df, candidates):
    normalized = {normalize_col(col): col for col in df.columns}
    for candidate in candidates:
        key = normalize_col(candidate)
        if key in normalized:
            return normalized[key]
    raise KeyError(f"No encontre ninguna columna candidata: {candidates}")


def load_data():
    ventas = pd.read_csv(TABLAS_DIR / "ventas_df.csv", sep=";", dtype=str, encoding="utf-8")
    inventario = pd.read_csv(TABLAS_DIR / "inventario.csv", sep=";", dtype=str, encoding="utf-8")

    sales_cols = {
        "school": get_column(ventas, ["colegio"]),
        "product": get_column(ventas, ["articulo", "producto"]),
        "size": get_column(ventas, ["talla"]),
        "qty": get_column(ventas, ["cantidad"]),
        "month": get_column(ventas, ["mes"]),
        "year": get_column(ventas, ["año", "ano", "a�o"]),
    }
    inv_cols = {
        "school": get_column(inventario, ["colegio"]),
        "product": get_column(inventario, ["producto"]),
        "size": get_column(inventario, ["talla"]),
        "stock": get_column(inventario, ["inventario"]),
    }

    ventas = ventas.rename(columns={value: key for key, value in sales_cols.items()})
    inventario = inventario.rename(columns={value: key for key, value in inv_cols.items()})

    ventas["school_norm"] = ventas["school"].map(normalize_text)
    ventas["product_norm"] = ventas["product"].map(normalize_text)
    ventas["size_norm"] = ventas["size"].fillna("UNICA").astype(str).str.strip().str.upper()
    ventas.loc[ventas["size_norm"].isin(["", "NAN", "NONE"]), "size_norm"] = "UNICA"
    ventas["qty"] = ventas["qty"].map(money_or_qty)
    ventas["month"] = ventas["month"].map(money_or_qty).astype(int)
    ventas["year"] = ventas["year"].map(money_or_qty).astype(int)

    inventario["school_norm"] = inventario["school"].map(normalize_text)
    inventario["product_norm"] = inventario["product"].map(normalize_text)
    inventario["size_norm"] = inventario["size"].fillna("UNICA").astype(str).str.strip().str.upper()
    inventario.loc[inventario["size_norm"].isin(["", "NAN", "NONE"]), "size_norm"] = "UNICA"
    inventario["stock"] = inventario["stock"].map(money_or_qty).clip(lower=0)

    school_norms = {normalize_text(school) for school in TARGET_SCHOOLS}
    aliases = {"inmaculada": "la inmaculada", "gimnsio plaza feliz": "gimnasio plaza feliz"}
    ventas["school_norm"] = ventas["school_norm"].replace(aliases)
    inventario["school_norm"] = inventario["school_norm"].replace(aliases)

    ventas = ventas[~ventas["product_norm"].str.contains("|".join(EXCLUDED_PRODUCT_WORDS), na=False)]
    inventario = inventario[~inventario["product_norm"].str.contains("|".join(EXCLUDED_PRODUCT_WORDS), na=False)]

    return (
        ventas[ventas["school_norm"].isin(school_norms)].copy(),
        inventario[inventario["school_norm"].isin(school_norms)].copy(),
    )


def build_plan():
    ventas, inventario = load_data()
    history = ventas[(ventas["year"] < TARGET_YEAR) & (ventas["month"].isin(TARGET_MONTHS))]
    monthly = (
        history.groupby(["month", "year", "school_norm", "product_norm", "size_norm"], dropna=False)["qty"]
        .sum()
        .reset_index()
    )

    inv_group = (
        inventario.groupby(["school_norm", "product_norm", "size_norm"], dropna=False)["stock"]
        .sum()
        .reset_index()
    )

    keys = pd.concat(
        [
            monthly[["month", "school_norm", "product_norm", "size_norm"]],
            pd.concat(
                [
                    inv_group.assign(month=month)[["month", "school_norm", "product_norm", "size_norm"]]
                    for month in TARGET_MONTHS
                ],
                ignore_index=True,
            ),
        ],
        ignore_index=True,
    ).drop_duplicates()

    current_year_sales = (
        ventas[(ventas["year"] == TARGET_YEAR) & (ventas["month"].isin(TARGET_MONTHS))]
        .groupby(["month", "school_norm", "product_norm", "size_norm"], dropna=False)["qty"]
        .sum()
        .reset_index(name="current_year_qty")
    )

    rows = []
    for _, key in keys.iterrows():
        subset = monthly[
            (monthly["month"] == key["month"])
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
                (monthly["month"] == key["month"])
                & (monthly["year"] == TARGET_YEAR - 1)
                & (monthly["school_norm"] == key["school_norm"])
                & (monthly["product_norm"] == key["product_norm"])
                & (monthly["size_norm"] == key["size_norm"])
            ]["qty"]
            recent_qty = float(recent.iloc[0]) if not recent.empty else 0.0

        current_match = current_year_sales[
            (current_year_sales["month"] == key["month"])
            & (current_year_sales["school_norm"] == key["school_norm"])
            & (current_year_sales["product_norm"] == key["product_norm"])
            & (current_year_sales["size_norm"] == key["size_norm"])
        ]["current_year_qty"]
        current_qty = float(current_match.iloc[0]) if not current_match.empty else 0.0

        weighted_recent = (recent_qty * 0.6) + (avg_qty * 0.4)
        forecast = math.ceil(max(avg_qty, p75_qty, weighted_recent, current_qty))
        safety_stock = math.ceil(max(forecast * 0.2, std_qty))
        if forecast == 0:
            safety_stock = 0

        stock_match = inv_group[
            (inv_group["school_norm"] == key["school_norm"])
            & (inv_group["product_norm"] == key["product_norm"])
            & (inv_group["size_norm"] == key["size_norm"])
        ]["stock"]
        stock = float(stock_match.iloc[0]) if not stock_match.empty else 0.0
        production = max(0, math.ceil(forecast + safety_stock - stock))

        if production > 0:
            rows.append(
                {
                    "mes": int(key["month"]),
                    "colegio": key["school_norm"],
                    "articulo": key["product_norm"],
                    "talla": str(key["size_norm"]),
                    "inventario": int(round(stock)),
                    "pronostico": int(forecast),
                    "stock_minimo": int(safety_stock),
                    "orden_produccion": int(production),
                    "producto_colegio": f"{key['product_norm']}_{key['school_norm']}",
                }
            )

    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, {}

    pivots = {}
    for month, month_name in TARGET_MONTHS.items():
        month_detail = detail[detail["mes"] == month]
        pivot = month_detail.pivot_table(
            index="producto_colegio",
            columns="talla",
            values="orden_produccion",
            aggfunc="sum",
            fill_value=0,
        )
        pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
        pivot = pivot[[col for col in sorted(pivot.columns, key=sort_size)]]
        pivot.insert(0, "producto_articulo_colegio", pivot.index)
        pivots[month_name] = pivot.reset_index(drop=True)
    return detail, pivots


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(doc.pagesize[0] - 1.2 * cm, 0.8 * cm, f"Pagina {doc.page}")
    canvas.restoreState()


def paragraph(text, style):
    return Paragraph(str(text), style)


def table_chunks(df, rows_per_page=28):
    for start in range(0, len(df), rows_per_page):
        yield df.iloc[start : start + rows_per_page]


def build_pdf(detail, pivots):
    output = OUTPUT_DIR / "orden_produccion_agosto_septiembre_2026_sin_unicor_bordados_medias.pdf"
    doc = BaseDocTemplate(
        str(output),
        pagesize=landscape(legal),
        leftMargin=0.8 * cm,
        rightMargin=0.8 * cm,
        topMargin=0.8 * cm,
        bottomMargin=1.0 * cm,
        title="Orden de produccion agosto y septiembre 2026",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=add_page_number)])

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleDYUNIC",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1f2933"),
        alignment=TA_LEFT,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "H2DYUNIC",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1f2933"),
        spaceBefore=8,
        spaceAfter=6,
    )
    body = ParagraphStyle("BodyDYUNIC", parent=styles["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("SmallDYUNIC", parent=styles["BodyText"], fontSize=7.5, leading=9)
    cell = ParagraphStyle("CellDYUNIC", parent=small, alignment=TA_RIGHT)
    left_cell = ParagraphStyle("LeftCellDYUNIC", parent=small, alignment=TA_LEFT)
    header_cell = ParagraphStyle(
        "HeaderCellDYUNIC",
        parent=small,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    story = [
        paragraph("Orden de produccion - Agosto y septiembre 2026", title_style),
        paragraph(f"Generado el {datetime.now():%Y-%m-%d %H:%M}", body),
        Spacer(1, 0.2 * cm),
    ]

    total_by_month = detail.groupby("mes")["orden_produccion"].sum().reindex(TARGET_MONTHS.keys(), fill_value=0)
    sku_by_month = detail.groupby("mes").size().reindex(TARGET_MONTHS.keys(), fill_value=0)
    summary_data = [[paragraph("Mes", header_cell), paragraph("Unidades a producir", header_cell), paragraph("SKUs con necesidad", header_cell)]]
    for month, month_name in TARGET_MONTHS.items():
        summary_data.append([paragraph(month_name, left_cell), f"{int(total_by_month.loc[month]):,}", f"{int(sku_by_month.loc[month]):,}"])
    summary_table = Table(summary_data, colWidths=[5 * cm, 4 * cm, 4 * cm], hAlign="LEFT")
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243b53")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd2d9")),
                ("FONTNAME", (1, 1), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
            ]
        )
    )
    story.extend(
        [
            paragraph("Resumen", h2),
            summary_table,
            paragraph("Criterio de calculo", h2),
            paragraph(
                "La demanda esperada toma el mayor valor entre promedio historico del mismo mes, percentil 75, una mezcla ponderada del ultimo ano disponible y el promedio historico, y ventas del ano objetivo si ya existen. El stock minimo se calcula como el mayor entre 20% del pronostico y la desviacion historica. Los inventarios negativos se tratan como cero. La orden es max(0, pronostico + stock minimo - inventario actual).",
                body,
            ),
            paragraph("Colegios incluidos", h2),
            paragraph(", ".join(TARGET_SCHOOLS), body),
        ]
    )

    for month_name, pivot in pivots.items():
        story.append(PageBreak())
        story.append(paragraph(f"Orden de produccion - {month_name}", title_style))

        for page_number, chunk in enumerate(table_chunks(pivot), start=1):
            if page_number > 1:
                story.append(PageBreak())
                story.append(paragraph(f"Orden de produccion - {month_name} (continuacion)", title_style))

            columns = list(chunk.columns)
            data = [[paragraph(col.replace("_", " "), header_cell) for col in columns]]
            for _, row in chunk.iterrows():
                data.append(
                    [
                        paragraph(row[columns[0]], left_cell),
                        *[paragraph("" if int(row[col]) == 0 else f"{int(row[col]):,}", cell) for col in columns[1:]],
                    ]
                )

            first_width = 8.4 * cm
            remaining_width = doc.width - first_width
            size_width = max(1.05 * cm, remaining_width / max(1, len(columns) - 1))
            table = Table(data, repeatRows=1, colWidths=[first_width] + [size_width] * (len(columns) - 1))
            table_commands = [
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
                        table_commands.append(("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.HexColor("#f8d7da")))
                        table_commands.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), colors.HexColor("#8a1f2d")))
                    elif value > 10:
                        table_commands.append(("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), colors.HexColor("#fff3cd")))
                        table_commands.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), colors.HexColor("#664d03")))
            table.setStyle(TableStyle(table_commands))
            story.append(table)

    doc.build(story)
    return output


def main():
    detail, pivots = build_plan()
    output = build_pdf(detail, pivots)
    detail.to_csv(
        OUTPUT_DIR / "orden_produccion_agosto_septiembre_2026_sin_unicor_bordados_medias_detalle.csv",
        index=False,
        encoding="utf-8-sig",
    )
    print(output)
    if not detail.empty:
        print(detail.groupby("mes")["orden_produccion"].sum().to_string())


if __name__ == "__main__":
    main()
