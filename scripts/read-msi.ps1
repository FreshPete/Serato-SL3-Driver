param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Output)
$ErrorActionPreference = 'Stop'
$installer = New-Object -ComObject WindowsInstaller.Installer
$database = $installer.OpenDatabase((Resolve-Path -LiteralPath $Path).Path, 0)
$result = [ordered]@{}
foreach ($table in @('Property','File','Directory','Component','Registry','LaunchCondition','CustomAction')) {
    try {
        $view = $database.OpenView(('SELECT * FROM `' + $table + '`'))
        $view.Execute()
        $columns = $view.ColumnInfo(0)
        $rows = @()
        while ($record = $view.Fetch()) {
            $row = [ordered]@{}
            $count = $record.GetType().InvokeMember('FieldCount', 'GetProperty', $null, $record, $null)
            for ($i = 1; $i -le $count; $i++) {
                $key = $columns.GetType().InvokeMember('StringData', 'GetProperty', $null, $columns, @($i))
                $row[$key] = $record.GetType().InvokeMember('StringData', 'GetProperty', $null, $record, @($i))
            }
            $rows += $row
        }
        $result[$table] = $rows
        $view.Close()
    } catch { $result[$table] = @{error=$_.Exception.Message} }
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Output -Encoding utf8
