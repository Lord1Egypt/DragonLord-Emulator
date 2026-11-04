param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath (Join-Path $OutputDirectory 'host.json')) { throw 'Use a fresh output directory' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$result = [ordered]@{scope='Read-only Windows API/device inventory, not a rendering workload';timestamp_utc=[DateTime]::UtcNow.ToString('o');status='BLOCKED';gfxstream_selected_adapter=$null;hardware_execution='NOT TESTED';commands=@()}
try {
    if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Native Windows required' }
    $result.os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version
    $result.gpus = @(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion)
    foreach ($spec in @(@('vulkaninfo.exe','--summary'),@('nvidia-smi.exe','--query-gpu=name,pci.bus_id,driver_version','--format=csv,noheader'))) {
        $tool = Get-Command $spec[0] -ErrorAction SilentlyContinue
        if (-not $tool) { $result.commands += @{tool=$spec[0];status='BLOCKED';reason='Not found'}; continue }
        $psi = New-Object Diagnostics.ProcessStartInfo
        $psi.FileName = $tool.Source
        $psi.Arguments = ($spec | Select-Object -Skip 1) -join ' '
        $psi.WorkingDirectory = $env:SystemRoot
        $psi.UseShellExecute=$false
        $psi.CreateNoWindow=$true
        $psi.RedirectStandardOutput=$true
        $psi.RedirectStandardError=$true
        $p=New-Object Diagnostics.Process
        $p.StartInfo=$psi
        [void]$p.Start()
        $stdout=$p.StandardOutput.ReadToEndAsync()
        $stderr=$p.StandardError.ReadToEndAsync()
        if (-not $p.WaitForExit(30000)) { $p.Kill(); $p.WaitForExit(); throw 'Host inventory command timeout' }
        $stdout.Result | Out-File -Encoding utf8 (Join-Path $OutputDirectory ($spec[0]+'.stdout.log'))
        $stderr.Result | Out-File -Encoding utf8 (Join-Path $OutputDirectory ($spec[0]+'.stderr.log'))
        $result.commands += @{tool=$tool.Source;argv=@($spec | Select-Object -Skip 1);exit_code=$p.ExitCode;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $tool.Source).Hash.ToLower()}
    }
    $libraries=@()
    foreach ($name in @('vulkan-1.dll','libEGL.dll','libGLESv2.dll')) {
        $paths=@()
        foreach ($dir in (($env:PATH -split ';') + @((Join-Path $env:SystemRoot 'System32')) | Select-Object -Unique)) {
            if (-not $dir) { continue }
            $candidate=Join-Path $dir $name
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $paths += $candidate }
        }
        $libraries += @{name=$name;paths=@($paths | Select-Object -Unique);scope='PATH and System32 search only; not runtime module loading'}
    }
    $result.library_discovery=$libraries
    $result.status='PASS'
    $result.reason='Inventory only; device/API strings do not prove Gfxstream hardware execution'
} catch { $result.reason=$_.Exception.Message }
$json=$result | ConvertTo-Json -Depth 8
if ($env:USERPROFILE) { $json=$json.Replace($env:USERPROFILE.Replace('\','\\'),'%USERPROFILE%') }
$json | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'host.json')
if ($result.status -eq 'PASS') { exit 0 }; exit 2
