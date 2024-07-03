# TODO: handle errors
import logging
import os
import subprocess
from time import sleep

import requests
import yaml

import openstack
import re
from openstack.cloud.exc import OpenStackCloudException
from timeout_decorator import timeout

from app.utils.common import timeit

log = logging.getLogger("app")


@timeit
def associateFloatingIP(cloudsPath, openstackServerName, fip):
    counter = 0

    # Initialize connection
    os.environ["OS_CLIENT_CONFIG_FILE"] = cloudsPath
    conn = openstack.connect(cloud="openstack")  # TODO: rm hard coded

    # wait for openstack instance to be ready
    server = None
    while server is None:
        log.info(
            f"wait for {openstackServerName} openstack instance to be ready"
        )
        server = conn.compute.find_server(openstackServerName)

    openstackServerName = server.name
    log.debug(f"Openstack Server: {openstackServerName}, fip {fip}")

    # associate the fip
    while True:
        try:
            conn.add_ip_list(server, fip)
            log.info(
                f"Associated floating IP {fip} with {openstackServerName}"
            )
            return fip
        except OpenStackCloudException as e:
            log.info(
                f"Failed to associate Floating IP {fip} "
                f"with {openstackServerName}: {e}"
            )
            log.info("Retrying...")
            sleep(1)
            counter += 1
            if counter >= 300:
                raise Exception("Floating IP Association Timed Out.")
            continue

def getDatacenterFlavors(cloudsPath):
    os.environ["OS_CLIENT_CONFIG_FILE"] = cloudsPath
    conn = openstack.connect(cloud="openstack")

    flavors = conn.compute.flavors()
    
    output = []
    
    for flavor in flavors:
        
        output.append(
                {
                "flavor": flavor.name,
                "memSizeGb": int(flavor.ram) / 1024,
                "cpuSize": flavor.vcpus,
                "diskSizeGb": flavor.disk    
            
                }
            )
        
        
    return output

def getlocation(cloudsPath):
    
    with open(cloudsPath, 'r') as file:
        yaml_data = yaml.safe_load(file)
    
    url = yaml_data.get('clouds').get("openstack").get("auth").get("auth_url")


    url = url.split(":")
    
    ip_address = url[1].strip("/")
    
    response = {}
    location_data = {
            "city": response.get("city", "Zurich"),
            "region": response.get("region", "Zurich"),
            "country": response.get("country_name", "Switzerland"),
            "latitude": response.get("latitude", 47.3682),
            "longitude": response.get("longitude", 8.5671)
    }
    
    
    return location_data


def getDatacenterNodes(cloudsPath):
    os.environ["OS_CLIENT_CONFIG_FILE"] = cloudsPath
    conn = openstack.connect(cloud="openstack")

    hypervisors = conn.compute.hypervisors(details=True)
    
    flavor_counts = {}
    number_of_cpus = 16

    for hypervisor in hypervisors:
        number_of_cpus = hypervisor.vcpus
        
        


    nodes_number =number_of_cpus-6

    conn.close()

    return nodes_number

def getDatacenterClusters(cloudsPath):
    os.environ["OS_CLIENT_CONFIG_FILE"] = cloudsPath
    conn = openstack.connect(cloud="openstack")

    clusters = conn.compute.servers()
    
    clusters_name = {}
       
    
    clusters_name = [{"name": cluster.name.split("-")[0]} for cluster in clusters]
    
    conn.close()
    return clusters_name


def getOpenstackMachineName(clusterName):
    counter = 0
    cmd = (
        "kubectl --kubeconfig="
        + os.environ["CAPI_KUBECONFIG"]
        + " get openstackmachine -o 'jsonpath={.items[*].metadata.name}' -n default"
    )
    # lookup for openstack instance name
    openstackMachineName = None
    while True:
        log.info("Looking up for openstack instance on Openstack")
        output, error = subprocess.Popen(
            cmd,
            universal_newlines=True,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).communicate()
        openstackMachineName = re.search(
            "(.*)(" + clusterName + "-control-plane-.{5})(.*)", output
        )
        if openstackMachineName is not None:
            return openstackMachineName.group(2)  # unpack and return value
        sleep(1)
        counter += 1
        if counter >= 300:
            raise Exception("Get OpenStack Machine Timed Out.")
    

### NEEDS CORRECTION
def getOpenStackAvailableResources(cloudsPath):
    cloudsPath = cloudsPath + "/" + "clouds.yaml"

    os.environ["OS_CLIENT_CONFIG_FILE"] = cloudsPath
    conn = openstack.connect(cloud="openstack")

    quotas = conn.compute.quotas.list(cloudsPath.get("project_id"))
    usage = conn.compute.get_usage(cloudsPath.get("project_id"))
    available_cpu = quotas.cores - usage['total_cores_used']
    available_ram = quotas.ram - usage['total_ram_used']
    available_disk = quotas.gigabytes - usage['total_disk_used']

    flavors = conn.compute.flavors()

    filtered_flavors = []
    for flavor in flavors:
        if flavor.vcpus <= available_cpu and flavor.ram <= available_ram and flavor.disk <= available_disk:
            filtered_flavors.append(flavor)

    log.info("Filtered Flavors:")
    for flavor in filtered_flavors:
        log.info(flavor)
