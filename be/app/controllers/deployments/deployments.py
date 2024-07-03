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

from app.controllers.clusters.capi import checkTaint, getClusterByName, getKubeconfigFromClusterctl
from app.utils.common import update_CRD_Status, get_orchestration_custom_resources
from app.controllers.clusters.liqo import labelClusterForLiqo, peerClusters
from app.controllers.providers.common import loadProviderByName
from timeout_decorator import timeout

log = logging.getLogger("app")

def getPodsStatus(namespace, app_name, cluster):
  tmp = tempfile.NamedTemporaryFile(mode="w+")   
  
  kubeconfig = getKubeconfigFromClusterctl(cluster)
  tmp.write(kubeconfig)
  tmp.seek(0)
  kubernetes.config.load_kube_config(tmp)

  api_client = kubernetes.client.CoreV1Api()
  api_response = api_client.list_namespaced_pod(
      namespace=namespace,
      label_selector=f"app={app_name}"
  )
  
  if len(api_response.items) == 0:
    return "Pod Not Found", "error"
  
  for pod in api_response.items:
    
    
    for states in pod.status.container_statuses:
      state = states.state
      status = ""
      if state.running != None:
        
        message = "Running"
        status = "running"
      elif state.waiting != None:
        if state.waiting.reason == "ContainerCreating":
          message = state.waiting.reason
          status = "pending"
          
        else:
          message = state.waiting.reason
          status = "error"
        
        return message, status

      elif state.terminated != None:
        message = state.terminated.reason
        status = "error"
        return message, status

  return message, status


def getDeplomentStatus(deployments: list, namespace, cluster):
  
  general_status = "running"
  counter = 0
  
  while counter < len(deployments):
    counter = 0
    for deployment in deployments:
      message, status = getPodsStatus(namespace, deployment, cluster)
      
      if status == "running":
        counter += 1
      elif status == "error": 
        return status
      elif status == "pending":
        break
      
  return general_status


def toscaGetAppByID(app_id):
    
    app = getAppById(app_id)
    
    if app == 0:
        raise HTTPException(status_code=404, detail="App not found")

    
    app_info = {"id": app_id}
    app_info["status"] = app["status"]
    
    
    
    app_cluster = getClusterByName(app["cluster"])
    if app_cluster == "Cluster Not Found":
        app_info["status"] = "Cluster Not Found"
        return app_info
    
    
    
    namespace = app["name"]
    
    
    if app["status"] == "pending":
        log.info("Pending deployment - Returning \"pending\" status")
        return app_info    
    
    app_info["outputParameters"] = []
    
    
    namespace = get_namespace(app["cluster"], app_id)

    

    
    for comp in app["components"]:
        
        cluster = getClusterByName(comp["cluster-selector"])
        kubeconfig = getKubeconfigFromClusterctl( comp["cluster-selector"])
        
        services = getApplicationServices(namespace, kubeconfig)
        ingresses = getApplicationIngress(namespace, kubeconfig)

        
        datacenter = loadProviderByName(cluster["datacenter"])
     
        log.info(comp["name"])
        message, status = getPodsStatus(namespace, comp["name"], app_cluster["name"])
        app_info["outputParameters"].append({"name": f"{comp['name']}_status", "value":  message})
        
        for output_param in comp["output-parameters"]:
            name = output_param.get("name")
            value = output_param.get("value")
            var = None
            if value == "namespace":
                var = namespace
            elif value == "deployment_context":
                var = kubeconfig
            elif value == "datacenter":
                var = cluster["datacenter"]
            elif value == "longitude":
                var = datacenter.get("location",{}).get("longitude","")
            elif value == "latitude":
                var =datacenter.get("location",{}).get("latitude","")
            elif value == "cluster":
                var = comp["cluster-selector"]
            
            if var:    
                app_info["outputParameters"].append({"name": name + "_" + value , "value" : var})
                
        
        # Check if the component has a service
        if "expose" in comp:
            
            for service in comp["expose"]:
                # Get services url (servicename.namespace:port)
                if service["is-public"] == False:
                    for svc in services.items:
                        for port in svc.spec.ports:
                            if service["name"].lower() == port.name:
                                    app_info["outputParameters"].append({"name": service["name"] + "_url", "value" : svc.metadata.name + "." + namespace + ":" + str(port.port)})


                # Get ingress url and paths
                if service["is-public"] == True:
                    if service["protocol"] == "HTTP":
                        for ingress in ingresses.items:
                            for rule in ingress.spec.rules:
                                for path in rule.http.paths:
                                    if (comp["name"] + service["name"].lower()) == path.backend.service.name or comp["name"]  == path.backend.service.name :
                                        app_info["outputParameters"].append({"name": service["name"] + "_url", "value": rule.host + path.path + " @ " +  re.findall(".*https://(.*):6443.*", kubeconfig)[0]})

                    elif service["protocol"] == "UDP" or service["protocol"] == "TCP":
                        for svc in services.items:
                            if comp["name"] in svc.spec.selector["app"]:
                                for port in svc.spec.ports:
                                    if service["name"].lower() == port.name:
                                        app_info["outputParameters"].append({"name": service["name"] + "_url", "value" : re.findall(".*https://(.*):6443.*", kubeconfig)[0] + ":" + str(port.port)})



                            
    log.info("Running deployment - Returning Deployment Info")

        
    return app_info
 
