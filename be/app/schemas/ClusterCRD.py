import yaml



class ClusterCRD:
    def __init__(self, value):
        self.value = value
        self.uuid = -1

    def setUUI(self, uuid):
        docs = list(yaml.safe_load_all(self.value))

        uuidLabel = {"uuid": str(uuid)}
        labels = {"labels": uuidLabel}

        for doc in docs:
            if doc["kind"] == "Cluster":
                doc["metadata"].update(
                    labels
                )
        
        self.value = yaml.dump_all(docs, default_style=None)
        return self


# TODO: this classes need a lot of refactoring to avoid hard-coded values
# so far it provides some helpers for our experiments
class CAPO(ClusterCRD):
    # receives a cluster api generated yaml for CAPO and disable securitygroups
    def disableSecurityGroups(self):

        docs = list(yaml.safe_load_all(self.value))
        # post yaml editing
        for doc in docs:
            if doc["kind"] == "OpenStackCluster":
                doc["spec"]["managedSecurityGroups"] = False
                doc["spec"]["disablePortSecurity"] = True

        self.value = yaml.dump_all(docs, default_style=None)
        return self


class CAPOKubeadmCRD(CAPO):

    # TOD: extract cmd list to arg
    def addPostKubeadmCommands(self):
        value = self.value
        postCMDsList = [
            "sudo wget https://raw.githubusercontent.com/flannel-io/flannel/v0.20.2/Documentation/kube-flannel.yml",
            "sudo sed -i 's/10.244.0.0\/16/192.168.0.0\/16/' kube-flannel.yml",
            "sudo kubectl --kubeconfig=/etc/kubernetes/admin.conf apply -f kube-flannel.yml",
        """sudo sh -c 'echo "31.171.250.32 harbor.hpe.charity-project.eu monitoring-manager.plexus.charity-project.eu" >> /etc/hosts'

sudo tee -a /etc/containerd/config.toml >/dev/null <<EOT
  [plugins."io.containerd.grpc.v1.cri".registry]
    config_path = "/etc/containerd/certs.d"
EOT

sudo mkdir -p /etc/containerd/certs.d/harbor.hpe.charity-project.eu
sudo touch /etc/containerd/certs.d/harbor.hpe.charity-project.eu/hosts.toml

sudo tee /etc/containerd/certs.d/harbor.hpe.charity-project.eu/hosts.toml >/dev/null <<EOT
server = "https://docker.io"

[host."https://harbor.hpe.charity-project.eu"]
  capabilities = ["pull", "resolve", "push"]
  skip_verify = true
EOT

sudo systemctl restart containerd.service
        """
        
        ]

        docs = list(yaml.safe_load_all(value))

        postKubeadmCommandsDict = {"postKubeadmCommands": postCMDsList}
        for doc in docs:
            if doc["kind"] == "KubeadmControlPlane":
                doc["spec"]["kubeadmConfigSpec"].update(
                    postKubeadmCommandsDict
                )

        self.value = yaml.dump_all(docs, default_style=None)
        return self

    # fix bug on pulling
    # TODO: remove if not needed anymore
    def removeImageRepository(self):
        docs = list(yaml.safe_load_all(self.value))
        # post yaml editing
        for doc in docs:
            if doc["kind"] == "KubeadmControlPlane":
                del doc["spec"]["kubeadmConfigSpec"]["clusterConfiguration"][
                    "imageRepository"
                ]

        self.value = yaml.dump_all(docs, default_style=None)
        return self

class CAPOK3sCRD(CAPO):
    pass


TOSCA_EXAMPLE = """tosca_definitions_version: tosca_simple_yaml_1_3

description: ssss

metadata:
  # The following fields are "normative" and expected in TOSCA 
  template_name: Cyango Cloud Studio - reimported
  template_author:  cyango-xr-developer
  template_version: ''

imports:
  - charity_custom_types_v08.yaml

topology_template:
  inputs:
    tls_cert:
      type: string
      required: true
      default: -----BEGIN CERTIFICATE----- [CERTIFICATE] -----END CERTIFICATE-----
    tls_key:
      type: string
      required: true
      default: -----BEGIN PRIVATE KEY----- [KEY] -----END PRIVATE KEY-----
    NODE_ENV:
      type: string
      required: true
      default: beta
  node_templates:
    charity-kafka:
      type: Charity.Component
      properties:
        name: charity-kafka
        deployment_unit: EXTERNAL
    AmazonS3:
      type: Charity.Component
      properties:
        name: amazons3
        deployment_unit: EXTERNAL
    cyango-backend:
      type: Charity.Component
      properties:
        name: cyango-backend
        deployment_unit: K8S_POD
        placement_hint: CLOUD
        image: repository.charity-project.eu/dotes/cyango-backend:beta
        environment:
          NODE_ENV: { get_input: NODE_ENV } 
      requirements:
        - host: cyango-backendNode
    cyango-backendNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 0 
                mem_size: 
                  - greater_than: 0 MB
 
    cyango-database:
      type: Charity.Component
      properties:
        name: cyango-database
        deployment_unit: K8S_POD
        geolocation: { get_input: null } 
        placement_hint: CLOUD
        image: repository.charity-project.eu/dotes/cyango-database:beta
        environment:
          MONGO_INITDB_PWD: PUkkwM7sgPYZgGZc7sTkSBnGixNhvbfM          
          MONGO_INITDB_USER: cyadmin          
          MONGO_INITDB_DATABASE: cyango_database_beta          
      requirements:
        - host: cyango-databaseNode
    cyango-databaseNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 0 
                mem_size: 
                  - greater_than: 0 MB
 
    cyango-cloud-editor:
      type: Charity.Component
      properties:
        name: cyango-cloud-editor
        deployment_unit: K8S_POD
        placement_hint: CLOUD
        image: repository.charity-project.eu/dotes/cyango-cloud-editor:beta
        environment:
          NODE_ENV: { get_input: NODE_ENV } 
      requirements:
        - host: cyango-cloud-editorNode
    cyango-cloud-editorNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 0 
                mem_size: 
                  - greater_than: 0 MB
 
    cyango-story:
      type: Charity.Component
      properties:
        name: cyango-story
        deployment_unit: K8S_POD
        placement_hint: CLOUD
        image: repository.charity-project.eu/dotes/cyango-story-express:beta
        environment:
          NODE_ENV: { get_input: NODE_ENV } 
      requirements:
        - host: cyango-storyNode
    cyango-storyNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 0 
                mem_size: 
                  - greater_than: 0 MB
 
    cyango-worker:
      type: Charity.Component
      properties:
        name: cyango-worker
        deployment_unit: K8S_POD
        placement_hint: CLOUD
        image: repository.charity-project.eu/dotes/cyango-worker:beta
        environment:
          NODE_ENV: { get_input: NODE_ENV } 
      requirements:
        - host: cyango-workerNode
    cyango-workerNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 0 
                mem_size: 
                  - greater_than: 0 MB
 
    VL1:
      type: Charity.VirtualLink
      properties:
        name: VL1
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
                - greater_or_equal: 50 Kbps            
              latency:
                - less_than: 5 ms
              jitter:
                - less_than: 100 ms
    VL2:
      type: Charity.VirtualLink
      properties:
        name: VL2
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
                - greater_or_equal: 0 Mbps            
              latency:
                - less_than: 10000 ms
              jitter:
                - less_than: 100 ms
    VL3:
      type: Charity.VirtualLink
      properties:
        name: VL3
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
                - greater_or_equal: 0 Mbps            
              latency:
                - less_than: 110 ms
              jitter:
                - less_than: 100 ms
    VL4:
      type: Charity.VirtualLink
      properties:
        name: VL4
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
                - greater_or_equal: 0 Mbps            
              latency:
                - less_than: 10000 ms
              jitter:
                - less_than: 100 ms
    VL5:
      type: Charity.VirtualLink
      properties:
        name: VL5
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
                - greater_or_equal: 0 Mbps            
              latency:
                - less_than: 10000 ms
              jitter:
                - less_than: 100 ms
    VL6:
      type: Charity.VirtualLink
      properties:
        name: VL6
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
                - greater_or_equal: 0 Mbps            
              latency:
                - less_than: 10000 ms
              jitter:
                - less_than: 100 ms
    VL7:
      type: Charity.VirtualLink
      properties:
        name: VL7
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
                - greater_or_equal: 0 Mbps            
              latency:
                - less_than: 10000 ms
              jitter:
                - less_than: 100 ms
    VL8:
      type: Charity.VirtualLink
      properties:
        name: VL8
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
                - greater_or_equal: 0 Mbps            
              latency:
                - less_than: 10000 ms
              jitter:
                - less_than: 100 ms
    CH-KAFKA:
      type: Charity.ConnectionPoint
      properties:
        name: CH-KAFKA
        port: 9092
        protocol: TCP
      requirements:
        - binding:
            node: charity-kafka
        - link: 
            node: VL1
        - link:         
            node: VL3
    CY_BACK:
      type: Charity.ConnectionPoint
      properties:
        name: CY_BACK
        port: 32777
        protocol: TCP
      requirements:
        - binding:
            node: cyango-backend
        - link: 
            node: VL1
        - link: 
            node: VL2
        - link: 
            node: VL4
        - link: 
            node: VL5            
        - link: 
            node: VL6            
    AWS-S3:
      type: Charity.ConnectionPoint
      properties:
        name: AWS-S3
        protocol: TCP
      requirements:
        - binding:
            node: AmazonS3
        - link: 
            node: VL2
        - link: 
            node: VL7
        - link: 
            node: VL8
    CY_WORKER:
      type: Charity.ConnectionPoint
      properties:
        name: CY_WORKER
        protocol: TCP
      requirements:
        - binding:
            node: cyango-worker
        - link: 
            node: VL3
    CY_DB:
      type: Charity.ConnectionPoint
      properties:
        name: CY_DB
        port: 27017
        protocol: TCP
      requirements:
        - binding:
            node: cyango-database
        - link: 
            node: VL4
    CY_CLOUD_EDITOR:
      type: Charity.ConnectionPoint
      properties:
        name: CY_CLOUD_EDITOR
        port: 443
        protocol: TCP
      requirements:
        - binding:
            node: cyango-cloud-editor
        - link: 
            node: VL5
        - link: 
            node: VL7
    CY_STORY:
      type: Charity.ConnectionPoint
      properties:
        name: CY_STORY
        port: 443
        protocol: TCP
      requirements:
        - binding:
            node: cyango-story
        - link: 
            node: VL6
        - link: 
            node: VL8"""
            
