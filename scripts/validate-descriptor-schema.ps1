#requires -Version 7.5
param([Parameter(Mandatory)][string]$SchemaPath,[Parameter(Mandatory)][string]$XmlPath)
$ErrorActionPreference='Stop'
function Read-Bounded([string]$Path,[long]$Limit){
    $item=Get-Item -LiteralPath $Path
    if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -le 0 -or $item.Length -gt $Limit){throw 'Bounded regular input file required'}
    $raw=[IO.File]::ReadAllBytes($item.FullName)
    if($raw.Length -le 0 -or $raw.Length -gt $Limit){throw 'Input size changed beyond bound'}
    return ,$raw
}
$errors=[Collections.Generic.List[string]]::new();$schemaReader=$null;$xmlReader=$null;$schemaStream=$null;$xmlStream=$null
$result=[ordered]@{schema='sl3.xml-schema-validation.v1';valid=$false;engine='.NET XmlSchemaSet';externalResolution=$false;knownSchemaDtdIgnored=$false;errors=@()}
try{
    $schemaBytes=Read-Bounded $SchemaPath 16777216;$xmlBytes=Read-Bounded $XmlPath 65536
    $result.schemaSha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($schemaBytes)).ToLowerInvariant()
    $result.xmlSha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($xmlBytes)).ToLowerInvariant()
    $settings=[Xml.XmlReaderSettings]::new();$settings.XmlResolver=$null;$settings.DtdProcessing=[Xml.DtdProcessing]::Prohibit
    if($result.schemaSha256 -ceq '9e15093df616f9b9eac7f2f0fc1dbebfc55ce353415e22569fcfa00b98c1cc56'){
        $settings.DtdProcessing=[Xml.DtdProcessing]::Ignore;$result.knownSchemaDtdIgnored=$true
    }
    $schemaStream=[IO.MemoryStream]::new($schemaBytes,$false);$schemaReader=[Xml.XmlReader]::Create($schemaStream,$settings)
    $onValidation=[Xml.Schema.ValidationEventHandler]{param($sender,$event) if($errors.Count -lt 16){$errors.Add($event.Severity.ToString()+': '+$event.Message)}}
    $schema=[Xml.Schema.XmlSchema]::Read($schemaReader,$onValidation)
    if($null -eq $schema -or $schema.Includes.Count){throw 'Standalone schema without external imports/includes required'}
    $set=[Xml.Schema.XmlSchemaSet]::new();$set.XmlResolver=$null;$set.add_ValidationEventHandler($onValidation)
    $null=$set.Add($schema);$set.Compile()
    if(-not $set.IsCompiled -or $errors.Count){throw 'Schema compilation did not pass'}
    $validation=[Xml.XmlReaderSettings]::new();$validation.XmlResolver=$null;$validation.DtdProcessing=[Xml.DtdProcessing]::Prohibit
    $validation.ValidationType=[Xml.ValidationType]::Schema;$validation.Schemas=$set;$validation.add_ValidationEventHandler($onValidation)
    $xmlStream=[IO.MemoryStream]::new($xmlBytes,$false);$xmlReader=[Xml.XmlReader]::Create($xmlStream,$validation)
    while($xmlReader.Read()){}
    $result.valid=($errors.Count -eq 0)
}catch{if($errors.Count -lt 16){$errors.Add($_.Exception.Message)}}
finally{
    if($xmlReader){$xmlReader.Dispose()};if($schemaReader){$schemaReader.Dispose()}
    if($xmlStream){$xmlStream.Dispose()};if($schemaStream){$schemaStream.Dispose()}
}
$result.errors=@($errors);$result|ConvertTo-Json -Depth 5
if(-not $result.valid){exit 1}
