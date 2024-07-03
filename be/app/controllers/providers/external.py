

import base64
import ipaddress
import yaml
import logging
import paramiko
from kubernetes.client.exceptions import ApiException
import kubernetes
import os
from app.controllers.clusters.capi import getClusterList, getClusterListFromCRD

log = logging.getLogger("app")

def update_dc_configuration(datacenter, ip, state, cluster):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])


    api_client = kubernetes.client.ApiClient()
    api_instance = kubernetes.client.CoreV1Api(api_client)
    
    
    try:
        api_response = api_instance.read_namespaced_config_map(namespace="orchestration", name ="external-providers")        

        for dc in api_response.data:
            if dc == datacenter:
                data = yaml.safe_load(api_response.data[dc])
                break
            
        for machine in data.get("machines", {}):
            if machine.get("ip") == ip:
                machine["cluster"] = cluster
                machine["used"] = state
                break
        
        api_response.data[datacenter] = yaml.safe_dump(data)


        api_response = api_instance.patch_namespaced_config_map(namespace="orchestration", name="external-providers", body=api_response)
    
    
    
        
    except ApiException as e:
        log.info(e.reason)
        raise e
    except Exception as e:
        raise e

def get_dc_configuration(datacenter):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    api_client = kubernetes.client.ApiClient()
    api_instance = kubernetes.client.CoreV1Api(api_client)
    
    
    try:
        api_response = api_instance.read_namespaced_config_map(namespace="orchestration", name ="external-providers")        

        for dc in api_response.data:
            if dc == datacenter:
                data = yaml.safe_load(api_response.data[dc])
                
                data = data.get("conf", {})
                
                for i in range(len(data.get("flavors", []))):
                    data["flavors"][i]["cpuSize"] = int(data["flavors"][i]["cpuSize"])
                    data["flavors"][i]["diskSizeGb"] = int(data["flavors"][i]["diskSizeGb"])
                    data["flavors"][i]["memSizeGb"] = int(data["flavors"][i]["memSizeGb"])

                for i in range(len(data.get("gpus", []))):
                    data["gpus"][i]["units"] = int(data["gpus"][i]["units"])

                data["nodes"] = int(data["nodes"])
                
                data["location"]["latitude"] = float(data["location"]["latitude"])
                data["location"]["longitude"] = float(data["location"]["longitude"] )
                return data             

        return {}
    
        
    except ApiException as e:
        log.info(e.reason)
        raise e
    except Exception as e:
        raise e
    
def get_dc_machines(datacenter):
    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    api_client = kubernetes.client.ApiClient()
    api_instance = kubernetes.client.CoreV1Api(api_client)
    
    
    try:
        api_response = api_instance.read_namespaced_config_map(namespace="orchestration", name ="external-providers")        

        for dc in api_response.data:
            if dc == datacenter:
                data = yaml.safe_load(api_response.data[dc])
                return data.get("machines", {})
            
        return {}
    
        
    except ApiException as e:
        log.info(e.reason)
        raise e
    except Exception as e:
        raise e
    


def external_dc_get_cluster_machine(datacenter, cluster_name):

    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    api_client = kubernetes.client.ApiClient()
    api_instance = kubernetes.client.CoreV1Api(api_client)
    
    
    try:
        api_response = api_instance.read_namespaced_config_map(namespace="orchestration", name ="external-providers")        

        for dc in api_response.data:
            if dc == datacenter:
                data = yaml.safe_load(api_response.data[dc])
                for machine in data.get("machines", {}):
                    if machine["cluster"] == cluster_name:
                        c = {
                                "ssh_key": os.path.join("/app/.config/capi-providers/external/" + datacenter + "/CHA-ORCH-SSH-KEY.pem"),
                                "ip": machine.get("ip"),
                                "user": machine.get("user"),
                                "name": datacenter,
                                "local_dir": "/app/.config/capi-providers/external/" + datacenter
                            
                                }
                        return c 
                    
            
        return None
    
        
    except ApiException as e:
        log.info(e.reason)
        raise e
    except Exception as e:
        raise e



