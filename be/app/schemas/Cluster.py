from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID, uuid4

CLUSTER_EXAMPLES = {
    
    "Kubeadm-DefaultValues": {
        "summary": "Kubeadm cluster with 1 control plane and 0 workers and default values",
        "description": "Default values for kubernetesType, Version and image",
        "value": {
            "name": "gdf-cluster",
            "datacenter": "openstack",
            "control":{
              "flavor": "m1.medium",
              "units": 1
            },
             "workers": {
              "flavor": "m1.medium",
              "units": 0
            }
        }}
    ,"Kubeadm": {
        "summary": "Kubeadm cluster with 1 control plane and 0 workers",
        "description": "Default values for kubeadm cluster",
        "value": {
            "name": "gdf-cluster",
            "datacenter": "openstack",
            "kubernetesType": "kubeadm",
            "kubernetesVersion": "v1.28.0",
            "control":{
              "flavor": "m1.medium",
              "units": 1
            },
             "workers": {
              "flavor": "m1.medium",
              "units": 0
            },
            "image": "ubuntu-2204-kube-v1.28.0"
        }},
    "k3s": {
        "summary": "K3s cluster with 1 control plane and 5 workers",
        "description": "Default values for k3s cluster",
         "value": {
            "name": "gdf-cluster",
            "datacenter": "openstack",
            "kubernetesType": "k3s",
            "kubernetesVersion": "v1.28.0",
            "control":{
              "flavor": "m1.medium",
              "units": 1
            },
             "workers": {
              "flavor": "m1.medium",
              "units": 5
            },
            "image": "ubuntu-22.04-server-cloudimg-amd64-disk-kvm"
        }},
    "microk8s": {
        "summary": "Microk8s cluster with 1 control plane and 0 workers",
        "description": "Default values for microk8s cluster",
         "value": {
            "name": "gdf-cluster",
            "datacenter": "openstack",
            "kubernetesType": "microk8s",
            "kubernetesVersion": "v1.28.0",
            "control":{
              "flavor": "m1.medium",
              "units": 1
            },
             "workers": {
              "flavor": "m1.medium",
              "units": 0
            },
            "image": "ubuntu-22.04-server-cloudimg-amd64-disk-kvm"
        }
    }
}


CLUSTER_EXAMPLES_OLD = {
    "Kubeadm": {
        "summary": "Kubeadm cluster with 1 control plane and 0 workers",
        "description": "Default values for kubeadm cluster",
        "value": {
            "clusterName": "gdf-cluster",
            "kubernetesType": "kubeadm",
            "kubernetesVersion": "v1.28.0",
            "controlPlaneCount": 1,
            "workerMachineCount": 0,
            "controlPlaneFlavor": "m1.medium",
            "workerMachineFlavor": "m1.medium",
            "image": "ubuntu-2204-kube-v1.28.0"
        }},
    "k3s": {
        "summary": "K3s cluster with 1 control plane and 5 workers",
        "description": "Default values for k3s cluster",
        "value": {
            "clusterName": "gdf",
            "kubernetesType": "k3s",
            "kubernetesVersion": "v1.21.5+k3s2",
            "controlPlaneCount": 1,
            "workerMachineCount": 5,
            "controlPlaneFlavor": "m1.medium",
            "workerMachineFlavor": "m1.medium",
            "image": "ubuntu-2204-kube-v1.28.0"
        }},
    "microk8s": {
        "summary": "Microk8s cluster with 1 control plane and 0 workers",
        "description": "Default values for microk8s cluster",
        "value": {
            "clusterName": "gdf",
            "kubernetesType": "microk8s",
            "kubernetesVersion": "1.25.0",
            "controlPlaneCount": 1,
            "workerMachineCount": 0,
            "controlPlaneCountFlavor": "m1.medium",
            "workerMachineFlavor": "m1.medium",
            "image": "ubuntu-22.04-server-cloudimg-amd64-disk-kvm"
        }
    }
}


