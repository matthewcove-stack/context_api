param(
  [string]$BaseUrl = "http://localhost:8001",
  [string]$Token = "change-me",
  [string]$TopicKey = "smoke_topic",
  [string]$FeedUrl = "https://example.com/feed"
)

$ErrorActionPreference = "Stop"
$headers = @{
  "Authorization" = "Bearer $Token"
  "Content-Type"  = "application/json"
}

Write-Host "Bootstrapping sources for topic '$TopicKey'..."
$bootstrapBody = @{
  topic_key      = $TopicKey
  suggestions    = @(
    @{
      kind     = "rss"
      name     = "Smoke Feed"
      base_url = $FeedUrl
      tags     = @("smoke")
    }
  )
  trigger_ingest = $true
  trigger        = "event"
  idempotency_key = "smoke-$TopicKey"
} | ConvertTo-Json -Depth 8

$bootstrap = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v2/research/sources/bootstrap" -Headers $headers -Body $bootstrapBody
if (-not $bootstrap.ingest.run_id) {
  throw "Bootstrap did not return run_id."
}
$runId = $bootstrap.ingest.run_id
Write-Host "Run queued: $runId"

Write-Host "Executing research worker once..."
docker compose run --rm api python -m app.research.worker --once | Out-Host

Write-Host "Polling ingest run status..."
$statusValue = ""
for ($i = 0; $i -lt 20; $i++) {
  Start-Sleep -Seconds 1
  $status = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v2/research/ingest/runs/$runId" -Headers $headers
  $statusValue = "$($status.status)"
  if ($statusValue -eq "completed" -or $statusValue -eq "failed") {
    break
  }
}

if ($statusValue -ne "completed") {
  throw "Ingest run did not complete successfully (status=$statusValue)."
}
Write-Host "Ingest completed."

Write-Host "Validating retrieval..."
$packBody = @{
  query     = "supply"
  topic_key = $TopicKey
  max_items = 3
} | ConvertTo-Json -Depth 8
$pack = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v2/research/context/pack" -Headers $headers -Body $packBody

if (-not $pack.pack.items -or $pack.pack.items.Count -lt 1) {
  throw "Retrieval returned no items."
}

Write-Host "Smoke PASS: bootstrap -> ingest -> retrieval returned $($pack.pack.items.Count) items."
