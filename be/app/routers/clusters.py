import json
import logging
import requests
import os
import traceback
from http import HTTPStatus
from typing import Dict, List
import yaml
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Request, Path
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError

from app.schemas.Cluster import new_rules


from app.schemas.ClusterCRD import APP_EXAMPLE, KUBECONFIG_EXAMPLE, TOSCA_EXAMPLE, toscaNew, TOSCA_EXAMPLE2, TOSCA_EXAMPLE3, TOSCA_EXAMPLE_DOTES, TOSCA_EXAMPLEV4, WEBAPP_EXAMPLE
from app.schemas.Cluster import CLUSTER_EXAMPLES, CLUSTER_EXAMPLES_OLD, LIST_CLUSTERS_EXAMPLE, ClusterRequest
from app.schemas.Task import Task
from app.controllers.clusters.capi import (
    addClusterToCRD,
    delete_cluster_from_CRD,
    deleteClusterByName,
    createAndScheduleCluster,
    getClusterByName,
    getClusterList,
    getClusterListFromCAPI,
    clusterUpdate,
    getControlPlane,

    deleteClusterFromCRD,
    createClusterToCRD,
    getKubeconfigFromClusterctl,
    update_CRD_Status,
)

from app.controllers.clusters.liqo import (
    peerClusters
)

from app.controllers.deployments.deployments import (

    apply_new_alerts,
    deleteAppFromCRD,
    install_app,
    toscaConversion,
    toscaDeleteApp,
    toscaGetAppByID,
    toscaGetAppList,
    unoffload_and_delete_app,
    update_deployment,
    updateCRD
)


from app.controllers.providers.common import (

    loadProviderByName,
    loadProviders
)

router = APIRouter()
log = logging.getLogger(__name__)


@router.post("/deploycluster", tags=["clusters"], status_code=HTTPStatus.ACCEPTED, response_model=Task, summary="Create a new Cluster")
async def create_cluster(
    background_tasks: BackgroundTasks,
    req: Request,
    providerName: str = "c01",
    cReq: ClusterRequest = Body(examples=CLUSTER_EXAMPLES_OLD),
):
    """
    This endpoint is designed to receive requests from the operator to create a new cluster

    - It will respond to a request to create a new cluster and creates the new cluster with the specifications given in the body of the request. 

    - It populates a new cluster object with the needed attributes, given by the cluster request object that comes in the body of the request.

    - It gets the new Cluster CRD and applies it.

    - It gets the kubeconfig of the new cluster and the IP of the cluster.

    - It gets the open stack machine name associated with the cluster and associates the IP to that machine.

    - It waits for the cluster to be ready and installs the needed packages (MetalLB, NGINX, Prometheus, and LIQO).

    Input:

    - Cluster Request

    - String with the name of the provider

    Output:

    - Status of the request


    """

    providers = req.app.state.providers
    tasks = req.app.state.tasks
    log.info(cReq.datacenter)
    log.info(cReq.clusterName)

    try:
        provider = next(
            (
                providers[uuid]
                for uuid in providers
                if providers[uuid].name == cReq.datacenter
            ),
            None,
        )
        if provider is None:
            update_CRD_Status(cReq.clusterName, "error", "clusters")
            raise ValueError("Provider Not Found")

        log.info("Scheduling on provider " + provider.name)
        task = Task()
        tasks[task.uuid] = task
        background_tasks.add_task(
            createAndScheduleCluster, cReq, provider, task=task)
        return task

    except ValueError as e:
        log.error("A value error exception occurred: {}".format(e))
        raise HTTPException(status_code=500, detail="{}".format(e))
    except Exception as e:
        tb = traceback.format_exc()
        log.error("An exception occurred: {}".format(tb))
        raise HTTPException(status_code=500, detail="{}".format(e))


