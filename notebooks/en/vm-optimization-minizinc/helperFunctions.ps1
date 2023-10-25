if ([System.Environment]::OSVersion.Platform -eq "Win32NT") {
    $rootFolderPath = ".\vm-optimization-minizinc"
}
else {
    $rootFolderPath = "./vm-optimization-minizinc"
}



function New-TempModelFile {
    [CmdletBinding()]
    param (
        $SourceModelPath = "$rootFolderPath\vmCostsCalculation-integer.mzn"
    )
    process {
        $tmpFile = New-TemporaryFile
        $newName = "$($tmpFile.BaseName).mzn"
        $newPath = Join-Path -Path $tmpFile.DirectoryName -ChildPath $newName
        Rename-Item -Path $tmpFile.FullName -NewName $newName

        Get-Content -Path $SourceModelPath -ReadCount 0 | Out-File $newPath -Force
        $newPath
    }    
}


function Invoke-Minizinc {
    [CmdletBinding()]
    param (
        $Solver = "gecode",
        $Modelpath,
        $DataPath,
        $TimeLimit = (10 * 60 * 1000)
    )   
    process {
        if (-not (Test-Path $Modelpath) ) {Write-Error "$Modelpath does not exist"}
        
        Write-Verbose "Invoking: minizinc --solver $Solver  $Modelpath $DataPath --time-limit (10 * 60 * 1000)"
        
        if ([System.Environment]::OSVersion.Platform -eq "Win32NT") {
            $k = minizinc.exe --solver $Solver  $Modelpath $DataPath --time-limit (10 * 60 * 1000)
        }
        else {
            $k = minizinc --solver $Solver  $Modelpath $DataPath --time-limit (10 * 60 * 1000)
        }

        
        $x = ((($k) -replace "==========","") -join "`n" -split "----------") | ConvertFrom-Json -Depth 10

        Write-Verbose "modelling res is: $x"

        $x | Where-Object {$_ -ne $null}
    }
}

function Start-MinizincVMOptimizationModel {
    [CmdletBinding()]
    param (
        [Parameter(ParameterSetName = "Costs", Mandatory)]
        [switch]$Costs,
        [Parameter(ParameterSetName = "Performance", Mandatory)]
        [switch]$Performance,
        
        [Parameter(ParameterSetName = "Performance")]
        [Parameter(ParameterSetName = "Costs")]
        [string]$DataPath = "$rootFolderPath\vmData-integer.dzn",

        [Parameter(ParameterSetName = "Performance", ValueFromPipeline = $true)]
        [Parameter(ParameterSetName = "Costs", ValueFromPipeline = $true)]
        $InputObject = $null
    )
    process {
        $tFile = New-TempModelFile

        if (-not (Test-Path $DataPath) ) {Write-Error "$DataPath does not exist"}

        if($Costs.IsPresent) {
            if ($null -eq $InputObject) {
                (Get-Content $tFile) -replace "%placeholder%", "solve  minimize totalPrice;" | out-file -FilePath $tFile -Force
            }
            else {
                (Get-Content $tFile) -replace "%placeholder%", "constraint totalACU >= $($InputObject.totalACU); solve  minimize totalPrice;" | out-file -FilePath $tFile -Force
            }

            $ret = Invoke-Minizinc -Modelpath $tFile -DataPath (Resolve-Path $DataPath).Path
            return $ret

        }

        if ($Performance.IsPresent){
            if ($null -eq $InputObject){
                (Get-Content $tFile) -replace "%placeholder%", "solve  maximize totalACU;" | out-file -FilePath $tFile -Force
            }
            else {
                (Get-Content $tFile) -replace "%placeholder%", "constraint totalPrice <= $($InputObject.totalPrice * 10000); solve  maximize totalACU;" | out-file -FilePath $tFile -Force
            }
            
            $ret = Invoke-Minizinc -Modelpath $tFile -DataPath (Resolve-Path $DataPath).Path
            return $ret
        }        
    }
}

# Start-MinizincVMOptimizationModel -Costs

# Start-MinizincVMOptimizationModel -Costs | Start-MinizincVMOptimizationModel -Performance