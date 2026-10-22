$ErrorActionPreference = 'Stop'

Push-Location $PSScriptRoot
try {
    $pythonCandidates = @(
        (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
        (Join-Path $PSScriptRoot 'venv313\Scripts\python.exe'),
        (Join-Path $PSScriptRoot 'venv\Scripts\python.exe')
    )
    $projectPython = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $projectPython) {
        throw 'No project Python environment found. Create .venv or venv313 first.'
    }

    function Invoke-QualityStep {
        param(
            [Parameter(Mandatory = $true)][string]$Label,
            [Parameter(Mandatory = $true)][string[]]$Arguments
        )

        Write-Host "`n=== $Label ===" -ForegroundColor Cyan
        & $projectPython @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Quality check failed: $Label (exit code $LASTEXITCODE)"
        }
    }

    Invoke-QualityStep -Label 'Django system check' -Arguments @('manage.py', 'check')
    Invoke-QualityStep -Label 'Migration drift check' -Arguments @('manage.py', 'makemigrations', '--check')
    Invoke-QualityStep -Label 'Migration plan' -Arguments @('manage.py', 'migrate', '--plan')
    Invoke-QualityStep -Label 'Automated tests' -Arguments @('manage.py', 'test', '--verbosity', '1')
    Invoke-QualityStep -Label 'Dependency consistency' -Arguments @('-m', 'pip', 'check')
    Invoke-QualityStep -Label 'Staticfiles collection (dry run)' -Arguments @('manage.py', 'collectstatic', '--noinput', '--dry-run', '--verbosity', '0')

    Write-Host "`nQuality checks passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