def get_TOSCA_cp(tosca):
    
    elements = tosca.get('topology_template',{}).get('node_templates',{})
            
    connection_points = {}
    for name, n in elements.items():
        
        if n["type"]=="Charity.ConnectionPoint":
            
            for req in n["requirements"]: 
                if "binding" in req:
                    connection_points[req["binding"]["node"]] = n
                    break 

    return connection_points 

def getApplicationIngress(namespace, kubeconfig):
    tmp = tempfile.NamedTemporaryFile(mode="w+")

    
    tmp.write(kubeconfig)
    tmp.seek(0)
    kubernetes.config.load_kube_config(tmp)
    # Create Kubernetes API client
    api_client = kubernetes.client.NetworkingV1Api()
    api_response = api_client.list_namespaced_ingress(
        namespace=namespace
    )
    
    return api_response

def getApplicationServices(namespace, kubeconfig):
    tmp = tempfile.NamedTemporaryFile(mode="w+")

    
    tmp.write(kubeconfig)
    tmp.seek(0)
    kubernetes.config.load_kube_config(tmp)
    # Create Kubernetes API client
    api_client = kubernetes.client.CoreV1Api()
    api_response = api_client.list_namespaced_service(
        namespace=namespace,
        
    )
    
    return api_response




def getAppById(id):
    crd_list = get_orchestration_custom_resources()
    
    for crd in crd_list["items"]:
        for app in crd["spec"].get("apps",[]):
            if app["id"] == id:
                
                app["cluster"] = app["cluster"]
                return(app)
    return 0

def undeploy_app(id):
    app = getAppById(id)
    
    if app == 0:
        return "App not found"
    
    cluster = app["cluster"]
    name = app["name"]
    
    
    cluster = getClusterByName(app["cluster"])
    
    if cluster == "Cluster Not Found":
        return "Cluster Not Found"
    
    kubeconfig = getKubeconfigFromClusterctl(app["cluster"])
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        # create a namespace where the app's components will run
        
        log.info("Deleting " + name + " application...")

        cmd = (
            "liqoctl --kubeconfig="
            + tmp_kube.name
            + " unoffload namespace "
            + name
        )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)

        log.info(name + " of cluster " + cluster + " unoffloaded...")

        cmd = (
            "kubectl --kubeconfig="
            + tmp_kube.name
            + " delete namespace "
            + name
        )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)

        log.info(name + " of cluster " + cluster + " deleted...")

    finally:
        tmp_kube.close()
        log.info(name + " application deleted...")
        return "App Successfully Uninstalled"

def update_deployment(toscaData):

    try:
        response = deleteAppFromCRD(toscaData["id"])
        
        sleep(25)
        
        response = toscaConversion(toscaData)
        
        return response
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail= str(e))
   
def update_namespace_appCRD(uid, namespace):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    # Create an instance of the Kubernetes API client
    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    orchestration_custom_resource = api_instance.list_namespaced_custom_object(
        group= "charity-project.eu",
        version="v1",
        namespace="default",
        plural="lowlevelorchestrations",
        
    )
            
    for crd in orchestration_custom_resource["items"]:
        crd_name = crd["metadata"]["name"]
        index = 0
        for component in crd["spec"]["apps"]:
            
            if component["id"] == uid:
                
                crd["spec"][type].pop(index)
                component["namespace"] = namespace
                crd["spec"][type].append(component)
                break
        
            index += 1
            
    api_instance.patch_namespaced_custom_object(
            group= "charity-project.eu",
            version="v1",
            namespace="default",
            plural="lowlevelorchestrations",
            name = crd_name,
            body=crd
        )
    
        
