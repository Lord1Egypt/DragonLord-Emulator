param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $OutputDirectory){throw 'Fresh output directory required'}
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
$result=[ordered]@{scope='Read-only relevant privilege and hook provenance inventory';timestamp_utc=[DateTime]::UtcNow.ToString('o');elevated_admin=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator);performance_log_users=$principal.IsInRole((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-559')));changes='NONE';hooks=@()}
foreach($path in @('C:\ProgramData\obs-studio-hook\graphics-hook64.dll','C:\Program Files\TikTok LIVE Studio\1.28.0\resources\app\electron\sdk\lib\MediaSDK_V2\plugins\game_detour_64.dll')){
    if(Test-Path -LiteralPath $path){
        $v=[Diagnostics.FileVersionInfo]::GetVersionInfo($path);$sig=Get-AuthenticodeSignature -LiteralPath $path
        $result.hooks+=@{path=$path;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower();file_version=$v.FileVersion;company=$v.CompanyName;signature_status=[string]$sig.Status;signer=if($sig.SignerCertificate){$sig.SignerCertificate.Subject}else{$null}}
    }else{$result.hooks+=@{path=$path;status='ABSENT'}}
}
$result | ConvertTo-Json -Depth 8 | Out-File -Encoding utf8 (Join-Path $OutputDirectory 'result.json')
