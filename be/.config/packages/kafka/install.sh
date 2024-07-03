#!/bin/bash

cd $APP_PACKAGES_PATH

echo "[0] Preparing..."

kubectl --kubeconfig=$KUBECONFIG taint nodes --all node-role.kubernetes.io/control-plane-
kubectl --kubeconfig=$KUBECONFIG create namespace messaging

echo "[1] Creating Operator CRDs..."

kubectl --kubeconfig=$KUBECONFIG create -f 'https://strimzi.io/install/latest?namespace=messaging' -n messaging

echo "[2] Deploying Kafka..."

kubectl --kubeconfig=$KUBECONFIG apply -f kafka/kafka-ephemeral-single.yaml -n messaging 

kubectl --kubeconfig=$KUBECONFIG wait kafka/node-01 --for=condition=Ready --timeout=300s -n messaging

liqo=$(kubectl --kubeconfig=$KUBECONFIG get foreignclusters.discovery.liqo.io)

if [ -z "$liqo" ]
then
    exit 0
else    
    liqoctl --kubeconfig=$KUBECONFIG offload namespace messaging --namespace-mapping-strategy EnforceSameName --pod-offloading-strategy Local
fi


echo "[3] Kafka installed..."