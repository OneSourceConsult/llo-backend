#!/bin/bash

cd $APP_PACKAGES_PATH

echo "[0] Preparing..."

kubectl --kubeconfig=$KUBECONFIG taint nodes --all node-role.kubernetes.io/control-plane-
kubectl --kubeconfig=$KUBECONFIG apply -f https://raw.githubusercontent.com/metallb/metallb/v0.13.7/config/manifests/metallb-native.yaml

echo "[1] Installing MetalLB..."

kubectl --kubeconfig=$KUBECONFIG -n metallb-system rollout status deployment controller
kubectl --kubeconfig=$KUBECONFIG -n metallb-system rollout status daemonset speaker

echo "[2] Defining MetalLB IPPools..."
kubectl --kubeconfig=$KUBECONFIG apply -f metallb/metallbconfig.yaml