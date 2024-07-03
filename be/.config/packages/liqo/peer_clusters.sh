#!/bin/bash

echo "[0] Connecting GREEN and ROSE cluster..."

liqoctl peer in-band --kubeconfig=$GREENKUBECONFIG --remote-kubeconfig=$ROSEKUBECONFIG --bidirectional

kubectl --kubeconfig=$GREENKUBECONFIG get foreignclusters.discovery.liqo.io 

kubectl --kubeconfig=$ROSEKUBECONFIG get foreignclusters.discovery.liqo.io 

echo "Peering Successful!!"