# Blindly attempt to rm CAPI cluster by name in best effort
@router.delete(
    "/deletecluster/{name}/{providerName}",
    tags=["clusters"],
    status_code=HTTPStatus.ACCEPTED, summary="Delete an Existent Cluster",
    response_model=Task
)
async def clusterDelete(
    background_tasks: BackgroundTasks,
    req: Request,
    providerName: str = "c01",
    name: str = "gdf-cluster",
):
    """
    This endpoint is designed to delete a given cluster.
    - It receives the name of a cluster and executes the kubectl command to delete the cluster.

    Input

    - String with the name of the cluster

    Output

    - Status of the request

    """
    tasks = req.app.state.tasks
    providers = req.app.state.providers

    try:
        provider = next(
            (
                providers[uuid]
                for uuid in providers
                if providers[uuid].name == providerName
            ),
            None,
        )
        if provider is None:
            raise ValueError("Provider Not Found")

        task = Task()
        tasks[task.uuid] = task

        # TODO: ftb this atempts to delete from CAPI regardless of provider
        log.info("Requested deletion of cluster " + name)
        background_tasks.add_task(
            deleteClusterByName, name, provider, task=task)
        return task

    except ValueError as e:
        log.error("A value error exception occurred: {}".format(e))
        raise HTTPException(status_code=500, detail="{}".format(e))
    except Exception as e:
        tb = traceback.format_exc()
        log.error("An exception occurred: {}".format(tb))
        raise HTTPException(status_code=500, detail="{}".format(e))

# List running clusters


@router.get("/getclusters", tags=["clusters"], summary="Get a List of Existent Clusters",
            responses={200: {"description": "JSON With Specifications of Current Clusters.", "content": {
                "application/json": {
                    "example": LIST_CLUSTERS_EXAMPLE
                }
            }
            }
}
)
def list_clusters():
    """
    This endpoint is designed to retrieve a list of clusters. 
    - It loads the CAPI configuration

    - It requests to the Kubernetes API for the deployed Clusters.

    Input

    - None

    Output

    - Dictionary with the clusters and its specifications.

    """
    return getClusterListFromCAPI()


@router.get("/cp", tags=["clusters"],
            summary="Get The IP of the Control Plane of a specific Cluster",
            responses={200: {"description": "String with the IP of the control plane", "content": {
                "application/json": {
                    "example": "192.168.1.1"
                }
            }
            }
})
def list_controlPlane(
    name: str = "gdf-cluster",
):
    """
    This endpoint is designed to retrieve the IP of the control plane of a given cluster.
    - It loads the CAPI configuration

    - It does a request to the Kubernetes API for the Custom Object controlplane of the given cluster

    - It extracts the host of the control plane endpoint.

    Input

    - String with the name of the cluster to get the control plane IP.


    Output

    - String with the value of the Cluster Control Plane IP.

    """
    return getControlPlane(name)


@router.post("/app", tags=["apps"], status_code=HTTPStatus.ACCEPTED,
             summary="Install Applications defined in a TOSCA File",
             responses={202: {"description": "YAML with the Kubeconfig Generated.", "content": {
                 "application/json": {
                     "example": KUBECONFIG_EXAMPLE
                 }
             }
             }
}
)
def tosca_request(
    toscaData: dict = Body(..., example=TOSCA_EXAMPLE)

):
    """

    This endpoint is designed to translate a TOSCA file to a CRD readable by the low level orchestrator operator and install the apps specified in it:

    - It receives a Tosca file and extracts information like the owner and the name.

    - It extracts the list of external links of each component. 

    - It goes through the nodes in the TOSCA file and initiates the variables of each non-external component, such as the name and the cluster where the app will be deployed. There is also the attribution of environment variables if there are any. 

    - It attributes the componenents that needs to be exposed by service.

    - It updates the CRD of the low level orchestrator.

    - It installs the applciations specified in the TOSCA file.

    Input: 

    - YAML with the TOSCA file

    Output:

    - The status of the operation

    - A kubeconfig file


    """
    response = toscaConversion(toscaData)

    return response
    # status
    # kubeconfig


