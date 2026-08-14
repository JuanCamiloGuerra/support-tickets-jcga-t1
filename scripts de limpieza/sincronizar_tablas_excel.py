import argparse
import csv
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import win32com.client


EXCEL_EPOCH = datetime(1899, 12, 30)


TABLES_WITH_HEADER = [
    ("_tabla_conceptos_costos", "grupos_egresos.csv"),
    ("Tabla31", "egresos.csv"),
]

LARGE_TABLES_WITH_HEADER = [
    ("TB_VENTAS", "ventas_df.csv"),
    ("TB_FACTURAS", "facturacion_ventas.csv"),
]

TABLES_WITHOUT_HEADER = [
    ("COLEGIO", "colegios.csv"),
    ("_liceo_pupo_jimenez_", "liceo pupo jimenez.csv"),
    ("_liceo_universitario_", "liceo universitario.csv"),
    ("_nuestra_señora_del_carmen_", "nuestra señora del carmen.csv"),
    ("_gimnasio_plaza_feliz_", "gimnasio plaza feliz.csv"),
    ("_gimnasio_vallegrande_", "gimnasio vallegrande.csv"),
    ("_colsafa_", "colsafa.csv"),
    ("_conalco_", "conalco.csv"),
    ("_la_inmaculada_", "la inmaculada.csv"),
    ("_hogar_", "hogar.csv"),
    ("_Pantalones_Azules_", "Pantalones Azules.csv"),
    ("_Bordados_", "Bordados.csv"),
    ("_TALLAS_", "tallas.csv"),
    ("_Antonio_narino_", "Antonio Narino.csv"),
    ("_Unicor_", "Unicor.csv"),
    ("_otros_", "otros.csv"),
    ("_Bermudas_Azules_", "bermudas azules.csv"),
    ("_Domicilios_", "Domicilios.csv"),
    ("_Policia_", "Policia.csv"),
    ("_Diac_", "Diac.csv"),
    ("_casa_del_niño_", "Casa del niño.csv"),
    ("_Inversiones_OM_", "Inversiones OM.csv"),
    ("INFO_ESTADO_FACTURAS", "info facturas.csv"),
    ("AJUSTES_INVENTARIO", "ajustes de inventario.csv"),
    ("_antifluido_", "antifluido.csv"),
    ("_dotacion_", "dotacion.csv"),
    ("_antonia_santos_", "antonia santos.csv"),
    ("_san_jose_", "san jose.csv"),
]


def normalize(value):
    return str(value or "").strip().lower()


def excel_date(value):
    return EXCEL_EPOCH + timedelta(days=float(value))


def long_spanish_date(value):
    days = [
        "lunes",
        "martes",
        "miércoles",
        "jueves",
        "viernes",
        "sábado",
        "domingo",
    ]
    months = [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]
    date_value = excel_date(value)
    return (
        f"{days[date_value.weekday()]}, "
        f"{date_value.day} de {months[date_value.month - 1]} de {date_value.year}"
    )


def short_date(value):
    date_value = excel_date(value)
    return f"{date_value.day}/{date_value.month:02d}/{date_value.year}"


def format_header(value):
    if value is None:
        return ""
    if isinstance(value, (int, float)) and abs(float(value) - round(float(value))) < 0.0000001:
        return str(int(round(float(value))))
    return str(value).strip()


def format_value(value, header, long_date_headers=None):
    if value is None:
        return ""

    long_date_headers = long_date_headers or set()
    header_norm = normalize(header)

    if isinstance(value, str):
        return value.strip()

    if "fecha" in header_norm or "fehca" in header_norm:
        if header_norm in long_date_headers:
            return long_spanish_date(value)
        return short_date(value)

    if isinstance(value, (int, float)):
        money_words = ["valor", "total", "pago", "pendiente", "subtotal", "precio"]
        if abs(float(value) - round(float(value))) < 0.0000001:
            return str(int(round(float(value))))
        if any(word in header_norm for word in money_words):
            return f"{float(value):.2f}".rstrip("0").rstrip(".")
        return f"{float(value):.10f}".rstrip("0").rstrip(".")

    return str(value).strip()


def as_matrix(values):
    if values is None:
        return []
    if not isinstance(values, tuple):
        return [[values]]
    if values and not isinstance(values[0], tuple):
        return [list(values)]
    return [list(row) for row in values]


def backup_file(csv_path, backup_dir):
    if csv_path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(csv_path, backup_dir / csv_path.name)


