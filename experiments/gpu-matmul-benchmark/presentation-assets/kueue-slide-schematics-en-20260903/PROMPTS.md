# Final image prompts

Generated with the built-in image generation tool.

## 01-from-ollama-to-batch-jobs.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only a few short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue/queue elements blue #4274B8. DRA elements violet #7656A7. Gold service class warm amber #D6A12D with pale amber fill. Bronze muted copper #A66F49 with pale copper fill. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. One physical A100 container may contain S, M and L partitions. Orthogonal arrows, consistent spacing. Scientifically accurate.
Primary request: show the conceptual transition after the Ollama experiment.
Composition: two balanced halves separated by a clear right arrow.
Left: one long horizontal service container labelled "Long-running service", attached to one MIG chip labelled "Fixed at startup"; underneath a small lock icon and the short label "Provision once".
Right: a circular lifecycle of five boxes labelled exactly "Submit", "Queue", "Admit", "Run", "Complete"; an arrow from Complete back to Submit. Beside Complete show a small released GPU chip with label "Release", and beside Admit show an interchangeable pair M and L with label "Choose again".
Key visual message only: a recurring Job releases its device and can receive a compatible device at the next execution. Do not imply in-place resizing or migration of a running Job.
```

## 02-kueue-admission-and-dra.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only a few short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue/queue elements blue #4274B8. DRA elements violet #7656A7. Gold service class warm amber #D6A12D with pale amber fill. Bronze muted copper #A66F49 with pale copper fill. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. One physical A100 container may contain S, M and L partitions. Orthogonal arrows, consistent spacing. Scientifically accurate.
Primary request: schematic of Kueue admission and DRA allocation, inspired by the previous Kueue admission image but with less text.
Composition: left-to-right flow.
At left: compact stack of amber Gold and copper Bronze job cards, label "Pending Jobs"; below, small label "LocalQueue".
Center-left: outlined blue box labelled "Kueue" containing only "Priority" and "Quotas".
Center-right: outlined violet box labelled "Scheduler + DRA".
At right: exactly ONE outer box labelled "A100" containing three partition tiles "S · 14 SM", "M · 28 SM", "L · 42 SM".
Arrows: Pending Jobs → Kueue labelled "Admission"; Kueue → Scheduler + DRA labelled "Admitted"; Scheduler + DRA → A100 labelled "Allocate"; A100 → Kueue return arrow labelled "Release".
Do not depict Kueue selecting the physical device; scheduler and DRA perform allocation.
```

## 03-priority-to-service-class.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only a few short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue/queue elements blue #4274B8. DRA elements violet #7656A7. Gold service class warm amber #D6A12D with pale amber fill. Bronze muted copper #A66F49 with pale copper fill. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. One physical A100 container may contain S, M and L partitions. Orthogonal arrows, consistent spacing. Scientifically accurate.
Primary request: minimal visual equation showing that priority alone controls admission order while the proposed service class adds a resource constraint.
Composition: two large horizontal rows.
Top row: blue badge "Priority" → box "Admission order".
Bottom row: badge "Service class" → two joined boxes "Priority" + "GPU constraint" → box "Admission + resource policy".
At far right show two small outputs: amber "Gold" and copper "Bronze".
Keep the plus sign visually prominent. No API logo. Do not suggest that ServiceClass is a native Kubernetes object; this is an experiment-level policy concept.
```

## 04-service-class-policies.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only a few short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue/queue elements blue #4274B8. DRA elements violet #7656A7. Gold service class warm amber #D6A12D with pale amber fill. Bronze muted copper #A66F49 with pale copper fill. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. One physical A100 container may contain S, M and L partitions. Orthogonal arrows, consistent spacing. Scientifically accurate.
Primary request: compare Bronze and Gold assignment policies.
Composition: two wide rows.
Bronze row: copper badge "Bronze · priority 100" → one gray partition chip "S · 14 SM" with small label "Always".
Gold row: amber badge "Gold · priority 1000" branching into three compact policy cards:
"Static M" → M · 28 SM;
"Static L" → L · 42 SM;
"Flexible" → two side-by-side compatible chips M · 28 SM and L · 42 SM joined by a large "OR", with short label "Available device".
Gold Flexible must select exactly one device per Job, M OR L, no preference shown. No Silver class.
```

