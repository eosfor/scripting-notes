enum existingVMs;
enum vmSizes;
enum vmDisks;
int: totalAcuMax;

array[existingVMs] of int: vmCPU;
array[existingVMs] of int: vmRAM;
array[existingVMs] of int: vmDisk;
array[existingVMs] of int: vmCpuToRamRatio;


array[vmSizes] of int: vmSizeCPU;
array[vmSizes] of int: vmSizeRAM;
array[vmSizes] of int: vmSizePrice;
array[vmSizes] of int: vmSizeACU;
array[vmSizes] of int: vmSizeCpuToRamRatio;

array[vmDisks] of int: vmDiskSizes;
% array[vmDisks] of int: vmDiskPrice;

array[existingVMs] of var vmSizes: selectedSize;
array[existingVMs] of var vmDisks: selectedDiskSize;


constraint forall(vm in existingVMs)(
    vmSizeRAM[selectedSize[vm]] >= vmRAM[vm] /\
    vmSizeRAM[selectedSize[vm]] < vmRAM[vm] * 4
);


constraint forall(vm in existingVMs)(
    vmSizeCPU[selectedSize[vm]] >=  vmCPU[vm] /\
    vmSizeCPU[selectedSize[vm]] <=  vmCPU[vm] * 4
);


var int: totalPrice = sum(vm in existingVMs)(vmSizePrice[selectedSize[vm]]);
var int: totalACU = sum(vm in existingVMs)( vmSizeACU[selectedSize[vm]] );

% constraint totalPrice <= 7478400;
constraint totalACU >= totalAcuMax;
% solve  maximize totalACU;
solve  minimize totalPrice;

output [ "{\n" ++ 
            "\"totalPrice\" :  \(totalPrice / 10000),\n" ++ 
            "\"totalACU\": \(totalACU),\n" ++
            "\"vmRecords\":" ++
            "[" ++
            join(", \n", [ "{" ++
                                "\"sourceVMName\": \"\(vm)\",\n" ++ 
                                "\"sourceVMCPU\": \(vmCPU[vm]),\n" ++
                                "\"sourceVMRAM\": \(vmRAM[vm] / 100),\n" ++
                                "\"sourceVMDisk\": \(vmDisk[vm]),\n" ++
                                "\"selectedSize\": \"\(selectedSize[vm])\",\n" ++
                                "\"targetVMCPU\": \(vmSizeCPU[selectedSize[vm]]),\n" ++
                                "\"targetVMRAM\": \(vmSizeRAM[selectedSize[vm]] / 100),\n" ++
                                "\"targetVMDisk\": \(vmDiskSizes[selectedDiskSize[vm]]),\n" ++
                                "\"targetVMPrice\": \(vmSizePrice[selectedSize[vm]] / 10000),\n" ++
                                "\"targetVMACU\": \(vmSizeACU[selectedSize[vm]])\n" ++
                        "   }" | vm in  existingVMs ]) ++
            "]" ++
            "}"
        ]