TOSCA_EXAMPLE2 = """tosca_definitions_version: tosca_simple_yaml_1_3

description: Charity Application model of UC3-1 ORBK Use Case

metadata:
  # The following fields are "normative" and expected in TOSCA 
  template_name: orbk-uc3-1
  template_author: HPE
  template_version: '0.3'

imports:
  - charity_custom_types_v09.yaml

topology_template:
  inputs:
    Location:
      type: Charity.geolocation
      required: true
      default: location 
    MeshMergeIp:
      type: string
      required: true
      default: '0.0.0.0'
      
  node_templates:

    GameServer:
      type: Charity.Component
      properties:
        name: GameServer
        deployment_unit: K8S_POD
        placement_hint: EDGE
        replicas: 2
        image: 'https://harbor.charity.eu/orbk/gs:v1.0'
        environment:
          orbk_site: 'http://games.orbk.com' 
          meshmerge_ip: { get_input: MeshMergeIp }
      requirements:
        - host: GameServerNode

    GameServerNode:
      type: Charity.Node
      requirements:
        - local_storage:
            node: MyStorage
            relationship:
              type: tosca.relationships.AttachesTo
              properties:
                location: /mnt
        - persistent_storage:
            node: PVCStorage
            relationship:
              type: tosca.relationships.AttachesTo
              properties:
                location: /pvc
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 1 
                mem_size: 
                  - greater_than: 512 MB
          - gpu:
              properties:
                model:
                  - equal: 'NVIDIA GeForce RTX 20-series'
                dedicated:
                  - equal: true
                units:
                  - equal: 2

    MyStorage:
      type: Charity.LocalStorage
      properties:
        name: 'Private-Storage'
        size: 10 GB

    PVCStorage:
      type: Charity.PersistentStorage
      properties:
        name: 'PVC-volume'
        size: 10 GB
        access: ReadWriteOnce

    MeshMerge:
      type: Charity.Component
      properties:
        name: meshmerge
        deployment_unit: EXTERNAL
        placement_hint: CLOUD

    UserDevice:
      type: Charity.Component
      properties:
        name: userdevice
        deployment_unit: EXTERNAL
        geolocation: { get_input: Location }
        placement_hint: EDGE

    GS-IN:
      type: Charity.ConnectionPoint
      properties:
        name: GS-IN
        protocol: TCP
      requirements:
        - binding:
            node: GameServer
        - link: 
            node: VL-1
    GS-OUT:
      type: Charity.ConnectionPoint
      properties:
        name: GS-OUT
        protocol: UDP
      requirements:
        - binding:
            node: GameServer
        - link: 
            node: VL-3

    GS-MM:
      type: Charity.ConnectionPoint
      properties:
        name: GS-MM
      requirements:
        - binding:
            node: GameServer
        - link: 
            node: VL-2

    MM-GS:
      type: Charity.ConnectionPoint
      properties:
        name: MM-GS
      requirements:
        - binding:
            node: MeshMerge
        - link: 
            node: VL-2

    UD-OUT:
      type: Charity.ConnectionPoint
      properties:
        name: UD-OUT
      requirements:
        - binding:
            node: UserDevice
        - link: 
            node: VL-1

    UD-IN:
      type: Charity.ConnectionPoint
      properties:
        name: UD-IN
      requirements:
        - binding:
            node: UserDevice
        - link: 
            node: VL-3

    VL-1:
      type: Charity.VirtualLink
      properties:
        name: VL-1
      node_filter:
        capabilities:
        - network:
           properties:
             latency:
               - less_than: 10 ms

    VL-2:
      type: Charity.VirtualLink
      properties:
        name: VL-2

    VL-3:
      type: Charity.VirtualLink
      properties:
        name: VL-3
      node_filter:
        capabilities:
        - network:
           properties:
             bandwith:
               - greater_or_equal: 1.0 GBps

  outputs:

    Gameserver_IP:
      description: The private IP address of the provisioned server.
      value: { get_attribute: [ GameServer, ip ] }
      type: string"""

