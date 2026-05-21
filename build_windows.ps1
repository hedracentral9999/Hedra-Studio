param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

Write-Host "== Hedra Studio Windows build =="

if (-not (Test-Path "venv")) {
    py -3.11 -m venv venv
}

& .\venv\Scripts\python.exe -m pip install --upgrade pip
& .\venv\Scripts\python.exe -m pip install -r requirements_build.txt

Write-Host "Security audit source..."
& .\venv\Scripts\python.exe scripts\security_audit_release.py --source .

Write-Host "Building portable EXE..."
& .\venv\Scripts\pyinstaller.exe TTS.spec --clean --noconfirm

Write-Host "Security audit portable EXE..."
& .\venv\Scripts\python.exe scripts\security_audit_release.py --artifact "dist\Hedra Studio.exe" --exact-local

if ($SkipInstaller) {
    Write-Host "Portable EXE: dist\Hedra Studio.exe"
    exit 0
}

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $paths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) {
            $iscc = Get-Item $p
            break
        }
    }
}

if (-not $iscc) {
    Write-Warning "Inno Setup not found. Install it or run: choco install innosetup -y"
    Write-Host "Portable EXE: dist\Hedra Studio.exe"
    exit 0
}

Write-Host "Building installer..."
& $iscc.Source setup.iss
Write-Host "Security audit installer..."
$installer = Get-ChildItem -Path . -Filter "Hedra-Studio-*-win-setup.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($installer) {
    & .\venv\Scripts\python.exe scripts\security_audit_release.py --artifact $installer.FullName --exact-local
}
Write-Host "Installer: Hedra-Studio-*-win-setup.exe"
