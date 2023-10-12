param location string = 'westus'

var globalTags =  {
  Environment: 'Non-Prod'
  'hidden-title': 'DEV-ENV'
}

// stub network
module publicIpAddress 'external/ResourceModules/modules/network/public-ip-address/main.bicep' = {
  name: '${uniqueString(deployment().name, location)}-pip'
  params: {
    // Required parameters
    name: 'default-nat-gw-pip'
    location: location
    skuName: 'Standard'
    tags: globalTags
  }
}

module natGateway 'external/ResourceModules/modules/network/nat-gateway/main.bicep' = {
  name: '${uniqueString(deployment().name, location)}-nat-gw'
  dependsOn: [
    publicIpAddress
  ]
  params: {
    // Required parameters
    location: location
    name: 'default-nat-gateway'
    natGatewayPipName: 'default-nat-gw-pip'
    tags: globalTags
  }
}

module virtualNetwork 'external/ResourceModules/modules/network/virtual-network/main.bicep' = {
  name: '${uniqueString(deployment().name, location)}-vnet-deployment'
  params: {
    // Required parameters
    location: location
    addressPrefixes: [
      '10.0.0.0/8'
    ]
    name: 'application-stub-vnet'
    subnets: [
      {
        addressPrefix: '10.10.0.0/16'
        name: 'appsvc1-subnet'
        natGatewayId: natGateway.outputs.resourceId
        delegations: [
          {
              name: 'dev1-appsvc-plan-delegation'
              properties: {
                  serviceName: 'Microsoft.Web/serverFarms'
              }
          }
        ]
      }
      {
        addressPrefix: '10.11.0.0/16'
        name: 'private-endpoint-subnet'
        properties: {
          natGatewayId: natGateway.outputs.resourceId
        }
      }
    ]
    tags: union(globalTags, {
      defaultNetwork: 'true'
      'dev1-appsvc-plan': 'appsvc1-subnet'
    })
  }
}

// App Service Plan
module serverfarm 'external/ResourceModules/modules/web/serverfarm/main.bicep' = {
  name: '${uniqueString(deployment().name, location)}-test-wsfcom'
  params: {
    // Required parameters
    location: location
    name: 'dev1-appsvc-plan'
    sku: {
      capacity: '1'
      family: 'S'
      name: 'S1'
      size: 'S1'
      tier: 'Standard'
    }
    tags: globalTags
  }
}

output ipAddress string = publicIpAddress.outputs.ipAddress
