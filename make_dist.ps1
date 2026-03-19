# MemoFast Dağıtım Zip Oluşturucu
$src = $PSScriptRoot
$zipPath = "$env:USERPROFILE\Desktop\MemoFast_1.1.2_dist.zip"

# Silinecek zip varsa sil
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

$excludeDirs = @('__pycache__','.pytest_cache','htmlcov','.cache','.backup','.agent','.logs','.secure','temp','temp_manual','temp_unpack','tests','.git','ping_booster_dev','NewYama','Patch_Folder')

$excludeFilePatterns = @('*.bak','*.pyc','.coverage','fix_*.py','tmp_*.py','test_*.py','*BROKEN*','*CLEAN*','SECURITY_AND_OPTIMIZATION_AUDIT.md','THREAD_SAFETY_AUDIT.md','remove_injector_popup.py','fix_gui.py','fix_unreal_bug.py','pytest.ini','make_dist.ps1')

$allFiles = Get-ChildItem $src -Recurse -File

$filtered = @()
foreach ($file in $allFiles) {
    $skip = $false
    
    # Dizin kontrolu
    foreach ($d in $excludeDirs) {
        if ($file.FullName -like "*\$d\*") {
            $skip = $true
            break
        }
    }
    if ($skip) { continue }
    
    # Dosya pattern kontrolu
    foreach ($p in $excludeFilePatterns) {
        if ($file.Name -like $p) {
            $skip = $true
            break
        }
    }
    if ($skip) { continue }
    
    $filtered += $file
}

$totalMB = [math]::Round(($filtered | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Host "Dahil edilecek dosya: $($filtered.Count), Toplam: $totalMB MB"

# Temp klasore kopyala
$tempDir = "$env:TEMP\MemoFast_dist"
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
New-Item $tempDir -ItemType Directory -Force | Out-Null

foreach ($file in $filtered) {
    $rel = $file.FullName.Substring($src.Length + 1)
    $dest = Join-Path $tempDir $rel
    $destDir = Split-Path $dest -Parent
    if (!(Test-Path $destDir)) { New-Item $destDir -ItemType Directory -Force | Out-Null }
    Copy-Item $file.FullName $dest -Force
}

# Zip yap
Compress-Archive -Path "$tempDir\*" -DestinationPath $zipPath -CompressionLevel Optimal
Remove-Item $tempDir -Recurse -Force

$zipSize = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)
Write-Host "ZIP olusturuldu: $zipPath ($zipSize MB)"