TOSCA_EXAMPLE3 = """
description: Online gaming platform
imports:
- charity_custom_types_v09.yaml
metadata:
  template_author: barone
  template_name: XRImmersiveGame
  template_version: 0.0.2
topology_template:
  node_templates:
    GC_in:
      properties:
        name: GC_in
        port: 21765
        protocol: UDP
      requirements:
      - binding:
          node: GameClient
      - link:
          node: VL_2
      type: Charity.ConnectionPoint
    GC_out:
      properties:
        name: GC_out
        protocol: UDP
      requirements:
      - binding:
          node: GameClient
      - link:
          node: VL_1
      type: Charity.ConnectionPoint
    GS:
      properties:
        name: GS
        port: 80
        protocol: TCP
      requirements:
      - binding:
          node: MeshMerger
      - link:
          node: VL_3
      type: Charity.ConnectionPoint
    GS_in:
      properties:
        name: GS_in
        port: 21765
        protocol: UDP
      requirements:
      - binding:
          node: GameServer
      - link:
          node: VL_1
      type: Charity.ConnectionPoint
    GS_out:
      properties:
        name: GS_out
        protocol: UDP
      requirements:
      - binding:
          node: GameServer
      - link:
          node: VL_2
      type: Charity.ConnectionPoint
    GameClient:
      properties:
        deployment_unit: EXTERNAL
        geolocation:
          exact: false
          latitude: '79'
          longitude: '8.16'
        name: gameclient
      type: Charity.Component
    GameServer:
      properties:
        deployment_unit: K8S_POD
        geolocation:
          exact: false
          latitude: '79'
          longitude: '8.16'
        image: harbor.hpe.charity-project.eu/hpe/amf-shell:dev-k8s
        name: GameServer
        placement_hint: EDGE
      requirements:
      - host: GameServerNode
      type: Charity.Component
    GameServerNode:
      attributes:
        instance_id: to_be_filled_in
      node_filter:
        capabilities:
        - host:
            properties:
              mem_size:
              - greater_than: 8 MB
              num_cpus:
              - equal: 1
        - datacenter:
            properties:
              name:
              - equal: cloudsigma_dublin
      type: Charity.Node
    MM:
      properties:
        name: MM
        protocol: TCP
      requirements:
      - binding:
          node: GameServer
      - link:
          node: VL_3
      type: Charity.ConnectionPoint
    MeshMerger:
      properties:
        deployment_unit: K8S_POD
        environment:
          myEnvParam: myValue
          name: defaultName
        geolocation:
          city: ''
          country: Italy
          exact: false
          region: Europe
        image: hpe/test-image:v1-hpe
        name: MeshMerger
        placement_hint: EDGE
      requirements:
      - host: MeshMergerNode
      type: Charity.Component
    MeshMergerNode:
      attributes:
        instance_id: to_be_filled_in
      node_filter:
        capabilities:
        - host:
            properties:
              mem_size:
              - greater_than: 8 MB
              num_cpus:
              - equal: 1
        - datacenter:
            properties:
              name:
              - equal: azure_paris
      type: Charity.Node
    VL_1:
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 399 Mbps
              jitter:
              - less_than: 100 ms
              latency:
              - less_than: 148 ms
      properties:
        name: VL_1
      type: Charity.VirtualLink
    VL_2:
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 698 Mbps
              jitter:
              - less_than: 100 ms
              latency:
              - less_than: 395 ms
      properties:
        name: VL_2
      type: Charity.VirtualLink
    VL_3:
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 399 Mbps
              jitter:
              - less_than: 100 ms
              latency:
              - less_than: 183 ms
      properties:
        name: VL_3
      type: Charity.VirtualLink
  outputs:
    GC_in_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - GC_in
        - url
    GC_out_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - GC_out
        - url
    GS_in_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - GS_in
        - url
    GS_out_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - GS_out
        - url
    GS_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - GS
        - url
    GameServer_IP:
      description: The private IP address of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - GameServer
        - ip
    GameServer_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      type: string
      value:
        get_attribute:
        - GameServerNode
        - datacenter
    GameServer_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      type: string
      value:
        get_attribute:
        - GameServer
        - deployment_context
    GameServer_latitude:
      description: The latitude of the VNF node.
      type: string
      value:
        get_attribute:
        - GameServerNode
        - latitude
    GameServer_longitude:
      description: The longitude of the VNF node.
      type: string
      value:
        get_attribute:
        - GameServerNode
        - longitude
    GameServer_namespace:
      description: The deployment namespace of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - GameServer
        - namespace
    MM_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - MM
        - url
    MeshMerger_IP:
      description: The private IP address of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - MeshMerger
        - ip
    MeshMerger_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      type: string
      value:
        get_attribute:
        - MeshMergerNode
        - datacenter
    MeshMerger_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      type: string
      value:
        get_attribute:
        - MeshMerger
        - deployment_context
    MeshMerger_latitude:
      description: The latitude of the VNF node.
      type: string
      value:
        get_attribute:
        - MeshMergerNode
        - latitude
    MeshMerger_longitude:
      description: The longitude of the VNF node.
      type: string
      value:
        get_attribute:
        - MeshMergerNode
        - longitude
    MeshMerger_namespace:
      description: The deployment namespace of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - MeshMerger
        - namespace
tosca_definitions_version: tosca_simple_yaml_1_3
"""

TOSCA_EXAMPLEV4 = """description: Online gaming platform
imports:
- charity_custom_types_v13.yaml
metadata:
  template_author: barone
  template_name: XRImmersiveGame
  template_version: 0.0.3
topology_template:
  node_templates:
    GC_in:
      properties:
        name: GC_in
        port: 21765
        protocol: UDP
      requirements:
      - binding:
          node: GameClient
      - link:
          node: VL_2
      type: Charity.ConnectionPoint
    GC_out:
      properties:
        name: GC_out
        protocol: UDP
      requirements:
      - binding:
          node: GameClient
      - link:
          node: VL_1
      type: Charity.ConnectionPoint
    GS:
      properties:
        name: GS
        port: 80
        protocol: TCP
      requirements:
      - binding:
          node: MeshMerger
      - link:
          node: VL_3
      type: Charity.ConnectionPoint
    GS_in:
      properties:
        name: GS_in
        port: 21765
        protocol: UDP
      requirements:
      - binding:
          node: GameServer
      - link:
          node: VL_1
      type: Charity.ConnectionPoint
    GS_out:
      properties:
        name: GS_out
        protocol: UDP
      requirements:
      - binding:
          node: GameServer
      - link:
          node: VL_2
      type: Charity.ConnectionPoint
    GameClient:
      properties:
        deployment_unit: EXTERNAL
        geolocation:
          exact: false
          latitude: '79'
          longitude: '8.16'
        name: gameclient
      type: Charity.Component
    GameServer:
      properties:
        deployment_unit: K8S_POD
        geolocation:
          exact: false
          latitude: '79'
          longitude: '8.16'
        image: harbor.hpe.charity-project.eu/hpe/charity-ms-vnfimage:dev-k8s
        name: GameServer
        placement_hint: EDGE
      requirements:
      - host: GameServerNode
      type: Charity.Component
    GameServerNode:
      attributes:
        instance_id: to_be_filled_in
      node_filter:
        capabilities:
        - host:
            properties:
              mem_size:
              - greater_than: 8 MB
              num_cpus:
              - equal: 1
        - deployment:
            properties:
              cluster:
              - equal: blue
              datacenter:
              - equal: c01
      type: Charity.Node
    MM:
      properties:
        name: MM
        protocol: TCP
      requirements:
      - binding:
          node: GameServer
      - link:
          node: VL_3
      type: Charity.ConnectionPoint
    MeshMerger:
      properties:
        deployment_unit: K8S_POD
        environment:
          myEnvParam: myValue
          name: defaultName
        geolocation:
          city: ''
          country: Italy
          exact: false
          region: Europe
        image: harbor.hpe.charity-project.eu/hpe/charity-ms-vnfimage:prod-k8s
        name: MeshMerger
        placement_hint: EDGE
      requirements:
      - host: MeshMergerNode
      type: Charity.Component
    MeshMergerNode:
      attributes:
        instance_id: to_be_filled_in
      node_filter:
        capabilities:
        - host:
            properties:
              mem_size:
              - greater_than: 8 MB
              num_cpus:
              - equal: 1
        - deployment:
            properties:
              cluster:
              - equal: blue
              datacenter:
              - equal: c01
      type: Charity.Node
    VL_1:
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 399 Mbps
              jitter:
              - less_than: 100 ms
              latency:
              - less_than: 148 ms
      properties:
        name: VL_1
      type: Charity.VirtualLink
    VL_2:
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 698 Mbps
              jitter:
              - less_than: 100 ms
              latency:
              - less_than: 395 ms
      properties:
        name: VL_2
      type: Charity.VirtualLink
    VL_3:
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 399 Mbps
              jitter:
              - less_than: 100 ms
              latency:
              - less_than: 183 ms
      properties:
        name: VL_3
      type: Charity.VirtualLink
  outputs:
    GC_in_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - GC_in
        - url
    GC_out_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - GC_out
        - url
    GS_in_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - GS_in
        - url
    GS_out_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - GS_out
        - url
    GS_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - GS
        - url
    GameServer_IP:
      description: The private IP address of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - GameServer
        - ip
    GameServer_cluster:
      description: The name of the Cluster hosting the VNF node.
      type: string
      value:
        get_attribute:
        - GameServerNode
        - deployment.cluster
    GameServer_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      type: string
      value:
        get_attribute:
        - GameServerNode
        - deployment.datacenter
    GameServer_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      type: string
      value:
        get_attribute:
        - GameServer
        - deployment_context
    GameServer_latitude:
      description: The latitude of the VNF node.
      type: string
      value:
        get_attribute:
        - GameServerNode
        - latitude
    GameServer_longitude:
      description: The longitude of the VNF node.
      type: string
      value:
        get_attribute:
        - GameServerNode
        - longitude
    GameServer_namespace:
      description: The deployment namespace of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - GameServer
        - namespace
    MM_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - MM
        - url
    MeshMerger_IP:
      description: The private IP address of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - MeshMerger
        - ip
    MeshMerger_cluster:
      description: The name of the Cluster hosting the VNF node.
      type: string
      value:
        get_attribute:
        - MeshMergerNode
        - deployment.cluster
    MeshMerger_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      type: string
      value:
        get_attribute:
        - MeshMergerNode
        - deployment.datacenter
    MeshMerger_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      type: string
      value:
        get_attribute:
        - MeshMerger
        - deployment_context
    MeshMerger_latitude:
      description: The latitude of the VNF node.
      type: string
      value:
        get_attribute:
        - MeshMergerNode
        - latitude
    MeshMerger_longitude:
      description: The longitude of the VNF node.
      type: string
      value:
        get_attribute:
        - MeshMergerNode
        - longitude
    MeshMerger_namespace:
      description: The deployment namespace of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - MeshMerger
        - namespace
tosca_definitions_version: tosca_simple_yaml_1_3"""

