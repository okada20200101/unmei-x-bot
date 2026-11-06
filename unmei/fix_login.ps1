$ErrorActionPreference = 'Stop'
$proj = 'C:\unmei_build\src\flutter_app'
$desk = [Environment]::GetFolderPath('Desktop')
$log  = Join-Path $desk 'build_v50_log.txt'
$dst  = Join-Path $proj 'lib\screens\login_screen.dart'

function L($m) { $m | Out-File -FilePath $log -Encoding UTF8 -Append }
"=== 運命の命式 v50 ビルド ===" | Out-File -FilePath $log -Encoding UTF8

if (-not (Test-Path (Join-Path $proj 'pubspec.yaml'))) {
  L "[NG] プロジェクトが見つかりません: $proj"
  Start-Process notepad.exe $log
  return
}
L "[OK] プロジェクト: $proj"

$url = 'https://raw.githubusercontent.com/okada20200101/unmei-x-bot/main/unmei/login_screen.dart'
try {
  $wc = New-Object System.Net.WebClient
  $wc.Headers.Add('User-Agent', 'unmei-app')
  $bytes = $wc.DownloadData($url)
} catch {
  L "[NG] ダウンロードに失敗しました: $($_.Exception.Message)"
  Start-Process notepad.exe $log
  return
}
L "[OK] 受信: $($bytes.Length) バイト"
if ($bytes.Length -lt 8000) {
  L "[NG] 受信サイズが想定と違います"
  Start-Process notepad.exe $log
  return
}

if (Test-Path $dst) {
  Copy-Item $dst (Join-Path $desk 'login_screen_backup.dart') -Force
  L "[OK] 元ファイルを控えました: デスクトップ\login_screen_backup.dart"
}
[IO.File]::WriteAllBytes($dst, $bytes)
$chk = Get-Content -Raw -LiteralPath $dst
if ($chk -notmatch 'loginWithPassword') {
  L "[NG] 書き込んだ内容が想定と違います"
  Start-Process notepad.exe $log
  return
}
L "[OK] login_screen.dart を差し替えました"

Set-Location $proj
L "[..] flutter pub get"
(& flutter pub get) 2>&1 | Out-File -FilePath $log -Encoding UTF8 -Append
L "[..] flutter build appbundle"
(& flutter build appbundle --release --build-name 1.0.10 --build-number 50) 2>&1 | Out-File -FilePath $log -Encoding UTF8 -Append

$aab = Join-Path $proj 'build\app\outputs\bundle\release\app-release.aab'
if (-not (Test-Path $aab)) {
  L "[NG] AAB ができませんでした。上のログを確認してください"
  Start-Process notepad.exe $log
  return
}
$out = Join-Path $desk 'unmei_v50.aab'
Copy-Item $aab $out -Force
$f = Get-Item $out
L ""
L "=== 完成 ==="
L ("サイズ: " + $f.Length + " バイト")
L ("SHA256: " + (Get-FileHash $out -Algorithm SHA256).Hash)
Start-Process notepad.exe $log
