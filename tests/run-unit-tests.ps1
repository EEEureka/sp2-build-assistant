param([string]$GameDir='D:\apps\steam\steamapps\common\SimplePlanes 2')
$ErrorActionPreference='Stop'
$sp2TestOutput=Join-Path $env:TEMP ('sp2build-tests-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $sp2TestOutput | Out-Null
$sp2Managed=Join-Path $GameDir 'SimplePlanes 2_Data\Managed'
$sp2Compiler='D:\apps\visualStudio\MSBuild\Current\bin\Roslyn\csc.exe'
$sp2Root=Split-Path -Parent $PSScriptRoot
$sp2Framework='C:\Windows\Microsoft.NET\Framework64\v4.0.30319'
$sp2Refs=@('mscorlib.dll','System.dll','System.Core.dll','System.Xml.dll','System.Xml.Linq.dll') | ForEach-Object { '/reference:'+(Join-Path $sp2Framework $_) }
$sp2Newtonsoft='D:\apps\visualStudio\MSBuild\Current\Bin\Newtonsoft.Json.dll'
$sp2Refs+=('/reference:'+$sp2Newtonsoft)
Copy-Item -LiteralPath $sp2Newtonsoft -Destination $sp2TestOutput
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'ExpressionTemplatesTests.exe')) (Join-Path $sp2Root 'bridge\ExpressionTemplates.cs') (Join-Path $PSScriptRoot 'ExpressionTemplatesTests.cs')
if($LASTEXITCODE -ne 0){throw 'Expression template test compilation failed.'}
& (Join-Path $sp2TestOutput 'ExpressionTemplatesTests.exe')
if($LASTEXITCODE -ne 0){throw 'Expression template tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'OperationResultsTests.exe')) (Join-Path $sp2Root 'bridge\OperationResults.cs') (Join-Path $PSScriptRoot 'OperationResultsTests.cs')
if($LASTEXITCODE -ne 0){throw 'Operation result retention test compilation failed.'}
& (Join-Path $sp2TestOutput 'OperationResultsTests.exe')
if($LASTEXITCODE -ne 0){throw 'Operation result retention tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'CameraStateTests.exe')) (Join-Path $sp2Root 'bridge\CameraState.cs') (Join-Path $PSScriptRoot 'CameraStateTests.cs')
if($LASTEXITCODE -ne 0){throw 'Camera state test compilation failed.'}
& (Join-Path $sp2TestOutput 'CameraStateTests.exe')
if($LASTEXITCODE -ne 0){throw 'Camera state tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'ReplacementLifetimeTests.exe')) (Join-Path $sp2Root 'bridge\ReplacementLifetime.cs') (Join-Path $PSScriptRoot 'ReplacementLifetimeTests.cs')
if($LASTEXITCODE -ne 0){throw 'Replacement lifetime test compilation failed.'}
& (Join-Path $sp2TestOutput 'ReplacementLifetimeTests.exe')
if($LASTEXITCODE -ne 0){throw 'Replacement lifetime tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'InputControllerFieldsTests.exe')) (Join-Path $sp2Root 'bridge\InputControllerFields.cs') (Join-Path $PSScriptRoot 'InputControllerFieldsTests.cs')
if($LASTEXITCODE -ne 0){throw 'Input controller test compilation failed.'}
& (Join-Path $sp2TestOutput 'InputControllerFieldsTests.exe')
if($LASTEXITCODE -ne 0){throw 'Input controller tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'ReadModelsTests.exe')) (Join-Path $sp2Root 'bridge\ReadModels.cs') (Join-Path $PSScriptRoot 'ReadModelsTests.cs')
if($LASTEXITCODE -ne 0){throw 'Read model test compilation failed.'}
& (Join-Path $sp2TestOutput 'ReadModelsTests.exe') (Join-Path $PSScriptRoot 'artifacts\live-0.3.1-20261002\baseline.json')
if($LASTEXITCODE -ne 0){throw 'Read model tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'BatchReferencesTests.exe')) (Join-Path $sp2Root 'bridge\BatchReferences.cs') (Join-Path $PSScriptRoot 'BatchReferencesTests.cs')
if($LASTEXITCODE -ne 0){throw 'Batch reference test compilation failed.'}
& (Join-Path $sp2TestOutput 'BatchReferencesTests.exe')
if($LASTEXITCODE -ne 0){throw 'Batch reference tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'ShapeCodecTests.exe')) (Join-Path $sp2Root 'bridge\ShapeCodec.cs') (Join-Path $PSScriptRoot 'ShapeCodecTests.cs')
if($LASTEXITCODE -ne 0){throw 'Shape test compilation failed.'}
& (Join-Path $sp2TestOutput 'ShapeCodecTests.exe') (Join-Path $PSScriptRoot 'artifacts\readonly-start.xml')
if($LASTEXITCODE -ne 0){throw 'Shape tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'SnapshotStateTests.exe')) (Join-Path $sp2Root 'bridge\SnapshotState.cs') (Join-Path $PSScriptRoot 'SnapshotStateTests.cs')
if($LASTEXITCODE -ne 0){throw 'Snapshot test compilation failed.'}
& (Join-Path $sp2TestOutput 'SnapshotStateTests.exe') (Join-Path $PSScriptRoot 'artifacts\readonly-start.xml')
if($LASTEXITCODE -ne 0){throw 'Snapshot tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'NativeRestoreCacheTests.exe')) (Join-Path $sp2Root 'bridge\SnapshotState.cs') (Join-Path $sp2Root 'bridge\NativeRestoreCachePlan.cs') (Join-Path $PSScriptRoot 'NativeRestoreCacheTests.cs')
if($LASTEXITCODE -ne 0){throw 'Native restore cache test compilation failed.'}
& (Join-Path $sp2TestOutput 'NativeRestoreCacheTests.exe')
if($LASTEXITCODE -ne 0){throw 'Native restore cache tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'AssemblyScopeTests.exe')) (Join-Path $sp2Root 'bridge\AssemblyScope.cs') (Join-Path $PSScriptRoot 'AssemblyScopeTests.cs')
if($LASTEXITCODE -ne 0){throw 'Assembly scope test compilation failed.'}
& (Join-Path $sp2TestOutput 'AssemblyScopeTests.exe') (Join-Path $PSScriptRoot 'artifacts\feedback-baseline.json')
if($LASTEXITCODE -ne 0){throw 'Assembly scope tests failed.'}
$sp2VisualSources=@('VisualCore.cs','CentersOverlay.cs','CentersCore.cs','VisualScope.cs') | ForEach-Object { Join-Path $sp2Root ('bridge\'+$_) }
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'GeometryMeasureTests.exe')) @sp2VisualSources (Join-Path $sp2Root 'bridge\GeometryMeasure.cs') (Join-Path $sp2Root 'bridge\SectionMeasure.cs') (Join-Path $PSScriptRoot 'GeometryMeasureTests.cs')
if($LASTEXITCODE -ne 0){throw 'Geometry test compilation failed.'}
& (Join-Path $sp2TestOutput 'GeometryMeasureTests.exe')
if($LASTEXITCODE -ne 0){throw 'Geometry tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'DesignerViewPlanTests.exe')) @sp2VisualSources (Join-Path $sp2Root 'bridge\DesignerViewPlan.cs') (Join-Path $PSScriptRoot 'DesignerViewPlanTests.cs')
if($LASTEXITCODE -ne 0){throw 'Designer view planning test compilation failed.'}
& (Join-Path $sp2TestOutput 'DesignerViewPlanTests.exe')
if($LASTEXITCODE -ne 0){throw 'Designer view planning tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'VisualTests.exe')) @sp2VisualSources (Join-Path $PSScriptRoot 'VisualTests.cs')
if($LASTEXITCODE -ne 0){throw 'Visual test compilation failed.'}
& (Join-Path $sp2TestOutput 'VisualTests.exe') (Join-Path $PSScriptRoot 'artifacts\visual-unit')
if($LASTEXITCODE -ne 0){throw 'Visual tests failed.'}
& $sp2Compiler /nologo /langversion:7.3 /nostdlib+ @sp2Refs ('/out:'+(Join-Path $sp2TestOutput 'CentersTests.exe')) @sp2VisualSources (Join-Path $PSScriptRoot 'CentersTests.cs')
if($LASTEXITCODE -ne 0){throw 'Centers test compilation failed.'}
& (Join-Path $sp2TestOutput 'CentersTests.exe') (Join-Path $PSScriptRoot 'artifacts\centers-0.4.0')
if($LASTEXITCODE -ne 0){throw 'Centers tests failed.'}
$sp2PriorPythonPath=$env:PYTHONPATH
try {
    $sp2LocalTestDependencies=Join-Path $PSScriptRoot '.deps'
    if(Test-Path -LiteralPath $sp2LocalTestDependencies) {
        $env:PYTHONPATH=$sp2LocalTestDependencies+[IO.Path]::PathSeparator+$sp2PriorPythonPath
    }
    & 'D:\apps\python\python.exe' -m unittest discover -s $PSScriptRoot -p 'test_*.py'
    if($LASTEXITCODE -ne 0){throw 'CLI tests failed. Optional schema dependencies belong in tests/.deps, not the CLI runtime.'}
} finally { $env:PYTHONPATH=$sp2PriorPythonPath }
