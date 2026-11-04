param(
    [Parameter(Mandatory=$true)][string]$SourceDirectory,
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$CMake = 'cmake.exe',
    [int]$TimeoutSeconds = 180,
    [switch]$Build
)
# Uses existing native Windows tools only. Does not install missing components.
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath (Join-Path $OutputDirectory 'result.json')) { throw 'Use a fresh output directory to preserve previous results' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$result = [ordered]@{scope='Pinned native Windows standalone Gfxstream build attempt';timestamp_utc=[DateTime]::UtcNow.ToString('o');status='BLOCKED';rendering='NOT TESTED';hardware_execution='NOT TESTED';qemu_integration='NOT TESTED'}
$process = $null
$started = $false
function Quote-Arg([string]$Value) {
    if ($Value.Contains('"') -or $Value.EndsWith('\')) { throw 'Unsupported embedded quote or trailing backslash' }
    return '"' + $Value + '"'
}
function Run-Tool([string]$Executable,[string[]]$Arguments,[string]$Name) {
    $script:process = New-Object Diagnostics.Process
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $Executable
    $start.Arguments = ($Arguments | ForEach-Object { Quote-Arg $_ }) -join ' '
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.WorkingDirectory = $env:SystemRoot
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $script:process.StartInfo = $start
    [void]$script:process.Start()
    $script:started = $true
    $stdout = $script:process.StandardOutput.ReadToEndAsync()
    $stderr = $script:process.StandardError.ReadToEndAsync()
    $timedOut = -not $script:process.WaitForExit($TimeoutSeconds * 1000)
    if ($timedOut) {
        # Kill only this build command and its child compiler processes.
        & "$env:SystemRoot\System32\taskkill.exe" /PID $script:process.Id /T /F | Out-Null
        $script:process.WaitForExit()
    }
    $stdout.Result | Out-File -Encoding utf8 (Join-Path $OutputDirectory ($Name + '.stdout.log'))
    $stderr.Result | Out-File -Encoding utf8 (Join-Path $OutputDirectory ($Name + '.stderr.log'))
    if ($timedOut) { throw "$Name timed out; partial logs preserved" }
    return $script:process.ExitCode
}
try {
    if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Native Windows required' }
    $pin = '94240f814c0097a63027ae680ea4bec7b0cb25f7'
    $git = (Get-Command git.exe -ErrorAction Stop).Source
    # The source may be owned by WSL. Scope safe.directory to this single invocation.
    $revision = (& $git -c "safe.directory=$SourceDirectory" -c core.filemode=false -c core.autocrlf=false -C $SourceDirectory rev-parse HEAD | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $revision -ne $pin) { throw 'Source revision differs from Phase 0 pin' }
    $dirtyLines = @(& $git -c "safe.directory=$SourceDirectory" -c core.filemode=false -c core.autocrlf=false -C $SourceDirectory status --porcelain --untracked-files=no)
    $gitExit = $LASTEXITCODE
    $result.native_git_status = $dirtyLines
    # Git for Windows sees this WSL-hosted CI symlink as a type change. It is
    # not a build input. Full source identity is checked by the Linux validator.
    $otherChanges = @($dirtyLines | Where-Object { $_ -ne ' T .kokoro/continuous.cfg' })
    if ($gitExit -ne 0 -or $otherChanges.Count -gt 0) { throw 'Pinned Gfxstream build inputs must be pristine' }
    $result.source_commit = $revision
    $cmakePath = (Get-Command $CMake -ErrorAction Stop).Source
    $result.cmake_path = $cmakePath
    $result.cmake_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $cmakePath).Hash.ToLower()
    $result.cmake_version = (& $cmakePath --version | Out-String).Trim()
    $arguments = @('-S',$SourceDirectory,'-B',$BuildDirectory,'-G','Visual Studio 17 2022','-A','x64','-T','ClangCL','-DBUILD_STANDALONE=ON','-DENABLE_VKCEREAL_TESTS=ON','-DASTC_CPU_DECODING=OFF','-DGFXSTREAM_ENABLE_HOST_TRACING=OFF')
    $result.configure_argv = $arguments
    $result.status = 'FAIL'
    $result.configure_exit_code = Run-Tool $cmakePath $arguments 'configure'
    if ($result.configure_exit_code -ne 0) {
        if ((Get-Content -Raw (Join-Path $OutputDirectory 'configure.stderr.log')) -match 'MSB8020') { $result.status = 'BLOCKED' }
        throw 'Native configure failed; inspect configure logs and missing toolchain/dependencies'
    }
    $result.status = 'PASS'
    $result.reason = 'Native configure passed only; renderer build and runtime remain unqualified'
    if ($Build) {
        $result.status = 'FAIL'
        $buildArgs = @('--build',$BuildDirectory,'--config','Release','--target','gfxstream_backend','--parallel','4')
        $result.build_argv = $buildArgs
        $result.build_exit_code = Run-Tool $cmakePath $buildArgs 'build'
        if ($result.build_exit_code -ne 0) { throw 'Native build failed; rendering was not executed' }
        $result.status = 'PASS'
        $result.reason = 'Renderer library build passed only; no hardware rendering claim'
    }
} catch { $result.reason=$_.Exception.Message }
$result | ConvertTo-Json -Depth 8 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'result.json')
if ($result.status -eq 'PASS') { exit 0 }; if ($result.status -eq 'BLOCKED') { exit 2 }; exit 1
