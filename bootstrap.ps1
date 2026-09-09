param(
    [switch]$NoGui,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$MarkerDir = Join-Path $env:LOCALAPPDATA "AURA\1.0.8"
$BrowserMarker = Join-Path $MarkerDir "playwright-browser-ready"
$RuntimeDir = Join-Path $Root ".runtime"
$NodeDir = Join-Path $RuntimeDir "node"
$LocalNode = Join-Path $Root ".runtime\node\node.exe"
$script:NodeExecutable = $null

function Write-Step([string]$Text) {
    Write-Host "[AURA] $Text" -ForegroundColor Cyan
}

function Find-Python {
    $candidates = @()
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) { $candidates += @($pythonCmd.Source) }
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) { $candidates += @("py") }
    $candidates += @(Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName)

    foreach ($candidate in $candidates) {
        try {
            if ($candidate -eq "py") {
                & py -3 -c "import sys; print(sys.executable)" *> $null
                if ($LASTEXITCODE -eq 0) { return "py" }
            } else {
                & $candidate -c "import sys; print(sys.executable)" *> $null
                if ($LASTEXITCODE -eq 0) { return $candidate }
            }
        } catch {}
    }
    return $null
}

function Ensure-Python {
    $python = Find-Python
    if ($python) { return $python }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python 3 fehlt und winget ist nicht verfügbar. Bitte Python 3.12 von python.org installieren."
    }

    Write-Step "Python 3.12 fehlt. Installiere das offizielle winget-Paket Python.Python.3.12 …"
    & winget install --id Python.Python.3.12 --exact --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "Python-Installation fehlgeschlagen (winget Exit $LASTEXITCODE)." }

    $python = Find-Python
    if (-not $python) { throw "Python wurde installiert, aber noch nicht gefunden. Bitte einmal Windows neu anmelden und START.bat erneut öffnen." }
    return $python
}

function Find-Node {
    $candidates = @()
    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCmd) { $candidates += @($nodeCmd.Source) }
    $candidates += @(
        $LocalNode,
        "$env:ProgramFiles\nodejs\node.exe",
        "${env:ProgramFiles(x86)}\nodejs\node.exe",
        "$env:LOCALAPPDATA\Programs\nodejs\node.exe"
    )
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not $candidate -or -not (Test-Path $candidate)) { continue }
        try {
            & $candidate --version *> $null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch {}
    }
    return $null
}

