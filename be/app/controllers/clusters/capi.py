import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import kubernetes
import yaml
import base64
from subprocess import PIPE, run
from time import sleep
from typing import Dict, Optional
from uuid import UUID
import threading
from jinja2 import Environment, FileSystemLoader
from kubernetes.client.exceptions import ApiException
import requests
from fastapi import HTTPException

from app.utils.common import update_CRD_Status
from timeout_decorator import timeout

from app.schemas.Cluster import Cluster, ClusterRequest
from app.schemas.ClusterCRD import CAPOK3sCRD, CAPOKubeadmCRD, ClusterCRD
from app.schemas.Package import BashScript, Package
from app.schemas.Provider import Provider
from app.controllers.common import timeit
from app.controllers.providers.openstack import (
    associateFloatingIP,
    getOpenstackMachineName,
)



# ------------------ METRICS IMPORT ------------------
# from .monitoring import num_clusters, num_apps, num_providers, num_components

# ------------------ METRICS IMPORT ------------------

log = logging.getLogger("app")

def getControlPlaneIP(name):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
    api = kubernetes.client.CustomObjectsApi()
    cluster = api.get_namespaced_custom_object(
        group="cluster.x-k8s.io", version="v1beta1", plural="clusters", namespace="default", name=name
    )

    ip = cluster["spec"]["controlPlaneEndpoint"]["host"]
    
    return ip

def getVirtualMachineIP(name):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
    api = kubernetes.client.CustomObjectsApi()

    machineDeployments = api.list_namespaced_custom_object(
        group="infrastructure.cluster.x-k8s.io", version="v1alpha6", plural="openstackmachines", namespace="default"
    )


    cp_name = name + "-control-plane"

    for machine in machineDeployments["items"]:
        if machine["metadata"]["labels"]["cluster.x-k8s.io/control-plane-name"] == cp_name:
            for address in machine["status"]["addresses"]:
                if address["type"] == "InternalIP":
                   return address["address"]
    return

def getClusterListFromCAPI():
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
    api = kubernetes.client.CustomObjectsApi()
    clusters = api.list_cluster_custom_object(
        group="cluster.x-k8s.io", version="v1beta1", plural="clusters"
    )
    
    return clusters

def getMachineDeployment(name):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
    api = kubernetes.client.CustomObjectsApi()
    machineDeployments = api.get_namespaced_custom_object(
        group="cluster.x-k8s.io", version="v1beta1", plural="machinedeployments", namespace="default", name=name
    )

    return machineDeployments

def getControlPlane(name):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
    api = kubernetes.client.CustomObjectsApi()
    controlPlanes = api.get_namespaced_custom_object(
        group="controlplane.cluster.x-k8s.io", version="v1beta1", plural="kubeadmcontrolplanes", namespace="default", name=name
    )

    return controlPlanes




