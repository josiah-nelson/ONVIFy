[CmdletBinding()]
param(
    [string]$Python,
    [string]$OutputDir = "dist",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

if (-not $Python) {
    $VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        $Python = $VenvPython
    } else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $PythonCommand) {
            $PythonCommand = Get-Command py -ErrorAction SilentlyContinue
        }
        if (-not $PythonCommand) {
            throw "Python not found. Install Python 3.11+ or pass -Python."
        }
        $Python = $PythonCommand.Source
    }
}

& $Python -c "import PyInstaller" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run: $Python -m pip install -e `".[packaging]`""
}

$DistPath = Join-Path $RepoRoot $OutputDir
$PyInstallerArgs = @(
    "-m", "PyInstaller",
    "--onefile",
    "--name", "onvify",
    "--distpath", $DistPath,
    "--workpath", (Join-Path $RepoRoot "build\pyinstaller"),
    "--specpath", (Join-Path $RepoRoot "build\pyinstaller"),
    "--paths", (Join-Path $RepoRoot "src"),
    "--collect-all", "onvify",
    (Join-Path $RepoRoot "src\onvify\cli.py")
)

if ($Clean) {
    $PyInstallerArgs = @("-m", "PyInstaller", "--clean") + $PyInstallerArgs[2..($PyInstallerArgs.Length - 1)]
}

& $Python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$Executable = Join-Path $DistPath "onvify.exe"
if (-not (Test-Path $Executable)) {
    throw "Expected bundle was not created at $Executable"
}

Write-Host "Created $Executable"
