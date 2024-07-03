


import logging
import subprocess
import tempfile
from time import sleep
import kubernetes
from app.controllers.clusters.capi import getClusterList, getClusterListFromCAPI, getKubeconfigFromClusterctl

log = logging.getLogger("app")

def labelClusterForLiqo(clusterName):
  kubeconfig = getKubeconfigFromClusterctl(clusterName) 

  tmp_kube = tempfile.NamedTemporaryFile(mode="w+")
  
  try:
    tmp_kube.write(kubeconfig)
    tmp_kube.seek(0)

    cmd = (
        "kubectl --kubeconfig="
        + tmp_kube.name
        + " get nodes | grep control-plane | awk {'print $1'}"
    )

    control_plane_nodes = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True, text=True).stdout.strip()

    log.info("RESULT: " + control_plane_nodes)

    cmd = (
        "kubectl --kubeconfig="
        + tmp_kube.name
        + " label nodes "
        + str(control_plane_nodes)
        + " topology.liqo.io/name="
        + clusterName
    )

    result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
  
  finally:
      tmp_kube.close()


def peerClusters(greenClusterName, roseClusterName, **kwargs):

    task = kwargs.get("task")
    task.status = "executing"

    greenKubeconfig = getKubeconfigFromClusterctl(greenClusterName)
    roseKubeconfig = getKubeconfigFromClusterctl(roseClusterName)

    tmp_green = tempfile.NamedTemporaryFile(mode="w+")
    tmp_rose = tempfile.NamedTemporaryFile(mode="w+")

    while True:
        if checkLiqo(greenClusterName) and checkLiqo(roseClusterName):
            break
        sleep(10)

    try:
        tmp_green.write(greenKubeconfig)
        tmp_green.seek(0)
        tmp_rose.write(roseKubeconfig)
        tmp_rose.seek(0)

        log.info("Peering " + greenClusterName + " and " + roseClusterName + "..." )

        cmd = (
            "liqoctl peer in-band --kubeconfig="
            + tmp_green.name
            + " --remote-kubeconfig="
            + tmp_rose.name
            + " --bidirectional"
        )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        log.debug(result.stdout)
        log.debug(result.stderr)
    finally:
        log.info("Clusters peered successfully!!!")
        task.status = "completed"
        tmp_green.close()
        tmp_rose.close()




def unpeerClusters(greenClusterName, roseClusterName, **kwargs):

    

    greenKubeconfig = getKubeconfigFromClusterctl(greenClusterName)
    roseKubeconfig = getKubeconfigFromClusterctl(roseClusterName)

    tmp_green = tempfile.NamedTemporaryFile(mode="w+")
    tmp_rose = tempfile.NamedTemporaryFile(mode="w+")

    while True:
        if checkLiqo(greenClusterName) and checkLiqo(roseClusterName):
            break
        sleep(10)

    try:
        tmp_green.write(greenKubeconfig)
        tmp_green.seek(0)
        tmp_rose.write(roseKubeconfig)
        tmp_rose.seek(0)

        log.info("Unpeering " + greenClusterName + " and " + roseClusterName + "..." )

        cmd = (
            "liqoctl unpeer in-band --kubeconfig="
            + tmp_green.name
            + " --remote-kubeconfig="
            + tmp_rose.name
        )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        log.debug(result.stdout)
        log.debug(result.stderr)
    finally:
        log.info("Clusters unpeered successfully!!!")
        tmp_green.close()
        tmp_rose.close()

def checkLiqo(clusterName):

    clusterList = getClusterList()
    ctl = 0
    log.info("Checking if cluster exists...")
    for cluster in clusterList:
        if cluster["name"] == clusterName:
            ctl = 1
            break

    if ctl == 1:
        liqoDeploymentList = [
            "liqo-auth",
            "liqo-controller-manager",
            "liqo-gateway",
            "liqo-metric-agent",
            "liqo-network-manager",
            "liqo-proxy",
            "liqo-route",
            "liqo-crd-replicator"
        ]

        kubeconfig = getKubeconfigFromClusterctl(clusterName)

        tmp = tempfile.NamedTemporaryFile(mode="w+")

        try:
            tmp.write(kubeconfig)
            tmp.seek(0)

            kubernetes.config.load_kube_config(tmp.name)
            api = kubernetes.client.AppsV1Api()

            namespaceList = api.list_namespace()

            # check if namespace exists
            # check if each deployment exists
            # check if each deployment is ready

            log.info("Checking liqo namespace...")
            if "liqo" not in [ns.metadata.name for ns in namespaceList.items]:
                log.info("Liqo Namespace does not exist!")
                return False
            else:
                log.info("Checking liqo components...")
                deploymentList = api.list_namespaced_deployment("liqo")
                i = 0
                readyCount = 0
                while(i < len(deploymentList)):
                    deployment = deploymentList[i]
                    if deployment.metadata.name in liqoDeploymentList:
                        if int(deployment.status.availableReplicas) >= 1:
                            log.info(f"Deployment: {deployment.metadata.name} --> AvailableReplicas: {deployment.status.availableReplicas}")
                            readyCount +=1
                    i += 1
                
                if readyCount == len(deploymentList):
                    return True
                return False
        finally:
            tmp.close()
            return True
