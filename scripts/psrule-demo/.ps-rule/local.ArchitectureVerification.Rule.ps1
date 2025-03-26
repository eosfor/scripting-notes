Rule 'local.Architecture.Verification' -Type 'Microsoft.Network/virtualNetworks' {
    $Assert.HasFieldValue($TargetObject, 'name', 'vnetDeployment')
}