#!/bin/bash

cd $APP_PACKAGES_PATH

function check_services_ip() {
    ip1=$(kubectl --kubeconfig=$KUBECONFIG -n liqo get svc liqo-gateway | awk {'print $4'} | grep -v EXTERNAL-IP)
    ip2=$(kubectl --kubeconfig=$KUBECONFIG -n liqo get svc liqo-gateway-metrics | awk {'print $4'} | grep -v EXTERNAL-IP)

    if [[ "$ip1" == "<pending>" || "$ip2" == "<pending>" ]]; then
        echo "A service did not obtain external IP."
        return 1
    else
        echo "Both services have obtained external IP."
        return 0
    fi
}

# GREEN CLUSTER ---------------------------------------------------------------------

echo "[0] Installing Liqo CLI..."

curl --fail -LS "https://github.com/liqotech/liqo/releases/download/$VERSION/liqoctl-linux-amd64.tar.gz" | tar -xz
install -o root -g root -m 0755 liqoctl /usr/local/bin/liqoctl

echo "[1] Installing Liqo..."

# LABEL OWN NODES
control_plane_nodes=$(kubectl --kubeconfig=$KUBECONFIG get nodes | grep control-plane | awk {'print $1'})
kubectl --kubeconfig=$KUBECONFIG label nodes $control_plane_nodes topology.liqo.io/name=$LIQO_CLUSTER_NAME

METRICS_PORT=5872

liqoctl install kubeadm --kubeconfig=$KUBECONFIG --version $VERSION --cluster-name $LIQO_CLUSTER_NAME --cluster-labels "topology.liqo.io/name=$LIQO_CLUSTER_NAME" --set auth.service.type="ClusterIP" --set auth.ingress.enable=true --set auth.config.addressOverride="liqo-auth.liqo.charity-project.eu" --set gateway.metrics.enabled=true --set gateway.metrics.port=$METRICS_PORT --set virtualKubelet.metrics.enabled=true --set virtualKubelet.metrics.port=5873
# --set gateway.metrics.enabled=true --set gateway.metrics.port=$METRICS_PORT --set virtualKubelet.metrics.enabled=true --set virtualKubelet.metrics.port=5873
# --set auth.service.type="ClusterIP" --set auth.ingress.enable=true --set auth.config.addressOverride="liqo-auth.liqo.charity-project.eu" 
# --set auth.service.annotations={'nginx.org/redirect-to-https':'true','nginx.org/ssl-services':'liqo-auth'}
# --set auth.tls=false
# --set auth.ingress.annotations.nginx.org/redirect-to-https: 'true' --set auth.ingress.annotations.nginx.org/ssl-services: 'liqo-auth'

echo "[1.5] Exposing Gateway Metrics Service..."

original_gw_metrics=$(kubectl --kubeconfig=$KUBECONFIG -n liqo get svc liqo-gateway-metrics -o yaml)
new_gw_metrics=$(echo "$original_gw_metrics" | yq eval '.spec.type = "LoadBalancer"' -)
echo "$new_gw_metrics" | kubectl --kubeconfig=$KUBECONFIG apply -f -

echo "[2] Fix shared-IP for liqo-auth and liqo-gateway services..."

# kubectl --kubeconfig=$KUBECONFIG -n liqo annotate svc liqo-auth metallb.universe.tf/allow-shared-ip=liqo-shared
kubectl --kubeconfig=$KUBECONFIG -n liqo annotate svc liqo-gateway metallb.universe.tf/allow-shared-ip=liqo-shared
kubectl --kubeconfig=$KUBECONFIG -n liqo annotate svc liqo-gateway-metrics metallb.universe.tf/allow-shared-ip=liqo-shared

if [[ $PROVIDER == "external" ]]; then
    kubectl --kubeconfig=$KUBECONFIG -n liqo annotate svc liqo-gateway-metrics metallb.universe.tf/address-pool=public-pool
    # kubectl --kubeconfig=$KUBECONFIG -n liqo annotate svc liqo-auth metallb.universe.tf/address-pool=liqo-pool
    kubectl --kubeconfig=$KUBECONFIG -n liqo annotate svc liqo-gateway metallb.universe.tf/address-pool=public-pool

else
    kubectl --kubeconfig=$KUBECONFIG -n liqo annotate svc liqo-gateway-metrics metallb.universe.tf/address-pool=liqo-pool
    # kubectl --kubeconfig=$KUBECONFIG -n liqo annotate svc liqo-auth metallb.universe.tf/address-pool=liqo-pool
    kubectl --kubeconfig=$KUBECONFIG -n liqo annotate svc liqo-gateway metallb.universe.tf/address-pool=liqo-pool

fi

echo "[3] Restarting MetalLB..."


while ! check_services_ip; do

kubectl --kubeconfig=$KUBECONFIG -n metallb-system rollout restart deployment controller
kubectl --kubeconfig=$KUBECONFIG -n metallb-system rollout status deployment controller
kubectl --kubeconfig=$KUBECONFIG -n metallb-system rollout restart daemonset speaker
kubectl --kubeconfig=$KUBECONFIG -n metallb-system rollout status daemonset speaker

sleep 5
echo "LOOPING"
done

echo "[4] Adding Targets to Prometheus..."

# GET THE IP
# OR MAYBE EXPOSE VIA INGRESS (MAKES NGINX A REQUIREMENT)
GW_METRICS_IP=$(kubectl --kubeconfig=$KUBECONFIG get svc -n liqo liqo-gateway-metrics -o yaml | yq '.status.loadBalancer.ingress[0].ip')

original_prometheus_cm=$(kubectl --kubeconfig=$CAPI_KUBECONFIG -n monitoring get cm prometheus-server-conf -o yaml)
job_list=$(echo "$original_prometheus_cm" | yq '.data."prometheus.yml"' | yq '.scrape_configs')
# prometheus_target=$(kubectl --kubeconfig=$KUBECONFIG -n default get ingress ingress-prometheus-monitoring | awk {'print $3'} | grep -v HOSTS)

ctl=0

for job in $(echo "$job_list" | yq -r '.[].job_name'); do
    if [[ "$job" == "$LIQO_CLUSTER_NAME-liqo-metrics" ]]; then
        echo "FOUND EQUAL JOB"
        target=$(echo "$original_prometheus_cm" | yq '.data."prometheus.yml"' | yq '.scrape_configs.[] | select(.job_name == "'$job'")' | yq '.static_configs[0].targets[0]')
        echo "$original_prometheus_cm" | sed "s/$target/$GW_METRICS_IP:$METRICS_PORT/g"
        ctl=0
        break
    else
        ctl=1
    fi
done

if [[ $ctl == 1 ]]
then
    echo "CREATING A NEW JOB"
    new_prometheus_cm=$(echo "$original_prometheus_cm" | yq eval '.data."prometheus.yml" |= (sub("scrape_configs:\\n", "scrape_configs:\n  - job_name: '"$LIQO_CLUSTER_NAME-liqo-metrics"'\n    static_configs:\n      - targets: ['"$GW_METRICS_IP:$METRICS_PORT"']\n"))' -)
fi

echo "$new_prometheus_cm" | kubectl --kubeconfig=$CAPI_KUBECONFIG -n monitoring apply -f -
kubectl --kubeconfig=$CAPI_KUBECONFIG -n monitoring rollout restart deployment prometheus-deployment
kubectl --kubeconfig=$CAPI_KUBECONFIG -n monitoring rollout status deployment prometheus-deployment