function Install-PortableNode {
    Write-Step "winget ist nicht verfügbar. Installiere Node.js LTS portabel vom offiziellen nodejs.org-Server …"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
    $TempDir = Join-Path ([IO.Path]::GetTempPath()) ("symbiose-node-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    try {
        $IndexUrl = "https://nodejs.org/dist/index.json"
        $Releases = Invoke-RestMethod -Uri $IndexUrl -UseBasicParsing
        $Release = $Releases | Where-Object { $_.lts -and ($_.files -contains "win-x64-zip") } | Select-Object -First 1
        if (-not $Release) { throw "Keine offizielle Node.js-LTS-Version für Windows x64 gefunden." }
        $Version = [string]$Release.version
        if ($Version -notmatch '^v\d+\.\d+\.\d+$') { throw "Ungültige Node.js-Version vom Release-Index: $Version" }
        $ArchiveName = "node-$Version-win-x64.zip"
        $BaseUrl = "https://nodejs.org/dist/$Version"
        $ArchivePath = Join-Path $TempDir $ArchiveName
        $SumsPath = Join-Path $TempDir "SHASUMS256.txt"

        Invoke-WebRequest -Uri "$BaseUrl/$ArchiveName" -OutFile $ArchivePath -UseBasicParsing
        Invoke-WebRequest -Uri "$BaseUrl/SHASUMS256.txt" -OutFile $SumsPath -UseBasicParsing

        $ExpectedLine = Get-Content $SumsPath | Where-Object { $_ -match ("^[0-9a-fA-F]{64}\s+" + [regex]::Escape($ArchiveName) + "$") } | Select-Object -First 1
        if (-not $ExpectedLine) { throw "SHA-256-Eintrag für $ArchiveName fehlt im offiziellen Manifest." }
        $ExpectedHash = ($ExpectedLine -split '\s+')[0].ToUpperInvariant()
        $ActualHash = (Get-FileHash -Path $ArchivePath -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($ActualHash -ne $ExpectedHash) { throw "SHA-256-Prüfung für Node.js fehlgeschlagen." }

        $ExtractDir = Join-Path $TempDir "extract"
        Expand-Archive -Path $ArchivePath -DestinationPath $ExtractDir -Force
        $ExtractedRoot = Get-ChildItem $ExtractDir -Directory | Select-Object -First 1
        if (-not $ExtractedRoot) { throw "Node.js-Archiv enthält kein Runtime-Verzeichnis." }
        $DownloadedNode = Join-Path $ExtractedRoot.FullName "node.exe"
        if (-not (Test-Path $DownloadedNode)) { throw "node.exe fehlt im verifizierten Archiv." }
        $Signature = Get-AuthenticodeSignature -FilePath $DownloadedNode
        if ($Signature.Status -ne "Valid" -or -not $Signature.SignerCertificate -or $Signature.SignerCertificate.Subject -notmatch "OpenJS Foundation|Node.js") {
            throw "Die Authenticode-Signatur von node.exe ist nicht gültig oder stammt nicht von OpenJS/Node.js."
        }

        $NewNodeDir = Join-Path $RuntimeDir "node.new"
        Remove-Item $NewNodeDir -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item $ExtractedRoot.FullName $NewNodeDir
        Remove-Item $NodeDir -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item $NewNodeDir $NodeDir
    } finally {
        Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Ensure-Node {
    $node = Find-Node
    if ($node) {
        $env:Path = "$(Split-Path -Parent $node);$env:Path"
        $script:NodeExecutable = $node
        return
    }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Step "Node.js LTS fehlt. Installiere das offizielle winget-Paket OpenJS.NodeJS.LTS …"
        & winget install --id OpenJS.NodeJS.LTS --exact --source winget --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { throw "Node.js-Installation fehlgeschlagen (winget Exit $LASTEXITCODE)." }
    } else {
        Install-PortableNode
    }

    $node = Find-Node
    if (-not $node) { throw "Node.js wurde installiert, konnte aber nicht gestartet werden." }
    $NodeDir = Split-Path -Parent $node
    $env:Path = "$NodeDir;$env:Path"
    $script:NodeExecutable = $node
    return
}

function Invoke-BasePython([string]$Python, [string[]]$Arguments) {
    if ($Python -eq "py") { & py -3 @Arguments } else { & $Python @Arguments }
    return $LASTEXITCODE
}

try {
    Write-Step "Prüfe Systemvoraussetzungen …"
    $BasePython = Ensure-Python
    Ensure-Node
    if (-not $script:NodeExecutable) { throw "Node.js-Prüfung lieferte keinen ausführbaren Pfad." }
    $env:SYM_NODE = $script:NodeExecutable

    if (-not (Test-Path $VenvPython)) {
        Write-Step "Erstelle isolierte Projektumgebung .venv …"
        $rc = Invoke-BasePython $BasePython @("-m", "venv", $VenvDir)
        if ($rc -ne 0) { throw "Virtuelle Python-Umgebung konnte nicht erstellt werden." }
    }

    Write-Step "Prüfe optionale Browser-Test-Abhängigkeiten …"
    & $VenvPython -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('playwright') else 1)" 2>$null
    $PlaywrightMissing = ($LASTEXITCODE -ne 0)
    $global:LASTEXITCODE = 0
    if ($PlaywrightMissing) {
        Write-Step "Installiere geprüfte Python-Abhängigkeiten aus requirements.txt …"
        & $VenvPython -m pip install --disable-pip-version-check --requirement (Join-Path $Root "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "Python-Abhängigkeiten konnten nicht installiert werden." }
    }

    if (-not (Test-Path $BrowserMarker)) {
        Write-Step "Installiere Chromium für den lokalen Browser-E2E-Test …"
        & $VenvPython -m playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium konnte nicht installiert werden." }
        New-Item -ItemType Directory -Path $MarkerDir -Force | Out-Null
        Set-Content -Path $BrowserMarker -Value (Get-Date -Format o) -Encoding UTF8
    }

    Write-Step "Alle Abhängigkeiten sind bereit."
    if ($CheckOnly) {
        Write-Host "BOOTSTRAP_CHECK_OK" -ForegroundColor Green
        exit 0
    }

    Write-Step "Starte Control Center …"
    if ($NoGui) {
        & $VenvPython (Join-Path $Root "start.py") --cli
    } else {
        & $VenvPython (Join-Path $Root "start.py")
    }
    exit $LASTEXITCODE
} catch {
    Write-Host ""
    $detail = $_.Exception.Message
    if (-not $detail -or $detail -eq "Traceback (most recent call last):") {
        $detail = ($_ | Out-String).Trim()
    }
    Write-Host "[FEHLER] $detail" -ForegroundColor Red
    Write-Host "Nichts wurde blind aus fremden Skripten ausgeführt. Installiert werden nur offizielle winget-Pakete und requirements.txt." -ForegroundColor Yellow
    Write-Host "" 
    Read-Host "Enter drücken zum Schließen"
    exit 1
}