def addPublicIPToMetalLB(pkg: BashScript, clusterName, provider):
    kubeconfig = getKubeconfigFromClusterctl(clusterName)
    
    if provider == "external":
        publicIP = liqoIP = re.findall(".*https://(.*):6443.*", kubeconfig)[0]
    elif provider == "openstack":
        liqoIP = getControlPlaneIP(clusterName)
        publicIP = getVirtualMachineIP(clusterName)
    
    # get MetalLB config path
    originalPath = pkg.installScriptPath
    originalPath = '/'.join(originalPath.split('/')[:-1])
    config_name = 'public-pool.yaml'
    config_liqo = 'liqo-pool.yaml'
    filePath = os.environ["APP_PACKAGES_PATH"] + originalPath + "/" + config_name   
    filePath2 = os.environ["APP_PACKAGES_PATH"] + originalPath + "/" + config_liqo

    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")
    tmp_metallb = tempfile.NamedTemporaryFile(mode="w+")
    tmp_liqo = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        # check if public-pool exists
        cmd = (
                "kubectl --kubeconfig="
                + tmp_kube.name
                + " get ipaddresspools.metallb.io "
                + " -n metallb-system "
                + "| grep public-pool"
        )

        p = subprocess.Popen(
            cmd,
            shell=True,
            executable="/bin/bash",
            universal_newlines=True,
            stdout=PIPE,
            stderr=PIPE,
        )
    
        stdout, err = p.communicate()

        if str(stdout) == "":
            log.info("Creating the public IP Pool...")
            # add the publicIP to the address pool in tmp file for concurrency
            with open(filePath, 'r') as original_file:
                original_config = yaml.safe_load(original_file)
                
                #log.info(original_config)
                
                if original_config["kind"] == "IPAddressPool" and original_config["metadata"]["name"] == "public-pool":
                # Update the addresses field
                    original_config["spec"]["addresses"] = [
                        publicIP + "/32"
                    ]
                
                #tmp_metallb.write(filePath)
            
                yaml.dump(original_config, tmp_metallb)
                tmp_metallb.seek(0)
                
                # move file to metallb folder
                #shutil.move(tmp.name, originalPath)
                
                log.info("Adding Public IP Pool...")

                cmd = (
                    "kubectl --kubeconfig="
                    + tmp_kube.name
                    + " apply -f "
                    + tmp_metallb.name
                )

                result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)

            cmd = (
                "kubectl --kubeconfig="
                + tmp_kube.name
                + " get ipaddresspools.metallb.io "
                + " -n metallb-system "
                + "| grep liqo-pool"
            )

            p = subprocess.Popen(
                cmd,
                shell=True,
                executable="/bin/bash",
                universal_newlines=True,
                stdout=PIPE,
                stderr=PIPE,
            )
    
            stdout, err = p.communicate()

            if str(stdout) == "":

                with open(filePath2, 'r') as original_file:
                    original_config = yaml.safe_load(original_file)
                    
                    if original_config["kind"] == "IPAddressPool" and original_config["metadata"]["name"] == "liqo-pool":
                    # Update the addresses field
                        original_config["spec"]["addresses"] = [
                            liqoIP + "/32"
                        ]
                
                    yaml.dump(original_config, tmp_liqo)
                    tmp_liqo.seek(0)
                    
                    log.info("Adding Public IP Pool...")

                    cmd = (
                        "kubectl --kubeconfig="
                        + tmp_kube.name
                        + " apply -f "
                        + tmp_liqo.name
                    )

                    result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)

            #log.info(result.stdout)
            #log.info(result.stderr)
            rollout_restart_controller = (
                "kubectl --kubeconfig="
                + tmp_kube.name
                + " -n metallb-system rollout restart deployment controller"
            )

            result = subprocess.run(rollout_restart_controller, stdout=subprocess.PIPE, shell=True)

            rollout_restart_speaker = (
                "kubectl --kubeconfig="
                + tmp_kube.name
                + " -n metallb-system rollout restart daemonset speaker"
            )

            result = subprocess.run(rollout_restart_speaker, stdout=subprocess.PIPE, shell=True)
    finally:
        log.info("Public IP Pool added successfully!!!")
        tmp_metallb.close()
        tmp_liqo.close()
        tmp_kube.close()


