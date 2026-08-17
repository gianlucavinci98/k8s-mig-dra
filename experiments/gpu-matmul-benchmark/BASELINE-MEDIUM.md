# Esperimento baseline-medium

La pool predefinita contiene 12 Job Gold e 2 Job Bronze:

- Gold: `gold-priority`, `baseline-medium-uq`, `claim-medium`;
- Bronze: `bronze-priority`, `baseline-medium-uq`, `claim-small`;
- `baseline-medium-cq`: al massimo un device M e un device S;
- lavoro identico per tutti i Job, definito da `manifests/benchmark-config.yaml`.

Prima dell'esecuzione verificare che non siano presenti altri carichi GPU sul nodo.
Usare il kubeconfig che punta al cluster su `ai-lab-a100-2` e non usare `sudo`:

```bash
cd experiments/gpu-matmul-benchmark
export KUBECONFIG=/percorso/del/kubeconfig-vm2
kubectl get nodes
./scripts/run-baseline-medium.sh
```

Per specificare anche il contesto:

```bash
KUBE_CONTEXT=nome-contesto-vm2 ./scripts/run-baseline-medium.sh
```

I conteggi e il timeout sono parametrizzabili:

```bash
GOLD_JOBS=12 BRONZE_JOBS=2 TIMEOUT=20m \
  EXPECTED_NODE=ai-lab-a100-2 \
  ./scripts/run-baseline-medium.sh
```

Lo script:

1. verifica contesto, nodo e LocalQueue;
2. elimina solo i vecchi Job etichettati `baseline-medium`;
3. genera e salva un manifest multi-documento della pool;
4. applica ConfigMap e pool;
5. attende tutti i completamenti;
6. salva oggetti Kubernetes/Kueue e log di ciascun Pod;
7. genera automaticamente il rapporto statistico.

Ogni replica crea `results/<timestamp>-baseline-medium/` con:

- `pool.yaml`: manifest esatto applicato;
- `jobs.json`, `pods.json`, `workloads.json`, `resourceclaims.json`;
- `clusterqueue.yaml` e `localqueue.yaml`;
- `logs/<job>.log`;
- `jobs.csv`: tempi di ogni Job;
- `summary.json`: makespan, throughput e statistiche per classe;
- `summary.txt`: riepilogo leggibile.

Il makespan è calcolato tramite timestamp del control plane:

```text
max(Job completionTime) - min(Job creationTimestamp)
```

Include quindi attesa Kueue, avvio ed esecuzione dell'intera pool.