toscaNew = """tosca_definitions_version: tosca_simple_yaml_1_3

description: ORBK GameServer and MeshMerger

metadata:
  # The following fields are "normative" and expected in TOSCA 
  template_name: Charity-GS-MM-BP
  template_author:  giuliani
  template_version: '0.2'

imports:
  - charity_custom_types_v13.yaml

topology_template:
  inputs:
    GamerLocation:
      type: Charity.geolocation
      required: true
      default:
        exact: false
  node_templates:
    GamerDevice:
      type: Charity.External
      properties:
        name: gamerdevice
        geolocation: { get_input: GamerLocation } 
    GameServerManager:
      type: Charity.External
      properties:
        name: gameservermanager
    GameServer:
      type: Charity.Component
      properties:
        name: GameServer
        deployment_unit: K8S_POD
        placement_hint: EDGE
        image: harbor.hpe.charity-project.eu/hpe/test-image:v1-hpe
      requirements:
        - host: GameServerNode
    GameServerNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 4.0 
                mem_size: 
                  - greater_than: 4000 MB
          - deployment:
              properties:
                cluster:
                - equal: blue
                datacenter:
                - equal: c01
 
    MeshMerger:
      type: Charity.Component
      properties:
        name: MeshMerger
        deployment_unit: K8S_POD
        placement_hint: CLOUD
        image: harbor.hpe.charity-project.eu/hpe/test-image:v1-hpe
      requirements:
        - host: MeshMergerNode
    MeshMergerNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 8.0 
                mem_size: 
                  - greater_than: 12000 MB
          - deployment:
              properties:
                cluster:
                - equal: blue
                datacenter:
                - equal: c01
 
    VLgamer:
      type: Charity.VirtualLink
      properties:
        name: VLgamer
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 2 ms
              jitter:
              - less_than: 100 ms
    VLmanage:
      type: Charity.VirtualLink
      properties:
        name: VLmanage
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLMM:
      type: Charity.VirtualLink
      properties:
        name: VLMM
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 10000 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    GSgamer:
      type: Charity.ConnectionPoint
      properties:
        name: GSgamer
        port: 80
        protocol: HTTP
        public: true
      requirements:
        - binding:
            node: GameServer
        - link: 
            node: VLgamer
    GSmanage:
      type: Charity.ConnectionPoint
      properties:
        name: GSmanage
        port: 8080
        protocol: HTTP
        public: true
      requirements:
        - binding:
            node: GameServer
        - link: 
            node: VLmanage
    MMgs:
      type: Charity.ConnectionPoint
      properties:
        name: MMgs
        port: 9000
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: MeshMerger
        - link: 
            node: VLMM
    GamerCP:
      type: Charity.ConnectionPoint
      properties:
        name: GamerCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: GamerDevice
        - link: 
            node: VLgamer
    GSManagerCP:
      type: Charity.ConnectionPoint
      properties:
        name: GSManagerCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: GameServerManager
        - link: 
            node: VLmanage
    GSmm:
      type: Charity.ConnectionPoint
      properties:
        name: GSmm
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: GameServer
        - link: 
            node: VLMM
  outputs:
    GameServer_IP:
      description: The private IP address of the provisioned VNF.
      value: { get_attribute: [ GameServer, ip ] }
      type: string
    GameServer_namespace:
      description: The deployment namespace of the provisioned VNF.
      value: { get_attribute: [ GameServer, namespace ] }
      type: string
    GameServer_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      value: { get_attribute: [ GameServer, deployment_context ] }
      type: string
    GameServer_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      value: { get_attribute: [ GameServerNode, deployment.datacenter ] }
      type: string
    GameServer_cluster:
      description: The name of the Cluster hosting the VNF node.
      value: { get_attribute: [ GameServerNode, deployment.cluster ] }
      type: string
    GameServer_latitude:
      description: The latitude of the VNF node.
      value: { get_attribute: [ GameServerNode, latitude ] }
      type: string
    GameServer_longitude:
      description: The longitude of the VNF node.
      value: { get_attribute: [ GameServerNode, longitude ] }
      type: string
    MeshMerger_IP:
      description: The private IP address of the provisioned VNF.
      value: { get_attribute: [ MeshMerger, ip ] }
      type: string
    MeshMerger_namespace:
      description: The deployment namespace of the provisioned VNF.
      value: { get_attribute: [ MeshMerger, namespace ] }
      type: string
    MeshMerger_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      value: { get_attribute: [ MeshMerger, deployment_context ] }
      type: string
    MeshMerger_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      value: { get_attribute: [ MeshMergerNode, deployment.datacenter ] }
      type: string
    MeshMerger_cluster:
      description: The name of the Cluster hosting the VNF node.
      value: { get_attribute: [ MeshMergerNode, deployment.cluster ] }
      type: string
    MeshMerger_latitude:
      description: The latitude of the VNF node.
      value: { get_attribute: [ MeshMergerNode, latitude ] }
      type: string
    MeshMerger_longitude:
      description: The longitude of the VNF node.
      value: { get_attribute: [ MeshMergerNode, longitude ] }
      type: string
    GSgamer_url:
      description: The url for this connection point
      value: { get_attribute: [ GSgamer, url ] }
      type: string
    GSmanage_url:
      description: The url for this connection point
      value: { get_attribute: [ GSmanage, url ] }
      type: string
    MMgs_url:
      description: The url for this connection point
      value: { get_attribute: [ MMgs, url ] }
      type: string
    GamerCP_url:
      description: The url for this connection point
      value: { get_attribute: [ GamerCP, url ] }
      type: string
    GSManagerCP_url:
      description: The url for this connection point
      value: { get_attribute: [ GSManagerCP, url ] }
      type: string
    GSmm_url:
      description: The url for this connection point
      value: { get_attribute: [ GSmm, url ] }
      type: string

"""

