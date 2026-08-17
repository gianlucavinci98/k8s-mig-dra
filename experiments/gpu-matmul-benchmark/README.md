# GPU matrix benchmark per MIG, DRA e Kueue

Questo esperimento esegue lo stesso carico di moltiplicazioni di matrici sulle tre
partizioni MIG già configurate nel cluster:

| Profilo | SM attesi | DeviceClass | ResourceClaimTemplate | LocalQueue |
|---|---:|---|---|---|
| S | 14 | `mig-small` | `claim-small` | `baseline-medium-uq` |
| M | 28 | `mig-medium` | `claim-medium` | `baseline-medium-uq` |
| L | 42 | `mig-large` | `claim-large` | `baseline-large-uq` |

I nomi provengono dai manifest in `manifests/experiment`. Il profilo L reale del
testbed è una MIG 3g da 42 SM. `claim-fast` non viene usato durante la calibrazione:
servirà in seguito per D-FLEX, dopo aver misurato separatamente M e L.

## Contenuto

- `benchmark.py`: benchmark CUDA/PyTorch e produzione di metriche JSON.
- `Dockerfile`: immagine riproducibile basata su PyTorch 2.7.1 e CUDA 12.8.
- `manifests/benchmark-config.yaml`: parametri comuni del carico.
- `manifests/calibration-{small,medium,large}.yaml`: Job Kueue/DRA separati.
- `scripts/run-calibration.sh`: esecuzione sequenziale e raccolta automatica.
- `results/`: risultati locali, ignorati da Git.

## Modalità del benchmark

La modalità predefinita è **fixed work**:

```text
DURATION_SECONDS=0
ITERATIONS=100
```

Ogni profilo esegue lo stesso numero di moltiplicazioni. Questa è la modalità da
usare per confrontare il tempo di completamento di S, M e L.

È disponibile anche la modalità a durata fissa:

```text
DURATION_SECONDS=60
```

In questo caso tutti i Job durano almeno 60 secondi e la metrica significativa è
`iterations_per_second`, non il tempo di completamento. È utile per stress test,
telemetria DCGM e consumi, ma non per la calibrazione iniziale.

## Parametri

I valori sono nella ConfigMap `manifests/benchmark-config.yaml` e possono essere
modificati senza ricostruire l'immagine:

| Variabile | Default | Significato |
|---|---:|---|
| `MATRIX_SIZE` | 8192 | Lato delle matrici quadrate |
| `ITERATIONS` | 100 | Moltiplicazioni misurate per trial |
| `WARMUP_ITERATIONS` | 5 | Iterazioni escluse dalla misura |
| `TRIALS` | 1 | Ripetizioni interne allo stesso Pod |
| `DTYPE` | `float32` | `float32`, `float16` o `bfloat16` |
| `ALLOW_TF32` | `false` | Abilita TF32 per matmul float32 |
| `SEED` | 42 | Seed uguale per tutti i Job |
| `DURATION_SECONDS` | 0 | Se positivo, attiva la modalità a durata |
| `DURATION_CHECK_INTERVAL` | 5 | Frequenza di sincronizzazione in modalità a durata |
| `STRICT_DEVICE_CHECK` | `true` | Fallisce se gli SM visibili non sono quelli attesi |

Il benchmark accetta anche gli stessi valori come opzioni CLI, per esempio:

```bash
--matrix-size 4096 --iterations 20 --dtype float16 --allow-tf32 false
```

Le opzioni CLI hanno precedenza sulle variabili d'ambiente.

## Build e push su Docker Hub

Accedere alla directory:

```bash
cd /mnt/c/Users/gianl/Polito/Tesi/Codex/k8s-mig-dra/experiments/gpu-matmul-benchmark
```

Verificare l'architettura dei nodi:

```bash
kubectl get nodes -o custom-columns=NAME:.metadata.name,ARCH:.status.nodeInfo.architecture
```

I comandi seguenti assumono nodi `amd64`.

Autenticarsi su Docker Hub:

```bash
docker login
```

Build locale:

```bash
docker buildx build \
  --platform linux/amd64 \
  --build-arg IMAGE_VERSION=0.1.0 \
  -t gianlucavinci98/gpu-matmul-benchmark:0.1.0 \
  --load .
```

Push diretto durante il build:

```bash
docker buildx build \
  --platform linux/amd64 \
  --build-arg IMAGE_VERSION=0.1.0 \
  -t gianlucavinci98/gpu-matmul-benchmark:0.1.0 \
  --push .
```

Gli stessi comandi sono disponibili tramite Makefile:

```bash
make build
make push
make inspect
```

Se si modifica il codice, usare un tag nuovo, ad esempio:

```bash
make push TAG=0.1.1
```

