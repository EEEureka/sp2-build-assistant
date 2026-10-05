param([Parameter(Mandatory=$true)][int]$GameProcessId,
      [Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
try {
    $sp2GpuSets=Get-Counter -ListSet '*GPU*'
    $sp2GpuPaths=@($sp2GpuSets.PathsWithInstances | Where-Object {
        $_ -match ('pid_'+$GameProcessId+'_') -and $_ -match 'Usage|Committed' -and $_ -notmatch 'Engine'
    })
    if(-not $sp2GpuPaths.Count){throw 'No PID-scoped GPU memory counter instances.'}
    $sp2GpuSample=Get-Counter -Counter $sp2GpuPaths -MaxSamples 1
    $sp2GpuRows=@($sp2GpuSample.CounterSamples | Select-Object Path,CookedValue,Status)
    $sp2GpuReport=[pscustomobject]@{pid=$GameProcessId;available=$true;capturedAt=$sp2GpuSample.Timestamp.ToUniversalTime().ToString('o');
        allCountersValid=(@($sp2GpuRows | Where-Object { $_.Status -notin @(0,1) }).Count -eq 0);
        counters=$sp2GpuRows;meaning='PDH GPU memory counters for this PID. Different counter types overlap; do not sum them or equate them with OS private bytes. This does not attribute driver CPU heap allocations.'}
}catch{
    $sp2GpuReport=[pscustomobject]@{pid=$GameProcessId;available=$false;error=$_.Exception.Message;meaning='Unavailable counters are not zero usage.'}
}
$sp2GpuReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding utf8
