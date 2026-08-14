import argparse
import importlib.util
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import msal
import requests
import win32com.client


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES = ["User.Read", "Files.Read.All"]

def app_data_dir():
    root = os.environ.get("APPDATA") or str(Path.home())
    path = Path(root) / "DYUNIC"
    path.mkdir(parents=True, exist_ok=True)
    return path


def token_cache_path():
    return app_data_dir() / "onedrive_graph_token_cache.bin"


def config_path(project_root):
    return Path(project_root) / "scripts de limpieza" / "configuracion_onedrive_excel.json"


def load_cache():
    cache = msal.SerializableTokenCache()
    path = token_cache_path()
    if path.exists():
        cache.deserialize(path.read_text(encoding="utf-8"))
    return cache


def save_cache(cache):
    if cache.has_state_changed:
        token_cache_path().write_text(cache.serialize(), encoding="utf-8")


def get_token_silent():
    cache = load_cache()
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    accounts = app.get_accounts()
    if not accounts:
        raise RuntimeError(
            "No hay sesion guardada de OneDrive. Ejecuta configurar_onedrive_excel.py primero."
        )
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    save_cache(cache)
    if "access_token" not in result:
        raise RuntimeError(
            "No pude renovar la sesion de OneDrive. Ejecuta configurar_onedrive_excel.py de nuevo."
        )
    return result["access_token"]


def download_workbook(config, token):
    url = f"{GRAPH_BASE}/drives/{config['drive_id']}/items/{config['item_id']}/content"
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=300)
    response.raise_for_status()
    suffix = Path(config.get("workbook_name", "ventas.xlsm")).suffix or ".xlsm"
    target = Path(tempfile.gettempdir()) / f"dyunic_excel_sync_{datetime.now():%Y%m%d_%H%M%S}{suffix}"
    target.write_bytes(response.content)
    return target


def load_desktop_sync_module(project_root):
    module_path = Path(project_root) / "scripts de limpieza" / "sincronizar_tablas_excel.py"
    spec = importlib.util.spec_from_file_location("sincronizar_tablas_excel", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export_with_excel_desktop(project_root, workbook_path, include_large):
    sync = load_desktop_sync_module(project_root)
    tablas_dir = Path(project_root) / "tablas"
    backup_dir = tablas_dir / "backups" / f"onedrive_sync_{datetime.now():%Y%m%d_%H%M%S}"

    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    workbook = None
    try:
        workbook = excel.Workbooks.Open(str(workbook_path), UpdateLinks=0, ReadOnly=True)
        exported = []
        for table_name, csv_name in sync.TABLES_WITH_HEADER:
            exported.append(sync.export_table(workbook, table_name, csv_name, True, tablas_dir, backup_dir))
        for table_name, csv_name in sync.TABLES_WITHOUT_HEADER:
            exported.append(sync.export_table(workbook, table_name, csv_name, False, tablas_dir, backup_dir))

        inventory_sheet = workbook.Worksheets("TB INVENTARIO")
        inventory_range = inventory_sheet.UsedRange
        exported.append(
            sync.export_sheet_range(
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
            sync.export_sheet_range(
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

        if include_large:
            for table_name, csv_name in sync.LARGE_TABLES_WITH_HEADER:
                exported.append(sync.export_table(workbook, table_name, csv_name, True, tablas_dir, backup_dir))
    finally:
        if workbook is not None:
            workbook.Close(SaveChanges=False)
        excel.Quit()

    return exported, backup_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--include-large", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    tablas_dir = project_root / "tablas"
    backup_dir = tablas_dir / "backups" / f"onedrive_sync_{datetime.now():%Y%m%d_%H%M%S}"
    config = json.loads(config_path(project_root).read_text(encoding="utf-8"))

    token = get_token_silent()
    workbook_path = download_workbook(config, token)
    exported, backup_dir = export_with_excel_desktop(
        project_root,
        workbook_path,
        include_large=args.include_large,
    )

    for csv_name, row_count, col_count in sorted(exported):
        print(f"{csv_name}\t{row_count} rows\t{col_count} cols")
    print(f"Archivo OneDrive: {config.get('workbook_name')}")
    print(f"Backup creado en: {backup_dir}")


if __name__ == "__main__":
    main()
