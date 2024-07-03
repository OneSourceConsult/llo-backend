#!/bin/bash

source $CAPO_ENVRC_PATH $CAPO_CLOUDS_PATH openstack && \
export $(cat $CAPO_ENV_PATH | grep -v "^#" | xargs)  && \
clusterctl generate cluster $CAPO_CLUSTER_NAME \
    --flavor without-lb \
    --kubernetes-version $CAPO_KUBERNETES_VERSION \
    --control-plane-machine-count=$CAPO_CONTROL_PLANE_MACHINE_COUNT \
    --worker-machine-count=$CAPO_WORKER_MACHINE_COUNT \
    --infrastructure openstack
