param(
    [Parameter(Mandatory=$true)][string]$Qemu,
    [Parameter(Mandatory=$true)][string]$Kernel,
    [Parameter(Mandatory=$true)][string]$Disk,
    [Parameter(Mandatory=$true)][string]$BiosDirectory,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [int]$TimeoutSeconds = 180
)
# Native Windows diagnostic only. No graphics/Android/KernelSU qualification.
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$result = [ordered]@{scope='Native Windows Linux diagnostic boot';status='BLOCKED';accelerator='whpx';gpu='NOT_TESTED';android16='NOT_TESTED';kernelsu='NOT_TESTED';timestamp_utc=[DateTime]::UtcNow.ToString('o')}
$process = $null
$started = $false
$serial = $null
$qmp = $null
function Free-Port {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
    $listener.Stop()
    return $port
}
function Connect-Console([int]$Port) {
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while ([DateTime]::UtcNow -lt $deadline) {
        try { return New-Object System.Net.Sockets.TcpClient('127.0.0.1',$Port) } catch {
            if ($process.HasExited) { throw 'QEMU exited before console connection; inspect qemu.err.log' }
            Start-Sleep -Milliseconds 100
        }
    }
    throw 'Console connection timed out'
}
function Quote-Argument([string]$Value) {
    # All generated args have no embedded quote; reject rather than alter semantics.
    if ($Value.Contains('"') -or $Value.EndsWith('\')) { throw 'Unsupported quote/trailing-backslash in argument' }
    return '"' + $Value + '"'
}
try {
    if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Native Windows is required' }
    $lock = Get-Content -Raw (Join-Path $PSScriptRoot '..\versions.lock.json') | ConvertFrom-Json
    $manifest = Get-Content -Raw (Join-Path (Split-Path $Disk) 'manifest.json') | ConvertFrom-Json
    $kernelHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Kernel).Hash.ToLower()
    $diskHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Disk).Hash.ToLower()
    if ($kernelHash -ne $lock.diagnostic_guest.kernel.sha256 -or $diskHash -ne $manifest.rootfs_sha256) { throw 'Guest checksum mismatch' }
    $version = (& $Qemu --version 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or -not $version.StartsWith('QEMU emulator version ' + $lock.qemu.version + ' ')) { throw 'QEMU version probe failed or differs from lock' }
    $accels = (& $Qemu -accel help 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $accels -notmatch '(?m)^whpx\s*$') { throw 'Binary has no WHPX accelerator' }
    $result.qemu_version = $version
    $result.qemu_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Qemu).Hash.ToLower()
    $result.kernel_sha256 = $kernelHash
    $result.rootfs_sha256 = $diskHash
    $serialPort = Free-Port
    $qmpPort = Free-Port
    while ($qmpPort -eq $serialPort) { $qmpPort = Free-Port }
    $diskEscaped = $Disk.Replace(',',',,')
    $arguments = @('-machine','pc-q35-11.1','-accel','whpx','-cpu','Nehalem','-smp','2','-m','1024','-display','none','-vga','none','-monitor','none','-nic','none','-no-reboot','-kernel',$Kernel,'-append','root=/dev/sda console=ttyS0 panic=-1','-drive',"file=$diskEscaped,format=raw,if=none,id=phase0disk,snapshot=on",'-device','ide-hd,drive=phase0disk,bus=ide.0,unit=0','-serial',"tcp:127.0.0.1:$serialPort,server=on,wait=off",'-qmp',"tcp:127.0.0.1:$qmpPort,server=on,wait=off",'-L',$BiosDirectory)
    $result.argv = $arguments
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $Qemu
    $startInfo.Arguments = ($arguments | ForEach-Object { Quote-Argument $_ }) -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $tmp = Join-Path $OutputDirectory 'tmp'
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $startInfo.EnvironmentVariables['TMP'] = $tmp
    $startInfo.EnvironmentVariables['TEMP'] = $tmp
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $result.status = 'FAIL'
    [void]$process.Start()
    $started = $true
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $serial = Connect-Console $serialPort
    $qmp = Connect-Console $qmpPort
    $qmpStream = $qmp.GetStream()
    $qmpStream.ReadTimeout = 10000
    $reader = New-Object System.IO.StreamReader($qmpStream)
    $writer = New-Object System.IO.StreamWriter($qmpStream)
    $writer.AutoFlush = $true
    $greeting = $reader.ReadLine()
    $writer.WriteLine('{"execute":"qmp_capabilities","id":1}')
    do { $response = $reader.ReadLine() | ConvertFrom-Json } while ($response.id -ne 1)
    if ($response.error) { throw 'QMP handshake failed' }
    $greeting | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'qmp-greeting.json')
    $stream = $serial.GetStream()
    $buffer = New-Object byte[] 65536
    $console = ''
    $sentLogin = $false
    $sentProbe = $false
    $nonce = [Guid]::NewGuid().ToString('N')
    $marker = 'PHASE0_READY_' + $nonce
    while ($clock.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        if ($stream.DataAvailable) {
            $count = $stream.Read($buffer,0,$buffer.Length)
            $console += [Text.Encoding]::UTF8.GetString($buffer,0,$count)
            if ($console.Contains('Kernel panic - not syncing')) { throw 'Guest kernel panic' }
            if (-not $sentLogin -and $console.Contains('tuxtest login:')) {
                $bytes = [Text.Encoding]::ASCII.GetBytes("root`n")
                $stream.Write($bytes,0,$bytes.Length)
                $sentLogin = $true
            }
            if (-not $sentProbe -and $console.Contains('root@tuxtest:~#')) {
                $command = "printf 'PHASE0_'; printf 'READY_$nonce\n'; uname -m; uname -r`n"
                $bytes = [Text.Encoding]::ASCII.GetBytes($command)
                $stream.Write($bytes,0,$bytes.Length)
                $sentProbe = $true
            }
            if ($console.Contains('Linux version ') -and $console -match ([regex]::Escape($marker) + '\r?\nx86_64\r?\n')) {
                $result.process_to_guest_ready_seconds = $clock.Elapsed.TotalSeconds
                $writer.WriteLine('{"execute":"quit","id":2}')
                if (-not $process.WaitForExit(15000) -or $process.ExitCode -ne 0) { throw 'QEMU did not quit cleanly' }
                if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Disk).Hash.ToLower() -ne $diskHash) { throw 'Base disk changed' }
                $result.status = 'PASS'
                $result.reason = 'Fresh guest command response under strict WHPX; clean QMP quit; base disk unchanged'
                break
            }
        }
        if ($process.HasExited) { throw 'QEMU exited before guest readiness' }
        Start-Sleep -Milliseconds 20
    }
    if ($result.status -ne 'PASS') { throw 'Guest readiness timeout' }
} catch {
    $result.reason = $_.Exception.Message
} finally {
    if ($started -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
    if ($started) {
        if ($stdout) { $stdout.Result | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'qemu.out.log') }
        if ($stderr) { $stderr.Result | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'qemu.err.log') }
    }
    if ($console) { $console | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'serial.log') }
    if ($serial) { $serial.Close() }
    if ($qmp) { $qmp.Close() }
    $result | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'result.json')
}
if ($result.status -eq 'PASS') { exit 0 }
if ($result.status -eq 'BLOCKED') { exit 2 }
exit 1
