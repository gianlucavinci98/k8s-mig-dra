# Esecuzione dei tre arm

Tutti gli arm usano per default la stessa pool di 12 Gold e 2 Bronze e lo stesso
`benchmark-config.yaml`.

| Arm | Gold | Bronze | LocalQueue | ClusterQueue |
|---|---|---|---|---|
| baseline-medium | `claim-medium` | `claim-small` | `baseline-medium-uq` | `baseline-medium-cq` |
| baseline-large | `claim-large` | `claim-small` | `baseline-large-uq` | `baseline-large-cq` |
| d-flex | `claim-fast` | `claim-small` | `dflex-uq` | `dflex-cq` |

Prima di ogni replica assicurarsi che non siano attivi altri workload GPU e che
`kubectl get nodes` mostri `ai-lab-a100-2`. Non eseguire gli arm in parallelo.

```bash
export KUBECONFIG=/percorso/del/kubeconfig-vm2
./scripts/run-baseline-medium.sh
./scripts/run-baseline-large.sh
./scripts/run-d-flex.sh
```

I tre script producono la stessa struttura sotto `results/`. In particolare:

- `summary.json` contiene il makespan e le statistiche per classe;
- `jobs.csv` contiene i tempi e la GPU realmente acquisita da ogni Job;
- `device_distribution_by_class_and_sm` mostra quanti Job hanno usato 14, 28 o
  42 SM ed è particolarmente importante per D-Flex.

In D-Flex `EXPECTED_MULTIPROCESSORS=0` disabilita il confronto con un singolo
numero perché l'immagine 0.1.0 accetta un solo valore atteso. Il vincolo è comunque
applicato da `mig-fast` (`SM >= 28`) e gli SM realmente ottenuti vengono registrati
e aggregati nel report.

Ripetere ciascun arm almeno cinque volte. Per confrontare tutti i riepiloghi:

```bash
python3 scripts/compare-arms.py \
  results/*-baseline-medium/summary.json \
  results/*-baseline-large/summary.json \
  results/*-d-flex/summary.json \
  --output results/arm-comparison.json
```

Il confronto usa il p50 dei makespan delle repliche indipendenti e calcola per
D-Flex secondi risparmiati, riduzione percentuale del makespan e speedup rispetto
a entrambe le baseline.
