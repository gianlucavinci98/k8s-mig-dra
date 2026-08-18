# Esperimento baseline-mix

`baseline-mix` usa le stesse tre partizioni contemporaneamente di D-Flex, ma
assegna staticamente i Gold:

- 6 Gold con `gold-priority` e `claim-medium`;
- 6 Gold con `gold-priority` e `claim-large`;
- 2 Bronze con `bronze-priority` e `claim-small`.

La priorità definisce l'ordine di ammissione, non il profilo GPU. Il vincolo
statico è imposto dal `ResourceClaimTemplate` di ciascun Job: un Job Gold con
`claim-medium` può usare soltanto M e un Job Gold con `claim-large` soltanto L.

## Installazione della queue

Una sola volta:

```bash
kubectl apply -f manifests/baseline-mix-queues.yaml
kubectl get clusterqueue baseline-mix-cq
kubectl get localqueue baseline-mix-uq -n experiment
```

La ClusterQueue espone una quota per S, una per M e una per L.

## Esecuzione

Assicurarsi che non siano attivi altri workload GPU e che il kubeconfig punti al
cluster contenente `ai-lab-a100-2`:

```bash
export KUBECONFIG=/percorso/del/kubeconfig-vm2
kubectl get nodes
./scripts/run-baseline-mix.sh
```

I valori predefiniti sono parametrizzabili, ma per l'esperimento comparativo
devono rimanere 6, 6 e 2:

```bash
GOLD_MEDIUM_JOBS=6 GOLD_LARGE_JOBS=6 BRONZE_JOBS=2 \
  ./scripts/run-baseline-mix.sh
```

Il risultato viene salvato in `results/<timestamp>-baseline-mix/` con la stessa
struttura degli altri arm. Nel `summary.json` la distribuzione attesa è:

```json
{
  "device_distribution_by_class_and_sm": {
    "bronze": {"14": 2},
    "gold": {"28": 6, "42": 6}
  }
}
```

## Confronto

Dopo avere almeno una replica per arm:

```bash
python3 scripts/compare-arms.py \
  results/*-baseline-medium/summary.json \
  results/*-baseline-large/summary.json \
  results/*-baseline-mix/summary.json \
  results/*-d-flex/summary.json \
  --output results/arm-comparison.json
```

Il confronto principale per isolare il vantaggio della flessibilità è
`d-flex_vs_baseline-mix`: entrambi usano S, M e L, ma soltanto D-Flex può adattare
dinamicamente la ripartizione dei Gold alla velocità e disponibilità dei device.
