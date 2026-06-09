# Run this script after closing your IDE to safely rename the remaining folders.
# This avoids "Access Denied" errors caused by active editor file-watchers.

Write-Host "Renaming folders to production structure..." -ForegroundColor Cyan

if (Test-Path "FYP_Project") {
    Rename-Item "FYP_Project" "frontend" -Force
    Write-Host "✓ FYP_Project -> frontend" -ForegroundColor Green
} else {
    Write-Host "- FYP_Project already renamed or not found" -ForegroundColor Yellow
}

if (Test-Path "backend") {
    Rename-Item "backend" "backend-fastapi" -Force
    Write-Host "✓ backend -> backend-fastapi" -ForegroundColor Green
} else {
    Write-Host "- backend already renamed or not found" -ForegroundColor Yellow
}

Write-Host "Finished! You can now reopen your IDE." -ForegroundColor Green
Read-Host "Press Enter to exit..."
