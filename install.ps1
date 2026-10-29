# Installation de Musicothèque : Python + bibliothèques + outils (ffmpeg, fpcalc, cyanrip) + raccourci bureau
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bin = Join-Path $Root "bin"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
$Tmp = Join-Path $env:TEMP "musicotheque_setup"
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

function Step($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }

# ---------- 1. Python ----------
Step "Python"
$py = $null
foreach ($c in @("py -3", "python")) {
    try { $v = & cmd /c "$c --version 2>&1"; if ($v -match "Python 3\.(1[0-9])") { $py = $c; break } } catch {}
}
if (-not $py) {
    Write-Host "Python 3.10+ absent : installation via winget..."
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
    $py = "py -3"
}
Write-Host "Python : $py"

# ---------- 2. Environnement + bibliothèques ----------
Step "Bibliothèques Python"
$venv = Join-Path $Root ".venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) { & cmd /c "$py -m venv `"$venv`"" }
& "$venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& "$venv\Scripts\python.exe" -m pip install -r (Join-Path $Root "requirements.txt") --quiet --disable-pip-version-check
Write-Host "Bibliothèques Python prêtes ✓" -ForegroundColor Green

function Get-GithubAsset($repo, $pattern) {
    $rel = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" -Headers @{ "User-Agent" = "musicotheque" }
    $a = $rel.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
    if (-not $a) { throw "Fichier introuvable dans $repo ($pattern)" }
    return $a.browser_download_url
}
function Download($url, $out) {
    # curl.exe (fourni avec Windows 10/11) : rapide, avec barre de progression et nouvelle tentative
    Write-Host "Téléchargement : $url"
    if (Test-Path $out) { Remove-Item -Force $out }
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -L --fail --retry 3 --retry-delay 3 --connect-timeout 20 --speed-limit 10000 --speed-time 60 `
            --progress-bar -o $out $url
        if ($LASTEXITCODE -ne 0) { throw "échec du téléchargement (code $LASTEXITCODE)" }
    } else {
        Invoke-WebRequest $url -OutFile $out -TimeoutSec 900 -UseBasicParsing
    }
    if (-not (Test-Path $out) -or (Get-Item $out).Length -lt 100000) { throw "fichier téléchargé incomplet" }
}
function Expand($zip, $dir) {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Write-Host "Décompression…"
    # tar.exe (Windows 10/11) décompresse bien plus vite qu'Expand-Archive
    $ok = $false
    if (Get-Command tar.exe -ErrorAction SilentlyContinue) {
        & tar.exe -xf $zip -C $dir
        $ok = ($LASTEXITCODE -eq 0)
    }
    if (-not $ok) { Expand-Archive $zip -DestinationPath $dir -Force }
}
function Get-Zip($url, $name) {
    $zip = Join-Path $Tmp "$name.zip"; $dir = Join-Path $Tmp $name
    Download $url $zip
    Expand $zip $dir
    return $dir
}

# ---------- 3. ffmpeg ----------
Step "ffmpeg (lecture et conversion) — environ 100 Mo, quelques minutes"
if (-not (Test-Path "$Bin\ffmpeg.exe")) {
    $sources = @(
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    )
    foreach ($u in $sources) {
        try {
            $d = Get-Zip $u "ffmpeg"
            Get-ChildItem $d -Recurse -Include ffmpeg.exe, ffprobe.exe | Copy-Item -Destination $Bin -Force
            if (Test-Path "$Bin\ffmpeg.exe") { break }
        } catch { Write-Warning "Source indisponible ($u) : $_ — essai suivant…" }
    }
    if (-not (Test-Path "$Bin\ffmpeg.exe")) {
        Write-Host "Essai via winget…"
        try {
            winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
            Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet" -Recurse -Include ffmpeg.exe, ffprobe.exe -ErrorAction SilentlyContinue |
                Copy-Item -Destination $Bin -Force
        } catch { Write-Warning "winget : $_" }
    }
    if (Test-Path "$Bin\ffmpeg.exe") { Write-Host "ffmpeg installé ✓" -ForegroundColor Green }
    else {
        Write-Warning ("ffmpeg n'a pas pu être téléchargé automatiquement. Solution manuelle :`n" +
            "  1. téléchargez https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip dans votre navigateur ;`n" +
            "  2. ouvrez le zip, dossier « bin », et copiez ffmpeg.exe et ffprobe.exe dans :`n     $Bin`n" +
            "  3. relancez installer.bat.")
    }
} else { Write-Host "déjà présent" }

# ---------- 4. fpcalc (empreinte audio Chromaprint) ----------
Step "fpcalc (reconnaissance des titres)"
if (-not (Test-Path "$Bin\fpcalc.exe")) {
    try {
        $d = Get-Zip (Get-GithubAsset "acoustid/chromaprint" "windows-x86_64\.zip$") "fpcalc"
        Get-ChildItem $d -Recurse -Include fpcalc.exe | Copy-Item -Destination $Bin -Force
    } catch {
        Write-Host "Téléchargement direct impossible, essai via winget..."
        winget install -e --id AcoustID.Chromaprint --accept-package-agreements --accept-source-agreements
    }
} else { Write-Host "déjà présent" }

# ---------- 5. cyanrip (extraction de CD) ----------
Step "cyanrip (CD audio -> MP3)"
if (-not (Test-Path "$Bin\cyanrip.exe")) {
    try {
        $url = Get-GithubAsset "cyanreg/cyanrip" "win.*64.*\.(zip|exe)$"
        if ($url -match "\.zip$") {
            $d = Get-Zip $url "cyanrip"
            Get-ChildItem $d -Recurse -Include *.exe, *.dll | Copy-Item -Destination $Bin -Force
        } else { Invoke-WebRequest $url -OutFile "$Bin\cyanrip.exe" }
    } catch {
        Write-Host "Téléchargement direct impossible, essai via winget..."
        winget install -e --id cyanreg.cyanrip --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Write-Warning "cyanrip indisponible : l'extraction de CD ne fonctionnera pas." }
    }
} else { Write-Host "déjà présent" }

# ---------- 6. Raccourci ----------
Step "Raccourci sur le Bureau"
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Musicothèque.lnk"))
$lnk.TargetPath = "$venv\Scripts\pythonw.exe"
$lnk.Arguments = "`"$Root\main.py`""
$lnk.WorkingDirectory = $Root
$lnk.IconLocation = "$env:SystemRoot\System32\imageres.dll,103"
$lnk.Save()

Write-Host "`nInstallation terminée. Lancez « Musicothèque » depuis le Bureau." -ForegroundColor Green
