param(
    [Parameter(Mandatory=$true)][string]$NativeRoot,
    [Parameter(Mandatory=$true)][string]$CommandFile,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
# Preserve the established runner's exit and raw logs, but surface diagnostics.
$ErrorActionPreference='Stop'
$runner=Join-Path $PSScriptRoot '..\..\gpu-recovery\tools\invoke-dev.ps1'
& $runner -NativeRoot $NativeRoot -CommandFile $CommandFile -OutputDirectory $OutputDirectory
$exitCode=$LASTEXITCODE
$file=Join-Path $OutputDirectory 'result.json'
if(Test-Path -LiteralPath $file){
    $r=Get-Content -Raw -LiteralPath $file | ConvertFrom-Json
    Write-Output ("Native status={0}; wrapper exit={1}; child exit={2}" -f $r.status,$exitCode,$r.exit_code)
    Write-Output ("Result: "+$file)
    if($exitCode -ne 0){
        Write-Output ("Reason: "+$r.reason)
        $stderr=Join-Path $OutputDirectory 'stderr.log'
        if(Test-Path -LiteralPath $stderr){
            Write-Output ("stderr tail (full log preserved at "+$stderr+"):")
            Get-Content -LiteralPath $stderr -Tail 25 | Write-Output
        }
    }
}else{
    Write-Output ('Native result unavailable: '+$file)
    if($exitCode -eq 0){$exitCode=2}
}
exit $exitCode
