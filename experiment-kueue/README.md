# Esperimento Kueue: benchmark GPU con MIG e DRA

Questa directory contiene il benchmark batch usato per confrontare quattro
politiche di allocazione su una NVIDIA A100 partizionata in tre device MIG.
Tutti i Job eseguono lo stesso carico di moltiplicazione di matrici; cambiano
soltanto classe di servizio e vincolo GPU.

L'esperimento verifica se una richiesta DRA flessibile, combinata con
l'ammissione Kueue, riduce il tempo necessario a completare una pool rispetto a
claim statici. La flessibilità opera **tra Job**: ogni Job acquisisce un device
all'avvio e lo rilascia alla terminazione. Non sono implementati resize o
migrazioni in esecuzione, riconfigurazione dinamica MIG, predizione o SLO.

## Disegno sperimentale

La geometria MIG rimane fissa:

| Profilo | SM | `DeviceClass` | `ResourceClaimTemplate` | Selettore |
|---|---:|---|---|---|
| S | 14 | `mig-small` | `claim-small` | SM = 14 |
| M | 28 | `mig-medium` | `claim-medium` | SM = 28 |
| L | 42 | `mig-large` | `claim-large` | SM = 42 |
| M oppure L | >= 28 | `mig-fast` | `claim-fast` | SM >= 28 |

Le definizioni sono in `../manifests/kueue-experiment/deviceClasses.yaml` e
`../manifests/kueue-experiment/rct.yaml`.

La pool standard comprende 14 Job:

- 12 Gold con `gold-priority` = 1000;
- 2 Bronze con `bronze-priority` = 100;
- un device per Job;
- stesso carico, immagine e configurazione per entrambe le classi.

La classe di servizio è una policy sperimentale composta da priorità e requisiti
GPU, non una nuova API Kubernetes. La priorità influenza l'ammissione, ma non
assegna da sola un profilo MIG né garantisce un tempo di completamento.

## I quattro arm finali

`baseline-M` e `baseline-L` sono le abbreviazioni degli identificativi usati
da script e risultati, rispettivamente `baseline-medium` e `baseline-large`.

| Arm | Gold | Bronze | LocalQueue / ClusterQueue | Quota |
|---|---|---|---|---|
| `baseline-medium` (baseline-M) | 12 x `claim-medium` | 2 x `claim-small` | `baseline-medium-uq` / `baseline-medium-cq` | 1 S + 1 M |
| `baseline-large` (baseline-L) | 12 x `claim-large` | 2 x `claim-small` | `baseline-large-uq` / `baseline-large-cq` | 1 S + 1 L |
| `baseline-mix` | 6 x `claim-medium` + 6 x `claim-large` | 2 x `claim-small` | `baseline-mix-uq` / `baseline-mix-cq` | 1 S + 1 M + 1 L |
| `d-flex` | 12 x `claim-fast` | 2 x `claim-small` | `dflex-uq` / `dflex-cq` | 1 S + 2 device M/L |

In `baseline-mix` tutti i Gold hanno la stessa priorità: la divisione 6/6 è
imposta dai claim. In `d-flex` ogni nuovo Gold può ricevere M oppure L secondo
la disponibilità, senza una preferenza esplicita per L.

`baseline-mix` è il confronto principale perché, come `d-flex`, può usare
contemporaneamente S, M e L. Le baseline M e L permettono invece ai Gold di usare
una sola partizione veloce e arrivano al massimo a due partizioni concorrenti
insieme a S.

Kueue gestisce ammissione e quote; scheduler e driver DRA assegnano un device
compatibile. Le quote contano i device attraverso i `deviceClassMappings`
configurati nel cluster.

## Struttura

- `benchmark.py`: benchmark CUDA/PyTorch e metriche JSON;
- `Dockerfile`, `Makefile`: build dell'immagine;
- `manifests/benchmark-config.yaml`: parametri comuni;
- `manifests/calibration-{small,medium,large}.yaml`: calibrazione S/M/L;
- `manifests/pool-job-template.yaml`: template comune dei Job;
- `manifests/baseline-mix-queues.yaml`: queue aggiuntive del quarto arm;
- `scripts/run-calibration.sh`: calibrazione sequenziale;
- `scripts/run-{baseline-medium,baseline-large,baseline-mix,d-flex}.sh`: runner;
- `scripts/run-pool-arm.sh`: runner comune a baseline-M, baseline-L e D-Flex;
- `scripts/analyze-pool.py`: report per Job e pool;
- `scripts/compare-arms.py`: confronto fra repliche;
- `results/`: manifest, snapshot, log e report delle esecuzioni.

