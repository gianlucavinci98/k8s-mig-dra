# Ollama experiment with delayed GPU telemetry

This directory is an independent copy of the Ollama load-test workflow. It
keeps request and GPU results under `experiment-ollama-new/results/`, without
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

## Why collection continues after the requests

DCGM can export no faster than every 5 seconds in this testbed, and Prometheus
scrapes that exporter asynchronously. A run shorter than 5 seconds can
therefore finish before its non-zero sample reaches Prometheus. The Grafana
plot still moves, but several seconds after the HTTP requests have completed.

The collector consequently does **not** clip GPU data to the request timestamps.
It performs these steps instead:

1. records the exact HTTP workload start and end;
2. polls the raw Prometheus samples until `GR_ENGINE_ACTIVE` becomes non-zero;
3. waits for the first following idle sample, or until the safety timeout;
4. saves the complete delayed pyramid/trapezoid, including an idle sample on
   each side;
5. integrates the pulse area and normalizes it using the actual workload wall
   time.

The implementation uses an instant PromQL range-vector query such as
`DCGM_FI_PROF_GR_ENGINE_ACTIVE[...s]`. This preserves the timestamps of stored
scrapes. It deliberately avoids `/query_range`, whose evaluation grid can miss
a short pulse even when Prometheus has stored it.

Optional telemetry overrides:

- `PROMETHEUS_URL` (default `http://10.146.0.55:30090`)
- `PROMETHEUS_SAMPLE_INTERVAL_SECONDS` (default `5`; the nominal DCGM interval)
- `PROMETHEUS_STEP_SECONDS` (legacy alias for the previous variable)
- `PROMETHEUS_PADDING_BEFORE_SECONDS` (default `20`; pre-run idle baseline)
- `PROMETHEUS_ACTIVITY_WAIT_TIMEOUT_SECONDS` (default `25`)
- `PROMETHEUS_POLL_SECONDS` (default `2`)
- `PROMETHEUS_SETTLE_SAMPLES` (default `1`; idle samples required after activity)
- `GPU_ACTIVITY_THRESHOLD_PCT` (default `0.1`, relative to each MIG partition)
- `MIG_TOTAL_COMPUTE_SLICES` (default `7` for the A100)
- `GPU_PHYSICAL_MEMORY_MIB` (optional; otherwise inferred from `modelName`)

The script checks all required DCGM series before sending requests. Collection
then waits adaptively; it usually ends after the delayed pulse and its next idle
scrape, rather than after a fixed sleep.

## Collected DCGM metrics

- `DCGM_FI_PROF_GR_ENGINE_ACTIVE`: primary SM/graphics-engine activity metric.
- `DCGM_FI_PROF_DRAM_ACTIVE`: active fraction of the memory interface.
- `DCGM_FI_DEV_FB_USED` and `DCGM_FI_DEV_FB_FREE`: allocated/free framebuffer.
- `DCGM_FI_DEV_POWER_USAGE`: physical GPU board power in watts.

`GR_ENGINE_ACTIVE` and `DRAM_ACTIVE` are fractions in `[0, 1]` in Prometheus;
the reports convert them to percentages.

## Partition and whole-GPU views

The normalized GPU CSV contains three scopes:

- `partition`: value reported for each `GPU_I_ID`, relative to that MIG instance;
- `physical_gpu`: instances of one GPU UUID, with SM activity weighted by the
  compute slices in `GPU_I_PROFILE` and divided by the seven A100 slices; DRAM
  activity is weighted by profile memory, and framebuffer use is summed;
- `system`: power is summed across distinct physical GPUs and utilization is
  capacity-normalized across them. On this single-GPU cluster it equals the
  physical-GPU view.

DCGM exposes the same board-power value once per MIG instance. These copies are
averaged per physical GPU UUID and timestamp and are never summed, avoiding an
artificial multiplication by the number of partitions.

## Aggregation method