## 05-deviceclass-capacity-filter.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only a few short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue/queue elements blue #4274B8. DRA elements violet #7656A7. Gold service class warm amber #D6A12D with pale amber fill. Bronze muted copper #A66F49 with pale copper fill. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. Orthogonal arrows, consistent spacing. Scientifically accurate.
Primary request: show visually that one capacity predicate is the core of flexible device eligibility.
Composition: three ResourceSlice device cards on the left: "S · 14 SM", "M · 28 SM", "L · 42 SM". They feed a central violet selector box labelled "mig-fast" containing the exact code line, rendered verbatim in monospace:
multiprocessors.compareTo(quantity("28")) >= 0
On the right, output exactly two accepted device cards: M · 28 SM with check mark, L · 42 SM with check mark. S must be rejected with a small gray X before the selector or filtered out.
Place a small short label above the selector: "DeviceClass selector".
The exact operator is greater-than-or-equal-to. No ellipsis, no extra code, no full YAML, no title.
```

## 06-deviceclass-exact-vs-flexible.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only a few short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue/queue elements blue #4274B8. DRA elements violet #7656A7. Gold service class warm amber #D6A12D with pale amber fill. Bronze muted copper #A66F49 with pale copper fill. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. Orthogonal arrows, consistent spacing. Scientifically accurate.
Primary request: compare an exact DeviceClass selector with a flexible DeviceClass selector.
Composition: two equal horizontal rows.
Top row label "mig-large"; code-like box with exact monospace text `SM == 42`; arrow to one teal device chip "L · 42 SM".
Bottom row label "mig-fast"; code-like box with exact monospace text `SM >= 28`; arrow branching to blue "M · 28 SM" and teal "L · 42 SM", separated by "OR".
Add a small lock icon near top row and a small open branching symbol near bottom row. No prose and no title. Exactly one device is allocated to each Job.
```

## 08-job-pool-composition.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only a few short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue/queue elements blue #4274B8. DRA elements violet #7656A7. Gold service class warm amber #D6A12D with pale amber fill. Bronze muted copper #A66F49 with pale copper fill. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. Orthogonal arrows, consistent spacing. Scientifically accurate.
Primary request: visualize the experimental Job pool.
Composition: at left, one clean matrix-multiplication icon labelled "Same GPU workload". In the center, a pool container with exactly TWELVE small amber job squares and exactly TWO copper job squares. Use two braces with labels "12 Gold" and "2 Bronze". At right, arrows to two priority badges: "Gold · 1000" and "Bronze · 100".
Below the pool, three small neutral tags: "Same image", "Same parameters", "Different service class".
Ensure the block count is exact and easy to verify. No title, no run date, no result.
```

## 07-claim-device-eligibility-v2.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue blue #4274B8. DRA violet #7656A7. Gold warm amber #D6A12D. Bronze copper #A66F49. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. Orthogonal arrows and consistent spacing. Scientifically accurate.
Primary request: four independent resource eligibility rows. No column headings, no extra concepts.
Row 1: "claim-small" → "mig-small" → "S · 14 SM".
Row 2: "claim-medium" → "mig-medium" → "M · 28 SM".
Row 3: "claim-large" → "mig-large" → "L · 42 SM".
Row 4, highlighted with pale violet background: "claim-fast" → "mig-fast" → a branching fork to "M · 28 SM" OR "L · 42 SM".
Render every label exactly. At bottom right put "1 Job = 1 device". Do not insert DRA, Gold, Bronze or other boxes inside the rows. Do not map a claim to a service class.
```