def addClusterToCRD(cluster_data):
    
    from app.controllers.providers.common import checkDatacenterProvider   
    from app.controllers.providers.external import external_dc_get_conf, external_install_cluster


    current_clusters = getClusterList()
    cluster_names = [cluster["name"] for cluster in current_clusters] 
    if cluster_data["name"] in cluster_names:
        raise HTTPException(status_code=400, detail=f"Cluster named {cluster_data['name']} already exists")
    
    provider = checkDatacenterProvider(cluster_data["datacenter"])  
    
    if provider == "external":
   
        machine = external_dc_get_conf(cluster_data["datacenter"])
        log.info(machine)
        if machine == None:
            raise HTTPException(status_code=400, detail="No machine Available to schedule the cluster") 
    if provider == None:
        raise HTTPException(status_code=404, detail ="Datacenter Not Found")
    elif provider == "openstack":
        if len(getClusterList()) >= 3:
            raise HTTPException(status_code=400, detail="Can't Create more cluster in this datacenter")


    
    log.info("Updating Cluster CRD")
    cluster_crd = {}
    cluster_crd["datacenter"] = cluster_data["datacenter"]   
    cluster_crd["name"] = cluster_data["name"]
    cluster_crd["status"] = "pending"
    cluster_crd["image"] = cluster_data.get("image", "ubuntu-2204-kube-v1.28.0")
    cluster_crd["provider"] =  provider
    cluster_crd["kubernetes-type"] = cluster_data.get("kubernetesType", "kubeadm")
    cluster_crd["kubernetes-version"] = cluster_data.get("kubernetesVersion", "v1.28.0")
    cluster_crd["control-plane-count"] = cluster_data["control"]["units"]
    cluster_crd["control-plane-flavor"] = cluster_data["control"]["flavor"]
    cluster_crd["worker-machine-count"] =  cluster_data["workers"]["units"]
    cluster_crd["worker-machine-flavor"] = cluster_data["workers"]["flavor"]
    
    
    
    
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    api_client = kubernetes.client.ApiClient()

    try:
        api_instance = kubernetes.client.CustomObjectsApi(api_client)
        orchestration_custom_resource = api_instance.get_namespaced_custom_object(
            group= "charity-project.eu",
            version="v1",
            namespace="default",
            plural="lowlevelorchestrations",
            name="kubeadm-based-orchestration"
        )

        ctl = 0

        if "clusters" in orchestration_custom_resource["spec"]:
            for clusters in orchestration_custom_resource["spec"]["clusters"]:
                if cluster_crd["name"] == clusters["name"]:
                    ctl = 1
                    break
            if ctl == 0:
                orchestration_custom_resource["spec"]["clusters"].append(cluster_crd)
        else:
            orchestration_custom_resource["spec"]["clusters"] = []
            orchestration_custom_resource["spec"]["clusters"].append(cluster_crd)

        api_instance.patch_namespaced_custom_object(
            group= "charity-project.eu",
            version="v1",
            namespace="default",
            plural="lowlevelorchestrations",
            name="kubeadm-based-orchestration",
            body=orchestration_custom_resource
        )
        
    except ApiException as e:
        if e.reason == "Not Found":
            orchestration_custom_resource = {
                    "apiVersion": "charity-project.eu/v1",
                    "kind": "LowLevelOrchestration",
                    "metadata": {
                        "name": "kubeadm-based-orchestration"
                            },
                    "spec": {}   
                    }

            orchestration_custom_resource["spec"]["clusters"] = []
            orchestration_custom_resource["spec"]["clusters"].append(cluster_crd)
            
            
            api_instance.create_namespaced_custom_object(
                    group= "charity-project.eu",
                    version="v1",
                    namespace="default",
                    plural="lowlevelorchestrations",
                    body=orchestration_custom_resource
                )
        else:
            log.info("An error occurred:", e)

    return {"status" : "pending", "name": cluster_crd["name"]}



def getClusterService(cluster_name, namespace, service_name):
    tmp = tempfile.NamedTemporaryFile(mode="w+")
    
    kubeconfig = getKubeconfigFromClusterctl(cluster_name)
    
    tmp.write(kubeconfig)
    tmp.seek(0)
    kubernetes.config.load_kube_config(tmp)
    # Create Kubernetes API client
    try:
        api_client = kubernetes.client.CoreV1Api()
        api_response = api_client.read_namespaced_service(
            namespace=namespace,
            name=service_name
        )
        
        return api_response
    
    except ApiException as e:
        if e.reason == "Not Found":
            return {}
        else:
            raise ApiException
    

def getClusterByName(name):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    orchestration_custom_resource = api_instance.get_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        name="kubeadm-based-orchestration"
    )
    
    cluster_data = {}
    
    if "clusters" in orchestration_custom_resource["spec"]:
        for cluster in orchestration_custom_resource["spec"]["clusters"]:
            if name == cluster["name"]:
                if cluster.get("status","") != "running":
            
                    cluster_data["monitoringIp"] = "Cluster Not Ready"
                else:
                    
                    cluster_monitoring_service = getClusterService(cluster["name"], "monitoring",  cluster["name"])
                    
                    if cluster_monitoring_service == {}:
                        cluster_data["monitoringIp"] = "Monitoring Not Ready"
                    else:
                        if cluster["provider"] == "external":
                            cluster_data["monitoringIp"] = cluster_monitoring_service.status.load_balancer.ingress[0].ip + ":9090" 
                        else:
                            cluster_capi_cr = api_instance.get_namespaced_custom_object(
                                group = "cluster.x-k8s.io",
                                version = "v1beta1",
                                namespace = "default",
                                plural = "clusters",
                                name = cluster.get("name")
                            )
                    
                            cluster_data["monitoringIp"] = cluster_capi_cr.get("spec",{}).get("controlPlaneEndpoint", {}).get("host","") + ":" + "9090"

            
                cluster_data["status"] = cluster["status"]
                cluster_data["datacenter"] = cluster["datacenter"]
                cluster_data["name"] = cluster["name"]
                cluster_data["image"] = cluster["image"]
                cluster_data["kubernetesType"] = cluster["kubernetes-type"]
                cluster_data["provider"] = cluster["provider"]
                cluster_data["kubernetesVersion"] = cluster["kubernetes-version"]
                cluster_data["control"] = {} 
                cluster_data["workers"] = {}
                cluster_data["control"]["units"] = cluster["control-plane-count"]
                cluster_data["control"]["flavor"] = cluster["control-plane-flavor"]
                cluster_data["workers"]["units"] = cluster["worker-machine-count"]
                cluster_data["workers"]["flavor"] = cluster["worker-machine-flavor"]

                return cluster_data

    return {"Error": "Cluster Not Found"}

