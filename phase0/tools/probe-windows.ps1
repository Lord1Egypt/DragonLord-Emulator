param(
    [Parameter(Mandatory=$true)][string]$Qemu,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
# Read-only inventory and device discovery. This probe cannot pass a GPU runtime gate.
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$result = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
    scope = 'Native Windows hardware and QEMU capability inventory only'
    status = 'BLOCKED'
    whpx_boot = 'NOT_TESTED'
    gpu_runtime = 'NOT_TESTED'
    android16 = 'NOT_TESTED'
    kernelsu = 'NOT_TESTED'
}
try {
    $result.os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture
    $result.cpu = Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,VirtualizationFirmwareEnabled
    $result.gpus = @(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM)
    $result.whpx_dll_present = Test-Path "$env:SystemRoot\System32\WinHvPlatform.dll"
    $result.qemu_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Qemu).Hash.ToLower()
    $result.qemu_version = (& $Qemu --version 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw 'qemu --version failed' }
    & $Qemu -accel help 2>&1 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'accelerators.txt')
    if ($LASTEXITCODE -ne 0) { throw 'accelerator enumeration failed' }
    & $Qemu -device help 2>&1 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'devices.txt')
    if ($LASTEXITCODE -ne 0) { throw 'device enumeration failed' }
    & $Qemu -display help 2>&1 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'displays.txt')
    $vk = Get-Command vulkaninfo.exe -ErrorAction SilentlyContinue
    if ($vk) {
        # Optional driver diagnostics must not invalidate a successful QEMU inventory.
        $previousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & $vk.Source --summary 2>&1 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'vulkan-summary.txt')
            $result.vulkaninfo_exit_code = $LASTEXITCODE
        } finally { $ErrorActionPreference = $previousPreference }
    }
    $result.status = 'INVENTORY_COLLECTED'
    $result.reason = 'Run the strict WHPX boot experiment and an Android rendering workload separately'
} catch {
    $result.reason = $_.Exception.Message
}
$result | ConvertTo-Json -Depth 8 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'inventory.json')
if ($result.status -eq 'BLOCKED') { exit 2 }
exit 0
