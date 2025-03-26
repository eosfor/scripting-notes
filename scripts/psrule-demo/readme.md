# State of the art

The powershell command below

```powershell
cd /workspaces/scripting-notes/scripts/psrule-demo/
Invoke-PSRule -Option ./ps-rule.yaml -InputObject . -Path ./.ps-rule -Verbose -Debug
```

return

```console
Invoke-PSRule: Cannot process argument transformation on parameter 'Option'. Cannot convert value "./ps-rule.yaml" to type "PSRule.Configuration.PSRuleOption". Error: "Options file does not exist."
```

But i would expect it tu run successfully.

Another attempt, with full paths

```powershell
Invoke-PSRule -Option /workspaces/scripting-notes/scripts/psrule-demo/ps-rule.yaml -InputObject /workspaces/scripting-notes/scripts/psrule-demo -Path /workspaces/scripting-notes/scripts/psrule-demo/.ps-rule -Verbose -Debug
```

return

```console
VERBOSE: [Invoke-PSRule] BEGIN::
VERBOSE: [New-PSRuleOption] BEGIN::
VERBOSE: [New-PSRuleOption] END::
VERBOSE: [PSRule][D] -- Scanning for source files: /workspaces/scripting-notes/scripts/psrule-demo/.ps-rule
VERBOSE: [PSRule][D] -- Scanning for source files: .ps-rule/
VERBOSE: [PSRule][D] -- Discovering rules in: /workspaces/scripting-notes/scripts/psrule-demo/.ps-rule/local.ArchitectureVerification.Rule.ps1
VERBOSE: [PSRule][D] -- Found .\local.Architecture.Verification in /workspaces/scripting-notes/scripts/psrule-demo/.ps-rule/local.ArchitectureVerification.Rule.ps1
VERBOSE: [PSRule][R][0][.\local.Architecture.Verification] :: db144ec1c65441c05eb49892888c704121ae5c84
DEBUG: Target failed Type precondition
VERBOSE: [Invoke-PSRule] END::
```

But my expectation here that it should find the rule, which it does, then it should run a rule, find a resource of a type `Microsoft.Network/virtualNetworks` which is defined in [modules/network.bicep](/scripts/psrule-demo/modules/network.bicep), and return `success`.

The scenario is simple, there is an, say, Architect, who defines how a sertain solution shouls look in in Azure. Basically in most cases iti is a diagram in visio or smth like that. Then an engineer looks at the diagram and tries to implement it in bicep. So now there is a need for an Architect, to verify if whatever has been developed matched the design. Basically i is about checking whether or not all required resources are in their places, connected to correct vnets/subnets with correct private endpoints, etc.