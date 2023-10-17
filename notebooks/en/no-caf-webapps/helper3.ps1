$global:PrivateLinkDNSZones = @{
    "Microsoft.Automation/automationAccounts"        = "privatelink.azure-automation.net"
    "Microsoft.Sql/servers"                          = "privatelink.database.windows.net"
    #"Microsoft.Sql/managedInstances"                 = "privatelink.{dnsPrefix}.database.windows.net"
    "Microsoft.Cache/Redis"                          = "privatelink.redis.cache.windows.net"
    "Microsoft.Synapse/workspaces"                   = @{
        "Sql"         = "privatelink.sql.azuresynapse.net"
        "SqlOnDemand" = "privatelink.sql.azuresynapse.net"
        "Dev"         = "privatelink.dev.azuresynapse.net"
    }
    "Microsoft.Synapse/privateLinkHubs"              = "privatelink.azuresynapse.net"
    "Microsoft.Storage/storageAccounts"              = @{
        "blob"  = "privatelink.blob.core.windows.net"
        "table" = "privatelink.table.core.windows.net"
        "queue" = "privatelink.queue.core.windows.net"
        "file"  = "privatelink.file.core.windows.net"
        "web"   = "privatelink.web.core.windows.net"
        "dfs"   = "privatelink.dfs.core.windows.net"
    }
    "Microsoft.AzureCosmosDB/databaseAccounts"       = @{
        "Sql"       = "privatelink.documents.azure.com"
        "MongoDB"   = "privatelink.mongo.cosmos.azure.com"
        "Cassandra" = "privatelink.cassandra.cosmos.azure.com"
        "Gremlin"   = "privatelink.gremlin.cosmos.azure.com"
        "Table"     = "privatelink.table.cosmos.azure.com"
    }
    "Microsoft.DBforPostgreSQL/serverGroupsv2"       = "privatelink.postgres.cosmos.azure.com"
    "Microsoft.DBforPostgreSQL/servers"              = "privatelink.postgres.database.azure.com"
    "Microsoft.DBforMySQL/servers"                   = "privatelink.mysql.database.azure.com"
    "Microsoft.DBforMariaDB/servers"                 = "privatelink.mariadb.database.azure.com"
    "Microsoft.KeyVault/vaults"                      = "privatelink.vaultcore.azure.net"
    "Microsoft.KeyVault/managedHSMs"                 = "privatelink.managedhsm.azure.net"
    # "Microsoft.ContainerService/managedClusters"     = "privatelink.{regionName}.azmk8s.io"
    "Microsoft.Search/searchServices"                = "privatelink.search.windows.net"
    "Microsoft.ContainerRegistry/registries"         = "privatelink.azurecr.io"
    "Microsoft.AppConfiguration/configurationStores" = "privatelink.azconfig.io"
    # "Microsoft.RecoveryServices/vaults"              = @{
    #     "AzureBackup"       = "privatelink.{regionCode}.backup.windowsazure.com"
    #     "AzureSiteRecovery" = "privatelink.siterecovery.windowsazure.com"
    # }
    "Microsoft.EventHub/namespaces"                  = "privatelink.servicebus.windows.net"
    "Microsoft.ServiceBus/namespaces"                = "privatelink.servicebus.windows.net"
}

function Get-SourceResource {
    param (
        [Parameter(Mandatory = $true)]
        [string]$resourceGroupName
    )
    $ret = Get-AzResource -ResourceGroupName $resourceGroupName | ? { Get-AzPrivateLinkResource -PrivateLinkResourceId $_.Id -ErrorAction SilentlyContinue }
    Write-Verbose "Found $($ret.name)"
    return $ret
}

# List resources in the RG, and return only those which support private endpoints
function New-PrivateDnsZoneName {
    [CmdletBinding()]
    param (
        [Microsoft.Azure.Commands.ResourceManager.Cmdlets.SdkModels.PSResource]$Resource
    )
    
    process {
        $resourceType = $resource.ResourceType
        return $global:PrivateLinkDNSZones[$resourceType]
    }
}

function Get-VnetList {
    param (
        [Parameter(Mandatory = $true)]
        [string]$ResourceGroupName
    )
    $vnet = Get-AzVirtualNetwork -ResourceGroupName $ResourceGroupName
    return $vnet
}

function Get-SubnetList {
    param (
        [Parameter(Mandatory = $true)]
        [string]$ResourceGroupName
    )
    $vnet = Get-AzVirtualNetwork -ResourceGroupName $ResourceGroupName
    $subnet = $vnet.Subnets
    return $subnet
}

