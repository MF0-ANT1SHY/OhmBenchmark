param([string]$InputHap, [string]$OutputHap, [string]$Bundle)
. C:\Users\30422\.harmony-dev\Activate-Harmony.ps1
$signWork = 'C:\Users\30422\Documents\Codex\2026-10-01\goal-project-git-pura-70-case\work\signing'
$signLib = "$env:HDC_HOME\lib"
$profile = Get-Content "$signWork\browser.json" -Raw | ConvertFrom-Json
$profile.'bundle-info'.'bundle-name' = $Bundle
$profile | ConvertTo-Json -Depth 10 | Set-Content "$signWork\current.json" -Encoding utf8
java -jar "$signLib\hap-sign-tool.jar" sign-profile -mode localSign -keyAlias 'openharmony application profile debug' -keyPwd 123456 -profileCertFile "$signLib\OpenHarmonyProfileDebug.pem" -inFile "$signWork\current.json" -signAlg SHA256withECDSA -keystoreFile "$signWork\dev.p12" -keystorePwd 123456 -outFile "$signWork\current.p7b"
java -jar "$signLib\hap-sign-tool.jar" sign-app -mode localSign -keyAlias 'openharmony application release' -keyPwd 123456 -appCertFile "$signWork\chain.cer" -profileFile "$signWork\current.p7b" -inFile $InputHap -signAlg SHA256withECDSA -keystoreFile "$signWork\dev.p12" -keystorePwd 123456 -outFile $OutputHap -compatibleVersion 18