TOSCA_EXAMPLE_DOTES = """tosca_definitions_version: tosca_simple_yaml_1_3
description: CYANGO DOTES VR Tour Creator

metadata:
  # The following fields are "normative" and expected in TOSCA 
  template_name: Charity-VRTC-BP
  template_author:  giuliani
  template_version: '0.1'

imports:
  - charity_custom_types_v13.yaml

topology_template:
  inputs:
    EditorLocation:
      type: Charity.geolocation
      required: true
      default:
        exact: false
    VisitorLocation:
      type: Charity.geolocation
      required: true
      default:
        exact: false
  node_templates:
    Editor:
      type: Charity.External
      properties:
        name: editor
        geolocation: { get_input: EditorLocation } 
    Visitor:
      type: Charity.External
      properties:
        name: visitor
        geolocation: { get_input: VisitorLocation } 
    Studio:
      type: Charity.Component
      properties:
        name: Studio
        deployment_unit: K8S_POD
        placement_hint: EDGE
        image: harbor.hpe.charity-project.eu/hpe/test-image:v1-hpe
      requirements:
        - host: StudioNode
    StudioNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 2.0 
                mem_size: 
                  - greater_than: 4000 MB
 
    Story:
      type: Charity.Component
      properties:
        name: Story
        deployment_unit: K8S_POD
        placement_hint: EDGE
        image: harbor.hpe.charity-project.eu/hpe/test-image:v1-hpe
      requirements:
        - host: StoryNode
    StoryNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 1.0 
                mem_size: 
                  - greater_than: 2000 MB
 
    MediaServer:
      type: Charity.Component
      properties:
        name: MediaServer
        deployment_unit: K8S_POD
        placement_hint: EDGE
        image: harbor.hpe.charity-project.eu/hpe/test-image:v1-hpe
      requirements:
        - host: MediaServerNode
    MediaServerNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 2.0 
                mem_size: 
                  - greater_than: 2000 MB
 
    BackEnd:
      type: Charity.Component
      properties:
        name: BackEnd
        deployment_unit: K8S_POD
        placement_hint: CLOUD
        image: harbor.hpe.charity-project.eu/hpe/test-image:v1-hpe
      requirements:
        - host: BackEndNode
    BackEndNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 8.0 
                mem_size: 
                  - greater_than: 16000 MB
 
    Moskito:
      type: Charity.Component
      properties:
        name: Moskito
        deployment_unit: K8S_POD
        placement_hint: CLOUD
        image: moskito:latest
      requirements:
        - host: MoskitoNode
    MoskitoNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 1.0 
                mem_size: 
                  - greater_than: 1000 MB
 
    Worker:
      type: Charity.Component
      properties:
        name: Worker
        deployment_unit: K8S_POD
        placement_hint: CLOUD
        image: harbor.hpe.charity-project.eu/hpe/test-image:v1-hpe
      requirements:
        - host: WorkerNode
    WorkerNode:
      type: Charity.Node
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 4.0 
                mem_size: 
                  - greater_than: 8000 MB
 
    Video:
      type: Charity.Component
      properties:
        name: Video
        deployment_unit: K8S_POD
        placement_hint: CLOUD
        image: harbor.hpe.charity-project.eu/hpe/test-image:v1-hpe
      requirements:
        - host: VideoNode
    VideoNode:
      type: Charity.Node
      requirements:
        - persistent_storage:
            node: VideoPersistentStorageNode-videos
            relationship:
              type: tosca.relationships.AttachesTo
              properties:
                location:  /s3
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 8.0 
                mem_size: 
                  - greater_than: 32000 MB
 
    VideoPersistentStorageNode-videos:
      type: Charity.PersistentStorage
      properties:
        name: videos
        size: 1000 GB
        access: READ_WRITE_ONCE
    DB:
      type: Charity.Component
      properties:
        name: DB
        deployment_unit: K8S_POD
        placement_hint: CLOUD
        image: harbor.hpe.charity-project.eu/hpe/test-image:v1-hpe
      requirements:
        - host: DBNode
    DBNode:
      type: Charity.Node
      requirements:
        - persistent_storage:
            node: DBPersistentStorageNode-db
            relationship:
              type: tosca.relationships.AttachesTo
              properties:
                location:  /db
      node_filter:
        capabilities:
          - host:
              properties:
                num_cpus: 
                  - equal: 2.0 
                mem_size: 
                  - greater_than: 8000 MB
 
    DBPersistentStorageNode-db:
      type: Charity.PersistentStorage
      properties:
        name: db
        size: 1000 GB
        access: READ_WRITE_MANY
    VLeditor:
      type: Charity.VirtualLink
      properties:
        name: VLeditor
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLvisitor:
      type: Charity.VirtualLink
      properties:
        name: VLvisitor
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLbackend:
      type: Charity.VirtualLink
      properties:
        name: VLbackend
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLstudioMS:
      type: Charity.VirtualLink
      properties:
        name: VLstudioMS
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLstoryMSCP:
      type: Charity.VirtualLink
      properties:
        name: VLstoryMSCP
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLbackendMoskito:
      type: Charity.VirtualLink
      properties:
        name: VLbackendMoskito
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VMmoskitoWorkerCP:
      type: Charity.VirtualLink
      properties:
        name: VMmoskitoWorkerCP
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLworkerVideo:
      type: Charity.VirtualLink
      properties:
        name: VLworkerVideo
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLbackendVideo:
      type: Charity.VirtualLink
      properties:
        name: VLbackendVideo
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLbackendDb:
      type: Charity.VirtualLink
      properties:
        name: VLbackendDb
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLvideoMS:
      type: Charity.VirtualLink
      properties:
        name: VLvideoMS
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    VLworkerBackend:
      type: Charity.VirtualLink
      properties:
        name: VLworkerBackend
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 0 Mbps            
              latency:
              - less_than: 10000 ms
              jitter:
              - less_than: 100 ms
    BackEndInputCP:
      type: Charity.ConnectionPoint
      properties:
        name: BackEndInputCP
        port: 80
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: BackEnd
        - link: 
            node: VLbackend
    MoskitoBackendCP:
      type: Charity.ConnectionPoint
      properties:
        name: MoskitoBackendCP
        port: 80
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Moskito
        - link: 
            node: VLbackendMoskito
    DBBackEndCP:
      type: Charity.ConnectionPoint
      properties:
        name: DBBackEndCP
        port: 80
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: DB
        - link: 
            node: VLbackendDb
    VideoMiediaServerCP:
      type: Charity.ConnectionPoint
      properties:
        name: VideoMiediaServerCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Video
        - link: 
            node: VLvideoMS
    VideoBackEndCP:
      type: Charity.ConnectionPoint
      properties:
        name: VideoBackEndCP
        port: 80
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Video
        - link: 
            node: VLbackendVideo
    StudioEditorCP:
      type: Charity.ConnectionPoint
      properties:
        name: StudioEditorCP
        port: 80
        protocol: HTTP
        public: true
      requirements:
        - binding:
            node: Studio
        - link: 
            node: VLeditor
    BackEndVideoCP:
      type: Charity.ConnectionPoint
      properties:
        name: BackEndVideoCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: BackEnd
        - link: 
            node: VLbackendVideo
    StudioMediaServerCP:
      type: Charity.ConnectionPoint
      properties:
        name: StudioMediaServerCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Studio
        - link: 
            node: VLstudioMS
    EditorCP:
      type: Charity.ConnectionPoint
      properties:
        name: EditorCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Editor
        - link: 
            node: VLeditor
    BackEndDbCP:
      type: Charity.ConnectionPoint
      properties:
        name: BackEndDbCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: BackEnd
        - link: 
            node: VLbackendDb
    WorkerBackendCP:
      type: Charity.ConnectionPoint
      properties:
        name: WorkerBackendCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Worker
        - link: 
            node: VLworkerBackend
    MediaServerBackendCP:
      type: Charity.ConnectionPoint
      properties:
        name: MediaServerBackendCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: MediaServer
        - link: 
            node: VLvideoMS
    StoryMediaServerCP:
      type: Charity.ConnectionPoint
      properties:
        name: StoryMediaServerCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Story
        - link: 
            node: VLstoryMSCP
    MediaServerStoryCP:
      type: Charity.ConnectionPoint
      properties:
        name: MediaServerStoryCP
        port: 9001
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: MediaServer
        - link: 
            node: VLstoryMSCP
    StoryVisitorCP:
      type: Charity.ConnectionPoint
      properties:
        name: StoryVisitorCP
        port: 80
        protocol: HTTP
        public: true
      requirements:
        - binding:
            node: Story
        - link: 
            node: VLvisitor
    WorkerMoskitoCP:
      type: Charity.ConnectionPoint
      properties:
        name: WorkerMoskitoCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Worker
        - link: 
            node: VMmoskitoWorkerCP
    MediaServerStudioCP:
      type: Charity.ConnectionPoint
      properties:
        name: MediaServerStudioCP
        port: 9000
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: MediaServer
        - link: 
            node: VLstudioMS
    MoskitoWorkerCP:
      type: Charity.ConnectionPoint
      properties:
        name: MoskitoWorkerCP
        port: 9000
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Moskito
        - link: 
            node: VMmoskitoWorkerCP
    StudioBackEndCP:
      type: Charity.ConnectionPoint
      properties:
        name: StudioBackEndCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Studio
        - link: 
            node: VLbackend
    VisitorCP:
      type: Charity.ConnectionPoint
      properties:
        name: VisitorCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Visitor
        - link: 
            node: VLvisitor
    VideoWorkerCP:
      type: Charity.ConnectionPoint
      properties:
        name: VideoWorkerCP
        port: 9000
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Video
        - link: 
            node: VLworkerVideo
    BackEndMoskitoCP:
      type: Charity.ConnectionPoint
      properties:
        name: BackEndMoskitoCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: BackEnd
        - link: 
            node: VLbackendMoskito
    BackEndWorkerCP:
      type: Charity.ConnectionPoint
      properties:
        name: BackEndWorkerCP
        port: 9000
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: BackEnd
        - link: 
            node: VLworkerBackend
    WorkerVideoCP:
      type: Charity.ConnectionPoint
      properties:
        name: WorkerVideoCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Worker
        - link: 
            node: VLworkerVideo
    StoryBackEndCP:
      type: Charity.ConnectionPoint
      properties:
        name: StoryBackEndCP
        protocol: HTTP
        public: false
      requirements:
        - binding:
            node: Story
        - link: 
            node: VLbackend
  outputs:
    Studio_IP:
      description: The private IP address of the provisioned VNF.
      value: { get_attribute: [ Studio, ip ] }
      type: string
    Studio_namespace:
      description: The deployment namespace of the provisioned VNF.
      value: { get_attribute: [ Studio, namespace ] }
      type: string
    Studio_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      value: { get_attribute: [ Studio, deployment_context ] }
      type: string
    Studio_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      value: { get_attribute: [ StudioNode, deployment.datacenter ] }
      type: string
    Studio_cluster:
      description: The name of the Cluster hosting the VNF node.
      value: { get_attribute: [ StudioNode, deployment.cluster ] }
      type: string
    Studio_latitude:
      description: The latitude of the VNF node.
      value: { get_attribute: [ StudioNode, latitude ] }
      type: string
    Studio_longitude:
      description: The longitude of the VNF node.
      value: { get_attribute: [ StudioNode, longitude ] }
      type: string
    Story_IP:
      description: The private IP address of the provisioned VNF.
      value: { get_attribute: [ Story, ip ] }
      type: string
    Story_namespace:
      description: The deployment namespace of the provisioned VNF.
      value: { get_attribute: [ Story, namespace ] }
      type: string
    Story_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      value: { get_attribute: [ Story, deployment_context ] }
      type: string
    Story_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      value: { get_attribute: [ StoryNode, deployment.datacenter ] }
      type: string
    Story_cluster:
      description: The name of the Cluster hosting the VNF node.
      value: { get_attribute: [ StoryNode, deployment.cluster ] }
      type: string
    Story_latitude:
      description: The latitude of the VNF node.
      value: { get_attribute: [ StoryNode, latitude ] }
      type: string
    Story_longitude:
      description: The longitude of the VNF node.
      value: { get_attribute: [ StoryNode, longitude ] }
      type: string
    MediaServer_IP:
      description: The private IP address of the provisioned VNF.
      value: { get_attribute: [ MediaServer, ip ] }
      type: string
    MediaServer_namespace:
      description: The deployment namespace of the provisioned VNF.
      value: { get_attribute: [ MediaServer, namespace ] }
      type: string
    MediaServer_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      value: { get_attribute: [ MediaServer, deployment_context ] }
      type: string
    MediaServer_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      value: { get_attribute: [ MediaServerNode, deployment.datacenter ] }
      type: string
    MediaServer_cluster:
      description: The name of the Cluster hosting the VNF node.
      value: { get_attribute: [ MediaServerNode, deployment.cluster ] }
      type: string
    MediaServer_latitude:
      description: The latitude of the VNF node.
      value: { get_attribute: [ MediaServerNode, latitude ] }
      type: string
    MediaServer_longitude:
      description: The longitude of the VNF node.
      value: { get_attribute: [ MediaServerNode, longitude ] }
      type: string
    BackEnd_IP:
      description: The private IP address of the provisioned VNF.
      value: { get_attribute: [ BackEnd, ip ] }
      type: string
    BackEnd_namespace:
      description: The deployment namespace of the provisioned VNF.
      value: { get_attribute: [ BackEnd, namespace ] }
      type: string
    BackEnd_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      value: { get_attribute: [ BackEnd, deployment_context ] }
      type: string
    BackEnd_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      value: { get_attribute: [ BackEndNode, deployment.datacenter ] }
      type: string
    BackEnd_cluster:
      description: The name of the Cluster hosting the VNF node.
      value: { get_attribute: [ BackEndNode, deployment.cluster ] }
      type: string
    BackEnd_latitude:
      description: The latitude of the VNF node.
      value: { get_attribute: [ BackEndNode, latitude ] }
      type: string
    BackEnd_longitude:
      description: The longitude of the VNF node.
      value: { get_attribute: [ BackEndNode, longitude ] }
      type: string
    Moskito_IP:
      description: The private IP address of the provisioned VNF.
      value: { get_attribute: [ Moskito, ip ] }
      type: string
    Moskito_namespace:
      description: The deployment namespace of the provisioned VNF.
      value: { get_attribute: [ Moskito, namespace ] }
      type: string
    Moskito_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      value: { get_attribute: [ Moskito, deployment_context ] }
      type: string
    Moskito_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      value: { get_attribute: [ MoskitoNode, deployment.datacenter ] }
      type: string
    Moskito_cluster:
      description: The name of the Cluster hosting the VNF node.
      value: { get_attribute: [ MoskitoNode, deployment.cluster ] }
      type: string
    Moskito_latitude:
      description: The latitude of the VNF node.
      value: { get_attribute: [ MoskitoNode, latitude ] }
      type: string
    Moskito_longitude:
      description: The longitude of the VNF node.
      value: { get_attribute: [ MoskitoNode, longitude ] }
      type: string
    Worker_IP:
      description: The private IP address of the provisioned VNF.
      value: { get_attribute: [ Worker, ip ] }
      type: string
    Worker_namespace:
      description: The deployment namespace of the provisioned VNF.
      value: { get_attribute: [ Worker, namespace ] }
      type: string
    Worker_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      value: { get_attribute: [ Worker, deployment_context ] }
      type: string
    Worker_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      value: { get_attribute: [ WorkerNode, deployment.datacenter ] }
      type: string
    Worker_cluster:
      description: The name of the Cluster hosting the VNF node.
      value: { get_attribute: [ WorkerNode, deployment.cluster ] }
      type: string
    Worker_latitude:
      description: The latitude of the VNF node.
      value: { get_attribute: [ WorkerNode, latitude ] }
      type: string
    Worker_longitude:
      description: The longitude of the VNF node.
      value: { get_attribute: [ WorkerNode, longitude ] }
      type: string
    Video_IP:
      description: The private IP address of the provisioned VNF.
      value: { get_attribute: [ Video, ip ] }
      type: string
    Video_namespace:
      description: The deployment namespace of the provisioned VNF.
      value: { get_attribute: [ Video, namespace ] }
      type: string
    Video_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      value: { get_attribute: [ Video, deployment_context ] }
      type: string
    Video_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      value: { get_attribute: [ VideoNode, deployment.datacenter ] }
      type: string
    Video_cluster:
      description: The name of the Cluster hosting the VNF node.
      value: { get_attribute: [ VideoNode, deployment.cluster ] }
      type: string
    Video_latitude:
      description: The latitude of the VNF node.
      value: { get_attribute: [ VideoNode, latitude ] }
      type: string
    Video_longitude:
      description: The longitude of the VNF node.
      value: { get_attribute: [ VideoNode, longitude ] }
      type: string
    DB_IP:
      description: The private IP address of the provisioned VNF.
      value: { get_attribute: [ DB, ip ] }
      type: string
    DB_namespace:
      description: The deployment namespace of the provisioned VNF.
      value: { get_attribute: [ DB, namespace ] }
      type: string
    DB_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      value: { get_attribute: [ DB, deployment_context ] }
      type: string
    DB_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      value: { get_attribute: [ DBNode, deployment.datacenter ] }
      type: string
    DB_cluster:
      description: The name of the Cluster hosting the VNF node.
      value: { get_attribute: [ DBNode, deployment.cluster ] }
      type: string
    DB_latitude:
      description: The latitude of the VNF node.
      value: { get_attribute: [ DBNode, latitude ] }
      type: string
    DB_longitude:
      description: The longitude of the VNF node.
      value: { get_attribute: [ DBNode, longitude ] }
      type: string
    BackEndInputCP_url:
      description: The url for this connection point
      value: { get_attribute: [ BackEndInputCP, url ] }
      type: string
    MoskitoBackendCP_url:
      description: The url for this connection point
      value: { get_attribute: [ MoskitoBackendCP, url ] }
      type: string
    DBBackEndCP_url:
      description: The url for this connection point
      value: { get_attribute: [ DBBackEndCP, url ] }
      type: string
    VideoMiediaServerCP_url:
      description: The url for this connection point
      value: { get_attribute: [ VideoMiediaServerCP, url ] }
      type: string
    VideoBackEndCP_url:
      description: The url for this connection point
      value: { get_attribute: [ VideoBackEndCP, url ] }
      type: string
    StudioEditorCP_url:
      description: The url for this connection point
      value: { get_attribute: [ StudioEditorCP, url ] }
      type: string
    BackEndVideoCP_url:
      description: The url for this connection point
      value: { get_attribute: [ BackEndVideoCP, url ] }
      type: string
    StudioMediaServerCP_url:
      description: The url for this connection point
      value: { get_attribute: [ StudioMediaServerCP, url ] }
      type: string
    EditorCP_url:
      description: The url for this connection point
      value: { get_attribute: [ EditorCP, url ] }
      type: string
    BackEndDbCP_url:
      description: The url for this connection point
      value: { get_attribute: [ BackEndDbCP, url ] }
      type: string
    WorkerBackendCP_url:
      description: The url for this connection point
      value: { get_attribute: [ WorkerBackendCP, url ] }
      type: string
    MediaServerBackendCP_url:
      description: The url for this connection point
      value: { get_attribute: [ MediaServerBackendCP, url ] }
      type: string
    StoryMediaServerCP_url:
      description: The url for this connection point
      value: { get_attribute: [ StoryMediaServerCP, url ] }
      type: string
    MediaServerStoryCP_url:
      description: The url for this connection point
      value: { get_attribute: [ MediaServerStoryCP, url ] }
      type: string
    StoryVisitorCP_url:
      description: The url for this connection point
      value: { get_attribute: [ StoryVisitorCP, url ] }
      type: string
    WorkerMoskitoCP_url:
      description: The url for this connection point
      value: { get_attribute: [ WorkerMoskitoCP, url ] }
      type: string
    MediaServerStudioCP_url:
      description: The url for this connection point
      value: { get_attribute: [ MediaServerStudioCP, url ] }
      type: string
    MoskitoWorkerCP_url:
      description: The url for this connection point
      value: { get_attribute: [ MoskitoWorkerCP, url ] }
      type: string
    StudioBackEndCP_url:
      description: The url for this connection point
      value: { get_attribute: [ StudioBackEndCP, url ] }
      type: string
    VisitorCP_url:
      description: The url for this connection point
      value: { get_attribute: [ VisitorCP, url ] }
      type: string
    VideoWorkerCP_url:
      description: The url for this connection point
      value: { get_attribute: [ VideoWorkerCP, url ] }
      type: string
    BackEndMoskitoCP_url:
      description: The url for this connection point
      value: { get_attribute: [ BackEndMoskitoCP, url ] }
      type: string
    BackEndWorkerCP_url:
      description: The url for this connection point
      value: { get_attribute: [ BackEndWorkerCP, url ] }
      type: string
    WorkerVideoCP_url:
      description: The url for this connection point
      value: { get_attribute: [ WorkerVideoCP, url ] }
      type: string
    StoryBackEndCP_url:
      description: The url for this connection point
      value: { get_attribute: [ StoryBackEndCP, url ] }
      type: string
"""

