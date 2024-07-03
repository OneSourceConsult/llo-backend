#!/bin/bash

ENDPOINT=http://orch-backend.orchestration.charity-project.eu

clusterData='{
  "provider": "kubeadm",
  "name": "blue",
  "kubernetes-version": "v1.25.0",
  "control-plane-count": 1,
  "control-plane-flavor": "m1.medium",
  "worker-machine-count": 0,
  "worker-machine-flavor": "m1.medium",
  "image": "ubuntu-2004-kube-v1.25"
}'

clusterName='{
  "clusterName": "blue"
}'

appName="httpbin"

appData='{
    "name": "httpbin",
    "owner": "charity-developer",
    "cluster": "kubeadm-based-orchestration-blue",
    "components": [
      {
        "name": "httpbin",
        "cluster-selector": "kubeadm-based-orchestration-blue",
        "image": "docker.io/kong/httpbin",
        "expose": [
          {
            "is-public": true,
            "is-peered": true,
            "containerPort": 80,
            "clusterPort": 8000
          }
        ]
      }
    ]
  }'


#------------DEPLOY-CLUSTER-----------
curl -X POST "$ENDPOINT/v1/createclusterCRD" -H 'Content-Type: application/json' -d "$clusterData"
sleep 300
#------------INSTALL-HTTPBIN-----------

# ENDPOINT/v1/installapp
# SEND APPDATA

curl -X POST "$ENDPOINT/v1/installappCRD" -H 'Content-Type: application/json' -d "$appData"
sleep 300

#------------DELETE-HTTPBIN-----------

# ENDPOINT/v1/uninstallapp
# SEND APPNAME

curl -X DELETE $ENDPOINT/v1/app/{$appName} -H 'Content-Type: application/json'
sleep 100

#------------DELETE-CLUSTER-----------
curl -X DELETE $ENDPOINT/v1/deleteclusterCRD -H 'Content-Type: application/json' -d "$clusterName"
sleep 100