@router.delete("/app/{uuid}", tags=["apps"], status_code=HTTPStatus.ACCEPTED,
               summary="Delete an Application from the low level orchestrator CRD",
               responses={202: {"description": "Successful Response", "content": {
                   "application/json": {
                       "example": "App Successfully Deleted"
                   }
               }
               }
}
)
def tosca_delete(
    appName: str = "app-name"
):
    """
    This endpoint is designed to delete an app from the low level orchestrator CRD.

    - It loads the kubeconfig and gets the current CRD with a request to Kubernetes API.

    - It checks if there are any apps in the CRD, if not, it skips the following steps and does nothing.

    - If there are apps in the current CRD, it goes through the apps present in the current CRD and checks if there is an app with the same name, if so, the function removes it from the CRD. 

    - It patches the new CRD into Kubernetes.

    - It Uninstalls the application. 

    Input: 

    - String with the name of te app to be deleted

    Output:

    - The status of the operation
    """
    return toscaDeleteApp(appName)
    # status


@router.get("/apps", tags=["apps"], status_code=HTTPStatus.ACCEPTED,
            response_model=List[str],
            summary="Get a list with the apps of a given owner",
            responses={202: {"description": "Successful Response",
                             "content": {
                                 "application/json": {
                                     "examples": {
                                         "example1": {
                                             "summary": "Example 1",
                                             "value": ["app1", "app2"]
                                         },
                                         "example2": {
                                             "summary": "Example 2",
                                             "value": ["webapp", "database"]
                                         },
                                         "dotes": {"summary": "dotes",
                                                   "value":  ["cyango-backend", "cyango-cloud-editor", "cyango-database", "cyango-worker", "cyango-story-express"]
                                                   }
                                     }
                                 }
                             }
                             }

                       })
def tosca_app_print(
    owner: str = "owner-id"
):
    """
    This enpoint is designed to retrieve a list with the apps in the CRD of a given owner.

    - It gets the CRD present in the orchestrator. 

    - It iterates over the apps defined in the CRD 

    - It returns the list with all the apps of the specified owner.

    Input

    - String with the name/identifier of the owner.

    Output

    - List of the apps of a given owner, each app is a dictionary with the apps components. 


    """
    return toscaGetAppList(owner)

# ----------------------- xrapplications -----------------------------------------------


@router.post("/xrapplicationdeployment", tags=["LowLevelOrchestrator/Deployments"], status_code=HTTPStatus.ACCEPTED, summary="Deploy an XR Service on Cluster Domains",
             responses={202: {"description": "Successful Response", "content": {
                 "application/json": {
                     "examples": {
                         "example": {
                             "summary": "Pending",
                             "value": {
                                 "status": "pending",
                                 "id": "1",
                             }
                         }
                     }
                 }
             }
             }
}
)
def xr_application_deployment(
        background_tasks: BackgroundTasks,
        req: Request,
        toscaData: dict = Body(..., example={
                               "id": "1a", "toscaFullModel": toscaNew})

):
    """
    Low Level Orchestrator deployment of a Full TOSCA Template
    """

    response = toscaConversion(toscaData)

    return response


@router.put("/xrapplicationdeployment", tags=["LowLevelOrchestrator/Deployments"], status_code=HTTPStatus.ACCEPTED, summary="Redeploy an XR Service on Cluster Domains",
            responses={202: {"description": "Successful Response", "content": {
                "application/json": {
                    "examples": {
                        "example": {
                                            "summary": "Pending",
                                            "value": {
                                                "status": "pending",
                                                "id": "1",
                                            }
                        }
                    }
                }
            }
            }
}
)
def xr_application_redeployment(
    background_tasks: BackgroundTasks,
    req: Request,
        toscaData: dict = Body(..., example={
                               "id": "app_id", "toscaFullModel": toscaNew})

):
    """
    Low Level Orchestrator redeployment of an updated Full TOSCA Template

    """

    # response = toscaConversion(toscaData)

    tasks = req.app.state.tasks
    task = Task()
    tasks[task.uuid] = task
    background_tasks.add_task(update_deployment, toscaData)

    return {"id": toscaData["id"], "status": "pending"}


