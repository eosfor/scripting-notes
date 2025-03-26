Rule 'architecture.Verification.Rule' {
    # Rule description
    # Description = 'This rule checks the architecture of the template.'

    # Check for the presence of a VNet
    $hasVnet = $TargetObject | Where-Object { $_.type -eq 'Microsoft.Resources/deployments' } |
    Where-Object { $_.name -eq 'vnetDeployment' } |
    Where-Object { $_.properties.template.resources.type -contains 'Microsoft.Network/virtualNetworks' }

    # # Look for a function
    # $functions = $TargetObject | Where-Object { $_.type -like 'Microsoft.Web/sites' -and $_.kind -like '*functionapp*' }

    # # Check if there is app service VNet integration (resource type Microsoft.Web/sites/virtualNetworkConnections or a property inside the function)
    # $hasVnetIntegration = $TargetObject | Where-Object { $_.type -like 'Microsoft.Web/sites/virtualNetworkConnections' }

    # # Look for a private endpoint for the function
    # $hasPrivateEndpoint = $TargetObject | Where-Object {
    #     $_.type -eq 'Microsoft.Network/privateEndpoints' -and
    #         ($_.properties.privateLinkServiceConnections.properties.privateLinkServiceId -match ($functions.properties.id -replace '/$', ''))
    # }

    # # Look for a Service Bus with Standard SKU
    # $hasServiceBusStandard = $TargetObject | Where-Object {
    #     $_.type -eq 'Microsoft.ServiceBus/namespaces' -and $_.sku.name -eq 'Standard'
    # }

    # Assertions:
    # $hasVnet | Should -Not -BeNullOrEmpty -Because 'The template does not contain a virtual network.'
    # $functions | Should -Not -BeNullOrEmpty -Because 'The template does not contain an Azure Function.'
    # $hasVnetIntegration | Should -Not -BeNullOrEmpty -Because 'Azure Function VNet integration not found.'
    # $hasPrivateEndpoint | Should -Not -BeNullOrEmpty -Because 'Private Endpoint for Azure Function not found.'
    # $hasServiceBusStandard | Should -Not -BeNullOrEmpty -Because 'Service Bus does not have Standard SKU.'
    #}
}