e aggiornare `image:` nei tre manifest. Non riutilizzare silenziosamente `0.1.0`
con `imagePullPolicy: IfNotPresent`, perché un nodo potrebbe conservare la vecchia
immagine in cache.

## Test locale facoltativo

Su una macchina con NVIDIA Container Toolkit:

```bash
docker run --rm --gpus all \
  gianlucavinci98/gpu-matmul-benchmark:0.1.0 \
  --matrix-size 4096 \
  --iterations 5 \
  --warmup-iterations 1 \
  --expected-multiprocessors 0
```

Il test locale controlla l'avvio dell'immagine, ma non sostituisce la prova DRA.

## Esecuzione manuale nel cluster

Applicare prima la configurazione comune:

```bash
kubectl apply -f manifests/benchmark-config.yaml
```

Eseguire **un profilo alla volta**, per evitare che power sharing, temperatura o
contesa del nodo alterino la calibrazione.

### Profilo S

```bash
kubectl delete job gpu-calibration-small -n experiment --ignore-not-found
kubectl apply -f manifests/calibration-small.yaml
kubectl wait --for=condition=complete job/gpu-calibration-small \
  -n experiment --timeout=30m
kubectl logs -n experiment job/gpu-calibration-small
```

### Profilo M

```bash
kubectl delete job gpu-calibration-medium -n experiment --ignore-not-found
kubectl apply -f manifests/calibration-medium.yaml
kubectl wait --for=condition=complete job/gpu-calibration-medium \
  -n experiment --timeout=30m
kubectl logs -n experiment job/gpu-calibration-medium
```

### Profilo L

```bash
kubectl delete job gpu-calibration-large -n experiment --ignore-not-found
kubectl apply -f manifests/calibration-large.yaml
kubectl wait --for=condition=complete job/gpu-calibration-large \
  -n experiment --timeout=30m
kubectl logs -n experiment job/gpu-calibration-large
```

Per seguire il Pod durante l'esecuzione:

```bash
kubectl get jobs,pods,workloads,resourceclaims -n experiment -w
```

Se il Job non parte:

```bash
kubectl describe job gpu-calibration-small -n experiment
kubectl get workloads -n experiment
kubectl describe workload -n experiment <nome-workload>
kubectl get resourceclaims -n experiment -o yaml
```

## Esecuzione e raccolta automatica

Lo script esegue i profili in sequenza, elimina solamente l'omonimo Job di
calibrazione prima di ricrearlo e salva log e oggetti Kubernetes in `results/`:

```bash
./scripts/run-calibration.sh all
```

È possibile eseguire un solo profilo:

```bash
./scripts/run-calibration.sh small
./scripts/run-calibration.sh medium
./scripts/run-calibration.sh large
```

Per aumentare il timeout:

```bash
TIMEOUT=60m ./scripts/run-calibration.sh all
```

Ogni directory dei risultati contiene:

- `benchmark.log`: output completo del container;
- `metrics.jsonl`: soli eventi JSON senza il prefisso `BENCHMARK_JSON`;
- `job.yaml` e `pods.yaml`;
- `workloads.yaml` e `resourceclaims.yaml`.

## Output principale

Il container stampa subito il device CUDA visibile:

```text
GPU_ACQUIRED name='NVIDIA A100-SXM4-40GB MIG ...' sm=14 memory_gib=4.75 ...
```

Ogni evento strutturato inizia con:

```text
BENCHMARK_JSON { ... }
```

L'evento finale `benchmark_summary` contiene:

- nome, memoria, compute capability e SM visibili;
- claim e profilo attesi;
- tempo wall-clock e tempo CUDA;
- iterazioni al secondo;
- millisecondi medi per moltiplicazione;
- TFLOP/s stimati;
- picco di memoria allocata e riservata;
- checksum;
- p50 e p95 dei trial interni.

Per estrarre solo il riepilogo:

```bash
kubectl logs -n experiment job/gpu-calibration-small \
  | grep '"event": "benchmark_summary"'
```

## Scelta del carico definitivo

1. Avviare con `MATRIX_SIZE=8192`, `ITERATIONS=100` e `TRIALS=1`.
2. Se S dura meno di 20 secondi, aumentare `ITERATIONS`.
3. Se S dura diversi minuti, ridurre `ITERATIONS`.
4. Se S va in OOM, ridurre `MATRIX_SIZE`.
5. Mantenere gli stessi parametri per S, M e L.
6. Ripetere ogni profilo almeno 3 volte, preferibilmente 5.
7. Per ogni profilo usare la mediana (`p50`) delle ripetizioni indipendenti.

Per la calibrazione scientifica è preferibile realizzare più Job indipendenti con
`TRIALS=1`, invece di un solo Job con molti trial: in questo modo si include e si
può misurare anche la variabilità fra Pod e allocazioni DRA successive.