@router.get("/xrapplicationdeployment/{id}", tags=["LowLevelOrchestrator/Deployments"], status_code=HTTPStatus.ACCEPTED, summary="Get low level deployment info on XR Service instance",
            responses={202: {"description": "Successful Response",
                             "content": {
                                 "application/json": {
                                     "examples": {

                                         "example-running": {
                                             "summary": "Running",
                                             "value": {
                                                 "status": "running",
                                                 "id": "1",
                                                 "output_parameters": [
                                                     {
                                                         "name": "component_cluster",
                                                         "value": "cluster"
                                                     },
                                                     {
                                                         "name": "component_datacenter",
                                                         "value": "datacenter"
                                                     },
                                                     {
                                                         "name": "component_deployment_context",
                                                         "value": "apiVersion: v1\nclusters:\n- cluster:\n    certificate-authority-data: CAD=\n    server: https://IP:PORT\n  name: cluster\ncontexts:\n- context:\n    cluster: cluster\n    user: cluster-admin\n  name: cluster-admin@cluster\ncurrent-context: cluster-admin@cluster\nkind: Config\npreferences: {}\nusers:\n- name: cluster-admin\n  user:\n    client-certificate-data: CCD=\n    client-key-data: CKD==\n\n"
                                                     },
                                                     {
                                                         "name": "component_latitude",
                                                         "value": "47.17266994976023"
                                                     },
                                                     {
                                                         "name": "component_longitude",
                                                         "value": "8.513652690561807"
                                                     },
                                                     {
                                                         "name": "component_namespace",
                                                         "value": "namespace"
                                                     },
                                                     {
                                                         "name": "component_url",
                                                         "value": "component.namespace.charity-project.eu/"
                                                     }
                                                 ]
                                             }
                                         },
                                         "example-pending": {
                                             "summary": "Pending",
                                             "value": {
                                                 "status": "pending",
                                                 "id": "1",

                                             }
                                         }
                                     }
                                 }
                             }
                             }
                       }
            )
def tosca_app_print_by_id(
    id: str = Path(..., title="The ID of the XR Application Deployment")
):
    """


    """

    return toscaGetAppByID((id))


@router.delete("/xrapplicationdeployment/{id}", tags=["LowLevelOrchestrator/Deployments"], status_code=HTTPStatus.ACCEPTED,
               summary="Undeploy an XR Service instance from Cluster Domains",
               responses={202: {"description": "Successful Response", "content": {
                   "application/json": {
                       "example": "App Successfully Uninstalled"
                   }
               }
               }
}
)
def undeployApp(
    background_tasks: BackgroundTasks,
    req: Request,

    id: str = Path(..., title="The ID of the XR Application Deployment")
):
    """


    """

    response = deleteAppFromCRD(id)
    # return undeploy_app(id)
    return response


@router.post("/clusters", tags=["LowLevelOrchestrator/Clusters"], status_code=HTTPStatus.ACCEPTED,
             summary="Allocate a new Cluster at a Datacenter",
             responses={202: {"description": "Successful Response", "content": {
                 "application/json": {
                     "example": {
                         "status": "pending",
                         "name": "name"
                     }
                 }
             }
             }
}
)
def allocate_cluster(
    cluster_data: dict = Body(examples=CLUSTER_EXAMPLES)

):
    """

    """

    return addClusterToCRD(cluster_data)


@router.get("/clusters/{cluster}", tags=["LowLevelOrchestrator/Clusters"], summary="Get info on a Cluster",
            responses={200: {"description": "JSON With Specifications of Current Clusters.", "content": {
                "application/json": {
                    "example": {"name": "gdf-cluster",
                                "status": "running",
                                "datacenter": "openstack",
                                "kubernetesType": "kubeadm",
                                "kubernetesVersion": "v1.28.0",
                                "control": {
                                    "flavor": "m1.medium",
                                    "units": 1
                                },
                                "workers": {
                                    "flavor": "m1.medium",
                                    "units": 0
                                },
                                "image": "ubuntu-22.04-server-cloudimg-amd64-disk-kvm",
                                "monitoringIp": "<IP>:<Port>"}
                }
            }
            }
}
)
def get_cluster_by_name(
    cluster: str = Path(..., title="The name of the Cluster")
):
    """

    """
    return getClusterByName(cluster)


