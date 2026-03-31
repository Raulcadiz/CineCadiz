# download-mpv.ps1
# Descarga mpv.exe y lo coloca en ./mpv/ para CineCADIZ Console

$mpvDir = Join-Path $PSScriptRoot "mpv"
$mpvExe = Join-Path $mpvDir "mpv.exe"

if (Test-Path $mpvExe) {
    Write-Host "[OK] mpv.exe ya existe en $mpvExe" -ForegroundColor Green
    exit 0
}

New-Item -ItemType Directory -Force -Path $mpvDir | Out-Null

# ── 1. Intentar con winget ────────────────────────────────────────────────────
if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "Instalando mpv via winget..." -ForegroundColor Cyan
    winget install mpv.mpv --silent 2>$null
    $inPath = Get-Command mpv.exe -ErrorAction SilentlyContinue
    if ($inPath) {
        Copy-Item $inPath.Source $mpvExe -Force
        Write-Host "[OK] mpv instalado y copiado a $mpvExe" -ForegroundColor Green
        exit 0
    }
}

# ── 2. Intentar con Chocolatey ────────────────────────────────────────────────
if (Get-Command choco -ErrorAction SilentlyContinue) {
    Write-Host "Instalando mpv via Chocolatey..." -ForegroundColor Cyan
    choco install mpv -y --no-progress 2>$null
    $inPath = Get-Command mpv.exe -ErrorAction SilentlyContinue
    if ($inPath) {
        Copy-Item $inPath.Source $mpvExe -Force
        Write-Host "[OK] mpv copiado a $mpvExe" -ForegroundColor Green
        exit 0
    }
}

# ── 3. Si mpv ya está en PATH, simplemente copiarlo ──────────────────────────
$inPath = Get-Command mpv.exe -ErrorAction SilentlyContinue
if ($inPath) {
    Copy-Item $inPath.Source $mpvExe -Force
    Write-Host "[OK] mpv copiado desde PATH a $mpvExe" -ForegroundColor Green
    exit 0
}

# ── 4. Descarga directa desde GitHub Releases (shinchiro builds) ─────────────
Write-Host "Buscando ultima version de mpv en GitHub..." -ForegroundColor Cyan
try {
    $releases = Invoke-RestMethod "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases"
    $latest   = $releases | Where-Object { $_.tag_name -match "^\d{8}$" } | Select-Object -First 1

    if ($latest) {
        $asset = $latest.assets | Where-Object { $_.name -match "mpv-x86_64-.*\.7z$" } | Select-Object -First 1
        if ($asset) {
            $zipPath = Join-Path $env:TEMP "mpv-download.7z"
            Write-Host "Descargando $($asset.name)..." -ForegroundColor Cyan
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing

            # Intentar extraer con 7zip si está disponible
            $7zip = Get-Command "7z.exe" -ErrorAction SilentlyContinue
            if (!$7zip) { $7zip = Get-Command "7za.exe" -ErrorAction SilentlyContinue }
            if ($7zip) {
                $extractDir = Join-Path $env:TEMP "mpv-extract"
                & $7zip.Source x $zipPath -o"$extractDir" -y | Out-Null
                $extracted = Get-ChildItem "$extractDir" -Recurse -Filter "mpv.exe" | Select-Object -First 1
                if ($extracted) {
                    Copy-Item $extracted.FullName $mpvExe -Force
                    Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue
                    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
                    Write-Host "[OK] mpv descargado e instalado en $mpvExe" -ForegroundColor Green
                    exit 0
                }
            } else {
                Write-Host "7zip no encontrado, no se puede extraer el .7z automaticamente." -ForegroundColor Yellow
            }
        }
    }
} catch {
    Write-Host "Error al descargar desde GitHub: $_" -ForegroundColor Yellow
}

# ── Sin exito: instrucciones manuales ─────────────────────────────────────────
Write-Host ""
Write-Host "No se pudo instalar mpv automaticamente." -ForegroundColor Yellow
Write-Host ""
Write-Host "OPCION 1 - winget (recomendado):" -ForegroundColor White
Write-Host "  winget install mpv.mpv" -ForegroundColor Cyan
Write-Host "  Luego copia mpv.exe a: $mpvDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "OPCION 2 - Descarga manual:" -ForegroundColor White
Write-Host "  https://mpv.io/installation/ (seccion Windows)" -ForegroundColor Cyan
Write-Host "  Extrae mpv.exe y copialo a: $mpvDir" -ForegroundColor Cyan
Write-Host ""
exit 1