def toscaConversion(toscaData):
    return toscaToYaml(toscaData)

def toscaDeleteApp(appID):
    return deleteAppFromCRD(appID)

def toscaGetAppList(owner):
    app_list = []
    # get CRDs
    resources = get_orchestration_custom_resources()
    for items in resources["items"]:
        if "spec" in items and "apps" in items["spec"]:
            for app in items["spec"]["apps"]:
                if app["owner"] == owner:
                    app_list.append(app["name"])
    log.info("DONE")

    if len(app_list) == 0:
        return []
    else:
        return app_list


def get_component_cps(nodes, component_node):
    output_cp = []
    for name, node in nodes.items():
        if node["type"] == "Charity.ConnectionPoint":
            for requirements in node["requirements"]:
                
                if requirements.get("binding",None):
                    if requirements["binding"]["node"] == component_node["properties"]["name"]: 
                        
                        output_cp.append({"name": node["properties"]["name"],"type": node["properties"]["protocol"] })
                        break
    log.info(str(output_cp))
    return output_cp

def get_output_parameters(params, component_node, component_cp_list):
    
    output_parameters = []
    node_name = ""
    for req in component_node.get("requirements", []):
        for key, value in req.items():
            if key == "host":
                node_name = value
                
    for name, node in params.items():
        param_name = node["value"]["get_attribute"][0]
        
        
        
        if param_name == component_node["properties"]["name"] or param_name == node_name:
            param_value = name.replace(component_node["properties"]["name"] + "_", "")
            value = {"name": component_node["properties"]["name"], "value":param_value}
            output_parameters.append(value)
        elif param_name in component_cp_list:
            param_value = name.replace(param_name + "_", "")
            value = {"name": param_name, "value":param_value}
            output_parameters.append(value)
            
    print(str(output_parameters))
    return output_parameters

def toscaToYaml(tosca):
  app_id  = tosca["id"]
  tosca = yaml.safe_load(tosca["toscaFullModel"])

  default_certificate = "tls-certificate"
  output_app = {}
  links = []

  output_app["owner"] = tosca["metadata"]["template_author"]
  output_app["name"] = tosca["metadata"]["template_name"].lower()
  output_app["status"] = "pending"
  output_app["id"] = app_id
  
  # array of components
  output_app["components"] = []

  externalComponentVLMappingList = getExternalComponentVLMappingList(tosca)

  nodes = tosca.get('topology_template',{}).get('node_templates',{})
  tosca_params = tosca.get('topology_template',{}).get('outputs',{})


  for name, node in nodes.items():
    if node["type"] == "Charity.Component":
      if node["properties"]["deployment_unit"] != "EXTERNAL":
        # INIT VARS
        output_component = {}
        output_component["expose"] = []
        output_component["tosca-cp"] = get_component_cps(nodes, node)
        output_component["output-parameters"] = get_output_parameters(tosca_params, node, output_component["tosca-cp"])
        output_component["tls"] = {}
        output_component["env"] = {}
        output_component["env"]["variables"] = []

        output_component["name"] = node["properties"]["name"].lower()
        output_component["image"] = node["properties"]["image"]
        output_component["tls"]["name"] = default_certificate

        if "environment" in node["properties"]:
            for var_name in node["properties"]["environment"]:
                var = {}

                if isinstance(node["properties"]["environment"][var_name], dict):
                    

                    name = node["properties"]["environment"][var_name]["get_input"]
                    
                    var["name"] = var_name 
                    var["value"] = tosca["topology_template"]["inputs"][name]["default"]
                else:
                    var["name"] = var_name
                    var["value"] = node["properties"]["environment"][var_name]

                output_component["env"]["variables"].append(var)

        #Get Cluster for each component
        for host in node["requirements"]:
            if "host" in host:
                component_node = host["host"]
        
        for capabiliy in nodes[component_node]["node_filter"]["capabilities"]:
            if "deployment" in capabiliy:
                for cluster in capabiliy["deployment"]["properties"]["cluster"]:
                    if cluster["equal"] != output_app.get("cluster", cluster["equal"]):
                        
                        links.append([str(cluster["equal"]), str(output_app.get("cluster",""))])
                        
                    output_component["cluster-selector"] = output_app["cluster"] = cluster["equal"]
        
            
        expose = checkIfPeerOrPublic(tosca, node["properties"]["name"], externalComponentVLMappingList)
        
        output_component["expose"] = expose
        
        
        output_app["components"].append(output_component)

  log.info(output_app)



  updateCRDLinks(links)
  
  if len(links) != 0:
    sleep(15)
  
  status = updateCRD(output_app)
  
  

  return status 