def getClusterListFromCRD():
    
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    orchestration_custom_resource = api_instance.get_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        name="kubeadm-based-orchestration"
    )

    clusters_list = []
    
    if "clusters" in orchestration_custom_resource["spec"]:
        for cluster in orchestration_custom_resource["spec"]["clusters"]:

            clusters_list.append(getClusterByNameFromCRD(cluster.get("name", "")))


    return clusters_list

def getClusterList():
    
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    orchestration_custom_resource = api_instance.get_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        name="kubeadm-based-orchestration"
    )

    clusters_list = []
    
    if "clusters" in orchestration_custom_resource["spec"]:
        for cluster in orchestration_custom_resource["spec"]["clusters"]:

            clusters_list.append(getClusterByName(cluster.get("name", "")))


    return clusters_list
    

def delete_cluster_from_CRD(clusterName):
    from app.controllers.clusters.liqo import unpeerClusters

    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])


    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    orchestration_custom_resource = api_instance.get_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        name="kubeadm-based-orchestration"
    )


    if "links" in orchestration_custom_resource["spec"]:
        for link in orchestration_custom_resource["spec"]["links"]:
            log.info(clusterName + "  --->  " + str(link))
            if clusterName in link:
                
                unpeerClusters(link[0], link[1])
                orchestration_custom_resource["spec"]["links"].remove(link)

    

    if "clusters" in orchestration_custom_resource["spec"]:
        for cluster in orchestration_custom_resource["spec"]["clusters"]:
            if cluster["name"] == clusterName:
                orchestration_custom_resource["spec"]["clusters"].remove(cluster)

    api_instance.patch_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        name="kubeadm-based-orchestration",
        body=orchestration_custom_resource
    )

    return "Cluster Successfully Deallocated"

# creates a cluster object by name and
# schedule the creation on specified provider

