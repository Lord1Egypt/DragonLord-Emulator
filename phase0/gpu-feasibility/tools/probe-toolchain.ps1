param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath (Join-Path $OutputDirectory 'toolchain.json')) { throw 'Use a fresh output directory to preserve previous results' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$result = [ordered]@{scope='Native Windows toolchain inventory; no rendering qualification';timestamp_utc=[DateTime]::UtcNow.ToString('o');status='BLOCKED';graphics='NOT TESTED'}
try {
    if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Native Windows required' }
    $result.os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture
    $result.gpus = @(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion)
    $where = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    $instances = @()
    if (Test-Path -LiteralPath $where) {
        $instances = @((& $where -all -products '*' -format json | Out-String | ConvertFrom-Json))
    }
    $result.visual_studio = @($instances | Select-Object installationPath,installationVersion,productId)
    $toolsFound = @()
    foreach ($name in @('cmake.exe','ninja.exe','clang-cl.exe','cl.exe','git.exe','python.exe','cargo.exe','rustc.exe','vulkaninfo.exe','nvidia-smi.exe','wpr.exe','xperf.exe')) {
        $found = @(Get-Command $name -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
        $toolsFound += [ordered]@{name=$name;paths=$found}
    }
    foreach ($instance in $instances) {
        foreach ($relative in @('VC\Tools\Llvm\x64\bin\clang-cl.exe','VC\Tools\Llvm\bin\clang-cl.exe','Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe','Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe','Common7\Tools\VsDevCmd.bat','VC\Auxiliary\Build\vcvars64.bat')) {
            $path = Join-Path $instance.installationPath $relative
            $toolsFound += [ordered]@{name=$relative;paths=@($path | Where-Object { Test-Path -LiteralPath $_ })}
        }
        $msvc = Join-Path $instance.installationPath 'VC\Tools\MSVC'
        if (Test-Path -LiteralPath $msvc) {
            $toolsFound += [ordered]@{name='MSVC compiler directories';paths=@(Get-ChildItem -Directory -LiteralPath $msvc | Select-Object -ExpandProperty FullName)}
        }
    }
    $toolsFound += [ordered]@{name='Standalone LLVM';paths=@((Join-Path $env:ProgramFiles 'LLVM\bin\clang-cl.exe') | Where-Object { Test-Path -LiteralPath $_ })}
    $result.tools = $toolsFound
    $result.vulkan_sdk = $env:VULKAN_SDK
    $result.vulkan_loader = Get-Item (Join-Path $env:SystemRoot 'System32\vulkan-1.dll') -ErrorAction SilentlyContinue | Select-Object FullName,@{Name='FileVersion';Expression={$_.VersionInfo.FileVersion}}
    $result.status = 'PASS'
    $result.reason = 'Inventory completed only; build and hardware rendering gates are separate'
} catch { $result.reason=$_.Exception.Message }
$json = $result | ConvertTo-Json -Depth 8
if ($env:USERPROFILE) { $json = $json.Replace($env:USERPROFILE.Replace('\','\\'),'%USERPROFILE%') }
$json | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'toolchain.json')
if ($result.status -eq 'PASS') { exit 0 }; exit 2
