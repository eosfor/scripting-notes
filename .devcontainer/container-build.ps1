sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y minizinc

# Install PowerShell dependencies
$ProgressPreference = [System.Management.Automation.ActionPreference]::SilentlyContinue;
if ($Null -eq (Get-PackageProvider -Name NuGet -ErrorAction Ignore)) {
    Install-PackageProvider -Name NuGet -Force -Scope CurrentUser;
}