@router.get("/clusters", tags=["LowLevelOrchestrator/Clusters"], summary="Get list of existent Cluster",
            responses={200: {"description": "List With Specifications of Current Clusters.", "content": {
                "application/json": {
                    "example": [{"name": "gdf-cluster",
                                 "status": "running",
                                 "datacenter": "openstack",
                                 "kubernetesType": "kubeadm",
                                 "kubernetesVersion": "v1.28.0",
                                 "control": {
                                     "flavor": "m1.medium",
                                     "units": 1
                                 },
                                 "workers": {
                                     "flavor": "m1.medium",
                                     "units": 0
                                 },
                                 "image": "ubuntu-22.04-server-cloudimg-amd64-disk-kvm",
                                 "monitoringIp": "<IP>:<Port>"}]
                }
            }
            }
}
)
def get_clusters(
):
    """

    """
    return getClusterList()


@router.delete("/clusters/{cluster}", tags=["LowLevelOrchestrator/Clusters"], status_code=HTTPStatus.ACCEPTED,
               summary="Deallocate a Cluster",
               responses={202: {"description": "Successful Response", "content": {
                   "application/json": {
                       "example": "Cluster Successfuly Deallocated"
                   }
               }
               }
}
)
def delete_cluster_by_name(
    cluster: str = Path(..., title="The name of the Cluster")
):
    """

    """

    return delete_cluster_from_CRD(cluster)


@router.get("/datacenters/{datacenter}", tags=["LowLevelOrchestrator/Datacenters"], status_code=HTTPStatus.ACCEPTED, summary="Get info about a Datacenter",

            responses={202: {"description": "Successful Response",
                             "content": {
                                 "application/json": {
                                     "examples": {

                                         "example-running": {
                                             "summary": "Example",
                                             "value": {

                                                 "name": "string",
                                                 "location": {
                                                        "region": "string",
                                                        "country": "string",
                                                        "city": "string",
                                                        "latitude": 0.0,
                                                        "longitude": 0.0
                                                 },
                                                 "flavors": [
                                                     {
                                                         "flavor": "S",
                                                         "cpuSizeGb": 0,
                                                         "memSize": 0,
                                                         "diskSizeGb": 0
                                                     }
                                                 ],
                                                 "nodes": 2,
                                                 "clusters": [
                                                     {
                                                         "name": "string"
                                                     }
                                                 ],
                                                 "gpus": [
                                                     {
                                                         "model": "string",
                                                         "units": 0
                                                     }
                                                 ],
                                                 "internalBandwidthMbps": 0,
                                                 "internalLatencyMillis": 0,
                                                 "externalBandwidthMbps": 0

                                             }
                                         }
                                     }
                                 }
                             }
                             }
                       }
            )
def get_datacenter_by_name(
    datacenter: str = Path(..., title="The name of the Datacenter")
):
    """


    """

    return loadProviderByName(datacenter)


@router.get("/datacenters", tags=["LowLevelOrchestrator/Datacenters"], status_code=HTTPStatus.ACCEPTED, summary="Get info about all Datacenters",
            responses={202: {"description": "Successful Response",
                             "content": {
                                 "application/json": {
                                     "examples": {

                                         "example-running": {
                                             "summary": "Example",
                                             "value": [
                                                     {

                                                         "name": "string",
                                                         "location": {
                                                             "region": "string",
                                                             "country": "string",
                                                             "city": "string",
                                                             "latitude": 0.0,
                                                             "longitude": 0.0
                                                         },
                                                         "flavors": [
                                                             {
                                                                 "flavor": "S",
                                                                 "cpuSizeGb": 0,
                                                                 "memSize": 0,
                                                                 "diskSizeGb": 0
                                                             }
                                                         ],
                                                         "nodes": 2,
                                                         "clusters": [
                                                             {
                                                                 "name": "string"
                                                             }
                                                         ],
                                                         "gpus": [
                                                             {
                                                                 "model": "string",
                                                                 "units": 0
                                                             }
                                                         ],
                                                         "internalBandwidthMbps": 0,
                                                         "internalLatencyMillis": 0,
                                                         "externalBandwidthMbps": 0

                                                     }

                                             ]


                                         }
                                     }
                                 }
                             }
                             }
                       }
            )
