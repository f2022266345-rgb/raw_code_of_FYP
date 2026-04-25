# Test the complete chat pipeline
Write-Host "=== TESTING FULL CHAT PIPELINE ==="
Write-Host ""

# Step 1: Signup/Login to get JWT token
Write-Host "Step 1: Creating/logging in user..."
$signupUrl = "http://localhost:4000/api/auth/signup"
$signupPayload = @{
  email = "test_chatpipeline@test.com"
  password = "TestPass123!"
  name = "Pipeline Tester"
} | ConvertTo-Json

try {
  $authResponse = Invoke-WebRequest -Uri $signupUrl -Method POST -ContentType "application/json" -Body $signupPayload -ErrorAction SilentlyContinue -TimeoutSec 5
  $authData = $authResponse.Content | ConvertFrom-Json
  
  $token = $authData.token
  $userId = $authData.user.id
  
  Write-Host "✓ Signup successful. User ID: $userId"
} catch {
  Write-Host "Signup failed, attempting login..."
  try {
    $loginUrl = "http://localhost:4000/api/auth/login"
    $loginPayload = @{
      email = "test_chatpipeline@test.com"
      password = "TestPass123!"
    } | ConvertTo-Json
    $authResponse = Invoke-WebRequest -Uri $loginUrl -Method POST -ContentType "application/json" -Body $loginPayload -TimeoutSec 5
    $authData = $authResponse.Content | ConvertFrom-Json
    
    $token = $authData.token
    $userId = $authData.user.id
    
    Write-Host "✓ Login successful. User ID: $userId"
  } catch {
    Write-Host "✗ Auth failed: $_"
    exit
  }
}

Write-Host "✓ Token length: $($token.Length)"
Write-Host ""
Write-Host "Step 2: Sending chat message to Gemini..."

# Step 2: Send chat message
$chatUrl = "http://localhost:4000/api/chat"
$chatPayload = @{
  userId = $userId
  message = "What is photosynthesis? Explain simply."
  skillName = "Biology"
  agentType = "academic"
} | ConvertTo-Json

$headers = @{
  "Content-Type" = "application/json"
  "Authorization" = "Bearer $token"
}

Write-Host "Sending payload: $chatPayload"

try {
  $chatResponse = Invoke-WebRequest -Uri $chatUrl -Method POST -Body $chatPayload -Headers $headers -TimeoutSec 60
  $chatData = $chatResponse.Content | ConvertFrom-Json
  
  Write-Host "✓ Chat response received (HTTP 200)"
  Write-Host ""
  Write-Host "Response details:"
  Write-Host "- Agent: $($chatData.agent)"
  Write-Host "- BKT State: p_mastery=$($chatData.state.p_mastery | Select-Object -First 1)"
  Write-Host "- Persona: $($chatData.persona)"
  Write-Host ""
  Write-Host "Gemini Response:"
  Write-Host "================"
  Write-Host $chatData.response
  Write-Host "================"
  
  # Check if it's a dummy/fallback response
  $dummyPatterns = @(
    "Let's break this down",
    "That's a great question",
    "I'm processing your context"
  )
  
  $isDummy = $false
  foreach ($pattern in $dummyPatterns) {
    if ($chatData.response -match [regex]::Escape($pattern)) {
      $isDummy = $true
      break
    }
  }
  
  if ($isDummy) {
    Write-Host ""
    Write-Host "⚠ WARNING: Response appears to be a fallback message, not real Gemini!"
  } else {
    Write-Host ""
    Write-Host "✓ Response appears to be REAL Gemini output!"
  }
  
} catch {
  Write-Host "✗ Chat request failed: $_"
  if ($_.Exception.Response) {
    Write-Host "Error Body: $($_.Exception.Response.GetResponseStream().ReadToEnd())"
  }
}