@timeit
def createAndScheduleCluster(req: ClusterRequest, provider, **kwargs):
    # pid = os.fork()
    # if pid == 0:
    from app.controllers.providers.external import external_install_cluster, external_dc_get_conf, get_kubeconfig_ssh, store_kubeconfig, update_dc_configuration


    task = kwargs.get("task")
    task.status = "executing"

    # populate new obj instance
    newCluster = Cluster(type=req.kubernetesType)
    clusterName = newCluster.name = req.clusterName
    newCluster.controlPlaneCount = req.controlPlaneCount
    newCluster.workerMachineCount = req.workerMachineCount
    
    log.info(f"Creating cluster: {clusterName}")
    log.info(f"Creating cluster: {provider}")

    newCluster.status = "creating"
    
    if provider.type == "openstack":
        
        crd = getClusterManifest(req, provider)

        # embed uuid into metadata field
        crd = crd.setUUI(newCluster.uuid)

        newCluster.yaml = clusterManifest = str(crd.value)
        # log.info(f"Applying cluster manifest\n{clusterManifest}")
        log.info(f"Applying cluster manifest")
        applyCAPIClusterManifest(clusterManifest)


        log.info("Retrieving kubeconfig")
        newCluster.kubeconfig = getKubeconfigFromClusterctl(clusterName)

        # grep API Server IP in kubeconfig
        fip = re.findall(".*https://(.*):6443.*", newCluster.kubeconfig)[0]

        # CAPI / OPENSTACK is failing to associate IP
        # so we do it using OpenStack API
        # first get the correct openstack instance name
        openStackMachineName = getOpenstackMachineName(clusterName)
        # then perform the association
        newCluster.controlPlaneIP = associateFloatingIP(
            provider.cloudsPath, openStackMachineName, fip
        )

    elif provider.type == "external":
        
        log.info(f"Creating External Cluster {newCluster.name}")
        machine = external_dc_get_conf(req.datacenter)
        log.info(machine)
        
        
        external_install_cluster(ssh_identity_file= machine.get("ssh_key"), remote_ip=machine.get("ip"),
                                    local_dir=machine.get("local_dir"), username=machine.get("user"))
        
        newCluster.kubeconfig = get_kubeconfig_ssh(remote_ip=machine.get("ip"), username=machine.get("user"), ssh_identity_file=machine.get("ssh_key"))

        update_dc_configuration(datacenter=req.datacenter, ip= machine.get("ip"), state=True, cluster=clusterName)

        log.info(newCluster.kubeconfig)
        store_kubeconfig(newCluster.kubeconfig, newCluster.name)
        
    waitForReadyCluster(newCluster)

    log.info("Cluster is created and ready to use")
    task.status = "completed"
    
    taintNoSchedule(newCluster.kubeconfig)
    

    pkg_metallb = BashScript(name="metallb", version="v0.13.12")
    installPackage(pkg_metallb, clusterName, provider.type)

    pkg_nginx = BashScript(name="nginx", dependencies=[{"public-ip": pkg_metallb}], version="v2.2.0")
    installPackage(pkg_nginx, clusterName, provider.type)

    pkg_prometheus = BashScript(name='prometheus', dependencies=[{"public-ip": pkg_metallb}], version="v0.2.40")
    installPackage(pkg_prometheus, clusterName, provider.type)

    pkg_liqo = BashScript(name='liqo', dependencies=[{"public-ip": pkg_metallb}], version="v0.8.1")
    installPackage(pkg_liqo, clusterName, provider.type)
    
    pkg_mqtt = BashScript(name="mqtt", version="doesnt matter")
    installPackage(pkg_mqtt, clusterName, provider.type)

    log.info(f"Orchestration related packages successfully installed!")
        # pkg_kafka = BashScript(name="kafka", version="v3.4.0")
        # installPackage(pkg_kafka, clusterName)
        # sys.exit()
    
    
    url = f"http://monitoring-manager.plexus.charity-project.eu/monitoring/create-cluster?datacenter={req.datacenter}&cluster={clusterName}"
    response = requests.get(url)
    log.info(response)
    
    update_CRD_Status(newCluster.name, "running", "clusters")


def taintNoSchedule(kubeconfig):
    

    tmp = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp.write(kubeconfig)
        tmp.seek(0)
        
        cmd = (
            "kubectl --kubeconfig="
            + tmp.name
            + " taint nodes --all node.cloudprovider.kubernetes.io/uninitialized:NoSchedule-"
        )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)

    finally:
        tmp.close()
        return True

@timeit
def getClusterManifest(req, provider):
    # gen func and pos steps
    # TODO: this could be refactored to settings
    CRD_MAP = {
        "kubeadm": (
            CAPOKubeadmCRD,
            generateCAPOManifestFromClusterctl,
            ["disableSecurityGroups", "addPostKubeadmCommands"],
        ),
        "k3s": (
            CAPOK3sCRD,
            generateCAPOManifestFromClusterctl,
            ["disableSecurityGroups"],
        ),
    }

    # check if the Kubernetes type is supported
    if req.kubernetesType not in CRD_MAP:
        raise ValueError(
            status_code=500, detail="Kubernetes type not supported"
        )

    # get the CRD type, generation function, and list
    # of post-generation commands for the Kubernetes type
    CRD_TYPE, GEN_FUNC, POST_GEN_COMMANDS = CRD_MAP[req.kubernetesType]

    # get crd
    crd = GEN_FUNC(provider, req)

    # apply any post-generation commands for the given type
    crd = CRD_TYPE(crd)
    for cmd in POST_GEN_COMMANDS:
        crd = getattr(crd, cmd)()

    return crd

