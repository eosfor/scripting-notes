// main.bicep
param location string = resourceGroup().location
param functionName string = 'myfunc${uniqueString(resourceGroup().id)}'
param planName string = '${functionName}-plan'
param serviceBusName string = 'sb${uniqueString(resourceGroup().id)}'

module network './modules/network.bicep' = {
  name: 'vnetDeployment'
  params: {
    location: location
  }
}

module subnets './modules/subnets.bicep' = {
  name: 'subnetsDeployment'
  params: {
    location: location
    vnetId: network.outputs.vnetId
  }
}

module plan './modules/appserviceplan.bicep' = {
  name: 'planDeployment'
  params: {
    location: location
    planName: planName
  }
}

module serviceBus './modules/servicebus.bicep' = {
  name: 'sbDeployment'
  params: {
    location: location
    serviceBusName: serviceBusName
  }
}

module function './modules/functionapp.bicep' = {
  name: 'functionDeployment'
  params: {
    location: location
    functionName: functionName
    planId: plan.outputs.planId
    functionSubnetId: subnets.outputs.functionSubnetId
    privateEndpointSubnetId: subnets.outputs.privateEndpointSubnetId
  }
}

resource stack 'Microsoft.Resources/deploymentStacks@2022-11-01' = {
  name: 'myDeploymentStack'
  location: location
  properties: {
    actionOnUnmanage: 'delete'
    deploymentProperties: {
      mode: 'Incremental'
      template: {
        '$schema': 'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#'
        contentVersion: '1.0.0.0'
        resources: [
          network
          subnets
          plan
          serviceBus
        ]
      }
    }
  }
}
