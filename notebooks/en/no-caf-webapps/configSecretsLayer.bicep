param location string = 'westus'

var tags =  {
  Environment: 'Non-Prod'
  'hidden-title': 'DEV-ENV'
}

module vault 'external/ResourceModules/modules/key-vault/vault/main.bicep' = {
  name: '${uniqueString(deployment().name, location)}-defaul-config-kv'
  params: {
    // Required parameters
    name: 'default-kv-${uniqueString(resourceGroup().name, location)}'
    location:location
    enablePurgeProtection: false
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
  }
}

module configurationStore 'external/ResourceModules/modules/app-configuration/configuration-store/main.bicep' = {
  name: '${uniqueString(deployment().name, location)}-default-appconfig'
  params: {
    // Required parameters
    name: 'default-configsvc-${uniqueString(resourceGroup().id, location)}'
    location: location
    // Non-required parameters
    createMode: 'Default'
  }
}
