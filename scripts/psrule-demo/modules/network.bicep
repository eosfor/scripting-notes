// network.bicep
param location string

resource vnet 'Microsoft.Network/virtualNetworks@2022-01-01' = {
  name: 'my-vnet'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: ['10.0.0.0/16']
    }
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