class ClusterRequest(BaseModel):
    clusterName: Optional[str] = "gdf-cluster"
    datacenter: Optional[str] = "c01"
    kubernetesType: Optional[str] = "kubeadm"
    kubernetesVersion: Optional[str] = "v1.28.0"
    controlPlaneCount: Optional[int] = 1
    workerMachineCount: Optional[int] = 0
    controlPlaneFlavor: Optional[str] = "m1.medium"
    workerMachineFlavor: Optional[str] = "m1.medium"
    image: Optional[str] = "ubuntu-2204-kube-v1.28.0"

    # class Config:
    #     schema_extra = {
    #         "examples":
    #     }


class Cluster(BaseModel):
    class Status(Enum):
        CREATING = 1
        READY = 2

    uuid: UUID = Field(default_factory=uuid4)
    name: str = ""
    name: str = ""
    type: str = ""
    yaml: str = ""
    kubeconfig: str = ""
    controlPlaneIP: str = ""
    status: str = ""
    controlPlaneCount: Optional[int] = 1
    workerMachineCount: Optional[int] = 0

    class Config:
        schema_extra = {
            "example": {
                "uuid": "40fea9fe-c807-4990-9c50-8fa4eba6df75",
                "name": "nameOfCluster",
                "datacenter":"c01",
                "type": "clusterType",
                "yaml": "capiGeneratedYaml",
                "kubeconfig": "kubeconfig_content",
                "controlPlaneIP": "controlPlaneIP",
                "controlPlaneCount": "controlPlaneCount",
                "workerMachineCount": "workerMachineCount",
                "status": "creating"
            }
        }

    def __repr__(self):
        return self.json()
      
      
new_rules = """groups:
- name: example
  rules:

  - alert: HighCPUUsage
    expr: 100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Instance {{ $labels.instance }} CPU usage is dangerously high"
      description: "{{ $labels.instance }} CPU usage is above 80%."


  - alert: HighMemoryUsage
    expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100 > 90
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Instance {{ $labels.instance }} memory usage is dangerously high"
      description: "{{ $labels.instance }} memory usage is above 90%."


  - alert: HighDiskUsage
    expr: (node_filesystem_size_bytes - node_filesystem_free_bytes) / node_filesystem_size_bytes * 100 > 80
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Instance {{ $labels.instance }} disk usage is dangerously high"
      description: "{{ $labels.instance }} disk usage is above 80%."

"""