# returns a cluster generated crd using clusterctl generate cmd
def generateCAPOManifestFromClusterctl(
    provider, req: Optional[ClusterRequest] = None
):

    controlPlaneMachineCount = req.controlPlaneCount
    workerMachineCount = req.workerMachineCount

    # set some env vars for clusterctl generation script
    os.environ["CAPO_KUBERNETES_VERSION"] = req.kubernetesVersion
    os.environ["CAPO_CONTROL_PLANE_MACHINE_COUNT"] = str(
        controlPlaneMachineCount
    )
    os.environ["CAPO_WORKER_MACHINE_COUNT"] = str(workerMachineCount)
    os.environ["CAPO_CLUSTER_NAME"] = req.clusterName

    os.environ[
        "OPENSTACK_CONTROL_PLANE_MACHINE_FLAVOR"
    ] = req.controlPlaneFlavor
    os.environ["OPENSTACK_NODE_MACHINE_FLAVOR"] = req.workerMachineFlavor
    os.environ["OPENSTACK_IMAGE_NAME"] = req.image

    os.environ["CAPO_CLOUDS_PATH"] = provider.cloudsPath
    os.environ["CAPO_ENVRC_PATH"] = provider.rootConfigPath + "/env.rc"
    os.environ["CAPO_ENV_PATH"] = (
        provider.rootConfigPath + "/" + req.kubernetesType + "-openstack.env"
    )

    os.environ["CAPO_CACERT"] = provider.caCert  # not used atm

    # set CAPI KUBECONFIG for clusterctl
    os.environ["KUBECONFIG"] = os.environ["CAPI_KUBECONFIG"]

    cmd = (
        provider.rootConfigPath
        + "/generate_cluster_"
        + req.kubernetesType
        + ".sh"
    )

    p = run(cmd.split(" "), stdout=PIPE, stderr=PIPE, universal_newlines=True)
    # check if command was successful
    if p.returncode != 0:
        log.info("Failed %d %s %s" % (p.returncode, p.stdout, p.stderr))
        return None

    # TODO: check if output is valid yaml
    output = p.stdout

    return output
    
# create a tmp file for applying and rm it at the end
@timeit
def applyCAPIClusterManifest(clusterManifest):
    
    tmp = tempfile.NamedTemporaryFile(mode="w")
    try:
        tmp.write(clusterManifest)
        #IMPORTANT: Point to the beginning of the file
        tmp.seek(0)
        # TODO test output
        cmd = (
            "kubectl --kubeconfig="
            + os.environ["CAPI_KUBECONFIG"]
            + " apply -f "
            + tmp.name
        )
        result = subprocess.run(cmd.split(" "), stdout=subprocess.PIPE)
        # log.debug(result.stdout)
    finally:
        tmp.close()


def getClusterByNameFromCRD(name):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    orchestration_custom_resource = api_instance.get_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        name="kubeadm-based-orchestration"
    )
    
    cluster_data = {}
    
    if "clusters" in orchestration_custom_resource["spec"]:
        for cluster in orchestration_custom_resource["spec"]["clusters"]:
            if name == cluster["name"]:
                return cluster

    return None

# retrieve kubeconfig by CAPI cluster name
@timeit
def getKubeconfigFromClusterctl(clusterName):
    
    cluster = getClusterByNameFromCRD(clusterName)

    if cluster == None:
        raise Exception("Cluster Not Found.")

    if (cluster["provider"] == "external") & (cluster.get("kubeconfig", None) != None):
        secret_name = cluster.get("kubeconfig")

        kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])
        api_client = kubernetes.client.ApiClient()

        try: 
            api_instance = kubernetes.client.CoreV1Api(api_client)
            kubeconfig = api_instance.read_namespaced_secret(
                name = secret_name,
                namespace="orchestration"
            )

            kubeconfig = base64.b64decode(kubeconfig.data["kubeconfig"]).decode('utf-8')

            return kubeconfig
        except ApiException as e:
            raise e

    counter = 0
    cmd = (
        "KUBECONFIG="
        + os.environ["CAPI_KUBECONFIG"]
        + " clusterctl get kubeconfig "
        + clusterName
    )
    output = ""
        
    while True:  # wait for cluster kubeconfig

        output, error = subprocess.Popen(
            cmd,
            universal_newlines=True,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).communicate()
        
    
        # test if output starts with Error
        if output.startswith("Error") or output == "":
            log.info("Waiting for " + clusterName + " bootstrapping")
            sleep(1)
            counter += 1
            if counter >= 100:
                raise Exception("Get Kubeconfig Timed Out.")
            
            continue
        else:
            break
    return output

