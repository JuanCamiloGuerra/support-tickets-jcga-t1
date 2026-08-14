import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote

import msal
import requests


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES = ["User.Read", "Files.Read.All"]
TARGET_FILE = "DEMO-FORMATO DE VENTAS 2.1"


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


def get_token_interactive():
    cache = load_cache()
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"No se pudo crear el flujo de autenticacion: {flow}")
        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    save_cache(cache)
    if "access_token" not in result:
        raise RuntimeError(f"No se pudo autenticar en Microsoft Graph: {result}")
    return result["access_token"]


def graph_get(url, token):
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    response.raise_for_status()
    return response.json()


def find_file(token, file_name):
    query = quote(file_name)
    urls = [
        f"{GRAPH_BASE}/me/drive/root/search(q='{query}')?$top=50",
        f"{GRAPH_BASE}/me/drive/root/search(q='DEMO')?$top=100",
        f"{GRAPH_BASE}/me/drive/root/search(q='VENTAS')?$top=100",
        f"{GRAPH_BASE}/me/drive/recent?$top=200",
        f"{GRAPH_BASE}/me/drive/sharedWithMe?$top=200",
    ]
    matches = []
    seen = set()
    for url in urls:
        payload = graph_get(url, token)
        for item in payload.get("value", []):
            name = item.get("name", "")
            item_id = item.get("id")
            if item_id in seen:
                continue
            seen.add(item_id)
            if file_name.lower() in name.lower() and name.lower().endswith((".xlsx", ".xlsm")):
                matches.append(item)

    if not matches:
        raise RuntimeError(f"No encontre en OneDrive un archivo Excel llamado: {file_name}")

    matches.sort(key=lambda item: item.get("lastModifiedDateTime", ""), reverse=True)
    item = matches[0]
    return {
        "file_name": file_name,
        "workbook_name": item.get("name"),
        "drive_id": item["parentReference"]["driveId"],
        "item_id": item["id"],
        "web_url": item.get("webUrl", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--file-name", default=TARGET_FILE)
    args = parser.parse_args()

    token = get_token_interactive()
    config = find_file(token, args.file_name)
    path = config_path(args.project_root)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Configuracion guardada:")
    print(path)
    print(f"Archivo: {config['workbook_name']}")
    print(f"URL: {config['web_url']}")


if __name__ == "__main__":
    main()
