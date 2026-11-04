param(
    [Parameter(Mandatory=$true)][string]$NativeRoot,
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [int]$Parallel = 2,
    [switch]$ConfigureOnly,
    [switch]$LeanWindowsHeaders,
    [string]$SourceOverlayManifest
)
# Existing VS/SDK plus isolated official LLVM; no installed toolchain changes.
$ErrorActionPreference='Stop'
if ($NativeRoot.StartsWith('\\') -or $BuildDirectory.StartsWith('\\')) { throw 'Primary source/build paths must be native local paths' }
if (Test-Path -LiteralPath (Join-Path $OutputDirectory 'result.json')) { throw 'Fresh output directory required' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$result=[ordered]@{scope='Native Windows pinned Gfxstream compilation; GPU NOT TESTED';timestamp_utc=[DateTime]::UtcNow.ToString('o');status='BLOCKED';hardware_rendering='NOT TESTED';independent_gpu_verification='NOT TESTED';commands=@()}
$childEnvironment=@{}
function Quote-Argument([string]$s) {
    if ($s.Contains('"') -or $s.EndsWith('\')) { throw 'Unsupported command argument' }
    return '"'+$s+'"'
}
function Invoke-Native([string]$exe,[string[]]$arguments,[string]$name,[int]$seconds) {
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=$exe
    $psi.Arguments=($arguments | ForEach-Object { Quote-Argument $_ }) -join ' '
    $psi.WorkingDirectory=$NativeRoot
    $psi.UseShellExecute=$false
    $psi.CreateNoWindow=$true
    $psi.RedirectStandardOutput=$true
    $psi.RedirectStandardError=$true
    foreach ($key in $childEnvironment.Keys) { $psi.EnvironmentVariables[$key]=$childEnvironment[$key] }
    $process=New-Object Diagnostics.Process
    $process.StartInfo=$psi
    $outFile=[IO.File]::Open((Join-Path $OutputDirectory ($name+'.stdout.log')),[IO.FileMode]::Create)
    $errFile=[IO.File]::Open((Join-Path $OutputDirectory ($name+'.stderr.log')),[IO.FileMode]::Create)
    try {
        [void]$process.Start()
        $outTask=$process.StandardOutput.BaseStream.CopyToAsync($outFile)
        $errTask=$process.StandardError.BaseStream.CopyToAsync($errFile)
        $timedOut=-not $process.WaitForExit($seconds*1000)
        if ($timedOut) { & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F | Out-Null; $process.WaitForExit() }
        $outTask.Wait(); $errTask.Wait()
        $result.commands+=@{executable=$exe;argv=$arguments;exit_code=$process.ExitCode;timed_out=$timedOut}
        if ($timedOut) { throw "$name timeout; partial logs preserved" }
        return $process.ExitCode
    } finally { $outFile.Dispose(); $errFile.Dispose(); $process.Dispose() }
}
try {
    if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Native Windows required' }
    Set-Location -LiteralPath $NativeRoot
    $vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    $vs=(& $vswhere -latest -products '*' -property installationPath | Out-String).Trim()
    $vcvars=Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
    $ninja=Join-Path $vs 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe'
    $cmake=(Get-Command cmake.exe -ErrorAction Stop).Source
    $llvm=Join-Path $NativeRoot 'tools\clang+llvm-23.1.5-x86_64-pc-windows-msvc\bin'
    $clang=Join-Path $llvm 'clang-cl.exe'
    $rust=Join-Path $NativeRoot 'tools\rust-1.88.0\bin'
    $source=Join-Path $NativeRoot 'src\hardware\google\gfxstream'
    foreach ($file in @($vcvars,$ninja,$cmake,$clang,(Join-Path $source 'CMakeLists.txt'))) {
        if (-not (Test-Path -LiteralPath $file)) { throw "Required native input missing: $file" }
    }
    $envBatch=Join-Path $OutputDirectory 'capture-vcvars.cmd'
    "@echo off`r`ncall `"$vcvars`" >nul`r`nif errorlevel 1 exit /b 1`r`nset`r`n" | Out-File -Encoding ascii -LiteralPath $envBatch
    $envRows=@(& $env:ComSpec /d /c $envBatch)
    if ($LASTEXITCODE -ne 0) { throw 'VS development environment initialization failed' }
    # Capture only selected build variables. Never log the full inherited environment.
    foreach ($line in $envRows) {
        if ($line -match '^([^=]+)=(.*)$') {
            $variableName=$matches[1]
            $variableValue=$matches[2]
            if ($variableName -match '^(PATH|INCLUDE|LIB|LIBPATH|VC.*|WindowsSdk.*|UCRT.*|UniversalCRT.*)$') {
                $childEnvironment[$variableName]=$variableValue
            }
        }
    }
    if (-not $childEnvironment['LIB'] -or -not $childEnvironment['INCLUDE']) { throw 'VS library/header environment was not captured' }
    $childEnvironment['PATH']=$llvm+';'+$rust+';'+$childEnvironment['PATH']
    $childEnvironment['CARGO_HOME']=Join-Path $NativeRoot 'cargo-cache'
    $childEnvironment['RUSTC']=Join-Path $rust 'rustc.exe'
    $result.source_commit='94240f814c0097a63027ae680ea4bec7b0cb25f7'
    if ($SourceOverlayManifest) {
        $overlay=Get-Content -Raw -LiteralPath $SourceOverlayManifest | ConvertFrom-Json
        foreach ($entry in $overlay.files) {
            $actual=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $source $entry.path)).Hash.ToLower()
            if ($actual -ne $entry.patched_sha256) { throw 'Native overlay source checksum mismatch' }
        }
        $result.source_overlay=$overlay
    }
    $result.source_directory=$source
    $result.build_directory=$BuildDirectory
    $result.environment_scope='VS build variables in child processes only; no global PATH changes'
    $result.library_directories=@($childEnvironment['LIB'] -split ';')
    $result.include_directories=@($childEnvironment['INCLUDE'] -split ';')
    $result.tools=@()
    foreach ($tool in @($cmake,$clang,$ninja,(Join-Path $rust 'rustc.exe'),(Join-Path $rust 'cargo.exe'))) {
        if (Test-Path -LiteralPath $tool) { $result.tools+=@{path=$tool;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $tool).Hash.ToLower()} }
    }
    if ((Invoke-Native $clang @('--version') 'clang-version' 30) -ne 0) { throw 'Clang version probe failed' }
    $arguments=@('-S',$source,'-B',$BuildDirectory,'-G','Ninja',"-DCMAKE_MAKE_PROGRAM=$ninja", "-DCMAKE_C_COMPILER=$clang", "-DCMAKE_CXX_COMPILER=$clang",'-DCMAKE_BUILD_TYPE=Release','-DBUILD_STANDALONE=ON','-DENABLE_VKCEREAL_TESTS=ON','-DASTC_CPU_DECODING=OFF','-DGFXSTREAM_ENABLE_HOST_TRACING=OFF')
    if ($LeanWindowsHeaders) {
        # Prevent windows.h from importing obsolete winsock.h before WinSock2.h.
        $arguments+=@('-DCMAKE_C_FLAGS=/DWIN32_LEAN_AND_MEAN','-DCMAKE_CXX_FLAGS=/DWIN32_LEAN_AND_MEAN')
    }
    $result.status='FAIL'
    $result.configure_exit_code=Invoke-Native $cmake $arguments 'configure' 180
    if ($result.configure_exit_code -ne 0) { throw 'Native configure failed; inspect full logs' }
    if ($ConfigureOnly) { $result.status='PASS'; $result.reason='Native configure only; no compilation or GPU claim' }
    else {
        $result.build_exit_code=Invoke-Native $cmake @('--build',$BuildDirectory,'--target','gfxstream_backend','OpenglRender_unittests','Vulkan_unittests','--parallel',"$Parallel") 'build' 1800
        if ($result.build_exit_code -ne 0) { throw 'Native compilation failed; no GPU workload executed' }
        $result.binaries=@(Get-ChildItem -LiteralPath $BuildDirectory -File | Where-Object { $_.Extension -in @('.exe','.dll') } | ForEach-Object { @{name=$_.Name;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLower()} })
        $result.status='PASS'
        $result.reason='Requested native library/tests compiled; rendering and physical GPU gates remain NOT TESTED'
    }
} catch { $result.reason=$_.Exception.Message }
$result | ConvertTo-Json -Depth 10 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'result.json')
if ($result.status -eq 'PASS') { exit 0 }; if ($result.status -eq 'BLOCKED') { exit 2 }; exit 1