def updateCRDLinks(inputCRD):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    # Create an instance of the Kubernetes API client
    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    try:
        orchestration_custom_resource = api_instance.get_namespaced_custom_object(
            group= "charity-project.eu",
            version="v1",
            namespace="default",
            plural="lowlevelorchestrations",
            name="kubeadm-based-orchestration"
        )
        
        if "links" in orchestration_custom_resource["spec"]:
            ctl = 0
            # for apps in orchestration_custom_resource["spec"]["apps"]:
            #     if inputCRD["owner"] == apps["owner"]:
            #         ctl = 1
            #         break
            # if ctl == 0:
            #     
            
            for link in inputCRD:
                if link not in orchestration_custom_resource["spec"]["links"] and list(reversed(link)) not in orchestration_custom_resource["spec"]["links"]:
                    orchestration_custom_resource["spec"]["links"].append(link)
        else:
            orchestration_custom_resource["spec"]["links"] = inputCRD


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
            
            orchestration_custom_resource["spec"]["links"] = inputCRD


            log.info(inputCRD)
            
            api_instance.create_namespaced_custom_object(
                group= "charity-project.eu",
                version="v1",
                namespace="default",
                plural="lowlevelorchestrations",
                body=orchestration_custom_resource
            )
        else:
            log.info("An error occurred:", e)
            
    return str(inputCRD)


def updateCRD(inputCRD):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    # Create an instance of the Kubernetes API client
    api_client = kubernetes.client.ApiClient()

    api_instance = kubernetes.client.CustomObjectsApi(api_client)
    try:
        orchestration_custom_resource = api_instance.get_namespaced_custom_object(
            group= "charity-project.eu",
            version="v1",
            namespace="default",
            plural="lowlevelorchestrations",
            name="kubeadm-based-orchestration"
        )
        
        if "apps" in orchestration_custom_resource["spec"]:
            ctl = 0
            # for apps in orchestration_custom_resource["spec"]["apps"]:
            #     if inputCRD["owner"] == apps["owner"]:
            #         ctl = 1
            #         break
            # if ctl == 0:
            #     
            for app_crd in orchestration_custom_resource["spec"]["apps"]:
                if app_crd["id"] == inputCRD["id"]:
                    return f"Application With id {app_crd['id']} Already Exists."
            
            orchestration_custom_resource["spec"]["apps"].append(inputCRD)
        else:
            orchestration_custom_resource["spec"]["apps"] = []
            orchestration_custom_resource["spec"]["apps"].append(inputCRD)

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
            
            orchestration_custom_resource["spec"]["apps"] = []
            orchestration_custom_resource["spec"]["apps"].append(inputCRD)

            log.info(inputCRD)
            
            api_instance.create_namespaced_custom_object(
                group= "charity-project.eu",
                version="v1",
                namespace="default",
                plural="lowlevelorchestrations",
                body=orchestration_custom_resource
            )
        else:
            log.info("An error occurred:", e)
            
    return {"id": inputCRD["id"], "status": "pending"}



def deleteAppFromCRD(id):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    log.info("Deleting app with id: " + str(id))

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

    if "apps" in orchestration_custom_resource["spec"]:
        for app in orchestration_custom_resource["spec"]["apps"]:
            if app["id"] == str(id):
                orchestration_custom_resource["spec"]["apps"].remove(app)
                cluster = app["cluster"]
                api_instance.patch_namespaced_custom_object(
                    group= "charity-project.eu",
                    version="v1",
                    namespace="default",
                    plural="lowlevelorchestrations",
                    name="kubeadm-based-orchestration",
                    body=orchestration_custom_resource
                )

                return "CRD Patched successfully(DELETE APP) from cluster - " + cluster
    
    raise HTTPException(status_code = 404, detail="App Not Found")
        
def getExternalComponentVLMappingList(tosca):
    vl_list = {}
    nodes = tosca.get('topology_template',{}).get('node_templates',{})
    for name, node in nodes.items():
        if node["type"] == "Charity.Component" and node["properties"]["deployment_unit"] == "EXTERNAL":
            vl_list[node["properties"]["name"].lower()] = []

    for name, node in nodes.items():
        if node["type"] == "Charity.ConnectionPoint":
            ctl = 0
            aux = ""
            for requirements in node["requirements"]:
                for key in requirements:
                  if key == "binding" and requirements["binding"]["node"].lower() in vl_list.keys():
                      aux = requirements["binding"]["node"].lower()
                      ctl = 1
                  elif ctl == 1 and key == "link":
                      vl_list[aux].append(requirements[key]["node"])
    return vl_list

