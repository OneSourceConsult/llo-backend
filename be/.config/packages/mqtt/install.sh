cd $APP_PACKAGES_PATH


kubectl --kubeconfig=$KUBECONFIG create namespace mqtt


kubectl --kubeconfig=$KUBECONFIG -n mqtt apply -f ./mqtt/resources/