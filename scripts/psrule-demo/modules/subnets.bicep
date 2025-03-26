// subnets-function.bicep
param location string
param vnetId string

var vnetIdSegments = split(vnetId, '/')
var vnetName = last(vnetIdSegments)

resource vnet 'Microsoft.Network/virtualNetworks@2022-01-01' existing = {
  name: vnetName
}

resource functionSubnet 'Microsoft.Network/virtualNetworks/subnets@2022-01-01' = {
  parent: vnet
  name: 'function-integration-subnet'
  properties: {
    addressPrefix: '10.0.1.0/24'
  }
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2022-01-01' = {
  parent: vnet
  name: 'private-endpoint-subnet'
  properties: {
    addressPrefix: '10.0.2.0/24'
    privateEndpointNetworkPolicies: 'Disabled'
  }
}

output functionSubnetId string = functionSubnet.id
output privateEndpointSubnetId string = privateEndpointSubnet.id
