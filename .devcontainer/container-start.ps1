# Update modules
Update-Module PSRule.Rules.Azure -Scope CurrentUser -Force;

$notebook = $env:NOTEBOOK

# Fetch the latest Bicep CLI binary
curl -Lo bicep https://github.com/Azure/bicep/releases/latest/download/bicep-linux-x64
# Mark it as executable
chmod +x ./bicep
# Add bicep to the PATH (requires admin)
sudo mv ./bicep /usr/local/bin/bicep
# Verify you can now access the 'bicep' command
bicep --version

if (![string]::IsNullOrWhiteSpace($notebook) -and (Test-Path $notebook)) {
    Write-Host "🚀 Opening notebook: $notebook"
    code $notebook
} else {
    Write-Host "📘 No notebook specified or file not found. Opening folder instead."
    code .
}