KUBECONFIG_EXAMPLE = """apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: {CERTIFICATE}
    server: https://{IP:PORT}}
  name: kubernetes
contexts:
- context:
    cluster: kubernetes
    user: kubernetes-admin
  name: kubernetes-admin@kubernetes
current-context: kubernetes-admin@kubernetes
kind: Config
preferences: {}
users:
- name: kubernetes-admin
  user:
    client-certificate-data: {CERTIFICATE}
    client-key-data: {KEY}
"""

APP_EXAMPLE = {
  "cluster": "kubeadm-based-orchestration-green",
  "name": "dotes",
  "components": [
    {
      "name": "cyango-story-express",
      "cluster-selector": "kubeadm-based-orchestration-green",
      "image": "repository.charity-project.eu/dotes/cyango-story-express:beta",
      "expose": [
        {
          "is-public": True,
          "is-peered": True,
          "containerPort": 443,
          "clusterPort": 443
        }
      ],
      "env": {
        "is-secret": False,
        "variables": [
          {
            "name": "NODE_ENV",
            "value": "beta"
          }
        ]
      },
      "tls": {
        "name": "cyango-certificate"
      }
    },
    {
      "name": "cyango-worker",
      "cluster-selector": "kubeadm-based-orchestration-rose",
      "image": "repository.charity-project.eu/dotes/cyango-worker:beta",
      "env": {
        "is-secret": False,
        "variables": [
          {
            "name": "NODE_ENV",
            "value": "beta"
          }
        ]
      }
    },
    {
      "name": "cyango-database",
      "cluster-selector": "kubeadm-based-orchestration-rose",
      "image": "repository.charity-project.eu/dotes/cyango-database:beta",
      "expose": [
        {
          "is-public": False,
          "is-peered": True,
          "containerPort": 27017,
          "clusterPort": 27017
        }
      ],
      "env": {
        "is-secret": False,
        "variables": [
          {
            "name": "MONGO_INITDB_PWD",
            "value": "PUkkwM7sgPYZgGZc7sTkSBnGixNhvbfM"
          },
          {
            "name": "MONGO_INITDB_USER",
            "value": "cyadmin"
          },
          {
            "name": "MONGO_INITDB_DATABASE",
            "value": "cyango_database_beta"
          }
        ]
      }
    },
    {
      "name": "cyango-cloud-editor",
      "cluster-selector": "kubeadm-based-orchestration-green",
      "image": "repository.charity-project.eu/dotes/cyango-cloud-editor:beta",
      "expose": [
        {
          "is-public": True,
          "is-peered": True,
          "containerPort": 443,
          "clusterPort": 443
        }
      ],
      "env": {
        "is-secret": False,
        "variables": [
          {
            "name": "NODE_ENV",
            "value": "beta"
          }
        ]
      },
      "tls": {
        "name": "cyango-certificate"
      }
    },
    {
      "name": "cyango-backend",
      "cluster-selector": "kubeadm-based-orchestration-rose",
      "image": "repository.charity-project.eu/dotes/cyango-backend:beta",
      "expose": [
        {
          "is-public": True,
          "is-peered": True,
          "containerPort": 32777,
          "clusterPort": 32777
        }
      ],
      "env": {
        "is-secret": False,
        "variables": [
          {
            "name": "NODE_ENV",
            "value": "beta"
          }
        ]
      },
      "tls": {
        "name": "cyango-certificate"
      }
    }
  ]
}

