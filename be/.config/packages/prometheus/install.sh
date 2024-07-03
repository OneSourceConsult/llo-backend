#!/bin/bash

cd $APP_PACKAGES_PATH

export SERVICE_NAME=$CLUSTER_NAME
# export INGRESS_URL=$CLUSTER_NAME.monitoring.charity-project.eu

function check_services_ip() {
    ip1=$(kubectl --kubeconfig=$KUBECONFIG -n monitoring get svc $CLUSTER_NAME | awk {'print $4'} | grep -v EXTERNAL-IP)

    if [[ "$ip1" == "<pending>" ]]; then
        echo "A service did not obtain external IP."
        return 1
    else
        echo "Both services have obtained external IP."
        return 0
    fi
}

echo "[1] Installing Prometheus..."

yq eval ".metadata.name = \"$SERVICE_NAME\"" -i ./prometheus/crds/prometheus-service.yaml
# yq eval ".spec.rules[0].host = \"$INGRESS_URL\"" -i ./prometheus/crds/prometheus-ingress.yaml
# yq eval ".spec.rules[0].http.paths[0].backend.service.name = \"$SERVICE_NAME\"" -i ./prometheus/crds/prometheus-ingress.yaml

kubectl --kubeconfig=$KUBECONFIG create namespace monitoring

# LATEST=$(curl -s https://api.github.com/repos/prometheus-operator/prometheus-operator/releases/latest | jq -cr .tag_name)
# curl -sL https://github.com/prometheus-operator/prometheus-operator/releases/download/v0.65.2/bundle.yaml | kubectl -n default create -f -
# kubectl wait --for=condition=Ready pods -l  app.kubernetes.io/name=prometheus-operator -n default

kubectl --kubeconfig=$KUBECONFIG -n monitoring apply -f ./prometheus/crds/
kubectl --kubeconfig=$KUBECONFIG -n monitoring rollout status deployment prometheus-deployment

echo "[2] Restarting MetalLB..."

while ! check_services_ip; do

kubectl --kubeconfig=$KUBECONFIG -n metallb-system rollout restart deployment controller
kubectl --kubeconfig=$KUBECONFIG -n metallb-system rollout status deployment controller
kubectl --kubeconfig=$KUBECONFIG -n metallb-system rollout restart daemonset speaker
kubectl --kubeconfig=$KUBECONFIG -n metallb-system rollout status daemonset speaker

sleep 5
echo "LOOPING"

done

kubectl --kubeconfig=$KUBECONFIG apply -f ./prometheus/kube-state-metrics-configs/