#!/bin/bash

HOST_IP=$(ip a | grep ens3 | grep inet | awk '{print $2}' | cut -d/ -f1)

#TODO SPLIT THIS SCRIPT INTO SMALLER ONES

# BASE SETUP

CONTAINERD_VERSION=1.7.12
RUNC_VERSION=1.1.11
CNI_PLUGINS_VERSION=1.4.0

# CLUSTER PARAMS

KUBERNETES_VERSION=1.29.0
CLUSTER_CIDR=172.16.0.0/16

# FIX FOR "UNABLE TO RESOLVE HOST"
# echo "127.0.0.1 $HOSTNAME" | tee -a /etc/hosts


ADMIN=$1

$ADMIN apt update
$ADMIN apt install -y git wget apt-transport-https ca-certificates curl gpg bash-completion

$ADMIN wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/bin/yq &&\
    $ADMIN chmod +x /usr/bin/yq

cat <<EOF | $ADMIN tee /etc/modules-load.d/containerd.conf
overlay
br_netfilter
EOF

$ADMIN modprobe overlay
$ADMIN modprobe br_netfilter

# Setup required sysctl params, these persist across reboots.
cat <<EOF | $ADMIN tee /etc/sysctl.d/99-kubernetes-cri.conf
net.bridge.bridge-nf-call-iptables  = 1
net.ipv4.ip_forward                 = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF

# Apply sysctl params without reboot
$ADMIN sysctl --system

# --------------------------- CONTAINERD ---------------------------

wget https://github.com/containerd/containerd/releases/download/v$CONTAINERD_VERSION/containerd-$CONTAINERD_VERSION-linux-amd64.tar.gz
$ADMIN tar Cxzvf /usr/local containerd-$CONTAINERD_VERSION-linux-amd64.tar.gz
rm containerd-$CONTAINERD_VERSION-linux-amd64.tar.gz

# download service file for systemd
wget https://raw.githubusercontent.com/containerd/containerd/main/containerd.service
$ADMIN mv containerd.service /usr/lib/systemd/system/

$ADMIN systemctl daemon-reload
$ADMIN systemctl enable --now containerd

# --------------------------- RUNC ---------------------------

wget https://github.com/opencontainers/runc/releases/download/v$RUNC_VERSION/runc.amd64
$ADMIN install -m 755 runc.amd64 /usr/local/sbin/runc
rm runc.amd64

# --------------------------- CNI ---------------------------

wget https://github.com/containernetworking/plugins/releases/download/v$CNI_PLUGINS_VERSION/cni-plugins-linux-amd64-v$CNI_PLUGINS_VERSION.tgz
$ADMIN mkdir -p /opt/cni/bin
$ADMIN tar Cxzvf /opt/cni/bin cni-plugins-linux-amd64-v$CNI_PLUGINS_VERSION.tgz
rm cni-plugins-linux-amd64-v$CNI_PLUGINS_VERSION.tgz

# --------------------------- CONTAINERD CONFIG ---------------------------

$ADMIN mkdir -p /etc/containerd
containerd config default | $ADMIN tee /etc/containerd/config.toml
$ADMIN sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
$ADMIN systemctl restart containerd

# --------------------------- INSTALL KUBEADM ---------------------------

$ADMIN swapoff -a

KUBERNETES_MAJOR_VERSION=$(echo "$KUBERNETES_VERSION" |  sed 's/\.[0-9]$//')

# KUBERNETES COMMUNITY REPOS (UP-TO-DATE)
$ADMIN mkdir /etc/apt/keyrings
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v$KUBERNETES_MAJOR_VERSION/deb/ /" | $ADMIN tee /etc/apt/sources.list.d/kubernetes.list
$ADMIN curl -fsSL https://pkgs.k8s.io/core:/stable:/v$KUBERNETES_MAJOR_VERSION/deb/Release.key | $ADMIN gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

$ADMIN apt update

#TODO
#W0121 02:12:29.743987   18927 checks.go:835] detected that the sandbox image "registry.k8s.io/pause:3.8" of the container runtime is inconsistent with that used by kubeadm. It is recommended that using "registry.k8s.io/pause:3.9" as the CRI sandbox image.

$ADMIN apt install -y --allow-change-held-packages kubeadm kubectl kubelet

$ADMIN apt-mark hold kubelet kubeadm kubectl

$ADMIN kubeadm init --pod-network-cidr=$CLUSTER_CIDR \
			 --cri-socket=unix:///run/containerd/containerd.sock

$ADMIN mkdir -p $HOME/.kube
yes | $ADMIN cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
$ADMIN chown $(id -u):$(id -g) $HOME/.kube/config

# CHECK BASH COMPLETION

# check_bash=$(grep "source <(kubectl completion bash)" -F ~/.bashrc)

# if [[ check_bash == "" ]]
# then
#   echo 'source <(kubectl completion bash)' >>~/.bashrc
#   source ~/.bashrc
# fi

# CHANGE FLANNEL CONFIGMAP CIDR

original_cni=$(cat addons/kube-flannel.yaml)

old_cidr=$(echo "$original_cni" | yq eval '(select(.kind == "ConfigMap" and .metadata.name == "kube-flannel-cfg").data."net-conf.json" | fromjson | .Network)' - | sed 's/[^^]/[&]/g; s/\^/\\^/g' )

new_cni=$(echo "$original_cni" | sed "s|$old_cidr|$CLUSTER_CIDR|g")
echo "$new_cni" | kubectl apply -f -

kubectl taint nodes --all node-role.kubernetes.io/control-plane-

echo "-----------> CLUSTER READY <-----------"

# INSTALL METRICS SERVER (UNLOCKS TOP COMMAND)

kubectl apply -f addons/metrics-server.yaml

echo "-----------> FULL SETUP FINISHED <-----------"
