// main.bicep
param location string = resourceGroup().location
param functionName string = 'myfunc${uniqueString(resourceGroup().id)}'
param planName string = '${functionName}-plan'
param serviceBusName string = 'sb${uniqueString(resourceGroup().id)}'

module network '../../modules/network.bicep' = {
  name: 'vnetDeployment'
  params: {
    location: location
  }
}

module subnets '../../modules/subnets.bicep' = {
  name: 'subnetsDeployment'
  params: {
    location: location
    vnetId: network.outputs.vnetId
  }
}

module plan '../../modules/appserviceplan.bicep' = {
  name: 'planDeployment'
  params: {
    location: location
    planName: planName
  }
}

module serviceBus '../../modules/servicebus.bicep' = {
  name: 'sbDeployment'
  params: {
    location: location
    serviceBusName: serviceBusName
  }
}

module function '../../modules/functionapp.bicep' = {
  name: 'functionDeployment'
  params: {
    location: location
    functionName: functionName
    planId: plan.outputs.planId
    functionSubnetId: subnets.outputs.functionSubnetId
    privateEndpointSubnetId: subnets.outputs.privateEndpointSubnetId
  }
}
