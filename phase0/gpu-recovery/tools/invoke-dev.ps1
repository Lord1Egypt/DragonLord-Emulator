param(
    [Parameter(Mandatory=$true)][string]$NativeRoot,
    [Parameter(Mandatory=$true)][string]$CommandFile,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
# Execute a declared development command with scoped VS/isolated-tool environment.
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath (Join-Path $OutputDirectory 'result.json')) { throw 'Fresh output directory required' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$result=[ordered]@{scope='Native development command only; no implicit GPU qualification';status='BLOCKED';timestamp_utc=[DateTime]::UtcNow.ToString('o')}
function Quote-Arg([string]$s) {
    if ($s.Contains('"') -or $s.EndsWith('\')) { throw 'Unsupported argument quoting' }
    return '"'+$s+'"'
}
try {
    Set-Location -LiteralPath $NativeRoot
    $command=Get-Content -Raw -LiteralPath $CommandFile | ConvertFrom-Json
    if ($command.working_directory.StartsWith('\\')) { throw 'Native local working directory required' }
    $where=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    $vs=(& $where -latest -products '*' -property installationPath | Out-String).Trim()
    $vcvars=Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
    $batch=Join-Path $OutputDirectory 'capture-vcvars.cmd'
    "@echo off`r`ncall `"$vcvars`" >nul`r`nif errorlevel 1 exit /b 1`r`nset`r`n" | Out-File -Encoding ascii -LiteralPath $batch
    $rows=@(& $env:ComSpec /d /c $batch)
    if ($LASTEXITCODE -ne 0) { throw 'VS environment initialization failed' }
    $variables=@{}
    foreach ($line in $rows) {
        if ($line -match '^([^=]+)=(.*)$') {
            $key=$matches[1]; $value=$matches[2]
            if ($key -match '^(PATH|INCLUDE|LIB|LIBPATH|VC.*|WindowsSdk.*|UCRT.*|UniversalCRT.*)$') { $variables[$key]=$value }
        }
    }
    if (-not $variables['LIB'] -or -not $variables['INCLUDE']) { throw 'VS environment missing library/header paths' }
    $variables['PATH']=(Join-Path $NativeRoot 'tools\clang+llvm-23.1.5-x86_64-pc-windows-msvc\bin')+';'+(Join-Path $NativeRoot 'tools\rust-1.88.0\bin')+';'+$variables['PATH']
    $variables['RUSTC']=Join-Path $NativeRoot 'tools\rust-1.88.0\bin\rustc.exe'
    $variables['RUSTDOC']=Join-Path $NativeRoot 'tools\rust-1.88.0\bin\rustdoc.exe'
    $variables['CARGO_HOME']=Join-Path $NativeRoot 'cargo-cache'
    $variables['CARGO_BUILD_JOBS']='2'
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=$command.executable
    $psi.Arguments=(@($command.arguments) | ForEach-Object { Quote-Arg $_ }) -join ' '
    $psi.WorkingDirectory=$command.working_directory
    $psi.UseShellExecute=$false; $psi.CreateNoWindow=$true
    $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
    foreach ($key in $variables.Keys) { $psi.EnvironmentVariables[$key]=$variables[$key] }
    if ($command.environment) {
        foreach ($entry in $command.environment.PSObject.Properties) { if ($null -eq $entry.Value) { $psi.EnvironmentVariables.Remove($entry.Name) } else { $psi.EnvironmentVariables[$entry.Name]=[string]$entry.Value } }
    }
    $p=New-Object Diagnostics.Process
    $p.StartInfo=$psi
    $outFile=[IO.File]::Open((Join-Path $OutputDirectory 'stdout.log'),[IO.FileMode]::Create)
    $errFile=[IO.File]::Open((Join-Path $OutputDirectory 'stderr.log'),[IO.FileMode]::Create)
    try {
        [void]$p.Start()
        $outTask=$p.StandardOutput.BaseStream.CopyToAsync($outFile)
        $errTask=$p.StandardError.BaseStream.CopyToAsync($errFile)
        $seconds=if($command.timeout_seconds){[int]$command.timeout_seconds}else{1200}
        $timeout=-not $p.WaitForExit($seconds*1000)
        if ($timeout) { & "$env:SystemRoot\System32\taskkill.exe" /PID $p.Id /T /F | Out-Null; $p.WaitForExit() }
        $outTask.Wait(); $errTask.Wait()
        $result.command=$command
        $result.process_id=$p.Id
        $result.exit_code=$p.ExitCode
        $result.timed_out=$timeout
        $result.executable_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $command.executable).Hash.ToLower()
        $result.status=if($p.ExitCode -eq 0 -and -not $timeout){'PASS'}else{'FAIL'}
        $result.reason='Raw command exit status only; inspect output and test counts for qualification'
    } finally { $outFile.Dispose(); $errFile.Dispose(); $p.Dispose() }
} catch { $result.reason=$_.Exception.Message }
$result | ConvertTo-Json -Depth 12 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'result.json')
if ($result.status -eq 'PASS') { exit 0 }; if ($result.status -eq 'BLOCKED') { exit 2 }; exit 1