def checkIfPeerOrPublic(tosca, component_name, external_list):
    # iterate through connectionpoints
    # get name and port
    # check the link
    # if external, do ingress
    
    output = []
    nodes = tosca.get('topology_template',{}).get('node_templates',{})
    for name, node in nodes.items():
        if node["type"] == "Charity.ConnectionPoint":
          expose = {}
          for requirements in node["requirements"]:
            if "binding" in requirements and requirements["binding"]["node"] == component_name:
                
              # IF CP EXISTS, WE NEED TO EXPOSE AT LEAST AS A SERVICE
              if "port" in node["properties"]:
                expose["name"] = node["properties"].get("name")
                expose["is-peered"] = True
                expose["containerPort"] = expose["clusterPort"] = node["properties"]["port"]
                expose["protocol"] = node["properties"].get("protocol", "TCP")
                expose["is-public"] = node["properties"].get("public", False)
                
                continue
              else:
                break
            else:
                break
          for requirements in node["requirements"]:
            if "link" in requirements and "is-peered" in expose and expose["is-peered"] == True:
              for ext_name, vl in external_list.items():
                if requirements["link"]["node"] in vl:
                  expose["is-public"] = True
                  break
                  # If VirtualLink is connected to an external component, it must be exposed as an ingress/loadbalancer
          
          if len(expose) != 0:
            output.append(expose)
          
    return output 

def offload_namespace(clusterName, namespace, offloadTargetCluster):
    kubeconfig = getKubeconfigFromClusterctl(clusterName)
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        if clusterName == offloadTargetCluster:
            
            cmd = (
                "liqoctl --kubeconfig="
                + tmp_kube.name
                + " offload namespace "
                + namespace
                + " --namespace-mapping-strategy EnforceSameName"
            )

        else:
            cmd = (
                "liqoctl --kubeconfig="
                + tmp_kube.name
                + " offload namespace "
                + namespace
                + " --namespace-mapping-strategy EnforceSameName"
                + " --selector topology.liqo.io/name="
                + offloadTargetCluster
            )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)

    finally:
        tmp_kube.close()
        
def create_namespace(app_id, namespace, kubeconfig):
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")
    tmp_kube.write(kubeconfig)
    tmp_kube.seek(0)
    kubernetes.config.load_kube_config(tmp_kube)

    api_client = kubernetes.client.ApiClient()
    api_instance = kubernetes.client.CoreV1Api(api_client)
    body = kubernetes.client.V1ObjectMeta(name=namespace, labels={"appid":str(app_id)})
    body = kubernetes.client.V1Namespace(metadata=body) 

    try:
        api_response = api_instance.create_namespace(body)
        return api_response

    except ApiException as e:
        if e.reason == "Conflict":
            body = json.loads(e.body)
            if body["reason"] == "AlreadyExists":
                return None
    except Exception as e:
        raise e

