## NVIDIA GPU Diagnostics and Monitoring

Use this command to show a concise real-time snapshot of GPU status (utilization, memory, temperature, and processes).

```sh
nvidia-smi
```

Use this command to refresh GPU status every second.

```sh
watch -n 1 nvidia-smi
```

Use this command to list all GPUs visible to the system with their indexes and names.

```sh
nvidia-smi -L
```

Use this command to run a container with access to specific GPU devices and verify visibility from inside the container.

```sh
docker run --rm --runtime=nvidia --gpus '"device=0:1"' ubuntu nvidia-smi
```

## MIG Management

Use this command to create MIG GPU instances and compute instances with predefined profiles.

```sh
sudo nvidia-smi mig -cgi 15,14 -C
```

##### Remove MIG Partitions

Use this command to delete a compute instance from GPU instance 3 (compute instance 0).

```sh
sudo nvidia-smi mig -dci -gi 3 -ci 0
```

Use this command to delete GPU instance 3 and free its allocated resources.

```sh
sudo nvidia-smi mig -dgi -gi 3
```

##### List MIG Profiles and Instances

Use this command to list available GPU instance profiles supported by the current GPU.

```sh
sudo nvidia-smi mig -lgip
```

Use this command to list available compute instance profiles.

```sh
sudo nvidia-smi mig -lci
```

Use this command to list currently created GPU instances.

```sh
sudo nvidia-smi mig -lgi
```

#### MIG Configuration via GPU Operator
Change mig configuration by updating `nvidia.com/mig.config` label on he node
```sh
kubectl label nodes <node-name> nvidia.com/mig.config=all-balanced --overwrite
```

## Container Test

Use this command to run a GPU-enabled container and execute the MNIST GPU workload.

```sh
docker run --gpus '"device=0:1"' --ipc=host --rm gianlucavinci98/mnist-gpu:latest
```

## K3s Service Management

Use this command to stop the k3s service safely.

```sh
sudo systemctl stop k3s
```

Use this command to start the k3s service.

```sh
sudo systemctl start k3s
```