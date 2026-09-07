# Suggested slide sequence — Kueue, DRA and MIG

The PNG assets contain only schematic labels. Titles, explanatory bullets and technical details remain outside the images so they can be arranged freely in the presentation.

## Slide 1 — From Static Services to Dynamic Batch Jobs

- The Ollama experiment demonstrated the consolidation benefits of MIG, but DRA was used only for initial provisioning.
- A long-running service acquires a device once and keeps it for its whole lifetime.
- Batch Jobs have a finite lifetime: they are submitted, admitted, executed and completed.
- Completion releases the resource claim. A later Job can therefore receive the best compatible partition currently available.
- Kueue controls admission according to priority and device quotas; the scheduler and DRA perform the actual device allocation.

**Core message:** the recurring lifecycle of batch Jobs creates repeated allocation decisions, which is where DRA flexibility becomes useful.

**Suggested images:** `01-from-ollama-to-batch-jobs.png`, `02-kueue-admission-and-dra.png`.

## Slide 2 — From Priority to Service Class

- Kueue priority defines which pending workload should be admitted first.
- Priority alone does not constrain the compute capacity assigned to the admitted Job and therefore provides no execution-time guarantee.
- The experiment introduces an application-level **service class**:
  **service class = admission priority + GPU constraint**.
- Gold and Bronze are policies implemented by combining a `WorkloadPriorityClass` with a DRA `ResourceClaimTemplate`/DeviceClass.
- This is an experimental policy concept, not a new native Kubernetes `ServiceClass` API.

**Suggested image:** `03-priority-to-service-class.png`.

## Slide 3 — Service Classes and GPU Assignment

- **Bronze:** priority 100; always requests S, the 14-SM partition.
- **Gold:** priority 1000; requires at least 28 SM.
- **Static M:** every Gold Job is bound to M (28 SM).
- **Static L:** every Gold Job is bound to L (42 SM).
- **D-Flex:** every Gold Job accepts M or L; DRA allocates one compatible device according to availability.
- Fixed-profile requests reproduce the restriction of a Device-Plugin-style configuration, where the Pod requests one predefined MIG resource profile.
- Allocation happens before execution: there is no in-place resizing or migration of a running Job.

**Suggested images:** `04-service-class-policies.png`, optionally `13-static-profile-vs-dra-selector.png`.

## Slide 4 — The DeviceClass Is the Key Enabler

Four DeviceClasses were created:

- `mig-small`: exactly 14 SM;
- `mig-medium`: exactly 28 SM;
- `mig-large`: exactly 42 SM;
- `mig-fast`: at least 28 SM, therefore M or L.

The exact selector for a fixed large partition is:

```yaml
apiVersion: resource.k8s.io/v1
kind: DeviceClass
metadata:
  name: mig-large
spec:
  selectors:
    - cel:
        expression: |-
          device.driver == "gpu.nvidia.com" &&
          device.attributes["gpu.nvidia.com"].type == "mig" &&
          device.capacity["gpu.nvidia.com"].multiprocessors.compareTo(quantity("42")) == 0
```

The flexible selector is:

```yaml
apiVersion: resource.k8s.io/v1
kind: DeviceClass
metadata:
  name: mig-fast
spec:
  selectors:
    - cel:
        expression: |-
          device.driver == "gpu.nvidia.com" &&
          device.attributes["gpu.nvidia.com"].type == "mig" &&
          device.capacity["gpu.nvidia.com"].multiprocessors.compareTo(quantity("28")) >= 0
```

The essential line is:

```text
device.capacity["gpu.nvidia.com"].multiprocessors.compareTo(quantity("28")) >= 0
```

It changes the request from “give me exactly profile M” to “give me any MIG device with at least 28 SM”. With the fixed geometry used in the experiment, the compatible set is M or L.

**Suggested images:** `05-deviceclass-capacity-filter.png`, `06-deviceclass-exact-vs-flexible.png`, `07-claim-device-eligibility-v2.png`.

## Slide 5 — Experiment Design

- One A100 GPU split into three concurrent MIG partitions: S = 14 SM, M = 28 SM and L = 42 SM.
- One pool of 14 Kubernetes Jobs: 12 Gold and 2 Bronze.
- Every Job runs the same matrix-multiplication benchmark with the same image and parameters; only the service class changes.
- Kueue ClusterQueues account for devices by count.
- **Baseline M:** Bronze uses S; all Gold Jobs use M.
- **Baseline L:** Bronze uses S; all Gold Jobs use L.
- **D-Flex:** Bronze uses S; Gold Jobs can use either M or L.
- Primary outcome: pool makespan, from the creation of the first Job to the completion of the last Job.

**Suggested images:** `08-job-pool-composition.png`, `09-experiment-arms.png`.

## Slide 6 — Why Introduce Baseline Mix?

- Baseline M and Baseline L allow only two partitions to work concurrently: S plus M, or S plus L.
- D-Flex can use all three partitions concurrently: S, M and L.
- This gives D-Flex a hardware-access advantage and makes the first comparison intentionally conservative but not fully resource-equivalent.
- **Baseline Mix** removes this confounding factor:
  - 6 Gold Jobs are statically assigned to M;
  - 6 Gold Jobs are statically assigned to L;
  - 2 Bronze Jobs remain assigned to S.
- Baseline Mix and D-Flex can therefore access the same S+M+L hardware. The remaining difference is static versus flexible Gold eligibility.

**Suggested image:** `10-fairness-baseline-mix.png`.

## Slide 7 — How the Job Pool Is Processed

- Baseline Mix fixes the Gold split at 6/6 before execution.
- If L finishes its assigned Jobs first, it becomes idle while Gold Jobs assigned to M remain queued.
- Those queued Jobs cannot borrow L because their claim accepts only M.
- D-Flex does not prescribe the final split. In the observed allocation, 5 Gold Jobs used M and 7 used L.
- Flexible eligibility shortens the final queue tail; it does not move a Job that has already started.

**Suggested image:** `11-pool-processing-baseline-mix-dflex.png`.

## Slide 8 — Results

Values reported by `results/arm-comparison.json`:

| Arm | Pool makespan |
| --- | ---: |
| Baseline M | 370 s |
| Baseline L | 275 s |
| Baseline Mix | 185 s |
| D-Flex | 157 s |

- D-Flex reduces makespan by **57.6%** versus Baseline M.
- D-Flex reduces makespan by **42.9%** versus Baseline L.
- In the resource-equivalent comparison, D-Flex reduces makespan by **15.1%** versus Baseline Mix.
- Baseline Mix is the strongest comparison because both arms can use S, M and L.
- The result demonstrates the benefit of the combined Kueue + DRA + MIG policy. It does not isolate DRA as the only causal component.
- These measurements are preliminary and should be repeated to quantify run-to-run variability.

**Suggested image:** `12-arm-comparison-results.png`.