@timeit
def deleteClusterByName(name, provider, **kwargs):
    
    from app.controllers.providers.external import  external_uninstall_cluster, delete_kubeconfig_secret, update_dc_configuration, external_dc_get_cluster_machine


    task = kwargs.get("task")
    task.status = "executing"

        
    if (provider.type == "external"):
        
        log.info("Scheduled cluster " + name + " for deletion")


        machine = external_dc_get_cluster_machine(provider.name, name)
        
        if machine == None:
            raise Exception("Machine Not found for Given Cluster")

        external_uninstall_cluster(ssh_identity_file= machine.get("ssh_key"), remote_ip=machine.get("ip"),
                                    local_dir=machine.get("local_dir"), username=machine.get("user"))
        
        delete_kubeconfig_secret(name)
        
        update_dc_configuration(datacenter= provider.name, ip= machine.get("ip"), state=False, cluster=None)
    
        url = "http://monitoring-manager.plexus.charity-project.eu/monitoring/delete-cluster?cluster=" + str(name)
        response = requests.get(url)

        log.info(response)

        return True

   
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    cmd = (
        "kubectl --kubeconfig="
        + os.environ["CAPI_KUBECONFIG"]
        + " delete cluster -n default "
        + str(name)
    )
    
    subprocess.run(cmd.split(" "), stdout=subprocess.PIPE)
    log.info("Scheduled cluster " + name + " for deletion")
    task.status = "completed"

    url = "http://monitoring-manager.plexus.charity-project.eu/monitoring/delete-cluster?cluster=" + str(name)
    response = requests.get(url)

    log.info(response)

    return True

def installPackage(pkg: Package, clusterName, provider):
    # get kubeconfig
    kubeconfig = getKubeconfigFromClusterctl(clusterName)

    # check for dependencies and install them
    log.info("Checking for dependencies...")
    
    for dep in pkg.dependencies:
        if "public-ip" in dep:
            log.info("Found public-ip dependency...")
            addPublicIPToMetalLB(dep["public-ip"], clusterName, provider)

                
    log.info("Installed dependencies...")
    
    # install package
    tmp = tempfile.NamedTemporaryFile(mode="w+")
    try:
        tmp.write(kubeconfig)
        tmp.seek(0)
        os.environ["KUBECONFIG"] = tmp.name
        os.environ["VERSION"] = pkg.version
        os.environ["PROVIDER"] = provider
        os.environ["LIQO_CLUSTER_NAME"] = clusterName
        os.environ["CLUSTER_NAME"] = clusterName

        log.info("Installing package " + pkg.name + "..." )

        cmd = (
        os.environ["APP_PACKAGES_PATH"] + pkg.installScriptPath 
        )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        log.info(result.stdout)
        log.info(result.stderr)
    finally:
        log.info(f"{pkg.name} installed successfully!!!")
        tmp.close()

def checkTaint(clusterName):
    kubeconfig = getKubeconfigFromClusterctl(clusterName)

    tmp = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp.write(kubeconfig)
        tmp.seek(0)
        
        cmd = (
            "kubectl --kubeconfig="
            + tmp.name
            + " taint nodes --all node-role.kubernetes.io/control-plane-"
        )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        

    finally:
        tmp.close()
        return True

def createClusterToCRD(inputCRD):
    
    if "-" in inputCRD["name"]:
        return "Invalid Cluster Name - Do not use \"-\""
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    # Create an instance of the Kubernetes API client
    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    orchestration_custom_resource = api_instance.get_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        name="kubeadm-based-orchestration"
    )

    ctl = 0

    if "clusters" in orchestration_custom_resource["spec"]:
        for clusters in orchestration_custom_resource["spec"]["clusters"]:
            if inputCRD["name"] == clusters["name"]:
                ctl = 1
                break
        if ctl == 0:
            orchestration_custom_resource["spec"]["clusters"].append(inputCRD)
    else:
        orchestration_custom_resource["spec"]["clusters"] = []
        orchestration_custom_resource["spec"]["clusters"].append(inputCRD)

    api_instance.patch_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        name="kubeadm-based-orchestration",
        body=orchestration_custom_resource
    )

    return "CRD Patched successfully..."

