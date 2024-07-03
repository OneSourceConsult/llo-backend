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

from timeout_decorator import timeout

from app.schemas.Provider import Provider
from app.controllers.common import timeit
from app.controllers.providers.openstack import (
    getDatacenterFlavors,
    getDatacenterNodes,
    getlocation,
)
from app.controllers.providers.external import get_dc_configuration, get_external_clusters

log = logging.getLogger("app")

# load a list of providers settings
# using a tree-based file structure like:
# root
# |_ providerType    (currently only CAPO was tested)
# |___ providerX
# |_____ providerXRequiredFiles (e.g., for CAPO: clouds.yaml,
# |                              kubeadm-openstack.env,
# |                              generate_cluster_kubeadm.sh)
# |___ providerY
# |_____ provideryRequiredFiles

@timeit
def loadProvidersFromConfig():
    # log.debug(f"Loading Providers from {os.environ['CAPI_PROVIDERS_PATH']}")

    providers: Dict[UUID, Provider] = {}

    path = os.environ["CAPI_PROVIDERS_PATH"]

    required_files = os.environ.get("CAPO_PROVIDERS_REQUIRES_FILES").split(",")
    for item in os.listdir(path):
        if "capo" == item:  # Openstack type
            path = os.path.join(path, item)
            for cloud in os.listdir(path):
                rootPath = os.path.join(path, cloud)
                for (
                    file
                ) in required_files:  # basic test for some required files
                    if os.path.exists(rootPath + "/" + file):
                        continue
                    else:
                        raise ValueError(f"Required File {file} is missing")

                c = Provider(
                    type="openstack",
                    name=cloud,
                    rootConfigPath=rootPath,
                    cloudsPath=rootPath
                    + "/clouds.yaml",  # using default files
                    caCert=rootPath + "/cacert.pem",  # names for now
                )
                providers[c.uuid] = c
        elif "external" == item:
            path = os.path.join(path, item)
            for cloud in os.listdir(path):
                rootPath = os.path.join(path, cloud)
                c = Provider(
                    type="external",
                    name=cloud,
                    rootConfigPath=rootPath,
                    cloudsPath="",
                    # using default files
                    caCert="",  # names for now
                )
                providers[c.uuid] = c
                
        path = os.environ["CAPI_PROVIDERS_PATH"]
                
    log.info("Loaded providers:")
    log.info(providers)
    return providers

@timeit
def loadProviders():
    # log.debug(f"Loading Providers from {os.environ['CAPI_PROVIDERS_PATH']}")

    providers = []
    
    path = os.environ["CAPI_PROVIDERS_PATH"]

    for item in os.listdir(path):
        prov_path = os.path.join(path, item)
        for cloud in os.listdir(prov_path):
            log.info(cloud)
            providers.append(loadProviderByName(cloud))
                
    log.info("Loaded providers")
    return providers

@timeit
def loadProviderByName(provider_name):
    # log.debug(f"Loading Providers from {os.environ['CAPI_PROVIDERS_PATH']}")

    c = {}

    path = os.environ["CAPI_PROVIDERS_PATH"]

    for item in os.listdir(path):
        if "capo" == item:  # Openstack type
            path = os.path.join(path, item)
            for cloud in os.listdir(path):
                rootPath = os.path.join(path, cloud)

                if cloud == provider_name:
                    cloudsPath = rootPath + "/" + "clouds.yaml"
                    c = {
                        "type":"openstack",
                        "name" : cloud,
                       
                        "location": 
                            getlocation(cloudsPath)
                        ,
                        "flavors": 
                           getDatacenterFlavors(cloudsPath)
                        ,
                        "nodes": 
                           getDatacenterNodes(cloudsPath)
                        ,
                        "clusters":
                            # getDatacenterClusters(cloudsPath)
                            get_external_clusters(cloud)
                        ,
                         "gpus": [
                               {
                                   "model": "NVIDIA GeForce RTX 3080",
                                    "units": 0
                                }
                        ],
                        "internalBandwidthMbps": 1000,
                        "internalLatencyMillis": 2,
                        "externalBandwidthMbps": 10000
                        }
                    break
                    
        elif "external" == item:
            path = os.path.join(path, item)
            for cloud in os.listdir(path):
                if cloud == provider_name:
                    rootPath = os.path.join(path, cloud)
                    c = get_dc_configuration(cloud)
                    c["type"] = "external"
                    c["name"] = cloud
                    c["internalBandwidthMbps"] = 1000
                    c["internalLatencyMillis"] = 2
                    c["externalBandwidthMbps"] = 10000
                    c["clusters"]= get_external_clusters(cloud)
                
                        
                    break
                
        path = os.environ["CAPI_PROVIDERS_PATH"]
        
    log.info("Loaded provider")
    return c

def checkDatacenterProvider(datacenter):
    
    datacenters = loadProvidersFromConfig()
    
    for uuid, provider in datacenters.items():
        if provider.name == datacenter:
            return provider.type

    return None