def get_datacenters_list(

):
    """


    """
    return loadProviders()


@router.get("/testendpoint/{clusterName}", tags=["test"], status_code=HTTPStatus.ACCEPTED, summary="TEST")
def get_datacenters_list(
    clusterName: str = Path(..., title="The name of the cluster"),
):
    """


    """
    # path = os.environ["CAPI_PROVIDERS_PATH"]

    # required_files = os.environ.get("CAPO_PROVIDERS_REQUIRES_FILES").split(",")
    # for item in os.listdir(path):
    #     if "capo" == item:  # Openstack type
    #         path = os.path.join(path, item)
    #         for cloud in os.listdir(path):
    #             rootPath = os.path.join(path, cloud)
    #             for (
    #                 file
    #             ) in required_files:  # basic test for some required files
    #                 if os.path.exists(rootPath + "/" + file):
    #                     continue
    #                 else:
    #                     raise ValueError(f"Required File {file} is missing")

    # url = f"http://monitoring-manager.plexus.charity-project.eu/monitoring/create-cluster?datacenter={datacenter}&cluster={clusterName}"
    # response = requests.get(url)
    return "Success"


@router.post("/alertmanager", tags=["LowLevelOrchestrator/Monitoring"], status_code=HTTPStatus.ACCEPTED, summary="Change the Alert Manager Configuration of a Given Cluster",
             responses={202: {"description": "Successful Response", "content": {
                 "application/json": {
                     "examples": {
                         "example": {
                             "summary": "Pending",
                             "value": {
                                 "status": "pending",
                                 "id": "1",
                             }
                         }
                     }
                 }
             }
             }
}
)
def alertManagerConfiguration(
        background_tasks: BackgroundTasks,
        req: Request,
        new_conf: dict = Body(..., example={"new_conf": new_rules}),
        cluster: str = "blue"

):
    """
    Alert Manager Reconfiguration
    """

    response = apply_new_alerts(new_conf["new_conf"], cluster)

    return response


# Blindly attempt to rm CAPI cluster by name in best effort
# @router.delete(
#     "/unpeer/{name}",
#     tags=["test"],
#     status_code=HTTPStatus.ACCEPTED, summary="Delete an Existent Cluster")
# async def clusterUnpeer(
#     background_tasks: BackgroundTasks,
#     req: Request,
#     name: str = "gdf-cluster",
# ):
#     """
#     This endpoint is designed to delete a given cluster.
#     - It receives the name of a cluster and executes the kubectl command to delete the cluster.

#     Input

#     - String with the name of the cluster

#     Output

#     - Status of the request

#     """

#     try:

#         delete_cluster_from_CRD(name)
#         return "yey"

#     except ValueError as e:
#         log.error("A value error exception occurred: {}".format(e))
#         raise HTTPException(status_code=500, detail="{}".format(e))
#     except Exception as e:
#         tb = traceback.format_exc()
#         log.error("An exception occurred: {}".format(tb))
#         raise HTTPException(status_code=500, detail="{}".format(e))


# --------------------------------------------------------------------------------------------------

