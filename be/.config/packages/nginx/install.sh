#!/bin/bash
cd $APP_PACKAGES_PATH

# VERSION=v2.2.0

echo "[0] Cloning NGINX repository..."

git clone https://github.com/nginxinc/kubernetes-ingress.git --branch $VERSION
cd kubernetes-ingress/deployments

echo "[1] Installing NGINX..."

kubectl --kubeconfig=$KUBECONFIG apply -f common/ns-and-sa.yaml
kubectl --kubeconfig=$KUBECONFIG apply -f rbac/rbac.yaml
kubectl --kubeconfig=$KUBECONFIG apply -f common/default-server-secret.yaml
kubectl --kubeconfig=$KUBECONFIG apply -f common/nginx-config.yaml
kubectl --kubeconfig=$KUBECONFIG apply -f common/ingress-class.yaml

kubectl --kubeconfig=$KUBECONFIG apply -f common/crds/k8s.nginx.org_virtualservers.yaml
kubectl --kubeconfig=$KUBECONFIG apply -f common/crds/k8s.nginx.org_virtualserverroutes.yaml
kubectl --kubeconfig=$KUBECONFIG apply -f common/crds/k8s.nginx.org_transportservers.yaml
kubectl --kubeconfig=$KUBECONFIG apply -f common/crds/k8s.nginx.org_policies.yaml
kubectl --kubeconfig=$KUBECONFIG apply -f common/crds/k8s.nginx.org_globalconfigurations.yaml

kubectl --kubeconfig=$KUBECONFIG apply -f deployment/nginx-ingress.yaml

sed -i 's/externalTrafficPolicy: Local/externalTrafficPolicy: Cluster/' service/loadbalancer.yaml

kubectl --kubeconfig=$KUBECONFIG apply -f service/loadbalancer.yaml

kubectl --kubeconfig=$KUBECONFIG -n nginx-ingress rollout status deployment nginx-ingress

# DELETE NGINX REPOSITORY
echo "[1.5] Deleting NGINX Repository..."

cd ../..
rm -rf kubernetes-ingress

echo "[2] MetalLB IPPool Annotation..."

kubectl --kubeconfig=$KUBECONFIG -n nginx-ingress annotate svc nginx-ingress metallb.universe.tf/allow-shared-ip=liqo-shared
kubectl --kubeconfig=$KUBECONFIG -n nginx-ingress annotate svc nginx-ingress metallb.universe.tf/address-pool=public-pool

echo "[3] Editing NGINX Configmap..."
# EDIT CONFIGMAP
    # GET ORIGINAL CONFIGMAP
    original_nginx_cm=$(kubectl --kubeconfig=$KUBECONFIG -n nginx-ingress get cm nginx-config -o yaml)

    # ADD HEADERS
    new_yaml=$(echo "$original_nginx_cm" | yq eval  '.data.add-header = "X-Forwarded-Proto https;"' -)
    new_yaml=$(echo "$new_yaml" | yq eval  '.data.use-forwarded-headers = "true"' -)
    new_yaml=$(echo "$new_yaml" | yq eval  '.data.client-max-body-size = "3000m"' -)

    # APPLY NEW YAML
    echo "$new_yaml" | kubectl --kubeconfig=$KUBECONFIG apply -f -

echo "[4] Editing NGINX Deployment..."

# EDIT DEPLOYMENT GLOBAL CONFIG
    original_nginx_deployment=$(kubectl --kubeconfig=$KUBECONFIG -n nginx-ingress get deployments.apps nginx-ingress -o yaml)

    new_yaml=$(echo "$original_nginx_deployment" | yq eval '.spec.template.spec.containers[0].args += ["-global-configuration=$(POD_NAMESPACE)/nginx-configuration"]' -)

    echo "$new_yaml" | kubectl --kubeconfig=$KUBECONFIG apply -f -

    # ROLLOUT RESTART

    kubectl --kubeconfig=$KUBECONFIG -n nginx-ingress rollout restart deployment nginx-ingress
    kubectl --kubeconfig=$KUBECONFIG -n nginx-ingress rollout status deployment nginx-ingress

echo "[5] Editing CoreDNS Configmap..."

# EDIT COREDNS
    original_coredns_cm=$(kubectl -n kube-system get cm coredns -o yaml)

    new_yaml=$(echo "$original_coredns_cm" | yq eval '.data.Corefile |= sub("ready"; "ready\n    rewrite stop {\n      name regex (.*)\.(.*)\.charity-project\.eu\.$ {1}.{2}.svc.cluster.local\n      answer name (.*)\.(.*)\.svc\.cluster\.local\.$ {1}.{2}.charity-project.eu\n    }")' -)

    echo "$new_yaml" | kubectl --kubeconfig=$KUBECONFIG apply -f -

    # ROLLOUT RESTART
    kubectl --kubeconfig=$KUBECONFIG -n kube-system rollout restart deployment coredns
    kubectl --kubeconfig=$KUBECONFIG -n kube-system rollout status deployment coredns

echo "[6] Everything installed!"