WEBAPP_EXAMPLE= """
description: Example Tosca Definition
imports:
- charity_custom_types_v09.yaml
metadata:
  template_author: CHARITY
  template_name: ExampleApp
  template_version: 0.0.2
topology_template:
  
  node_templates:
    DB_cp:
      properties:
        name: DB_cp
        port: 27017
        protocol: TCP
        public: False
      requirements:
      - binding:
          node: Database
      - link:
          node: VL_1
      type: Charity.ConnectionPoint
    WEBAPP_cp:
      properties:
        name: WEBAPP_cp
        port: 3000
        protocol: TCP
        public: True
      requirements:
      - binding:
          node: WebApp
      - link:
          node: VL_1
      type: Charity.ConnectionPoint
    
    WebApp:
      properties:
        deployment_unit: K8S_POD
        environment:
          USER_NAME: bW9uZ291c2Vy
          USER_PWD: bW9uZ29wYXNzd29yZA==
          DB_URL: database
        geolocation:
          exact: false
          latitude: '79'
          longitude: '8.16'
        image: docker.io/nanajanashia/k8s-demo-app:v1.0
        name: WebApp
        placement_hint: CLOUD
      requirements:
      - host: WebAppNode
      type: Charity.Component
    WebAppNode:
      attributes:
        instance_id: to_be_filled_in
      node_filter:
        capabilities:
        - host:
            properties:
              mem_size:
              - greater_than: 8 MB
              num_cpus:
              - equal: 1
        - deployment:
            properties:
              cluster:
              - equal: blue
              datacenter:
              - equal: c01
      type: Charity.Node
    Database:
      properties:
        deployment_unit: K8S_POD
        environment:
          MONGO_INITDB_ROOT_USERNAME: bW9uZ291c2Vy
          MONGO_INITDB_ROOT_PASSWORD: bW9uZ29wYXNzd29yZA==
        geolocation:
          city: ''
          country: Italy
          exact: false
          region: Europe
        image: mongo:5.0
        name: Database
        placement_hint: CLOUD
      requirements:
      - host: DatabaseNode
      type: Charity.Component
    DatabaseNode:
      attributes:
        instance_id: to_be_filled_in
      node_filter:
        capabilities:
        - host:
            properties:
              mem_size:
              - greater_than: 8 MB
              num_cpus:
              - equal: 1
        - deployment:
            properties:
              cluster:
              - equal: blue
              datacenter:
              - equal: c01
      type: Charity.Node
    VL_1:
      node_filter:
        capabilities:
        - network:
            properties:
              bandwidth:
              - greater_or_equal: 399 Mbps
              jitter:
              - less_than: 100 ms
              latency:
              - less_than: 148 ms
      properties:
        name: VL_1
      type: Charity.VirtualLink
  outputs:
    DB_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - DB_cp
        - url
    WebApp_url:
      description: The url for this connection point
      type: string
      value:
        get_attribute:
        - WEBAPP_cp
        - url
    Webapp_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      type: string
      value:
        get_attribute:
        - WebAppNode
        - datacenter
    WebApp_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      type: string
      value:
        get_attribute:
        - WebApp
        - deployment_context
    WebApp_latitude:
      description: The latitude of the VNF node.
      type: string
      value:
        get_attribute:
        - WebAppNode
        - latitude
    WebApp_longitude:
      description: The longitude of the VNF node.
      type: string
      value:
        get_attribute:
        - WebAppNode
        - longitude
    WebApp_namespace:
      description: The deployment namespace of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - WebApp
        - namespace
    Database_IP:
      description: The private IP address of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - Database
        - ip
    Database_datacenter:
      description: The name of the Datacenter  hosting the VNF node.
      type: string
      value:
        get_attribute:
        - DatabaseNode
        - datacenter
    Database_deployment_context:
      description: The deployment context for accessing the provisioned VNF.
      type: string
      value:
        get_attribute:
        - Database
        - deployment_context
    Database_latitude:
      description: The latitude of the VNF node.
      type: string
      value:
        get_attribute:
        - DatabaseNode
        - latitude
    Database_longitude:
      description: The longitude of the VNF node.
      type: string
      value:
        get_attribute:
        - DatabaseNode
        - longitude
    Database_namespace:
      description: The deployment namespace of the provisioned VNF.
      type: string
      value:
        get_attribute:
        - Database
        - namespace
tosca_definitions_version: tosca_simple_yaml_1_3"""