@router.post("/installapp", tags=["clusters"], status_code=HTTPStatus.ACCEPTED,
             responses={202: {"description": "Successful Response", "content": {
                 "application/json": {
                     "example": "App Successfully Installed"
                 }
             }
             }
})
def install_application(
    background_tasks: BackgroundTasks,
    req: Request,
    appData=Body(APP_EXAMPLE)
):
    """

    This endpoint is designed to install an application in a cluster.

    - It gets the kubeconfig of the cluster 

    - It checks if the cluster is able to run nodes in the control plane.

    - It labels the cluster for offloading purposes and creates the namespace where the app will run. 

    - It applies the orchestrator secret, in the created namespace, to pull the images of the app 

    - It applies the tls certificate to access the domain where the app can be exposed, by ingress, in a secure way. 

    - It offloads the namespace to all the peered clusters

    - It gets the list of the needed services for the application. 

    - It applies the deployment for every component in the app.  

    - It applies the ingress and services if required.

    - It offloads the app to the cluster specified in the component data.

    Input

    - Dictionary with the specifications of the app to be installed.

    Output

    - Status of the request

    """

    tasks = req.app.state.tasks
    task = Task()
    tasks[task.uuid] = task
    response = background_tasks.add_task(install_app, appData)

    return response


@router.delete("/uninstallapp", tags=["clusters"], status_code=HTTPStatus.ACCEPTED,
               summary="Uninstall an Application",
               responses={202: {"description": "Successful Response", "content": {
                   "application/json": {
                       "example": "App Successfully Uninstalled"
                   }
               }
               }
}
)
def uninstallapp(
    background_tasks: BackgroundTasks,
    req: Request,
    cluster: str,
    name: str,
    id: str
):
    """
    This endpoint is designed to unoffload a namespace from one cluster to another. 

    - It gets the kubeconfig of the cluster where the namespace is contained

    - It runs the liqoctl command to unoffload a namespace

    - It runs the kubectl command to delete the namespace.

    Input

    - String with the name of the cluster where the app is running.

    - String with the name of the namespace where the app to be unoffloaded and deleted is held.

    Output

    - Status of the Request

    """
    tasks = req.app.state.tasks
    task = Task()
    tasks[task.uuid] = task
    background_tasks.add_task(unoffload_and_delete_app, cluster, name, id)
    return "App schedulled for deletion"


@router.delete("/deleteclusterCRD", tags=["clusters"], status_code=HTTPStatus.ACCEPTED,
               summary="Delete a Cluster from the CRD",
               responses={202: {"description": "Successful Response", "content": {
                   "application/json": {
                       "example": "Cluster Successfuly Removed from the CRD"
                   }
               }
               }
}
)
def delete_cluster(
    clusterName: str = "greencluster"
):
    """
    This endpoint is designed to delete a cluster from the low orchestrator CRD.

    - It loads the kubeconfig and gets the current CRD with a request to Kubernetes API. 

    - It checks if there are any clusters in the CRD, 

        - If not, it skips the following steps and does nothing. 

        - If there are clusters in the current CRD, it goes through the clusters present in the current CRD and checks if there is a cluster with the same name

            - If so, removes it from the CRD. 

    - It patches the new CRD into Kubernetes.
    """
    log.info(clusterName)
    return deleteClusterFromCRD(clusterName)


@router.post("/createclusterCRD", tags=["clusters"], status_code=HTTPStatus.ACCEPTED,
             summary="Add a Cluster to the CRD",
             responses={202: {"description": "Successful Response", "content": {
                 "application/json": {
                     "example": "Cluster Successfuly Added to the CRD"
                 }
             }
             }
})
def create_cluster(
    appData=Body({})
):
    """
    This endpoint is designed to add clusters to the low orchestrator CRD.

    - It loads the kubeconfig and gets the current CRD with a request to Kubernetes API. 

    - It checks if there are any clusters in the CRD:

        - If not, it adds the cluster present in the new CRD. 

        - If there are clusters in the current CRD, it goes through the clusters present in the current CRD and checks if there is a cluster with the same name:

            - If so, the function adds it to the CRD. 

    - It patches the new CRD into Kubernetes.

    Input

    - YAML file containing the new CRD.


    Output

    - Status of the request.

    """

    return createClusterToCRD(appData)