## Configurazione del carico

La modalità predefinita è **fixed work**:

```text
MATRIX_SIZE=8192
ITERATIONS=100
WARMUP_ITERATIONS=5
TRIALS=1
DTYPE=float32
ALLOW_TF32=false
DURATION_SECONDS=0
```

Ogni profilo esegue lo stesso numero di moltiplicazioni. Questa è la modalità per
confrontare tempi di completamento, makespan e throughput. I valori sono nella
ConfigMap `manifests/benchmark-config.yaml`; `SEED=42` mantiene uguale la
generazione dei dati e `STRICT_DEVICE_CHECK=true` verifica gli SM attesi.

Con `DURATION_SECONDS>0` si ottiene uno stress test a durata fissa. La metrica
utile diventa `iterations_per_second`, non il tempo di completamento. È adatto a
telemetria DCGM e potenza, ma non al confronto principale.

Gli argomenti CLI di `benchmark.py` hanno precedenza sulle variabili d'ambiente:

```bash
python3 benchmark.py --matrix-size 4096 --iterations 20 \
  --dtype float16 --allow-tf32 false
```

## Prerequisiti e installazione

```bash
cd /mnt/c/Users/gianl/Polito/Tesi/Codex/k8s-mig-dra/experiment-kueue
```

Prima di una campagna verificare che kubeconfig e `KUBE_CONTEXT` puntino al
cluster corretto, che `kubectl get nodes` mostri `ai-lab-a100-2`, che non siano
attivi altri workload GPU e che namespace `experiment`, Kueue, driver DRA e
geometria S=14/M=28/L=42 siano operativi.

Installare o aggiornare le risorse:

```bash
kubectl apply -f ../manifests/kueue-experiment/deviceClasses.yaml
kubectl apply -f ../manifests/kueue-experiment/rct.yaml
kubectl apply -f ../manifests/kueue-experiment/wlPriority.yaml
kubectl apply -f ../manifests/kueue-experiment/queues.yaml
kubectl apply -f manifests/baseline-mix-queues.yaml
kubectl apply -f manifests/benchmark-config.yaml
```

Usare lo stesso kubeconfig nei controlli manuali e nei runner:

```bash
export KUBECONFIG=/percorso/del/kubeconfig-vm2
export KUBE_CONTEXT=nome-contesto-vm2   # facoltativo
kubectl get nodes
```

I runner verificano nodo, LocalQueue e ClusterQueue prima della sottomissione.

## Build

L'immagine predefinita è
`gianlucavinci98/gpu-matmul-benchmark:0.1.0` per `linux/amd64`:

```bash
docker login
make build
make push
make inspect
```

Dopo una modifica usare un tag nuovo e aggiornare `image:` nei manifest, così
`imagePullPolicy: IfNotPresent` non riutilizza una copia obsoleta:

```bash
make push TAG=0.1.1
```

Test locale facoltativo (non sostituisce la prova DRA):

```bash
docker run --rm --gpus all \
  gianlucavinci98/gpu-matmul-benchmark:0.1.0 \
  --matrix-size 4096 --iterations 5 --warmup-iterations 1 \
  --expected-multiprocessors 0
```

## Calibrazione

Eseguire S, M e L in sequenza per evitare contesa e power sharing:

```bash
./scripts/run-calibration.sh all
./scripts/run-calibration.sh small    # singolo profilo
TIMEOUT=60m ./scripts/run-calibration.sh all
```

Con la configurazione corrente i tempi CUDA indicativi sono circa 44 s su S,
22 s su M e 14 s su L; non sono tempi end-to-end. Se S dura meno di 20 s,
aumentare `ITERATIONS`; se dura diversi minuti, ridurlo; in caso di OOM ridurre
`MATRIX_SIZE`. I parametri devono restare uguali sui tre profili.

Per misurare la variabilità fra Pod e allocazioni DRA, preferire almeno tre
(meglio cinque) Job indipendenti con `TRIALS=1` e usare la mediana.

## Esecuzione

Non eseguire gli arm in parallelo:

```bash
./scripts/run-baseline-medium.sh
./scripts/run-baseline-large.sh
./scripts/run-baseline-mix.sh
./scripts/run-d-flex.sh
```

I conteggi e il timeout sono configurabili. Per il confronto ufficiale devono
restare 12 Gold e 2 Bronze, con divisione 6/6 in `baseline-mix`:

