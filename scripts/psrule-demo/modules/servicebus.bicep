// servicebus.bicep
param location string
param serviceBusName string

resource sb 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: serviceBusName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
}

output serviceBusId string = sb.id