## 09-experiment-arms.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue blue #4274B8. DRA violet #7656A7. Gold warm amber #D6A12D. Bronze copper #A66F49. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. Orthogonal arrows and consistent spacing. Scientifically accurate.
Primary request: compare four experiment arms as four clean equal columns. Each column contains a tiny queue of Gold and Bronze cards at top and the set of partitions they are allowed to use below.
Column labels exactly: "Baseline M", "Baseline L", "Baseline Mix", "D-Flex".
Baseline M: Bronze arrow to S; Gold arrow only to M; show L gray and unused.
Baseline L: Bronze arrow to S; Gold arrow only to L; show M gray and unused.
Baseline Mix: Bronze arrow to S; split Gold label "6 + 6" with arrows to M and L.
D-Flex: Bronze arrow to S; Gold arrow to a fork "M OR L", labelled "dynamic".
Use the same S/M/L chips in every column. No performance numbers and no title.
```

## 10-fairness-baseline-mix.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue blue #4274B8. DRA violet #7656A7. Gold warm amber #D6A12D. Bronze copper #A66F49. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. Orthogonal arrows and consistent spacing. Scientifically accurate.
Primary request: show why a fairer baseline was introduced.
Composition: top comparison marked with a small warning triangle. Left card "Static baseline" contains only two colored active devices, S plus either M or L, and one gray unused device; label "2 active partitions". Right card "D-Flex" contains S, M and L active; label "3 active partitions". Between them a not-equal sign.
Below a strong downward arrow labelled "Fairness correction".
Bottom comparison: left card "Baseline Mix" and right card "D-Flex"; both contain the same three active devices S, M and L. Between them an equals sign with short label "Same hardware access".
No makespan numbers, no title, no detailed captions.
```

## 11-pool-processing-baseline-mix-dflex.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue blue #4274B8. DRA violet #7656A7. Gold warm amber #D6A12D. Bronze copper #A66F49. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. Orthogonal arrows and consistent spacing. Scientifically accurate.
Primary request: recreate the useful pool-processing schematic without a title and without any run metadata. Two stacked panels, sequences explicitly schematic and not to scale.
Top panel label "Baseline Mix · static 6 / 6". Three lanes labelled S, M, L. S has exactly two copper Bronze blocks. M has exactly six amber Gold blocks and determines the rightmost endpoint labelled "185 s". L has exactly six amber Gold blocks and ends earlier, followed by a gray dashed empty tail labelled "L idle".
Bottom panel label "D-Flex · dynamic 5 / 7". S has exactly two copper Bronze blocks. M has exactly five amber Gold blocks. L has exactly seven amber Gold blocks and endpoint labelled "157 s".
At bottom show only a plain right-pointing arrow labelled "Progress · schematic, not to scale". Add no numbered time axis. Exact block counts are mandatory: top2/6/6, bottom2/5/7. Do not imply migration of running Jobs.
```

## 12-arm-comparison-results.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue blue #4274B8. DRA violet #7656A7. Gold warm amber #D6A12D. Bronze copper #A66F49. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. Orthogonal arrows and consistent spacing. Scientifically accurate.
Primary request: clean horizontal bar chart of pool makespan comparison, with no chart title.
Four horizontal bars, ordered longest to shortest:
"Baseline M" 370 s
"Baseline L" 275 s
"Baseline Mix" 185 s
"D-Flex" 157 s
Static baselines use muted blue-gray bars; D-Flex uses violet. Put the exact value at the end of each bar. Axis label only "Pool makespan (s)" and simple ticks at 0,100,200,300,400.
At right, three compact callouts connected from D-Flex: "−57.6% vs M", "−42.9% vs L", "−15.1% vs Mix". Do not use or show p50, p95, median, percentile, date, run or replica. Do not invent error bars.
```

## 13-static-profile-vs-dra-selector.png

```text
Use case: infographic-diagram.
Asset type: standalone schematic element to insert into a university thesis presentation.
Create ONE clean high-resolution landscape diagram on a pure white background. Flat vector-like visual language, crisp thin outlines, generous whitespace, no slide title, no paragraph caption, no footnote, no date, no run identifier, no logos, no watermark, no photos, no gradients, no shadows, no textures, no decorative elements. Use only short English labels in a large clean sans-serif font. Dark navy text #172B3A. Kueue blue #4274B8. DRA violet #7656A7. Gold warm amber #D6A12D. Bronze copper #A66F49. MIG S light gray, M pale blue with blue outline, L pale teal with teal outline #22816E. Orthogonal arrows and consistent spacing. Scientifically accurate.
Primary request: conceptual comparison between fixed profile requests and DRA capacity-based selection.
Two equal horizontal rows.
Top row label "Fixed profile request"; Gold Job → one exact resource card "M · 28 SM"; a small closed lock icon. Under it, compact label "One predefined profile".
Bottom row label "DRA DeviceClass"; Gold Job → violet predicate box "SM >= 28" → branch to "M · 28 SM" OR "L · 42 SM"; a small branching icon. Under it, compact label "Compatible set".
Do not claim that DRA changes a running Job. Exactly one device is assigned per Job. No title.
```

