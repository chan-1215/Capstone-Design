param([switch]$Install)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$datasetRoot = Join-Path $projectRoot 'Dataset Project'

Write-Host "Project: $projectRoot"
Write-Host "Checking required programs..."

$checks = @(
    @{ Name = 'Git'; Command = 'git'; WingetId = 'Git.Git' },
    @{ Name = 'GitHub CLI'; Command = 'gh'; WingetId = 'GitHub.cli' },
    @{ Name = 'Python'; Command = 'python'; WingetId = 'Python.Python.3.13' }
)

foreach ($item in $checks) {
    $found = Get-Command $item.Command -ErrorAction SilentlyContinue
    if ($found) {
        Write-Host "[OK] $($item.Name): $($found.Source)"
    } elseif ($Install) {
        Write-Host "[INSTALL] $($item.Name)"
        winget install --id $item.WingetId --exact --accept-package-agreements --accept-source-agreements
    } else {
        Write-Warning "$($item.Name) is missing. Re-run with -Install after review."
    }
}

$webots = 'C:\Program Files\Webots\msys64\mingw64\bin\webots.exe'
if (Test-Path -LiteralPath $webots) {
    Write-Host "[OK] Webots: $webots"
} else {
    Write-Warning 'Webots R2025a is missing. Install it before opening a .wbt world.'
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    if ($Install) {
        python -m pip install --upgrade numpy opencv-python
    } else {
        python -c "import cv2, numpy; print('[OK] OpenCV', cv2.__version__, 'NumPy', numpy.__version__)"
    }

    $runtimeIni = Join-Path $datasetRoot 'controllers\rc_car_controller\runtime.ini'
    if (Test-Path -LiteralPath $runtimeIni) {
        try {
            @(
                '[python]'
                "COMMAND = $($pythonCommand.Source)"
            ) | Set-Content -LiteralPath $runtimeIni -Encoding ASCII
            Write-Host "[OK] Webots controller Python runtime: $($pythonCommand.Source)"
        } catch {
            Write-Warning "Could not update Webots controller Python runtime: $runtimeIni"
            Write-Warning $_.Exception.Message
        }
    }
}

$required = @(
    (Join-Path $datasetRoot 'worlds\collect_rectangle_lane_1.wbt'),
    (Join-Path $datasetRoot 'dataset\runs\run_20260831_015552\driving.csv'),
    (Join-Path $datasetRoot 'models\steering_v1.npz')
)
foreach ($path in $required) {
    if (Test-Path -LiteralPath $path) { Write-Host "[OK] $path" }
    else { Write-Warning "Missing project artifact: $path" }
}

Write-Host 'Read: Dataset Project\HANDOFF.md'
