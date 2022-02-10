include "all_equal.mzn";

% config section
int: maxClusterSize = 6;
float: minNodeRAMConsumption = 0.5;
float: maxNodeRAMConsumption = 0.8;
float: minNodeCPUConsumption = 0.1;
float: maxNodeCPUConsumption = 0.8;
% end config

% applications and their attributes
enum appNames = {A, B, C, D, E};
array[appNames] of int: appRAM = [2,4,6,8,4];
array[appNames] of int: appCPU = [200,400,400,450,2250];
array[appNames] of int: appConnectionsPerInstance = [5,2,2, 2,2];
array[appNames] of int: appConnectionsFact = [4*5,2*2,3*2,2*2, 5*2];

% cluster nodes and their attributes
enum nodeKinds = {D2sv5, D4sv5, D8sv5}; 
array[nodeKinds] of int: clusterNodeRAM = [8,16,32];
array[nodeKinds] of int: clusterNodeCPU = [2000,4000,8000];
array[nodeKinds] of float: clusterNodePrice = [0.048, 0.096, 0.192];

% CLUSTER node index
set of int: CLUSTER = 1..maxClusterSize;

array[CLUSTER, appNames] of var bool: runningApps; % apps running on a node
array[CLUSTER] of var nodeKinds: nodes; 

% CONSTRAINTS
% all nodes are of equal size
constraint all_equal(nodes);

% assuming the load, calculate target number of pods
array[appNames] of var int: appInstanceCount;
constraint forall (j in appNames)(
  appInstanceCount[j] = ceil(appConnectionsFact[j]/appConnectionsPerInstance[j])
);

% assuming the load, use calculated number of pods
constraint forall (j in appNames) ( 
  sum(i in CLUSTER) (runningApps[i,j]) = appInstanceCount[j]
);

% supporting constraint to calculate and store RAM consumption
array[CLUSTER] of var int: nodeRAMConsumption;
constraint forall (i in CLUSTER) ( 
  nodeRAMConsumption[i] =   sum(j in appNames) (runningApps[i,j] * appRAM[j])
);

% sum of RAM of all apps on the node >=minNodeRAMConsumption and <= maxNodeRAMConsumption of total node RAM
constraint forall (i in CLUSTER) ( 
  nodeRAMConsumption[i] >= (clusterNodeRAM[nodes[i]] * minNodeRAMConsumption) /\
  nodeRAMConsumption[i] <= (clusterNodeRAM[nodes[i]] * maxNodeRAMConsumption)
);

% supporting constraint to calculate and store CPU consumption
array[CLUSTER] of var int: nodeCPUConsumption;
constraint forall (i in CLUSTER) ( 
  nodeCPUConsumption[i] =   sum(j in appNames) (runningApps[i,j] * appCPU[j])
);

% sum of CPU of all apps on the node >= minNodeCPUConsumption and <= maxNodeCPUConsumption of total node CPU
constraint forall (i in CLUSTER) ( 
  nodeCPUConsumption[i] >= (clusterNodeCPU[nodes[i]] * minNodeCPUConsumption) /\
  nodeCPUConsumption[i] <= (clusterNodeCPU[nodes[i]] * maxNodeCPUConsumption)
);

var float: cost =  (sum(i in nodes)(clusterNodePrice[i])) * 24 * 30 ; % target function to optimize
solve minimize cost;

output [ if j = A then "\(nodes[i]); CPU:\(nodeCPUConsumption[i])/\(clusterNodeCPU[nodes[i]]); RAM:\(nodeRAMConsumption[i])/\(clusterNodeRAM[nodes[i]]), " else "" endif ++ 
         if fix(runningApps[i,j]) = 1 then show(fix(appNames[j])) ++ ";" else "" endif ++ 
         if j = E then "\n" else "" endif
         | i in CLUSTER, j in appNames
];