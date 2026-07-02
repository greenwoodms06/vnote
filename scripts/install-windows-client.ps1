# Installs the vnote flow client on Windows Python and (optionally) starts it at login.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install-windows-client.ps1
#   ... -Startup            also drop a pythonw shortcut into shell:startup
#   ... -RepoPath C:\src\vnote -Flags "--tray --vad --stream"
#
# Re-run after every `git pull` — the Windows install is a copy, not editable.

param(
    [string]$RepoPath = "D:\Projects\vnote",
    [string]$Flags = "--tray --vad --clean --stream",
    [switch]$Startup
)

$ErrorActionPreference = "Stop"

Write-Host "Installing vnote[flow] from $RepoPath ..."
py -m pip install --upgrade --quiet "$RepoPath[flow]"
py -m vnote.client.app --version

if ($Startup) {
    # pythonw = no console window; the --tray icon is the UI. Ask the interpreter
    # where it lives — pythonw.exe sits next to python.exe, not next to py.exe.
    $pyw = py -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"
    if (-not (Test-Path $pyw)) { $pyw = (Get-Command pythonw).Source }
    $dir = [Environment]::GetFolderPath("Startup")
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut((Join-Path $dir "vnote-flow.lnk"))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = "-m vnote.client.app $Flags"
    $lnk.Description = "vnote flow dictation client"
    $lnk.Save()
    Write-Host "Startup shortcut created: $dir\vnote-flow.lnk"
    Write-Host "(it needs the daemon; auto-start that too — see the README)"
}

Write-Host "Done. Run now with:  py -m vnote.client.app $Flags"