"""
def external_provider_get_location(path):

    with open(path + "/conf.yaml", 'r') as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
        
    return data.get("location")



def get_external_kubeconfig(path, clustername):
    with open(path + "/clusters.yaml", 'r') as file:
        data = yaml.load(file, Loader=yaml.FullLoader)

    for cluster in data.get("clusters"):
        if cluster.get("name") == clustername:
            kubeconfig = cluster.get("config")
            kubeconfig = yaml.load(kubeconfig, Loader=yaml.FullLoader)

    return kubeconfig


def get_external_nodes(path):
    with open(path + "/conf.yaml", 'r') as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
    
    return data.get("nodes")

def get_external_gpus(path):
    with open(path + "/conf.yaml", 'r') as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
    
    return data.get("gpus")

def get_external_flavors(path):
    with open(path + "/conf.yaml", "r") as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
        
    return data.get("flavors")
"""


def get_external_clusters(datacenter):
        
    clusters = getClusterListFromCRD()
    c = []
    for cluster in clusters:
        if cluster["datacenter"] == datacenter:
            c.append({"name": cluster["name"]})
    
    return c



def external_install_cluster(ssh_identity_file, remote_ip, local_dir, username):
    try:
        
        rsa_key = paramiko.RSAKey.from_private_key_file(ssh_identity_file, password=None)
        
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=remote_ip, username=username, pkey=rsa_key)

        scp_client = ssh_client.open_sftp()
        
        if ipaddress.ip_address(remote_ip).is_private:
            sudo = ""
            remote_dir = f"/home"
        else:
            sudo = "sudo"
            remote_dir = f"/home/{username}"

        try:
            scp_client.stat(remote_dir + "/install_cluster")
        except FileNotFoundError:
            scp_client.mkdir(remote_dir + "/install_cluster")
        
        
        scp_client.put(local_dir + "/install-management-cluster.sh", remote_dir + "/install_cluster/install_cluster.sh")
        
        try:
            scp_client.stat(remote_dir + "/install_cluster/addons")
        except FileNotFoundError:
            scp_client.mkdir(remote_dir + "/install_cluster/addons")

        
        scp_client.put(local_dir + "/addons/kube-flannel.yaml", remote_dir + "/install_cluster/addons/kube-flannel.yaml")
        scp_client.put(local_dir + "/addons/metrics-server.yaml", remote_dir + "/install_cluster/addons/metrics-server.yaml")

        scp_client.close()

        
        command = f"cd {remote_dir}/install_cluster && chmod +x install_cluster.sh && ./install_cluster.sh {sudo}"
        log.info(command)

        stdin, stdout, stderr = ssh_client.exec_command(command)

        for line in iter(stdout.readline, ""):
            log.info(line.strip())


    except Exception as e:
        log.info(f"Error: {e}")
        raise e
    
    



def external_get_available_machine(datacenter):
    machines = get_dc_machines(datacenter)
    
    for machine in machines:
        if machine.get("used") == False:
            return machine

    return None

def external_dc_get_conf(dc_name):
    

    path = os.environ["CAPI_PROVIDERS_PATH"]

    for item in os.listdir(path):
        if "external" == item:
            path = os.path.join(path, item)
            for cloud in os.listdir(path):
                if cloud == dc_name:
                    rootPath = os.path.join(path, cloud)
                    machine = external_get_available_machine(cloud)
                    if machine != None:
                        c = {
                                "ssh_key": os.path.join(rootPath, "CHA-ORCH-SSH-KEY.pem"),
                                "ip": machine.get("ip"),
                                "user": machine.get("user"),
                                "name":cloud,
                                "local_dir": rootPath
                            
                                }
                    else:
                        return None
                        
                    break
                
        path = os.environ["CAPI_PROVIDERS_PATH"]
        
    log.info("Loaded provider")
    return c

