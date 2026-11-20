<#
.SYNOPSIS
  One-command Memory Lane startup for Windows/VS Code: setup + API + web.

.DESCRIPTION
  Checks prerequisites, creates backend/.venv, installs dependencies,
  ensures the PostgreSQL database exists, runs migrations, installs
  frontend dependencies, then opens the API (8000) and web (3000) servers
  in two new windows. Re-running is safe (idempotent).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
  .\scripts\dev.ps1 -CheckOnly   # dry run: checks only, changes nothing
#>
param(
  [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Fail($message) {
  Write-Host ""
  Write-Host "ERROR: $message" -ForegroundColor Red
  exit 1
}

function Find-Python {
  $candidates = @(
    @{ Command = 'py'; Args = @('-3.12', '--version') },
    @{ Command = 'python3.12'; Args = @('--version') },
    @{ Command = 'python'; Args = @('--version') }
  )
  foreach ($candidate in $candidates) {
    try {
      $output = & $candidate.Command @($candidate.Args) 2>&1 | Out-String
      if ($output -match 'Python (\d+)\.(\d+)') {
        $major = [int]$matches[1]; $minor = [int]$matches[2]
        if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 12)) {
          return @{ Exe = $candidate.Command }
        }
      }
    } catch { }
  }
  return $null
}

Write-Host "Memory Lane dev startup" -ForegroundColor Cyan
Write-Host "Root: $root"

# 1. Prerequisites
$python = Find-Python
if (-not $python) { Fail 'No Python 3.12+ found. Install Python 3.12+ from python.org and re-run.' }
Write-Host "Python: $($python.Exe) (3.12+ OK)"
try {
  $nodeVersion = (node --version 2>&1 | Out-String).Trim()
  if ($nodeVersion -notmatch 'v(\d+)') { throw 'parse error' }
  if ([int]$matches[1] -lt 18) { Fail "Node 18+ required (found $nodeVersion)." }
  Write-Host "Node: $nodeVersion"
} catch {
  Fail 'Node.js not found. Install Node 20+ LTS from nodejs.org and re-run.'
}

# 2. Env file
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
  if ($CheckOnly) { Write-Host '[check] would copy .env.example -> .env' }
  else {
    Copy-Item (Join-Path $root '.env.example') $envFile
    Write-Host 'Created .env from .env.example (edit passwords/ports if needed).'
  }
} else { Write-Host '.env present.' }

# 3. DATABASE_URL
$databaseUrl = ''
foreach ($line in (Get-Content $envFile -ErrorAction SilentlyContinue)) {
  if ($line -match '^\s*DATABASE_URL\s*=\s*(.+?)\s*$') { $databaseUrl = $matches[1] }
}
if (-not $databaseUrl) {
  $databaseUrl = 'postgresql+asyncpg://memorylane:memorylane@127.0.0.1:5432/memorylane_dev'
  Write-Host 'DATABASE_URL not set in .env; using default dev database.'
}
Write-Host "Database: $databaseUrl"

if ($CheckOnly) {
  Write-Host ''
  Write-Host '[check] would: create backend/.venv, pip install, ensure DB, migrate, npm install, start API :8000 + web :3000.'
  Write-Host '[check] nothing was changed.'
  exit 0
}

# 4. Backend venv + deps
$venv = Join-Path $root 'backend\.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
  Write-Host 'Creating backend/.venv ...'
  $createArgs = @()
  if ($python.Exe -eq 'py') { $createArgs = @('-3.12', '-m', 'venv', $venv) }
  else { $createArgs = @('-m', 'venv', $venv) }
  $launcher = if ($python.Exe -eq 'python3.12') { 'python3.12' } elseif ($python.Exe -eq 'py') { 'py' } else { 'python' }
  & $launcher @createArgs
  if ($LASTEXITCODE -ne 0) { Fail 'Could not create backend/.venv.' }
}
Write-Host 'Installing backend dependencies (quiet; first run needs network) ...'
& $venvPython -m pip install -q --upgrade pip
& $venvPython -m pip install -q -e "$root\backend[dev]"
if ($LASTEXITCODE -ne 0) { Fail 'Backend pip install failed. Check network output above.' }

# 5. Database + migrations
Write-Host 'Ensuring database exists ...'
$env:DATABASE_URL = $databaseUrl
& $venvPython "$root\backend\scripts\ensure_db.py"
if ($LASTEXITCODE -ne 0) { Fail 'Database setup failed (see message above).' }
Write-Host 'Running migrations ...'
Push-Location (Join-Path $root 'backend')
& $venvPython -m alembic upgrade head
$migrateCode = $LASTEXITCODE
Pop-Location
if ($migrateCode -ne 0) { Fail 'Alembic migration failed.' }

# 6. Frontend deps
$nodeModules = Join-Path $root 'frontend\node_modules'
if (-not (Test-Path $nodeModules)) {
  Write-Host 'Installing frontend dependencies (first run needs network) ...'
  Push-Location (Join-Path $root 'frontend')
  npm install --no-audit --no-fund
  $npmCode = $LASTEXITCODE
  Pop-Location
  if ($npmCode -ne 0) { Fail 'npm install failed. Check network output above.' }
} else { Write-Host 'Frontend node_modules present.' }

# 7. Launch both servers in new windows
$apiCommand = "`$host.UI.RawUI.WindowTitle='Memory Lane API'; `$ErrorActionPreference='Stop'; cd '$root\backend'; & .\.venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --port 8000"
$webCommand = "`$host.UI.RawUI.WindowTitle='Memory Lane Web'; `$ErrorActionPreference='Stop'; cd '$root\frontend'; npm run dev"
Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $apiCommand | Out-Null
Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $webCommand | Out-Null

Write-Host ''
Write-Host 'Running:' -ForegroundColor Green
Write-Host '  Web app:  http://localhost:3000  (open this in your browser)'
Write-Host '  API docs: http://localhost:8000/docs'
Write-Host '  Health:   http://localhost:8000/healthz'
Write-Host ''
Write-Host 'Notes:'
Write-Host '  - Sign-in codes land in .devdata/mail/*.json (MAIL_DRIVER=file default).'
Write-Host '  - Photo/video uploads need the compose stack (MinIO); text/stories work fully.'
Write-Host '  - Stop the servers by closing the two new windows.'
