param location string = 'westus'

// SQL Server configuration
module defaultSqlServer 'external/ResourceModules/modules/sql/server/main.bicep' = {
  name: '${uniqueString(deployment().name, location)}-sql-server'
  params: {
    // Required parameters
    name: 'sqlserver${uniqueString(deployment().name, location)}'
    // Non-required parameters
    administratorLogin: 'rndUsrName06'
    administratorLoginPassword: 'bvljdbvirboiqwbvv13df#dfssimt'
    location: location
    restrictOutboundNetworkAccess: 'Disabled'
    publicNetworkAccess: 'Disabled'
  }
}

module redis 'external/ResourceModules/modules/cache/redis/main.bicep' = {
  name: '${uniqueString(deployment().name, location)}-redis'
  params: {
    // Required parameters
    name: 'redis${uniqueString(deployment().name, location)}'
    location: location
    // Non-required parameters
    capacity: 1
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    redisVersion: '6'
    shardCount: 1
    skuName: 'Basic'
    zoneRedundant: false
  }
}