def get_kubeconfig_ssh(remote_ip, username, ssh_identity_file):
    try:
        rsa_key = paramiko.RSAKey.from_private_key_file(ssh_identity_file, password=None)
        
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=remote_ip, username=username, pkey=rsa_key)
        scp_client = ssh_client.open_sftp()

        remote_file = scp_client.open(".kube/config", 'r')
        kubeconfig = remote_file.read()
        remote_file.close()

        scp_client.close()
        ssh_client.close()

        return kubeconfig.decode("utf-8")

    except Exception as e:
        print(f"Error: {e}")
        return None

def store_kubeconfig(kubeconfig, clustername):
    

    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    api_client = kubernetes.client.ApiClient()
    api_instance = kubernetes.client.CoreV1Api(api_client)
    
    kubeconfig = base64.b64encode(kubeconfig.encode('utf-8'))
    kubeconfig = kubeconfig.decode('utf-8')
    
    metadata = kubernetes.client.V1ObjectMeta(name=clustername + "-kubeconfig")
    secret = kubernetes.client.V1Secret(data={"kubeconfig":kubeconfig}, type="Opaque", metadata=metadata) 

    id = 1
    try:
        
        api_instance.create_namespaced_secret(namespace="orchestration", body=secret)
        
        
        api_instance = kubernetes.client.CustomObjectsApi(api_client)
        orchestration_custom_resource = api_instance.get_namespaced_custom_object(
            group= "charity-project.eu",
            version="v1",
            namespace="default",
            plural="lowlevelorchestrations",
            name="kubeadm-based-orchestration"
        )

        
        for cluster in orchestration_custom_resource["spec"].get("clusters", []):
            if clustername == cluster.get("name"):
                orchestration_custom_resource["spec"]["clusters"].remove(cluster)
                cluster["kubeconfig"] = str(clustername) + "-kubeconfig" 
                orchestration_custom_resource["spec"]["clusters"].append(cluster)
        
        api_instance.patch_namespaced_custom_object(
            group= "charity-project.eu",
            version="v1",
            namespace="default",
            plural="lowlevelorchestrations",
            name="kubeadm-based-orchestration",
            body=orchestration_custom_resource
        )        
        
    except ApiException as e:
        print(e.reason)
    except Exception as e:
        raise e
    
    

def external_uninstall_cluster(ssh_identity_file, remote_ip, local_dir, username):
    try:
        
        rsa_key = paramiko.RSAKey.from_private_key_file(ssh_identity_file, password=None)
        
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=remote_ip, username=username, pkey=rsa_key)

        scp_client = ssh_client.open_sftp()
        
        if ipaddress.ip_address(remote_ip).is_private:
            sudo = ""
            remote_dir = f"/home"
        else:
            sudo = "sudo"
            remote_dir = f"/home/{username}"

        try:
            scp_client.stat(remote_dir + "/uninstall_cluster")
        except FileNotFoundError:
            scp_client.mkdir(remote_dir + "/uninstall_cluster")
        
        
        scp_client.put(local_dir + "/uninstall-management-cluster.sh", remote_dir + "/uninstall_cluster/uninstall_cluster.sh")
        
        scp_client.close()
        
        
        
        command = f"cd {remote_dir}/uninstall_cluster && chmod +x uninstall_cluster.sh && ./uninstall_cluster.sh {sudo}"
        log.info(command)
        stdin, stdout, stderr = ssh_client.exec_command(command)

        for line in iter(stdout.readline, ""):
            log.info(line.strip())




    except Exception as e:
        log.info(f"Error: {e}")
        raise e



def delete_kubeconfig_secret(cluster_name):
    

    kubernetes.config.load_kube_config(os.environ["CAPI_KUBECONFIG"])

    api_client = kubernetes.client.ApiClient()
    api_instance = kubernetes.client.CoreV1Api(api_client)
    

    try:
        
        api_response = api_instance.delete_namespaced_secret(name=cluster_name+"-kubeconfig", namespace="orchestration")
        
    except ApiException as e:
        print(e.reason)
    except Exception as e:
        raise e