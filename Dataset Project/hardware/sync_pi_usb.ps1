param(
    [string]$PiHost = "192.168.137.8",
    [string]$PiUser = "pi",
    [string]$RemoteParent = "~",
    [switch]$IncludeDatasetV2,
    [switch]$IncludeRawRuns,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptPath = if ($PSCommandPath) { $PSCommandPath } else { $MyInvocation.MyCommand.Path }
$projectRoot = (Resolve-Path -LiteralPath (Join-Path (Split-Path -Parent $scriptPath) "..")).Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $projectRoot "..")).Path

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("capstone-pi-usb-" + [System.Guid]::NewGuid().ToString("N"))
$stageRoot = Join-Path $tempRoot "Capstone-Design"
$archivePath = Join-Path $tempRoot "capstone_design_usb_deploy.tgz"

function Assert-CommandAvailable {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Copy-RelativePath {
    param([string]$RelativePath)

    $source = Join-Path $repoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing required path: $source"
    }

    $destination = Join-Path $stageRoot $RelativePath
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
}

function Remove-StagedPycache {
    if (-not (Test-Path -LiteralPath $stageRoot)) {
        return
    }

    $stageFullPath = [System.IO.Path]::GetFullPath($stageRoot)
    $cacheDirs = @(Get-ChildItem -LiteralPath $stageRoot -Recurse -Force -Directory -Filter "__pycache__")
    foreach ($dir in $cacheDirs) {
        $dirFullPath = [System.IO.Path]::GetFullPath($dir.FullName)
        if ($dirFullPath.StartsWith($stageFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $dir.FullName -Recurse -Force
        }
    }
}

function Remove-TempRoot {
    if (-not (Test-Path -LiteralPath $tempRoot)) {
        return
    }

    $systemTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $target = [System.IO.Path]::GetFullPath($tempRoot)
    $leaf = Split-Path -Leaf $target
    if ($target.StartsWith($systemTemp, [System.StringComparison]::OrdinalIgnoreCase) -and
        $leaf.StartsWith("capstone-pi-usb-", [System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $target -Recurse -Force
    } else {
        Write-Warning "Temporary path was not removed because it did not pass the safety check: $target"
    }
}

try {
    Assert-CommandAvailable "ssh"
    Assert-CommandAvailable "scp"
    Assert-CommandAvailable "tar"

    New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null

    $paths = @(
        "AGENTS.md",
        "Lee",
        "Dataset Project\controllers",
        "Dataset Project\hardware",
        "Dataset Project\models",
        "Dataset Project\RASPBERRY_PI_DEPLOY.md",
        "Dataset Project\HANDOFF.md"
    )

    foreach ($path in $paths) {
        Copy-RelativePath $path
    }

    if ($IncludeDatasetV2) {
        Copy-RelativePath "Dataset Project\dataset_v2"
    }

    if ($IncludeRawRuns) {
        Copy-RelativePath "Dataset Project\dataset\runs"
    }

    Remove-StagedPycache

    $files = @(Get-ChildItem -LiteralPath $stageRoot -Recurse -File)
    $bytes = ($files | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $bytes) {
        $bytes = 0
    }
    $mb = [math]::Round($bytes / 1MB, 2)

    Write-Host "Prepared deployment package:"
    Write-Host "  files: $($files.Count)"
    Write-Host "  size : $mb MB"
    Write-Host "  mode : runtime/model files$(if ($IncludeDatasetV2) { ' + dataset_v2' } else { '' })$(if ($IncludeRawRuns) { ' + raw runs' } else { '' })"

    if ($DryRun) {
        Write-Host "Dry run only. Nothing was copied to the Pi."
        return
    }

    Write-Host "Creating archive..."
    & tar -czf $archivePath -C $tempRoot "Capstone-Design"
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE"
    }

    Write-Host "Checking SSH over USB network: $PiUser@$PiHost"
    $sshOpen = Test-NetConnection -ComputerName $PiHost -Port 22 -InformationLevel Quiet
    if (-not $sshOpen) {
        throw "SSH port 22 is not reachable at $PiHost. Check the USB cable, Pi power, and USB network sharing."
    }

    $remote = "$PiUser@$PiHost"
    $remoteArchive = "/tmp/capstone_design_usb_deploy.tgz"
    $sshOptions = @("-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10")

    Write-Host "Uploading archive to ${remote}:$remoteArchive"
    & ssh @sshOptions $remote "rm -f $remoteArchive"
    if ($LASTEXITCODE -ne 0) {
        throw "ssh pre-clean failed. Check Pi username/password."
    }

    & scp @sshOptions $archivePath "${remote}:${remoteArchive}"
    if ($LASTEXITCODE -ne 0) {
        throw "scp upload failed. Check Pi username/password and free space."
    }

    Write-Host "Extracting on Pi under $RemoteParent/Capstone-Design"
    $extractCommand = "mkdir -p $RemoteParent && tar -xzf $remoteArchive -C $RemoteParent && rm -f $remoteArchive && ls -lah $RemoteParent/Capstone-Design/'Dataset Project'/models"
    & ssh @sshOptions $remote $extractCommand
    if ($LASTEXITCODE -ne 0) {
        throw "remote extract failed"
    }

    Write-Host "Done."
    Write-Host "Pi run command:"
    Write-Host "  cd ~/Capstone-Design/Dataset\ Project"
    Write-Host "  python3 -B hardware/run_learned_pi.py --duration 10"
} finally {
    Remove-TempRoot
}