def install_app(appData):
    
    
    # get Kubeconfig
    kubeconfig = getKubeconfigFromClusterctl(appData["cluster"])
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")

    checkTaint(appData["cluster"])

    namespace = appData["name"]
    namespace = namespace.lower()
    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        # create a namespace where the app's components will run

        result = create_namespace(app_id=appData["id"],namespace=namespace, kubeconfig=kubeconfig)
        id = 0
        while result == None:
            # if id > 0:
            #     app_name = namespace.split("-")[:-1]
            #     namespace_id = namespace.split("-")[-1] 
            #     namespace = app_name + '-' + str(int(namespace.split("-")[-1]) + 1)
            # else: 
            namespace = appData["name"] + '-' + str(id)
            result = create_namespace(app_id=appData["id"],namespace=namespace, kubeconfig=kubeconfig)
            id += 1            
            
        # update_namespace_appCRD(appData["id"], namespace)

        log.info("Labelling cluster for Liqo")
        labelClusterForLiqo(appData["cluster"])


        install_default_tls(appData["cluster"], namespace)

        offload_namespace(appData["cluster"], namespace, appData["cluster"])



    finally:
        tmp_kube.close()

    svc_list = svc_to_env(appData)
    
    
    component_list = []
    for component in appData["components"]:
        component["cluster-selector"] = component["cluster-selector"]
        # install_docker_secret(appData["cluster"], component, namespace)
        if "harbor" in component["image"]:
            install_secret(appData["cluster"], namespace,"harbor_secret.yaml")
            secret = "harbor-secret"
        else:
            install_secret(appData["cluster"], namespace,"orchestrator_secret.yaml")
            secret = "orchestrator-secret"
 
        install_deployment(appData["cluster"], component, namespace, secret, svc_list, app_id= appData["id"])
        log.info("INSTALL DEPLOYMENT" + component["cluster-selector"])
        # svc = []
        
        if "expose" in component:
            for exp in component["expose"]:
                # svc.append({"port": exp["port"], "protocol": exp["protocol"]})
                
                if "is-peered" in exp and exp["is-peered"] == True:
                    number_of_services = len(component["expose"])

                    install_service(appData["cluster"], component, exp, namespace, number_of_services)
                if "is-public" in exp and exp["is-public"] == True:
                    number_of_services = len(component["expose"])
                    if namespace == "dotes":
                        install_default_tls(appData["cluster"], namespace)
                    if exp.get("protocol", "HTTP") == "HTTP":
                        install_ingress(appData["cluster"], component, exp, namespace, number_of_services)

        if appData["cluster"] != component["cluster-selector"]:
            offload_namespace(appData["cluster"], namespace, component["cluster-selector"])
        
        log.info(component["name"] + " installed successfully!!!")
        component_list.append(component["name"])
    
    status = getDeplomentStatus(component_list, namespace, appData["cluster"])
    update_CRD_Status(appData["id"], status, "apps")
    
    log.info(appData["name"] + " application installed successfully!!! Final Status -> " + status)
    

def svc_to_env(appData):
    l = []
    for component in appData["components"]:
        if "expose" in component:
            for exp in component["expose"]:
                d = {}
                if "is-peered" in exp and exp["is-peered"] == True:
                    d["name"] = component["name"]
                    d["port"] = exp["clusterPort"]
                    l.append(d)
    return l

def install_deployment(clusterName, component, namespace, secretName, service_list, app_id):
    # TODO: HANDLE NAMESPACE FOR INGRESS ENDPOINTS 
    
    # get template
    environment = Environment(loader=FileSystemLoader(os.environ["APP_TEMPLATES_PATH"]))
    deployment_template = environment.get_template("deployment_template.yaml")

    # get Kubeconfig
    kubeconfig = getKubeconfigFromClusterctl(clusterName)
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")
    tmp_deployment = tempfile.NamedTemporaryFile(mode="w+")


    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        env_vars = component.get("env",{}).get("variables",[])
        deployment_kubeconfig = getKubeconfigFromClusterctl(component["cluster-selector"])
        env_vars.append({"name": "CHA_DOMAIN_IP", "value":   re.findall(".*https://(.*):6443.*", deployment_kubeconfig)[0]} )
        component["env"]["variables"] = env_vars
        
        rendered_deployment = deployment_template.render(   name=component["name"].lower(), 
                                                            image=component["image"],
                                                            expose=component.get("expose", ""),
                                                            env=component.get("env", ""),
                                                            namespace=namespace,
                                                            secretName=secretName,
                                                            clusterLabel=component.get("cluster-selector", ""),
                                                            service_list=service_list,
                                                            app_id=app_id
                                                    )
    
        yaml_output = yaml.safe_load(rendered_deployment)
        yaml.dump(yaml_output, tmp_deployment)
        tmp_deployment.seek(0)

        cmd = (
                    "kubectl --kubeconfig="
                    + tmp_kube.name
                    + " apply -f "
                    + tmp_deployment.name
                )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        
    finally:
        tmp_kube.close()
        tmp_deployment.close()
        log.info(component["name"] + " deployment installed...")

def install_default_tls(clusterName, namespace):
    
    # get template
    environment = Environment(loader=FileSystemLoader(os.environ["APP_TEMPLATES_PATH"]))
    tls_template = environment.get_template("tls_default.yaml")

    # get Kubeconfig
    kubeconfig = getKubeconfigFromClusterctl(clusterName)
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")
    tmp_tls = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        rendered_tls = tls_template.render(namespace=namespace)
    
        yaml_output = yaml.safe_load(rendered_tls)
        yaml.dump(yaml_output, tmp_tls)
        tmp_tls.seek(0)

        cmd = (
                    "kubectl --kubeconfig="
                    + tmp_kube.name
                    + " apply -f "
                    + tmp_tls.name
                )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        
    finally:
        tmp_kube.close()
        tmp_tls.close()
        log.info("TLS SECRET installed...")

