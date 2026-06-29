$taskId = "52d61e67-c255-471a-82f4-1e98b4c8fe24"
$maxAttempts = 20
$headers = @{ 'Authorization' = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTc4MTE2MDU0MH0.03g1rTPfpq_FSO68zWauM-q4dmVutXZgJtBI3PEEJ9c' }

for ($i = 1; $i -le $maxAttempts; $i++) {
    Start-Sleep -Seconds 30
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:8000/api/analysis/tasks/$taskId/status" -Headers $headers -TimeoutSec 10
        Write-Host "[$i/$maxAttempts] STATUS: $($r.status) | PROGRESS: $($r.progress)% | STEP: $($r.current_step)"
        if ($r.status -eq 'completed' -or $r.status -eq 'failed') {
            Write-Host "FINAL STATUS: $($r.status)"
            Write-Host ($r | ConvertTo-Json -Depth 5)
            break
        }
        if ($i -eq $maxAttempts) {
            Write-Host "TIMEOUT: Reached max attempts without completion"
        }
    } catch {
        Write-Host "[$i/$maxAttempts] QUERY FAILED: $($_.Exception.Message)"
    }
}
