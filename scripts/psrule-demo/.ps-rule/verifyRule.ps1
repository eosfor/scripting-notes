# Read resources in from file
$resources = Get-Content -Path ./scripts/psrule-demo/rules/main.json | ConvertFrom-Json;

# Process resources
$resources | Invoke-PSRule -Path ./scripts/psrule-demo/rules