def deleteClusterFromCRD(clusterName):
    from app.controllers.clusters.liqo import unpeerClusters

    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])


    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    orchestration_custom_resource = api_instance.get_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        name="kubeadm-based-orchestration"
    )


    if "links" in orchestration_custom_resource["spec"]:
        for link in orchestration_custom_resource["spec"]["links"]:
            log.info(id + "    " + str(link))
            if id in link:
                
                unpeerClusters(link[0], link[1])
                orchestration_custom_resource["spec"]["links"].remove(link)
            
    log.info(clusterName)

    if "clusters" in orchestration_custom_resource["spec"]:
        for cluster in orchestration_custom_resource["spec"]["clusters"]:
            if cluster["name"] == clusterName:
                orchestration_custom_resource["spec"]["clusters"].remove(cluster)

    api_instance.patch_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        name="kubeadm-based-orchestration",
        body=orchestration_custom_resource
    )

    return "CRD Patched successfully(DELETE)..."

# return True if current nodes ready count >= count
def isClusterReady(kubeconfigPath, count=1):

    cmd = (
        "kubectl --kubeconfig="
        + kubeconfigPath
        + " get nodes -n kube-system -o wide "
        + "| grep -v NotReady | grep Ready | wc -l"
    )

    p = subprocess.Popen(
        cmd,
        shell=True,
        executable="/bin/bash",
        universal_newlines=True,
        stdout=PIPE,
        stderr=PIPE,
    )
    
    readyCount, err = p.communicate()

    # log.info(cmd)
    readyCount = int(readyCount)

    log.info(f"Current Node Ready count {readyCount}, desired {count}")

    if readyCount is None or int(readyCount) < count:
        return False
    elif int(readyCount) >= count:
        return True
    
    return False

def clusterUpdate(cReq: ClusterRequest, **kwargs):
    task = kwargs.get("task")
    task.status = "executing"

    # append the resources' suffix to the cluster name

    mdName = cReq.clusterName + "-md-0"
    cpName = cReq.clusterName + "-control-plane"

    md = getMachineDeployment(mdName)
    cp = getControlPlane(cpName)

 

    if cReq.workerMachineCount != int(md["spec"]["replicas"]):
        scaleResources(mdName, cReq.workerMachineCount, "worker-machine")

    if cReq.controlPlaneCount != int(cp["spec"]["replicas"]):
        scaleResources(cpName, cReq.controlPlaneCount, "control-plane")


    task.status = "completed"
    
    update_CRD_Status(cReq.clusterName, "running", "clusters")

    return True

def scaleResources(name, count, resourceType):

    if resourceType == "control-plane":
        cmd = (
            "kubectl --kubeconfig="
            + os.environ["CAPI_KUBECONFIG"]
            + " -n default scale kubeadmcontrolplane "
            + str(name)
            + " --replicas="
            + str(count)
        )
        subprocess.run(cmd.split(" "), stdout=subprocess.PIPE)
        log.info("Scaling cluster " + str(name) + "...")

    elif resourceType == "worker-machine":
        cmd = (
        "kubectl --kubeconfig="
        + os.environ["CAPI_KUBECONFIG"]
        + " -n default scale machinedeployment "
        + str(name)
        + " --replicas="
        + str(count)
        )
        subprocess.run(cmd.split(" "), stdout=subprocess.PIPE)
        log.info("Scaling cluster " + str(name) + "...")

    return True

@timeit
def waitForReadyCluster(cluster: Cluster):
    counter = 0
    tmp = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp.write(cluster.kubeconfig)
        tmp.seek(0)

        while True:
            sleep(5)
            counter += 5
            if counter >= 600:
                raise Exception("Get Kubeconfig Timed Out.")
            if not isClusterReady(tmp.name, cluster.controlPlaneCount):
                continue
            log.info("Control Plane node(s) are ready")

            # not need for two ifs but this way
            # we can distiguinsh between CP and Worker times
            if not isClusterReady(
                tmp.name,
                cluster.controlPlaneCount + cluster.workerMachineCount,
            ):
                continue
            log.info("Control Plane and Worker(s) are ready")
            
            tmp.close()
            return True
    finally:
        tmp.close()
        return False