Let the delayed non-idle SM episode be the samples from the last idle sample
before activity through the first idle sample after activity. The script
integrates its pyramid/trapezoid with the trapezoidal rule:

```text
capacity-equivalent SM seconds = integral(physical SM utilization / 100 dt)
workload-normalized SM utilization = integral(physical SM utilization dt)
                                     / HTTP workload wall time
```

The first value measures how much physical-GPU capacity was active. The second
makes runs with different completion times comparable without pretending that
the delayed sample was synchronous with an individual request. The report also
retains the observed-episode average and peak, which describe the sampled shape
itself.

Framebuffer occupancy is persistent rather than a short pulse, so its average
and peak are evaluated over the captured GPU episode.

Energy separates idle consumption from the delayed response:

```text
dynamic energy [J] = integral(max(power - idle_power, 0) dt)
total run energy [J] = idle_power * HTTP wall time + dynamic energy
energy [Wh] = energy [J] / 3600
```

`idle_power` is the median of the samples before the delayed SM episode. The
same run-level energy is used for joules/token and tokens/joule. The report also
shows the raw observed-episode power average, p95 and peak.

## Quality and interpretation

`run-summary.json` contains `gpu_metrics.telemetry_episode.quality`:

- `good`: a complete episode was captured with at least two active samples and
  the run lasted at least two nominal telemetry intervals;
- `coarse_but_comparable`: the pulse is complete, but the workload is shorter
  than 10 seconds or contains only one active sample;
- `incomplete_episode`: the leading or trailing idle boundary is missing;
- `invalid_no_activity_episode`: no non-idle SM sample was observed; utilization
  and energy are reported as `n/a`, never as a misleading zero.

A `coarse_but_comparable` result is suitable for repeated, like-for-like
comparisons across MIG configurations and concurrency levels, but not as an
exact point-by-point reconstruction. Longer runs remain preferable for absolute
energy values and correlations.

Per-request GPU averages and correlations between instantaneous active-request
count and GPU values are intentionally disabled. With delayed 5-second samples,
assigning a value to one overlapping request would fabricate precision. Request
latency, token throughput and GPU metrics are crossed only at run level.

## Outputs

The following scratch files always describe the latest run:

- `results/results.jsonl`: Ollama response measurements;
- `results/metadata.json`: experiment and capture settings;
- `results/gpu-metrics.json`: raw Prometheus samples and capture status;
- `results/gpu-metrics.csv`: normalized partition, GPU and system samples;
- `results/run-summary.json`: request, telemetry-episode, power and energy summary.

When `SAVE_RESULT_LOG` is enabled, the workflow also preserves run-specific
`.log`, per-request `.csv`, `-gpu-metrics.json`, `-gpu-metrics.csv`, and
`-summary.json` files and appends one row to `results/results_table.csv`.

Run `python3 plot.py` after collecting multiple configurations/concurrency
levels. It produces throughput, utilization, power, energy-per-token,
power-versus-SM, and throughput-versus-energy-efficiency plots.

## Mapping to the presentation claims

The measurements test, rather than assume, the Experiment 1 claims:

- **Resource waste:** compare workload-normalized physical SM utilization and
  physical framebuffer utilization at equal work and concurrency.
- **Power is not necessarily linear in load:** compare episode-level SM area,
  power and dynamic energy across load levels. Power-to-SM correlation is
  descriptive within the delayed episode.
- **More useful work per unit time:** compare real generated-token throughput at
  equal output-token settings.
- **Energy efficiency:** compare joules/token or tokens/joule, not utilization
  alone.
- **Right sizing and multiple MIG instances:** compare throughput, latency,
  physical utilization, power and energy-per-token together.

Repeated runs are required before treating a difference as reproducible. Keep
the exporter interval, collector thresholds and workload parameters identical
across configurations; separate `good` and `coarse_but_comparable` runs during
statistical analysis.
