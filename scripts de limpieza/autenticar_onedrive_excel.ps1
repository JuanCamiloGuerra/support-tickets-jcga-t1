param(
    [string]$ProjectRoot = "C:\Users\juanc\Documents\GitHub\proyecto-de-ventas-dyunic",
    [string]$PythonPath = "C:\Users\juanc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)

$ErrorActionPreference = "Stop"
$ScriptPath = Join-Path $ProjectRoot "scripts de limpieza\configurar_onedrive_excel.py"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    $PythonPath = "python"
}

& $PythonPath $ScriptPath --project-root $ProjectRoot
