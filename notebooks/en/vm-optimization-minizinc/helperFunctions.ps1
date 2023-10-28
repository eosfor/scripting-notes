if ([System.Environment]::OSVersion.Platform -eq "Win32NT") {
    $rootFolderPath = ".\vm-optimization-minizinc"
}
else {
    $rootFolderPath = "./vm-optimization-minizinc"
}

function Start-MinizincVMOptimizationModel {
    [CmdletBinding(DefaultParameterSetName = 'MinimizeCosts')]
    param (
        [Parameter(ParameterSetName = "MinimizeCosts", Mandatory)]
        [switch]$MinimizeCosts,
        [Parameter(ParameterSetName = "MaximizeACU", Mandatory)]
        [switch]$MaximizeACU,
        [Parameter(ParameterSetName = "FixCostsMaximizeACU", Mandatory)]
        [switch]$FixCostsMaximizeACU,
        [Parameter(ParameterSetName = "FixACUMinimizeCosts", Mandatory)]
        [switch]$FixACUMinimizeCosts,
        [Parameter(ParameterSetName = "FixCostsMaximizeACU", ValueFromPipeline = $true)]
        [Parameter(ParameterSetName = "FixACUMinimizeCosts", ValueFromPipeline = $true)]
        $InputObject = $null
    )
    begin {
        $maximizeTotalACU = 'vm-optimization-minizinc/maximize-totalACU.mzn'
        $minimizeTotalPrice = 'vm-optimization-minizinc/minimize-totalPrice.mzn'
        $fixTotalACU = 'vm-optimization-minizinc/fix-totalACU.mzn'
        $fixTotalPrice = 'vm-optimization-minizinc/fix-totalPrice.mzn'
        $DataPath = "vm-optimization-minizinc/vmData-integer.dzn"
    }
    process {
        switch ($PSCmdlet.ParameterSetName) {
            'MinimizeCosts' { Invoke-Minizinc -ModelPath $minimizeTotalPrice -DataPath $DataPath; break }
            'MaximizeACU' { Invoke-Minizinc -ModelPath $maximizeTotalACU -DataPath $DataPath; break }
            'FixCostsMaximizeACU' { Invoke-Minizinc -ModelPath $fixTotalPrice -DataPath $DataPath -Data "totalPriceMax=$($InputObject.totalPrice*10000)"; break }
            'FixACUMinimizeCosts' { Invoke-Minizinc -ModelPath $fixTotalACU -DataPath $DataPath -Data "totalAcuMax=$($InputObject.totalACU)"; break}
            Default {}
        }
        
    }
}