def install_service(clusterName, component, expose, namespace, number_of_services):
    # get template
    
    environment = Environment(loader=FileSystemLoader(os.environ["APP_TEMPLATES_PATH"]))
    service_template = environment.get_template("service_template.yaml")

    # get Kubeconfig
    kubeconfig = getKubeconfigFromClusterctl(clusterName)
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")
    tmp_service = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        if number_of_services <= 1:
            name = component["name"]
        else:
            name = component["name"] + expose["name"].lower()
        
        rendered_service = service_template.render(  name=component["name"],
                                                        svc_name = name,
                                                        exp=expose,
                                                        is_public=expose["is-public"],
                                                        namespace=namespace,
                                                    )
    
        yaml_output = yaml.safe_load(rendered_service)
        yaml.dump(yaml_output, tmp_service)
        tmp_service.seek(0)

        cmd = (
                    "kubectl --kubeconfig="
                    + tmp_kube.name
                    + " apply -f "
                    + tmp_service.name
                )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        
    finally:
        tmp_kube.close()
        tmp_service.close()
        log.info(component["name"] + " service installed...")

def install_ingress(clusterName, component, expose, namespace, number_of_services):
   # get template
    environment = Environment(loader=FileSystemLoader(os.environ["APP_TEMPLATES_PATH"]))
    ingress_template = environment.get_template("ingress_template.yaml")

    # get Kubeconfig
    kubeconfig = getKubeconfigFromClusterctl(clusterName)
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")
    tmp_ingress = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        if number_of_services  <= 1:
            name = component["name"]
        else:
            name = component["name"] + expose["name"].lower()
        

        endpoint= name + "." + namespace + ".charity-project.eu"

        if namespace == "dotes":
            rendered_ingress = ingress_template.render(     name=name,
                                                        serviceName=name,
                                                        exp=expose,
                                                        namespace=namespace,
                                                        url=endpoint,
                                                        secretName="tls-certificate"
                                                    )
        else:
            rendered_ingress = ingress_template.render(     name=name,
                                                        serviceName=name,
                                                        exp=expose,
                                                        namespace=namespace,
                                                        url=endpoint,
                                                        # secretName=component.get("tls", "")
                                                    )
    
        yaml_output = yaml.safe_load(rendered_ingress)
        yaml.dump(yaml_output, tmp_ingress)
        tmp_ingress.seek(0)

        cmd = (
                    "kubectl --kubeconfig="
                    + tmp_kube.name
                    + " apply -f "
                    + tmp_ingress.name
                )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        
    finally:
        tmp_kube.close()
        tmp_ingress.close()
        log.info(component["name"] + " ingress installed...")

def install_docker_secret(clusterName, component, namespace):
    # get Kubeconfig
    kubeconfig = getKubeconfigFromClusterctl(clusterName)
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        cmd = (
                    "kubectl --kubeconfig="
                    + tmp_kube.name
                    + " -n "
                    + namespace
                    + " create secret docker-registry "
                    + component["name"] + "-docker-secret"
                    + " --docker-server="
                    + component["registry"]["repository"]
                    + " --docker-username="
                    + component["registry"]["username"]
                    + " --docker-password="
                    + component["registry"]["password"]
                    + " --docker-email="
                    + component["registry"]["email"]
                )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        
    finally:
        tmp_kube.close()
        log.info(component["name"] + " docker secret installed...")

def install_secret(clusterName, namespace, secret_dir):
   # get template
    environment = Environment(loader=FileSystemLoader(os.environ["APP_TEMPLATES_PATH"]))
    secret_template = environment.get_template(secret_dir)

    # get Kubeconfig
    kubeconfig = getKubeconfigFromClusterctl(clusterName)
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")
    tmp_secret = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        rendered_secret = secret_template.render(namespace=namespace)
    
        yaml_output = yaml.safe_load(rendered_secret)
        yaml.dump(yaml_output, tmp_secret)
        tmp_secret.seek(0)

        cmd = (
                    "kubectl --kubeconfig="
                    + tmp_kube.name
                    + " apply -f "
                    + tmp_secret.name
                )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        
    finally:
        tmp_kube.close()
        tmp_secret.close()
        log.info("Orchestrator secret installed...")