```bash
GOLD_JOBS=12 BRONZE_JOBS=2 TIMEOUT=20m \
  EXPECTED_NODE=ai-lab-a100-2 ./scripts/run-d-flex.sh

GOLD_MEDIUM_JOBS=6 GOLD_LARGE_JOBS=6 BRONZE_JOBS=2 \
  ./scripts/run-baseline-mix.sh
```

Ogni runner elimina soltanto vecchi Job dello stesso arm, genera `pool.yaml`,
applica la pool, attende il completamento, raccoglie gli oggetti e produce:

- `jobs.json`, `pods.json`, `workloads.json`, `resourceclaims.json`;
- `clusterqueue.yaml`, `localqueue.yaml`, `logs/<job>.log`;
- `jobs.csv` con tempi e device per Job;
- `summary.json` e `summary.txt`.

In D-Flex `EXPECTED_MULTIPROCESSORS=0` disabilita il confronto con un singolo
numero, perché l'immagine 0.1.0 non esprime l'insieme `{28, 42}`. Il vincolo SM
>= 28 resta applicato da `mig-fast`; il device ottenuto viene registrato e
aggregato in `device_distribution_by_class_and_sm`.

## Metriche e confronto

- `makespan`: ultimo `Job completionTime` meno primo `Job creationTimestamp`;
- `throughput`: Job sottomessi diviso makespan;
- `queue_wait`: ammissione Workload meno creazione Job;
- `startup`: avvio Pod meno ammissione Workload;
- `execution`: completamento Job meno `Pod startTime`;
- `end_to_end`: completamento meno creazione del Job;
- `gpu_cuda`: solo calcolo misurato tramite eventi CUDA.

Il makespan include attesa Kueue, startup ed esecuzione dell'intera pool. p50 e
p95 di un `summary.json` descrivono i Job della singola pool, non repliche
indipendenti.

```bash
python3 scripts/compare-arms.py \
  results/*-baseline-medium/summary.json \
  results/*-baseline-large/summary.json \
  results/*-baseline-mix/summary.json \
  results/*-d-flex/summary.json \
  --output results/arm-comparison.json
```

Il confronto usa il p50 dei makespan delle repliche fornite. Il file
`results/arm-comparison.json` esistente riguarda il confronto iniziale a tre
arm e va rigenerato per includere `baseline-mix`.

## Risultati disponibili

Le run verificate contengono 14 Job completati su 14 e zero fallimenti:

| Data UTC | Arm | Makespan | Throughput | Gold |
|---|---|---:|---:|---|
| 2026-08-17 14:52 | `baseline-medium` | 370 s | 0,03784 Job/s | 12 M |
| 2026-08-17 16:39 | `baseline-large` | 275 s | 0,05091 Job/s | 12 L |
| 2026-08-17 16:47 | `d-flex` | 156 s | 0,08974 Job/s | M oppure L |
| 2026-08-18 10:12 | `baseline-mix` | 185 s | 0,07568 Job/s | 6 M, 6 L |
| 2026-08-18 10:16 | `d-flex` | 158 s | 0,08861 Job/s | 5 M, 7 L |

Il confronto principale del 18 agosto, a parità di partizioni utilizzabili,
mostra:

- makespan da 185 s a 158 s: 27 s risparmiati, -14,59%, speedup 1,171x;
- throughput da 0,07568 a 0,08861 Job/s: +17,09%;
- Gold end-to-end p50 invariato a 90,5 s e p95 da 167,95 s a 154,15 s;
- Bronze stabile: execution media 52,5 s ed end-to-end medio 79,5 s vs 80 s.

Il beneficio è soprattutto nella coda finale: in `baseline-mix` un Gold legato
a M non può usare L quando si libera, mentre D-Flex mantiene M e L ammissibili
per i Job non ancora avviati.

I confronti con baseline-M e baseline-L includono anche il vantaggio di rendere
disponibili entrambe le partizioni veloci. I dati correnti sono singole
esecuzioni, non una campagna sufficiente per inferenza statistica, e il carico è
matriciale omogeneo, non ancora inferenza AI. Il risultato riguarda quindi la
soluzione combinata MIG + DRA + Kueue e non isola causalmente il solo DRA.

## Diagnostica

```bash
kubectl get jobs,pods,workloads,resourceclaims -n experiment -w
kubectl get clusterqueues
kubectl get localqueues -n experiment
kubectl describe workload -n experiment <nome-workload>
kubectl get resourceclaims -n experiment -o yaml
```

Il container stampa `GPU_ACQUIRED` con nome, SM e memoria del device. Gli eventi
`BENCHMARK_JSON` includono il riepilogo finale con device, claim, tempi CUDA e
wall-clock, iterazioni/s, TFLOP/s stimati, memoria e checksum.
