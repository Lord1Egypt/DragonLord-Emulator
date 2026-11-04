param(
    [Parameter(Mandatory=$true)][string]$CommandFile,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
# Scoped child rendering plus independent Windows GPU Engine telemetry.
# A named ETW session is attempted; no existing/global session is stopped.
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $OutputDirectory){throw 'Fresh output directory required'}
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$c=Get-Content -Raw -LiteralPath $CommandFile | ConvertFrom-Json
$r=[ordered]@{scope='Observed standalone Gfxstream component; no QEMU/Android qualification';status='FAIL';command=$c;timestamp_utc=[DateTime]::UtcNow.ToString('o');observer_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLower();command_sha256=(Get-FileHash -LiteralPath $CommandFile -Algorithm SHA256).Hash.ToLower()}
$traceName='DLGPU_'+[Guid]::NewGuid().ToString('N');$traceStarted=$false
$p=$null;$out=$null;$err=$null
try {
    $xperf=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Windows Performance Toolkit\xperf.exe'
    $r.etw=[ordered]@{session=$traceName;status='NOT TESTED'}
    if(Test-Path -LiteralPath $xperf){
        $ErrorActionPreference='Continue'
        $etwOutput=@(& $xperf -start $traceName -on Microsoft-Windows-DxgKrnl -f (Join-Path $OutputDirectory 'gpu.etl') 2>&1)
        $traceExit=$LASTEXITCODE
        $ErrorActionPreference='Stop'
        $r.etw.start_exit_code=$traceExit
        $r.etw.start_output=@($etwOutput | ForEach-Object {"$_"})
        $traceStarted=$traceExit -eq 0
        $r.etw.status=if($traceStarted){'STARTED'}else{'BLOCKED'}
    }
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=$c.executable
    $psi.Arguments=(@($c.arguments)|ForEach-Object {if($_.Contains('"') -or $_.EndsWith('\')){throw 'Unsupported quoting'};'"'+$_+'"'}) -join ' '
    $psi.WorkingDirectory=$c.working_directory
    $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true
    $psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    foreach($e in $c.environment.PSObject.Properties){if($null -eq $e.Value){$psi.EnvironmentVariables.Remove($e.Name)}else{$psi.EnvironmentVariables[$e.Name]=[string]$e.Value}}
    $p=New-Object Diagnostics.Process;$p.StartInfo=$psi
    $out=[IO.File]::Open((Join-Path $OutputDirectory 'stdout.log'),[IO.FileMode]::Create)
    $err=[IO.File]::Open((Join-Path $OutputDirectory 'stderr.log'),[IO.FileMode]::Create)
    $watch=[Diagnostics.Stopwatch]::StartNew();[void]$p.Start();$r.process_id=$p.Id
    $ot=$p.StandardOutput.BaseStream.CopyToAsync($out);$et=$p.StandardError.BaseStream.CopyToAsync($err)
    $samples=New-Object Collections.Generic.List[object]
    $errors=New-Object Collections.Generic.List[string]
    $modules=@{};$timedOut=$false
    while(-not $p.HasExited){
        try {
            $p.Refresh()
            foreach($m in $p.Modules){$modules[$m.FileName]=$m.ModuleName}
            $s=[ordered]@{elapsed_ms=$watch.ElapsedMilliseconds;cpu_seconds=$p.TotalProcessorTime.TotalSeconds;working_set_bytes=$p.WorkingSet64;private_bytes=$p.PrivateMemorySize64;gpu=@()}
            # A disappearing unrelated instance can invalidate the aggregate query.
            # Preserve returned samples and every sample's status; never count invalid samples.
            $counterIssues=@()
            $counter=Get-Counter -Counter '\GPU Engine(*)\Utilization Percentage' -MaxSamples 2 -SampleInterval 1 -ErrorAction SilentlyContinue -ErrorVariable counterIssues
            foreach($issue in $counterIssues){$errors.Add($issue.Exception.Message)}
            if($null -eq $counter){throw 'No GPU counter sample set returned'}
            $s.gpu=@($counter.CounterSamples | Where-Object {$_.InstanceName -match ('^pid_'+$p.Id+'_')} | ForEach-Object {@{instance=$_.InstanceName;value=$_.CookedValue;status=$_.Status;timestamp=$_.Timestamp.ToUniversalTime().ToString('o')}})
            $samples.Add($s)
        } catch {$errors.Add($_.Exception.Message);Start-Sleep -Milliseconds 250}
        if($watch.Elapsed.TotalSeconds -gt [int]$c.timeout_seconds){$timedOut=$true;$p.Kill();break}
    }
    $p.WaitForExit();$ot.Wait();$et.Wait();$watch.Stop()
    $r.exit_code=$p.ExitCode;$r.timed_out=$timedOut;$r.elapsed_ms=$watch.ElapsedMilliseconds
    $r.executable_sha256=(Get-FileHash -LiteralPath $c.executable -Algorithm SHA256).Hash.ToLower()
    $r.counter_errors=@($errors);$r.samples=@($samples.ToArray())
    $r.modules=@(foreach($path in $modules.Keys | Sort-Object){
        $v=[Diagnostics.FileVersionInfo]::GetVersionInfo($path)
        $entry=@{path=$path;name=$modules[$path];sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower();file_version=$v.FileVersion;company=$v.CompanyName}
        if($entry.name -match 'vulkan|swiftshader|nvog|igvk|gfxstream'){$sig=Get-AuthenticodeSignature -LiteralPath $path;$entry.authenticode_status=[string]$sig.Status;$entry.signer=if($sig.SignerCertificate){$sig.SignerCertificate.Subject}else{$null}}
        $entry
    })
    $r.status=if($p.ExitCode -eq 0 -and -not $timedOut){'PASS'}else{'FAIL'}
    $r.reason='Raw rendering exit status; independently inspect pixel tests, device identity, software controls and telemetry'
} catch {$r.reason=$_.Exception.Message}
finally {
    if($traceStarted){
        $stop=@(& $xperf -stop $traceName 2>&1);$r.etw.stop_exit_code=$LASTEXITCODE;$r.etw.stop_output=@($stop | ForEach-Object {"$_"})
        $r.etw.status=if($LASTEXITCODE -eq 0){'CAPTURED'}else{'FAIL'}
    }
    if($out){$out.Dispose()};if($err){$err.Dispose()};if($p){$p.Dispose()}
    $r | ConvertTo-Json -Depth 16 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'result.json')
}
if($r.status -eq 'PASS'){exit 0};exit 1