def install_tls_secret(clusterName, component, namespace):
    # get template
    environment = Environment(loader=FileSystemLoader(os.environ["APP_TEMPLATES_PATH"]))
    tls_secret_template = environment.get_template("tls_secret_template.yaml")

    # get Kubeconfig
    kubeconfig = getKubeconfigFromClusterctl(clusterName)
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")
    tmp_tls_secret = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

        trunk_cert = component["tls"]["certificate"].replace('\n', '')
        trunk_key = component["tls"]["key"].replace('\n', '')

        log.info(trunk_cert)

        certificate_encoded = base64.b64encode(trunk_cert.encode("ascii"))
        key_encoded = base64.b64encode(trunk_key.encode("ascii"))

        rendered_tls_secret = tls_secret_template.render(name=component["tls"]["name"], 
                                                        certificate=certificate_encoded,
                                                        key=key_encoded,
                                                        namespace=namespace
                                                    )
    
        yaml_output = yaml.safe_load(rendered_tls_secret)
        yaml.dump(yaml_output, tmp_tls_secret)
        tmp_tls_secret.seek(0)

        cmd = (
                    "kubectl --kubeconfig="
                    + tmp_kube.name
                    + " apply -f "
                    + tmp_tls_secret.name
                )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
        
    finally:
        tmp_kube.close()
        log.info(component["name"] + " tls secret installed...")

def get_namespace(cluster, app_id):
    kubeconfig = getKubeconfigFromClusterctl(cluster)
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

 
        kubernetes.config.load_kube_config(tmp_kube)

        api_client = kubernetes.client.ApiClient()
        api_instance = kubernetes.client.CoreV1Api(api_client)

        api_response = api_instance.list_namespace(label_selector="appid")
        
        namespace_name = ""
        for namespace in api_response.items:
            if namespace.metadata.labels["appid"] == str(app_id):
                namespace_name = (namespace.metadata.name)
                
        return namespace_name 
    except:
        log.info("Namespace not found")
        return False

def unoffload_and_delete_app(cluster, name, id):
    
    
    
    kubeconfig = getKubeconfigFromClusterctl(cluster)
    tmp_kube = tempfile.NamedTemporaryFile(mode="w+")

    try:
        tmp_kube.write(kubeconfig)
        tmp_kube.seek(0)

 
        kubernetes.config.load_kube_config(tmp_kube)

        api_client = kubernetes.client.ApiClient()
        api_instance = kubernetes.client.CoreV1Api(api_client)

        # api_response = api_instance.list_namespace(label_selector="appid")
        
        # namespace_name = ""
        # for namespace in api_response.items:
        #     if namespace.metadata.labels["appid"] == str(id):
        #         namespace_name = (namespace.metadata.name) 
        
        namespace_name = get_namespace(cluster, id)
        
        log.info("Deleting " + name + " application...")

        cmd = (
            "liqoctl --kubeconfig="
            + tmp_kube.name
            + " unoffload namespace "
            + namespace_name
        )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)

        log.info(namespace_name + " of cluster " + cluster + " unoffloaded...")

        cmd = (
            "kubectl --kubeconfig="
            + tmp_kube.name
            + " delete namespace "
            + namespace_name
        )

        result = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)

        log.info(namespace_name + " of cluster " + cluster + " deleted...")

    finally:
        tmp_kube.close()
        log.info(name + " application deleted...")

def apply_new_alerts(new_conf, cluster):
    kubeconfig = getKubeconfigFromClusterctl(cluster)
    tmp = tempfile.NamedTemporaryFile(mode="w+")
    tmp.write(kubeconfig)
    tmp.seek(0)
    kubernetes.config.load_kube_config(tmp)

    api_client = kubernetes.client.ApiClient()
    api_instance = kubernetes.client.CoreV1Api(api_client)
    try:
        api_response = api_instance.read_namespaced_config_map("prometheus-server-conf", "monitoring")
        
        new_conf = yaml.safe_load(new_conf)

        new_conf = yaml.dump(new_conf, default_flow_style=False, sort_keys=False)

        api_response.data["prometheus.rules"] = new_conf
                   
        api_response = api_instance.patch_namespaced_config_map(name="prometheus-server-conf", namespace="monitoring", body=api_response)
        
        pods = api_instance.list_namespaced_pod("monitoring", label_selector="app=prometheus-server")

        for pod in pods.items:
            pod_name = pod.metadata.name
            api_instance.delete_namespaced_pod(name=pod_name, namespace="monitoring")
            
        return {"Details": "Configuration of Alert Manager Changed"}
        
    except ApiException as e:
        print(e.reason)
    