@router.post("/installappCRD", tags=["clusters"], status_code=HTTPStatus.ACCEPTED,
             summary="Add an Application to the CRD",
             responses={202: {"description": "Successful Response", "content": {
                 "application/json": {
                     "example": "Application Successfuly Added to the CRD"
                 }
             }
             }
})
def install_app_CRD(
    appData=Body({})
):
    """
    This endpoint is designed to add apps to the low orchestrator CRD.

    - It loads the kubeconfig and gets the current CRD with a request to Kubernetes API. 

    - It checks if there are any apps in the CRD:

        - If not, it adds the apps present in the new CRD. 

        - If there are apps in the current CRD:

            - It goes through the apps present in the current CRD 

            - It checks if the owner already has an app with the same name:

                - If so, the function skips all the next steps and does nothing. 

                - If the owner does not have an app with the given name, it adds the app to the CRD.     

    - It patches the new CRD into Kubernetes.

    Input

    - YAML file containing the new CRD.

    Output

    - Status of the request.

    """
    return updateCRD(appData)


@router.get("/peer", tags=["clusters"], status_code=HTTPStatus.ACCEPTED,
            summary="Peer Two Clusters",
            responses={202: {"description": "Successful Response", "content": {
                "application/json": {
                    "example": "Clusters successfuly peered"
                }
            }
            }
})
async def peer(
    background_tasks: BackgroundTasks,
    req: Request,
    providerName: str = "c01",
    greenClusterName: str = "kubeadm-based-orchestration-green",
    roseClusterName: str = "kubeadm-based-orchestration-rose",
):
    """
    This endpoint is designed to peer two given clusters using Liqo.

    - It starts by getting the kubeconfig of each cluster.

    - IT checks if Liqo is correctly installed and running in both clusters. 

    - It runs the liqoctl command to peer the clusters using the In-band approach.

    Input

    - String with the name of a first cluster to peer.

    - String with the name of a second cluster to peer.

    Output

    - Status of the request.

    """
    tasks = req.app.state.tasks
    providers = req.app.state.providers

    try:
        provider = next(
            (
                providers[uuid]
                for uuid in providers
                if providers[uuid].name == providerName
            ),
            None,
        )
        if provider is None:
            raise ValueError("Provider Not Found")

        task = Task()
        tasks[task.uuid] = task

        # TODO: ftb this atempts to delete from CAPI regardless of provider
        log.info("Requested peering of two clusters: " +
                 greenClusterName + " <-----> " + roseClusterName)
        background_tasks.add_task(
            peerClusters, greenClusterName, roseClusterName, task=task)
        return task

    except ValueError as e:
        log.error("A value error exception occurred: {}".format(e))
        raise HTTPException(status_code=500, detail="{}".format(e))
    except Exception as e:
        tb = traceback.format_exc()
        log.error("An exception occurred: {}".format(tb))
        raise HTTPException(status_code=500, detail="{}".format(e))


@router.patch(
    "/cluster/{name}",
    tags=["clusters"],
    status_code=HTTPStatus.ACCEPTED
)
async def clusterCRDUpdate(
    background_tasks: BackgroundTasks,
    req: Request,
    providerName: str = "c01",
    cReq: ClusterRequest = Body(examples=CLUSTER_EXAMPLES),
):

    tasks = req.app.state.tasks
    providers = req.app.state.providers

    try:
        provider = next(
            (
                providers[uuid]
                for uuid in providers
                if providers[uuid].name == providerName
            ),
            None,
        )
        if provider is None:
            raise ValueError("Provider Not Found")

        task = Task()
        tasks[task.uuid] = task

        log.info("Requested update of cluster " + cReq.clusterName)
        background_tasks.add_task(clusterUpdate, cReq, task=task)
        return task

    except ValueError as e:
        log.error("A value error exception occurred: {}".format(e))
        raise HTTPException(status_code=500, detail="{}".format(e))
    except Exception as e:
        tb = traceback.format_exc()
        log.error("An exception occurred: {}".format(tb))
        raise HTTPException(status_code=500, detail="{}".format(e))