def write_csv(csv_path, rows, backup_dir):
    backup_file(csv_path, backup_dir)
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter=";", lineterminator="\n")
        writer.writerows(rows)


def rows_from_range(excel_range, include_header, long_date_headers=None):
    values = as_matrix(excel_range.Value2)
    if not values:
        return []

    long_date_headers = long_date_headers or set()
    headers = [format_header(value) for value in values[0]]
    rows = []

    if include_header:
        rows.append(headers)
        data_rows = values[1:]
    else:
        data_rows = values

    for row in data_rows:
        output = []
        has_value = False
        for index, value in enumerate(row):
            header = headers[index] if include_header and index < len(headers) else ""
            formatted = format_value(value, header, long_date_headers=long_date_headers)
            if formatted != "":
                has_value = True
            output.append(formatted)

        if has_value:
            rows.append(output)

    return rows


def find_table(workbook, table_name):
    target = table_name.strip().lower()
    for worksheet in workbook.Worksheets:
        for table in worksheet.ListObjects:
            if str(table.Name).strip().lower() == target:
                return table
    raise ValueError(f"No se encontro la tabla de Excel: {table_name}")


def find_workbook(excel):
    for workbook in excel.Workbooks:
        try:
            find_table(workbook, "TB_FACTURAS")
            return workbook
        except ValueError:
            continue
    raise ValueError("No se encontro un libro abierto con la tabla TB_FACTURAS.")


def export_table(workbook, table_name, csv_name, include_header, tablas_dir, backup_dir):
    table = find_table(workbook, table_name)
    excel_range = table.Range if include_header else table.DataBodyRange
    long_date_headers = set()
    if table_name == "TB_VENTAS":
        long_date_headers = {"fecha"}
    elif table_name == "TB_FACTURAS":
        long_date_headers = {"fecha de venta", "fecha de pago 2"}
    rows = rows_from_range(
        excel_range,
        include_header=include_header,
        long_date_headers=long_date_headers,
    )
    write_csv(tablas_dir / csv_name, rows, backup_dir)
    return csv_name, len(rows), len(rows[0]) if rows else 0


def export_sheet_range(workbook, sheet_name, start_row, start_col, row_count, col_count, csv_name, tablas_dir, backup_dir):
    worksheet = workbook.Worksheets(sheet_name)
    excel_range = worksheet.Range(
        worksheet.Cells(start_row, start_col),
        worksheet.Cells(start_row + row_count - 1, start_col + col_count - 1),
    )
    rows = rows_from_range(excel_range, include_header=True)
    write_csv(tablas_dir / csv_name, rows, backup_dir)
    return csv_name, len(rows), len(rows[0]) if rows else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--include-large", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    tablas_dir = project_root / "tablas"
    backup_dir = tablas_dir / "backups" / f"excel_sync_{datetime.now():%Y%m%d_%H%M%S}"

    excel = win32com.client.GetActiveObject("Excel.Application")
    workbook = find_workbook(excel)

    exported = []

    for table_name, csv_name in TABLES_WITH_HEADER:
        exported.append(
            export_table(workbook, table_name, csv_name, True, tablas_dir, backup_dir)
        )

    for table_name, csv_name in TABLES_WITHOUT_HEADER:
        exported.append(
            export_table(workbook, table_name, csv_name, False, tablas_dir, backup_dir)
        )

    inventory_sheet = workbook.Worksheets("TB INVENTARIO")
    inventory_range = inventory_sheet.UsedRange
    exported.append(
        export_sheet_range(
            workbook,
            "TB INVENTARIO",
            inventory_range.Row,
            inventory_range.Column,
            inventory_range.Rows.Count,
            5,
            "inventario.csv",
            tablas_dir,
            backup_dir,
        )
    )

    prices_sheet = workbook.Worksheets("TB PRECIOS")
    prices_range = prices_sheet.UsedRange
    prices_last_row = prices_range.Row + prices_range.Rows.Count - 1
    exported.append(
        export_sheet_range(
            workbook,
            "TB PRECIOS",
            4,
            1,
            prices_last_row - 4 + 1,
            13,
            "precios.csv",
            tablas_dir,
            backup_dir,
        )
    )

    if args.include_large:
        for table_name, csv_name in LARGE_TABLES_WITH_HEADER:
            exported.append(
                export_table(workbook, table_name, csv_name, True, tablas_dir, backup_dir)
            )

    for csv_name, row_count, col_count in sorted(exported):
        print(f"{csv_name}\t{row_count} rows\t{col_count} cols")

    print(f"Backup creado en: {backup_dir}")


if __name__ == "__main__":
    main()
