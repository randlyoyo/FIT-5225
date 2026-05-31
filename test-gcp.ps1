# AussieEcoLens GCP 服务测试脚本
# 使用方法: 在 PowerShell 中运行 .\test-gcp.ps1

$base = "http://localhost:8080"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AussieEcoLens GCP 服务测试" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---- Test 1: Health ----
Write-Host "[Test 1] Health Check" -ForegroundColor Yellow
$r = Invoke-RestMethod -Uri "$base/health" -Method GET
$r | ConvertTo-Json
Write-Host ""

# ---- Test 2: Internal Infer (correct secret) ----
Write-Host "[Test 2] Internal Infer — correct secret" -ForegroundColor Yellow
$body = @{
    fileUrl  = "https://httpbin.org/image/jpeg"
    fileId   = "test-001"
    fileType = "image"
} | ConvertTo-Json

$headers = @{
    "Content-Type"      = "application/json"
    "X-Internal-Secret" = "change-me-in-production"
}

$r = Invoke-RestMethod -Uri "$base/internal/infer" -Method POST -Headers $headers -Body $body
$r | ConvertTo-Json
Write-Host ""

# ---- Test 3: Internal Infer (wrong secret) ----
Write-Host "[Test 3] Internal Infer — wrong secret" -ForegroundColor Yellow
$headers["X-Internal-Secret"] = "wrong-secret"
try {
    $r = Invoke-RestMethod -Uri "$base/internal/infer" -Method POST -Headers $headers -Body $body
    Write-Host "UNEXPECTED: Should have failed!" -ForegroundColor Red
} catch {
    Write-Host "Status: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Green
    Write-Host "Body: $($_.Exception.Message)" -ForegroundColor Green
}
Write-Host ""

# ---- Test 4: Missing required fields ----
Write-Host "[Test 4] Missing fileUrl/fileId" -ForegroundColor Yellow
$headers["X-Internal-Secret"] = "change-me-in-production"
$badBody = '{}'
try {
    $r = Invoke-RestMethod -Uri "$base/internal/infer" -Method POST -Headers $headers -Body $badBody
} catch {
    Write-Host "Status: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  测试完成!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
