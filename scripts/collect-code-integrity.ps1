param([string]$Output = 'tests/results/local/code-integrity.json', [int]$Hours = 2)
$ErrorActionPreference = 'Stop'
$events = @(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-CodeIntegrity/Operational';StartTime=(Get-Date).AddHours(-$Hours)} -ErrorAction SilentlyContinue)
$hits = @($events | Where-Object Message -match 'strmdrv|RaneAsioSL3')
$activities = @($hits | ForEach-Object { ([xml]$_.ToXml()).Event.System.Correlation.ActivityID } | Where-Object { $_ })
$rows = @(foreach ($event in $events) {
    $xml = [xml]$event.ToXml()
    if ($event.Message -notmatch 'strmdrv|RaneAsioSL3' -and $xml.Event.System.Correlation.ActivityID -notin $activities) { continue }
    $fields = [ordered]@{}
    foreach ($field in $xml.Event.EventData.Data) { $fields[$field.Name] = $field.'#text' }
    [ordered]@{id=$event.Id;timeUtc=$event.TimeCreated.ToUniversalTime().ToString('o');activityId=$xml.Event.System.Correlation.ActivityID;fields=$fields;message=$event.Message}
})
$parent = Split-Path -Parent $Output
if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
ConvertTo-Json -InputObject $rows -Depth 8 | Set-Content -LiteralPath $Output -Encoding utf8
Write-Output $Output
