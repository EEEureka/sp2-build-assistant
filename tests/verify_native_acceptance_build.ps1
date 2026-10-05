param([Parameter(Mandatory=$true)][string]$AcceptanceDll,
      [Parameter(Mandatory=$true)][string]$ShippingDll,
      [Parameter(Mandatory=$true)][string]$Report,
      [string]$GameDir='D:\apps\steam\steamapps\common\SimplePlanes 2')
$ErrorActionPreference='Stop'
[void][Reflection.Assembly]::LoadFrom((Join-Path $GameDir 'BepInEx/core/Mono.Cecil.dll'))
$taskNativeChecks = @()
foreach ($taskNativeBuild in @(@{Path=$AcceptanceDll;Hooks=$true},@{Path=$ShippingDll;Hooks=$false})) {
    $taskNativeAssembly = [Mono.Cecil.AssemblyDefinition]::ReadAssembly((Resolve-Path -LiteralPath $taskNativeBuild.Path).Path)
    try {
        $taskNativeRuntime = $taskNativeAssembly.MainModule.Types | Where-Object FullName -eq 'SP2BuildAssistant.BuildRuntime'
        $taskNativeEntry = $taskNativeRuntime.Methods | Where-Object Name -eq 'AcceptanceNative'
        if (-not $taskNativeEntry) { throw 'Missing explicit acceptance rejection/dispatch entry.' }
        $taskNativeHelpers = @($taskNativeRuntime.Methods | Where-Object { $_.Name -in @('NativeControls','NativeInput') })
        $taskNativeStates = @($taskNativeRuntime.NestedTypes | Where-Object { $_.Name -like '<AcceptanceNative>*' })
        $taskOverloadMethods = @($taskNativeRuntime.Methods | Where-Object Name -eq 'AcceptanceOverload')
        $taskOverloadStates = @($taskNativeRuntime.NestedTypes | Where-Object { $_.Name -like '<AcceptanceOverload>*' })
        if ($taskNativeBuild.Hooks) {
            if ($taskNativeHelpers.Count -ne 2 -or $taskNativeStates.Count -ne 1) { throw 'Acceptance build has no native reference implementation.' }
        } else {
            if ($taskNativeHelpers.Count -ne 0 -or $taskNativeStates.Count -ne 0) { throw 'Shipping build retained native reference mutation code.' }
            if ($taskOverloadMethods.Count -ne 0 -or $taskOverloadStates.Count -ne 0) { throw 'Shipping build retained native Overload reference mutation code.' }
            $taskNativeOpcodes = @($taskNativeEntry.Body.Instructions | ForEach-Object { $_.OpCode.Code.ToString() })
            $taskNativeStrings = @($taskNativeEntry.Body.Instructions | Where-Object { $_.OpCode.Code.ToString() -eq 'Ldstr' } | ForEach-Object Operand)
            if ('Throw' -notin $taskNativeOpcodes -or 'acceptance_build_required' -notin $taskNativeStrings) { throw 'Shipping entry must unconditionally reject.' }
            $taskNativeCalls = @($taskNativeEntry.Body.Instructions | Where-Object { $_.OpCode.Code.ToString() -in @('Call','Callvirt') })
            if ($taskNativeCalls.Count -ne 0) { throw 'Shipping entry unexpectedly calls runtime/game code.' }
        }
        $taskNativeChecks += [pscustomobject]@{acceptanceHooks=$taskNativeBuild.Hooks;path=$taskNativeBuild.Path;
            sha256=(Get-FileHash -LiteralPath $taskNativeBuild.Path).Hash;buildId=$taskNativeAssembly.MainModule.Mvid.ToString();nativeHelperCount=$taskNativeHelpers.Count;
            nativeAsyncStateMachineCount=$taskNativeStates.Count;passed=$true}
    } finally { $taskNativeAssembly.Dispose() }
}
$taskNativeChecks | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Report -Encoding utf8
$taskNativeChecks | Select-Object acceptanceHooks,nativeHelperCount,nativeAsyncStateMachineCount,passed