LIST_CLUSTERS_EXAMPLE = {
  "apiVersion": "cluster.x-k8s.io/v1beta1",
  "items": [
    {
      "apiVersion": "cluster.x-k8s.io/v1beta1",
      "kind": "Cluster",
      "metadata": {
        "annotations": {
          "kubectl.kubernetes.io/last-applied-configuration": "{\"apiVersion\":\"cluster.x-k8s.io/v1beta1\",\"kind\":\"Cluster\",\"metadata\":{\"annotations\":{},\"labels\":{\"uuid\":\"71e55ee0-8b77-42da-9633-d0bc1e600949\"},\"name\":\"kubeadm-based-orchestration-green\",\"namespace\":\"default\"},\"spec\":{\"clusterNetwork\":{\"pods\":{\"cidrBlocks\":[\"192.168.0.0/16\"]},\"serviceDomain\":\"cluster.local\"},\"controlPlaneRef\":{\"apiVersion\":\"controlplane.cluster.x-k8s.io/v1beta1\",\"kind\":\"KubeadmControlPlane\",\"name\":\"kubeadm-based-orchestration-green-control-plane\"},\"infrastructureRef\":{\"apiVersion\":\"infrastructure.cluster.x-k8s.io/v1alpha7\",\"kind\":\"OpenStackCluster\",\"name\":\"kubeadm-based-orchestration-green\"}}}\n"
        },
        "creationTimestamp": "2023-11-15T12:30:26Z",
        "finalizers": [
          "cluster.cluster.x-k8s.io"
        ],
        "generation": 2,
        "labels": {
          "uuid": "71e55ee0-8b77-42da-9633-d0bc1e600949"
        },
        "managedFields": [
          {
            "apiVersion": "cluster.x-k8s.io/v1beta1",
            "fieldsType": "FieldsV1",
            "fieldsV1": {
              "f:metadata": {
                "f:annotations": {
                  ".": {},
                  "f:kubectl.kubernetes.io/last-applied-configuration": {}
                },
                "f:labels": {
                  ".": {},
                  "f:uuid": {}
                }
              },
              "f:spec": {
                ".": {},
                "f:clusterNetwork": {
                  ".": {},
                  "f:pods": {
                    ".": {},
                    "f:cidrBlocks": {}
                  },
                  "f:serviceDomain": {}
                },
                "f:controlPlaneRef": {},
                "f:infrastructureRef": {}
              }
            },
            "manager": "kubectl-client-side-apply",
            "operation": "Update",
            "time": "2023-11-15T12:30:26Z"
          },
          {
            "apiVersion": "cluster.x-k8s.io/v1beta1",
            "fieldsType": "FieldsV1",
            "fieldsV1": {
              "f:metadata": {
                "f:finalizers": {
                  ".": {},
                  "v:\"cluster.cluster.x-k8s.io\"": {}
                }
              },
              "f:spec": {
                "f:controlPlaneEndpoint": {
                  "f:host": {},
                  "f:port": {}
                }
              }
            },
            "manager": "manager",
            "operation": "Update",
            "time": "2023-11-15T12:30:46Z"
          },
          {
            "apiVersion": "cluster.x-k8s.io/v1beta1",
            "fieldsType": "FieldsV1",
            "fieldsV1": {
              "f:status": {
                ".": {},
                "f:conditions": {},
                "f:failureDomains": {
                  ".": {},
                  "f:nova": {
                    ".": {},
                    "f:controlPlane": {}
                  }
                },
                "f:infrastructureReady": {},
                "f:observedGeneration": {},
                "f:phase": {}
              }
            },
            "manager": "manager",
            "operation": "Update",
            "subresource": "status",
            "time": "2023-11-15T12:33:21Z"
          }
        ],
        "name": "kubeadm-based-orchestration-green",
        "namespace": "default",
        "resourceVersion": "2220047",
        "uid": "86ccf1d2-6c97-43cc-99b8-1942fb3e4301"
      },
      "spec": {
        "clusterNetwork": {
          "pods": {
            "cidrBlocks": [
              "192.168.0.0/16"
            ]
          },
          "serviceDomain": "cluster.local"
        },
        "controlPlaneEndpoint": {
          "host": "10.20.20.10",
          "port": 6443
        },
        "controlPlaneRef": {
          "apiVersion": "controlplane.cluster.x-k8s.io/v1beta1",
          "kind": "KubeadmControlPlane",
          "name": "kubeadm-based-orchestration-green-control-plane",
          "namespace": "default"
        },
        "infrastructureRef": {
          "apiVersion": "infrastructure.cluster.x-k8s.io/v1alpha7",
          "kind": "OpenStackCluster",
          "name": "kubeadm-based-orchestration-green",
          "namespace": "default"
        }
      },
      "status": {
        "conditions": [
          {
            "lastTransitionTime": "2023-11-15T12:33:21Z",
            "message": "1 of 2 completed",
            "reason": "InstanceStateError @ /kubeadm-based-orchestration-green-control-plane-9674r",
            "severity": "Error",
            "status": "False",
            "type": "Ready"
          },
          {
            "lastTransitionTime": "2023-11-15T12:30:26Z",
            "message": "Waiting for control plane provider to indicate the control plane has been initialized",
            "reason": "WaitingForControlPlaneProviderInitialized",
            "severity": "Info",
            "status": "False",
            "type": "ControlPlaneInitialized"
          },
          {
            "lastTransitionTime": "2023-11-15T12:33:21Z",
            "message": "1 of 2 completed",
            "reason": "InstanceStateError @ /kubeadm-based-orchestration-green-control-plane-9674r",
            "severity": "Error",
            "status": "False",
            "type": "ControlPlaneReady"
          },
          {
            "lastTransitionTime": "2023-11-15T12:30:46Z",
            "status": "True",
            "type": "InfrastructureReady"
          }
        ],
        "failureDomains": {
          "nova": {
            "controlPlane": "true"
          }
        },
        "infrastructureReady": "true",
        "observedGeneration": 2,
        "phase": "Provisioned"
      }
    }
  ],
  "kind": "ClusterList",
  "metadata": {
    "continue": "",
    "resourceVersion": "4215413"
  }
}