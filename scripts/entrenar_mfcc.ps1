param(
    [string]$Python = 'py',
    [switch]$Reanudar,
    [switch]$SoloPreparar
)

$ErrorActionPreference = 'Stop'
$pythonArgs = @()
if ($Python -eq 'py') { $pythonArgs = @('-3.12') }
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$datasetPath = Join-Path $projectRoot 'data/datasets/audio/fma_small'
$venvPath = Join-Path $projectRoot '.venv-entrenamiento'
$venvPython = Join-Path $venvPath 'Scripts/python.exe'
$modelPath = Join-Path $projectRoot 'data/modelos/audio_mfcc'
if (-not (Get-ChildItem -LiteralPath $datasetPath -Recurse -File -Filter '*.mp3' -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    throw 'No se encontraron MP3: espera a que termine la copia o extraccion del dataset.'
}

if (-not (Test-Path -LiteralPath $datasetPath -PathType Container)) {
    throw "No se encuentra el dataset: $datasetPath"
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    & $Python @pythonArgs -c 'import sys; assert sys.version_info >= (3, 10), "Se requiere Python 3.10 o superior"'
    if ($LASTEXITCODE -ne 0) { throw 'Instala Python 3.10+ o indica su ruta con -Python.' }
    & $Python @pythonArgs -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno de entrenamiento.' }
}

& $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-audio-mfcc.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }

& $venvPython (Join-Path $PSScriptRoot 'entrenar_Kmeans.py') --autoprueba
if ($LASTEXITCODE -ne 0) { throw 'La autoprueba falló; no se iniciará el entrenamiento.' }
if ($SoloPreparar) { return }

$trainingArgs = @(
    (Join-Path $PSScriptRoot 'entrenar_Kmeans.py'),
    '--dataset', $datasetPath, '--tipo', 'audio',
    '--sr', '22050', '--mfcc', '13', '--segundos', '30', '--normalizacion', 'none', '--k', '256', '--semilla', '42', '--iteraciones', '50',
    '--salida', $modelPath
)
if ($Reanudar) { $trainingArgs += '--reanudar' }
& $venvPython @trainingArgs
if ($LASTEXITCODE -ne 0) { throw "El entrenamiento terminó con código $LASTEXITCODE." }
