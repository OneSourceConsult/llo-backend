#!/bin/bash

# --------------------------- CLEANUP ---------------------------

#TODO DURING UNINSTALLATION STOP, DISABLE AND DELETE DAEMONS

ADMIN=$1

yes | $ADMIN kubeadm reset 

$ADMIN rm -rf /etc/cni/net.d
$ADMIN rm -rf ~/.kube

$ADMIN rm /etc/apt/keyrings/kubernetes-apt-keyring.gpg
$ADMIN rm /etc/apt/sources.list.d/kubernetes.list

$ADMIN apt-mark unhold kubeadm 
$ADMIN apt-mark unhold kubectl 
$ADMIN apt-mark unhold kubelet

$ADMIN rm -rf /etc/systemd/system/kubelet.service.d
$ADMIN rm -rf /opt/cni/bin

$ADMIN apt -y remove kubeadm 
$ADMIN apt -y remove kubectl
$ADMIN apt -y remove kubelet
$ADMIN apt -y remove kubernetes-cni
$ADMIN apt -y remove kube*

$ADMIN apt -y autoremove
$ADMIN apt clean

