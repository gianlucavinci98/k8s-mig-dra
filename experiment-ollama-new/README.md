# Ollama experiment with GPU telemetry

This directory is an independent copy of the Ollama load-test workflow. It keeps
new request and GPU results under `experiment-ollama-new/results/`, without
overwriting the historical data in `experiment-ollama/results/`.

## Run

Use the same positional arguments as the original script:

```bash
./load-test.sh [TOTAL_REQUESTS] [CONCURRENCY] [SAVE_RESULT_LOG]
```

Example:

```bash
./load-test.sh 500 100 1
```

The existing `NUM_PREDICT` override is unchanged:

```bash
NUM_PREDICT=100 ./load-test.sh 500 100 1
```

Optional telemetry overrides:

- `PROMETHEUS_URL` (default `http://10.146.0.55:30090`)
- `PROMETHEUS_STEP_SECONDS` (default `5`, matching the DCGM export and scrape interval)
- `PROMETHEUS_PADDING_BEFORE_SECONDS` (default `15`, used for the idle-power estimate)
- `PROMETHEUS_PADDING_AFTER_SECONDS` (default `5`)
- `PROMETHEUS_SCRAPE_WAIT_SECONDS` (default `6`)
- `MIG_TOTAL_COMPUTE_SLICES` (default `7` for the A100)
- `GPU_PHYSICAL_MEMORY_MIB` (optional override; otherwise inferred from `modelName`)

The script checks all required DCGM series before sending requests. After the
last request, it waits for the final Prometheus scrape, collects the range data,
and runs `evaluate.py`.

## Collected DCGM metrics

- `DCGM_FI_PROF_GR_ENGINE_ACTIVE`: primary SM/graphics-engine activity metric.
- `DCGM_FI_PROF_DRAM_ACTIVE`: active fraction of the memory interface.
- `DCGM_FI_DEV_FB_USED` and `DCGM_FI_DEV_FB_FREE`: allocated/free framebuffer memory.
- `DCGM_FI_DEV_POWER_USAGE`: physical GPU board power in watts.

`GR_ENGINE_ACTIVE` and `DRAM_ACTIVE` are fractions in `[0, 1]` in Prometheus;
the reports convert them to percentages.

## Partition and whole-GPU views

The normalized GPU CSV contains three scopes:

- `partition`: the value reported for each `GPU_I_ID`; utilization is relative
  to that MIG instance.
- `physical_gpu`: all MIG instances belonging to one GPU UUID. SM activity is
  weighted by the compute-slice count in `GPU_I_PROFILE` and divided by the
  seven A100 compute slices. DRAM activity is weighted by the memory capacity
  encoded in the profile. Framebuffer use is summed across distinct instances.
- `system`: power is summed across distinct physical GPUs, while utilization is
  capacity-normalized across them. In the current single-GPU cluster this view
  equals the physical-GPU view.

DCGM exposes the same board-power measurement once for every MIG instance.
Those copies are averaged per physical GPU UUID and timestamp; they are never
summed. This avoids multiplying A100 power by the number of MIG partitions.

## Energy and useful work

Energy is computed with trapezoidal integration over the same wall-clock window
used by the request analysis: first request start to last request completion.

```text
energy [J] = integral(power [W] dt)
energy [Wh] = energy [J] / 3600
```

The analysis also reports:

- average, p95, and peak board power;
- total energy and dynamic energy above the pre-test idle estimate;
- joules per generated token and generated tokens per joule;
- capacity-equivalent SM-active seconds;
- average/peak framebuffer occupancy;
- correlations between active requests, SM activity, and power.

Per-request CSV rows include the average shared GPU state during each request.
They do **not** assign energy to individual requests, because concurrent request
windows overlap. Energy-per-token and energy-per-request are calculated only by
dividing the run-level integral by completed work.

## Outputs

The following scratch files always describe the latest run:

- `results/results.jsonl`: Ollama response measurements.
- `results/metadata.json`: experiment configuration and collection settings.
- `results/gpu-metrics.json`: raw Prometheus range-query responses.
- `results/gpu-metrics.csv`: normalized partition, physical-GPU, and system samples.
- `results/run-summary.json`: request, GPU, power, and energy summary.

When `SAVE_RESULT_LOG` is enabled, the workflow also preserves run-specific
`.log`, per-request `.csv`, `-gpu-metrics.json`, `-gpu-metrics.csv`, and
`-summary.json` files and appends one row to `results/results_table.csv`.

Run `python3 plot.py` after collecting multiple configurations/concurrency
levels. It produces throughput, utilization, power, energy-per-token,
power-versus-SM, and throughput-versus-energy-efficiency plots.

## Mapping to the presentation claims

The collected evidence can test, but must not predetermine, the claims in the
Experiment 1 slides:

- **Resource waste:** compare physical SM utilization and physical framebuffer
  utilization at equal workload and concurrency.
- **Power is not necessarily linear in load:** compare average power against
  physical SM utilization and active requests across several load levels; use
  the saved correlations only as within-run descriptive statistics.
- **More useful work per unit time:** compare real throughput at equal output
  token count and concurrency.
- **Energy efficiency:** compare joules/token or tokens/joule, not utilization
  alone.
- **Right sizing and multiple MIG instances:** compare throughput, latency,
  physical utilization, power, and energy-per-token together. A throughput gain
  is beneficial only if latency/SLO behavior remains acceptable.

Repeated runs are required before treating differences as reproducible. The
plots aggregate repeated points by configuration and concurrency and show one
standard-deviation error bars when replicas are available.