function New-PrivateDnsZone {
    param (
        [Parameter(Mandatory = $true)]
        [string]$ResourceGroupName,
        [Parameter(Mandatory = $true, ValueFromPipeline = $true)]
        [Microsoft.Azure.Commands.ResourceManager.Cmdlets.SdkModels.PSResource]$Resource
    )
    process {
        $privateDnsZoneName = New-PrivateDnsZoneName -Resource $Resource

        Write-Verbose "Attempting to create $privateDnsZoneName in $ResourceGroupName"
        $privateDnsZone = Get-AzPrivateDnsZone -Name $privateDNSZoneName -ResourceGroupName $ResourceGroupName -ErrorAction SilentlyContinue
        if (-not $privateDNSZone) {
            Write-Verbose "Zone does not exist, creating $privateDnsZoneName in $ResourceGroupName"
            $privateDNSZone = New-AzPrivateDnsZone -Name $privateDnsZoneName -ResourceGroupName $ResourceGroupName
        }
        else {
            Write-Verbose "The Zone $privateDnsZoneName does exist in $ResourceGroupName. Skipping"
        }
    
        return $privateDNSZone
    }
}

function Connect-PrivateDnsZone {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $true, ValueFromPipeline = $true)]
        [Microsoft.Azure.Commands.PrivateDns.Models.PSPrivateDnsZone]$PrivateDNSZone,
        [Parameter(Mandatory = $true)]
        [string]$ResourceGroupName
    )
    process {
        $vnets = Get-VnetList -ResourceGroupName $ResourceGroupName
        $existingLinks = Get-AzPrivateDnsVirtualNetworkLink -ResourceGroupName $ResourceGroupName -ZoneName $PrivateDNSZone.Name

        foreach ($vnet in $vnets) {
            if ($existingLinks.VirtualNetworkId -notcontains $vnet.Id) {
                $virtualNetworkLinkName = "$($vnet.name)-VNetLink-$($PrivateDNSZone.Name)"
                $virtualNetworkLink = New-AzPrivateDnsVirtualNetworkLink -ResourceGroupName $ResourceGroupName `
                    -ZoneName $PrivateDNSZone.Name `
                    -Name $virtualNetworkLinkName `
                    -VirtualNetworkId $vnet.Id
            }
        }
        
        return $virtualNetworkLink
    }
}

function Get-GroupId {
    param (
        [Parameter(Mandatory = $true)]
        [string]$ResourceId
    )
    return @((Get-AzPrivateLinkResource -PrivateLinkResourceId $resourceId).GroupId)[0]
}

function Test-PrivateEndpoint {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $true, ValueFromPipeline = $true)]
        [Microsoft.Azure.Commands.ResourceManager.Cmdlets.SdkModels.PSResource]$Resource,
        [Parameter(Mandatory = $true)]
        $subnet,
        [Parameter(Mandatory = $true)]
        $ResourceGroupName,
        [Parameter(Mandatory = $true)]
        [Microsoft.Azure.Commands.Network.Models.PSPrivateEndpoint[]]
        $Endpoints

    )
    process {
        $ret = $null
        Write-Verbose "Searching for a PE pointing at $($Resource.id) in $($subnet.id)"
        $ret = $endpoints | ? { $_.Subnet.Id -eq $subnet.id } | ? { $_.PrivateLinkServiceConnections.PrivateLinkServiceId -eq $Resource.id }
        if ($ret) { Write-Verbose "The private endpoint $($ret.name) found" }
        else {
            Write-Verbose "The private endpoint not found"
        }
        return $ret
    }
}

function New-PrivateEndpoint {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $true, ValueFromPipeline = $true)]
        [Microsoft.Azure.Commands.ResourceManager.Cmdlets.SdkModels.PSResource]$Resource,
        [Parameter(Mandatory = $true)]
        [string]$ResourceGroupName
    )
    process {
        $subnets = Get-SubnetList -ResourceGroupName $ResourceGroupName | Where-Object { $_.name -eq 'private-endpoint-subnet' }
        $groupId = Get-GroupId -ResourceId $Resource.Id
        $endpoints = @(Get-AzPrivateEndpoint -ResourceGroupName $ResourceGroupName)

        foreach ($subnet in $subnets) {
            $privateEndpoint = Test-PrivateEndpoint -Resource $Resource -Subnet $subnet -ResourceGroupName $ResourceGroupName -Endpoints $endpoints
            if (! $privateEndpoint ) {
                $privateEndpointName = "$($Resource.Name)-$($subnet.name)-PE"
                $privateLinkServiceConnectionName = "$($Resource.Name)-PLSConnection"
    
                $plSvcConnectionObject = @{
                    Name                 = $privateLinkServiceConnectionName
                    PrivateLinkServiceId = $Resource.Id
                    GroupIds             = $groupId
                }
    
                $privateEndpoint = New-AzPrivateEndpoint -ResourceGroupName $ResourceGroupName `
                    -Name $privateEndpointName `
                    -Location $Resource.Location `
                    -Subnet $subnet `
                    -PrivateLinkServiceConnection $plSvcConnectionObject
            }

            return $privateEndpoint
        }
    }
}

function New-PrivateDnsZoneGroup {
    [CmdletBinding()]
    param (
        [Microsoft.Azure.Commands.Network.Models.PSPrivateEndpoint[]]$PrivateEndpoints,
        [Microsoft.Azure.Commands.PrivateDns.Models.PSPrivateDnsZone[]]$PrivateDnsZone,
        [string]$ResourceGroupName

    )  
    process {
        foreach ($pvtEndpoint in $PrivateEndpoints) {
            $serviceType = ($pvtEndpoint.PrivateLinkServiceConnections[0].PrivateLinkServiceId -split '/' | Select-Object -Index 6, 7) -join '/'
            $dnsZoneName = $global:PrivateLinkDNSZones[$serviceType]
            $dnsZone = $PrivateDnsZone | where Name -eq $dnsZoneName

            $peDnsGroup = Get-AzPrivateDnsZoneGroup -ResourceGroupName $ResourceGroupName -PrivateEndpointName $pvtEndpoint.Name
            $newConfig = New-AzPrivateDnsZoneConfig -Name "$dnsZoneName-pe-dns-config" -PrivateDnsZoneId $dnsZone.ResourceId

            if ($peDnsGroup.count -le 0) {
                New-AzPrivateDnsZoneGroup -ResourceGroupName $ResourceGroupName -PrivateEndpointName $pvtEndpoint.Name -name "$dnsZoneName-pe-dns-group"  -PrivateDnsZoneConfig $newConfig
            }
            else {
                $config = $peDnsGroup.PrivateDnsZoneConfigs | where name -eq "$dnsZoneName-pe-dns-config"
                if (! $config ) {
                    # $peDnsGroup.PrivateDnsZoneConfigs.Add($newConfig)
                    # Set-AzPrivateDnsZoneGroup -ResourceGroupName $ResourceGroupName -PrivateDnsZoneConfig $peDnsGroup.PrivateDnsZoneConfigs -PrivateEndpointName $pvtEndpoint.Name --name "$dnsZoneName-pe-dns-group"
                    Set-AzPrivateDnsZoneGroup -ResourceGroupName $ResourceGroupName -PrivateDnsZoneConfig $newConfig -PrivateEndpointName $pvtEndpoint.Name --name "$dnsZoneName-pe-dns-group"
                }
            }



            # if (! $peDnsGroup) {
            #     $config = New-AzPrivateDnsZoneConfig -Name "$dsZoneName-pe-dns-config" -PrivateDnsZoneId $dnsZone.ResourceId
            #     New-AzPrivateDnsZoneGroup -ResourceGroupName $ResourceGroupName -PrivateEndpointName $pvtEndpoint.Name -name "$dsZoneName-pe-dns-group"  -PrivateDnsZoneConfig $config -Force
            # }

        }
    }
}

function Connect-Environment {
    [CmdletBinding()]
    param (
        $SourceEnvResourceGroup,
        $TargetEnvResourceGroup
    )
    process {
        Write-Verbose "Connecting $SourceEnvResourceGroup to $TargetEnvResourceGroup"
        $resourcesToConnect = Get-SourceResource -ResourceGroupName $SourceEnvResourceGroup
        $pvtDnsZones = $resourcesToConnect | New-PrivateDnsZone -ResourceGroupName $TargetEnvResourceGroup
        $pvtDnsLinks = $pvtDnsZones | Connect-PrivateDnsZone -ResourceGroupName $TargetEnvResourceGroup 
        $pvtEndpoints = $resourcesToConnect | New-PrivateEndpoint -ResourceGroupName $TargetEnvResourceGroup
        $pvtDnsZoneGroups = New-PrivateDnsZoneGroup -ResourceGroupName $TargetEnvResourceGroup -PrivateDnsZone $pvtDnsZones -PrivateEndpoints $pvtEndpoints
    }
}


function Get-AppServicePlanDetail {
    [CmdletBinding()]
    param (
        $ResourceGroupName,
        [switch]$AsHTML
    )

    process {
        $webApp = Get-AzWebApp -ResourceGroupName $ResourceGroupName
        $webAppMapping = $webApp | select-object @{l = "AppServicePlan"; e = { $_.ServerFarmId -split '/' | Select-Object -Last 1 } },
        Name,
        @{l = "VNETName"; e = { $_.VirtualNetworkSubnetId -split '/' | Select-Object -Index 8 } },
        @{l = "SubnetName"; e = { $_.VirtualNetworkSubnetId -split '/' | Select-Object -Index 10 } }, 
        @{l = "SubnetId"; e = { $_.VirtualNetworkSubnetId } } | Sort-Object AppServicePlan
        if ($AsHTML.IsPresent) {
            $webAppMappingHtml = $webAppMapping | ConvertTo-Html -Fragment
            $webAppMappingHtml
        }
        else {
            $webAppMapping
        }
    }
}

function New-WebApp {
    [CmdletBinding(DefaultParameterSetName = 'autovnet')]
    param (
        [Parameter(Mandatory = $true, ParameterSetName = 'autovnet')]
        [Parameter(Mandatory = $true, ParameterSetName = 'explicitvnet')]
        $ResourceGroupName,
        [Parameter(Mandatory = $true, ParameterSetName = 'autovnet')]
        [Parameter(Mandatory = $true, ParameterSetName = 'explicitvnet')]
        $TargetAppSvcPlan,
        [Parameter(Mandatory = $true, ParameterSetName = 'autovnet')]
        [Parameter(Mandatory = $true, ParameterSetName = 'explicitvnet')]
        $WebAppName,
        [Parameter(Mandatory = $true, ParameterSetName = 'explicitvnet')]
        $TargetVnetName,
        [Parameter(Mandatory = $true, ParameterSetName = 'explicitvnet')]
        $TargetSubnetName
    )

    process {
        $resourceGroup = Get-AzResourceGroup -Name $ResourceGroupName
        $webAppMapping = Get-AppServicePlanDetail -ResourceGroupName $ResourceGroupName
        $matchingPlans = @($webAppMapping | Where-Object AppServicePlan -eq $TargetAppSvcPlan)
        if ($matchingPlans.Count -eq 0) {
            if ($PSCmdlet.ParameterSetName -ne 'explicitvnet'){
                Write-Error 'No Web apps are on the $TargetAppSvcPlan. Vnet and Subnet must be provided explicitly'
            }
        }
        switch ($PSCmdlet.ParameterSetName) {
            'autovnet' { 
                $subnetResourceId = @($webAppMapping | Where-Object AppServicePlan -eq $TargetAppSvcPlan)[0].SubnetId
            }
            'explicitvnet' { 
                $vnetObj = Get-AzVirtualNetwork -ResourceGroupName $ResourceGroupName -Name $TargetVnetName
                $subnetResourceId = @($vnetObj.Subnets | Where-Object Name -eq $TargetSubnetName)[0].SubnetId
            }
        }
            
        $appSvcPlan = Get-AzAppServicePlan -ResourceGroupName $ResourceGroupName -Name $TargetAppSvcPlan
        $webApp = Get-AzWebApp -ResourceGroupName $ResourceGroupName -Name $WebAppName -ErrorAction SilentlyContinue
        if (-not $webApp) {
            $webApp = New-AzWebApp -ResourceGroupName $ResourceGroupName -Name $WebAppName -Location $resourceGroup.Location -AppServicePlan $appSvcPlan.Name
            $webApp = Set-AzWebApp -AssignIdentity $true -Name $WebAppName -ResourceGroupName $ResourceGroupName 
        }
    
        $webAppResource = Get-AzResource -ResourceType 'Microsoft.Web/sites' -ResourceGroupName $ResourceGroupName -ResourceName $webApp.Name
        $webAppResource.Properties.publicNetworkAccess = 'Disabled'
        $webAppResource.Properties.virtualNetworkSubnetId = $subnetResourceId
        $webAppResource.Properties.vnetRouteAllEnabled = 'false'
        $webAppResource | Set-AzResource -Force
    }

}