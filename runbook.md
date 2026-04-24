# Kubernetes + NVIDIA GPU Stack Runbook

This runbook provides a comprehensive guide for setting up and managing a kubernetes cluster with NVIDIA GPU support using k3s, NVIDIA GPU Operator and Kubernetes DRA API.

## Prerequisites

Verifiy GPU is visible on the host:

```sh
lspci -k | grep -i nvidia
```

The output should be similar to:

```hs
00:04.0 3D controller: NVIDIA Corporation GA100 [A100 SXM4 40GB] (rev a1)
    Subsystem: NVIDIA Corporation GA100 [A100 SXM4 40GB]
    Kernel modules: nvidiafb
```

### Install NVIDIA Drivers also on the host (OPTIONAL)

If you proceed with the instllation **remeber to disable the installation via the GPU Operator.**  
***TODO: INSERIRE LINK ALLA DOC QUI***  
You can proceed following the [NVIDIA Datacenter Instruction](#nvidia-datacenter-instruction) or ubuntu [built-in packet](#ubuntu-built-in-packet).

#### [NVIDIA Datacenter Instruction](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/ubuntu.html)

```sh
# The kernel headers and development packages for the currently running kernel can be installed with:
apt install linux-headers-$(uname -r)

# Fill the env variables and download the NVIDIA driver repository:
wget https://developer.download.nvidia.com/compute/nvidia-driver/$version/local_installers/nvidia-driver-local-repo-$distro-$version_$arch.deb

# Install local repository on file system:
sudo dpkg -i nvidia-driver-local-repo-$distro-$version_$arch.deb
sudo apt update

# Enroll ephemeral public GPG key:
cp /var/nvidia-driver-local-repo-$distro-$version/nvidia-driver-*-keyring.gpg /usr/share/keyrings/

# To confine and pin the system to track a specific branch or driver version, install the appropriate pinning package, for example
sudo apt install nvidia-driver-pinning-<version>

# Proprietary Kernel Modules
sudo apt install cuda-drivers

# Compute-only System
sudo apt -V install libnvidia-gl nvidia-dkms

sudo reboot
```

#### Ubuntu built-in packet

```sh
sudo apt install nvidia-driver-590-server nvidia-utils-590-server 
```

---

Now the output should be similar to:

```hs
00:04.0 3D controller: NVIDIA Corporation GA100 [A100 SXM4 40GB] (rev a1)
        Subsystem: NVIDIA Corporation GA100 [A100 SXM4 40GB]
        Kernel driver in use: nvidia
        Kernel modules: nvidiafb, nvidia_drm, nvidia
```

Verify with `nvidia-smi`:

```md
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 590.48.01              Driver Version: 590.48.01      CUDA Version: 13.1     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA A100-SXM4-40GB          Off |   00000000:00:04.0 Off |                   On |
| N/A   33C    P0            104W /  400W |    4017MiB /  40960MiB |     N/A      Default |
|                                         |                        |              Enabled |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| MIG devices:                                                                            |
+------------------+----------------------------------+-----------+-----------------------+
| GPU  GI  CI  MIG |              Shared Memory-Usage |        Vol|        Shared         |
|      ID  ID  Dev |                Shared BAR1-Usage | SM     Unc| CE ENC  DEC  OFA  JPG |
|                  |                                  |        ECC|                       |
|==================+==================================+===========+=======================|
|  0    2   0   0  |            3892MiB / 20096MiB    | 42      0 |  3   0    2    0    0 |
|                  |               0MiB / 12210MiB    |           |                       |
+------------------+----------------------------------+-----------+-----------------------+
|  0    3   0   1  |              62MiB /  9984MiB    | 28      0 |  2   0    1    0    0 |
|                  |               0MiB /  6105MiB    |           |                       |
+------------------+----------------------------------+-----------+-----------------------+
|  0    9   0   2  |              32MiB /  4864MiB    | 14      0 |  1   0    0    0    0 |
|                  |               0MiB /  3052MiB    |           |                       |
+------------------+----------------------------------+-----------+-----------------------+
|  0   10   0   3  |              32MiB /  4864MiB    | 14      0 |  1   0    0    0    0 |
|                  |               0MiB /  3052MiB    |           |                       |
+------------------+----------------------------------+-----------+-----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|    0    2    0          3438385      C   python                                 3796MiB |
+-----------------------------------------------------------------------------------------+
```

## Install k3s

Install a k3s version >= 1.35 in order to natively support the DRA API and the GPU Operator:

```sh
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.35.2+k3s1 sh -
```

#### Post install

Commands to move the kubeconfig in the user home and enable bash completion also for the alias `k`:

```sh
mkdir -p $HOME/.kube
sudo cp /etc/rancher/k3s/k3s.yaml $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
chmod 600 $HOME/.kube/config
export KUBECONFIG=$HOME/.kube/config
echo 'export KUBECONFIG=$HOME/.kube/config' >> ~/.bashrc
sudo apt-get install bash-completion
echo 'source <(kubectl completion bash)' >>~/.bashrc
echo "alias k='kubectl'" >> ~/.bashrc
echo "complete -o default -F __start_kubectl k" >> ~/.bashrc
source ~/.bashrc
```

## Install NVIDIA GPU Operator

### Prerequisites

Install Helm:

```sh
sudo apt-get install curl gpg apt-transport-https --yes
curl -fsSL https://packages.buildkite.com/helm-linux/helm-debian/gpgkey | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/helm.gpg] https://packages.buildkite.com/helm-linux/helm-debian/any/ any main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
sudo apt-get update
sudo apt-get install helm
```

### Install GPU Operator

Add the NVIDIA Helm repository:

```sh
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia \
    && helm repo update
```

Create a node selector label on all the nodes in your cluster that support GPU allocation through DRA:

```sh
kubectl label node <node-name> nvidia.com/dra-kubelet-plugin=true
```

Install the GPU Operator without device plugin and ready for monitoring:

```sh
helm upgrade --install gpu-operator nvidia/gpu-operator \
  --version=v26.3.0 \
  --create-namespace \
  --namespace gpu-operator \
  -f helm-values/gpu-operator.yaml
```

Install DRA Driver:

```sh
helm upgrade -i nvidia-dra-driver-gpu nvidia/nvidia-dra-driver-gpu \
  --version="25.12.0" \
  --namespace nvidia-dra-driver-gpu \
  --create-namespace \
  -f helm-values/dra-driver.yaml
```

## Install kube-prometheus-stack for monitoring

Add the Prometheus Helm repository:

```sh
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```
Create and label the configmap for the dashboard:
```sh
kubectl create configmap dcgm-dashboard \
  --from-file=dcgm-dashboard_v2.json \
  -n prometheus

kubectl label configmap dcgm-dashboard \
  grafana_dashboard=1 \
  -n prometheus
```

Install helm for kube-prometheus-stack:

```sh
helm upgrade --install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  --namespace prometheus \
  --create-namespace \
  -f helm-values/prometheus-stack.yaml
```

Get the admin password for Grafana:

```sh
kubectl --namespace prometheus get secrets kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | base64 -d ; echo
```