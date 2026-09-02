# Schemi per la presentazione Kueue / MIG / DRA

Creati il 27 agosto 2026 con lo strumento imagegen integrato (non CLI).
Formato: PNG, sfondo bianco. Immagini schematiche da inserire nelle slide.

## Ordine consigliato

1. 01-kueue-ammissione.png — ruolo di Kueue e separazione tra ammissione e allocazione.
2. 02-priorita-classi-servizio.png — classe di servizio come policy che combina priorità e vincolo GPU.
3. 03-claim-assegnazione-mig.png — compatibilità tra claim e partizioni.
4. 04-pool-baseline-mix-dflex.png — confronto della stessa pool sulle stesse risorse.

## Note scientifiche

- S, M e L sono partizioni MIG della stessa GPU A100, non tre GPU fisiche.
- La classe di servizio è una policy dell'esperimento, non una nuova API ServiceClass.
- Ogni Job riceve un solo device.
- claim-fast ammette M oppure L senza una preferenza per L.
- La divisione D-Flex 5/7 è quella osservata nella run, non una divisione prestabilita.
- La quarta immagine è una sequenza NON IN SCALA, non un Gantt dei singoli Pod.
- I makespan 185 s e 158 s provengono dalle run del 18/08/2026:
  results/20260818T101230Z-baseline-mix/summary.json
  results/20260818T101649Z-d-flex/summary.json
- Riduzione del makespan: (185 - 158) / 185 = 14,6%.

## Prompt finali

### 1. 01-kueue-ammissione.png

```text
Use case: infographic-diagram / productivity-visual.
Create ONE standalone slide-ready scientific schematic image, landscape 16:9, high-resolution. Pure WHITE background edge to edge. Extremely clean flat vector-like diagram, no photos, no gradients, no shadows, no textures, no decorative illustrations, no 3D, no watermark. Generous margins and whitespace. Large readable Italian text with correct accents, clean sans-serif font (Inter/Arial-like), dark charcoal #172B3A. Straight orthogonal connectors and thin consistent outlines. Consistent palette across the set: Gold service class warm amber #D6A12D with pale amber fill, Bronze muted copper #A66F49 with pale copper fill. Partitions S light gray with dark outline, M pale blue with blue outline #4274B8, L pale teal with teal outline #22816E. Make text and arrow direction scientifically exact. Use only specified copy, no invented labels, no logos. This is a thesis figure to INSERT in a slide, not a photo of a slide or screen.
Title at top: "Kueue: ammissione dei workload".
Large simple left-to-right flow of FOUR main groups across the center.
1. At left a stack of small job rectangles, amber Gold and copper Bronze. Labels "Job sospesi" and below "LocalQueue".
2. Next a large outlined box headed "Kueue", subheading "ClusterQueue". Inside only two short lines "Priorità" and "Quote device". Left arrow from LocalQueue labelled "In coda"; right arrow labelled "Job ammessi".
3. Next box "Scheduler + DRA", subtitle "Allocazione del device".
4. At right a SINGLE outer container labelled "GPU A100", subtitle "Partizioni MIG", containing THREE rectangles "S · 14 SM", "M · 28 SM", "L · 42 SM", using S gray, M blue and L teal.
A single thin feedback arrow below returns from the GPU group to the Kueue box. Its label is "Job completato → quota liberata".
Bottom short key sentence: "Kueue decide l’ammissione; scheduler e DRA assegnano la GPU."
Scientific invariants: Kueue must NOT appear to select the physical device. The MIG partitions are on ONE physical GPU, never draw three physical GPU boards. Pending jobs wait before admission. Completion releases quota. Minimize all decoration.
```

### 2. 02-priorita-classi-servizio.png

```text
Use case: infographic-diagram / productivity-visual.
Create ONE standalone slide-ready scientific schematic image, landscape 16:9, high-resolution. Pure WHITE background edge to edge. Extremely clean flat vector-like diagram, no photos, no gradients, no shadows, no textures, no decorative illustrations, no 3D, no watermark. Generous margins and whitespace. Large readable Italian text with correct accents, clean sans-serif font (Inter/Arial-like), dark charcoal #172B3A. Straight orthogonal connectors and thin consistent outlines. Consistent palette across the set: Gold service class warm amber #D6A12D with pale amber fill, Bronze muted copper #A66F49 with pale copper fill. Partitions S light gray with dark outline, M pale blue with blue outline #4274B8, L pale teal with teal outline #22816E. Make text and arrow direction scientifically exact. Use only specified copy, no invented labels, no logos. This is a thesis figure to INSERT in a slide, not a photo of a slide or screen.
Title: "Dalla priorità alla classe di servizio".
Top half: two schematic statements on two rows, with large simple boxes and plus sign.
First row "PRIORITÀ" arrow to "Ordine di ammissione".
Second row "CLASSE DI SERVIZIO" arrow to two joined boxes "Priorità" + "Vincolo GPU".
Below small heading "Policy D-Flex dell’esperimento".
Then TWO very clean horizontal service rows:
Gold row, amber class badge "Gold", then "Priorità 1000", then arrow to two small compatible partition chips "M · 28 SM" and "L · 42 SM". A brace under the two chips says "Almeno 28 SM".
Bronze row, copper class badge "Bronze", then "Priorità 100", then arrow to one gray chip "S · 14 SM".
Bottom explanatory text in readable size: "Classe di servizio = priorità + requisiti di risorsa".
Below that a single short qualification: "La priorità non garantisce un tempo di completamento."
Scientific constraints: Service class is an application policy used in this experiment, NOT a new built-in Kubernetes ServiceClass API. Gold uses WorkloadPriorityClass priority 1000, Bronze100. Gold can receive either M or L; do not depict a preference for L. No deadline, SLO predictor, classifier or broker. All jobs do identical matrix multiplication work.
```

### 3. 03-claim-assegnazione-mig.png

```text
Use case: infographic-diagram / productivity-visual.
Create ONE standalone slide-ready scientific schematic image, landscape 16:9, high-resolution. Pure WHITE background edge to edge. Extremely clean flat vector-like diagram, no photos, no gradients, no shadows, no textures, no decorative illustrations, no 3D, no watermark. Generous margins and whitespace. Large readable Italian text with correct accents, clean sans-serif font (Inter/Arial-like), dark charcoal #172B3A. Straight orthogonal connectors and thin consistent outlines. Consistent palette across the set: Gold service class warm amber #D6A12D with pale amber fill, Bronze muted copper #A66F49 with pale copper fill. Partitions S light gray with dark outline, M pale blue with blue outline #4274B8, L pale teal with teal outline #22816E. Make text and arrow direction scientifically exact. Use only specified copy, no invented labels, no logos. This is a thesis figure to INSERT in a slide, not a photo of a slide or screen.
Title: "Dai claim alle partizioni MIG".
A narrow simple flow at the top: "Job" → "ResourceClaimTemplate" → "DeviceClass" → "Device compatibile".
Below, one large impeccably aligned eligibility matrix with SIX columns:
"Claim" | "DeviceClass" | "Vincolo" | "S · 14 SM" | "M · 28 SM" | "L · 42 SM".
Four rows EXACTLY:
"claim-small" | "mig-small" | "SM = 14" | check mark | em dash | em dash
"claim-medium" | "mig-medium" | "SM = 28" | em dash | check mark | em dash
"claim-large" | "mig-large" | "SM = 42" | em dash | em dash | check mark
"claim-fast" | "mig-fast" | "SM ≥ 28" | em dash | check mark | check mark
Only those cells may contain checks; ensure no extra checks. Right column headers use gray S, blue M and teal L fills. Shade last row very lightly to show flexibility. Use large text and minimal thin horizontal rules, no heavy spreadsheet grid.
Under matrix show two short statements in separate compact lines:
"Baseline: claim-medium o claim-large → scelta statica"
"D-Flex: claim-fast → M oppure L disponibile"
Footer: "Stessa GPU A100, geometria MIG fissa."
Scientific constraints: The table shows eligibility, NOT simultaneous allocation of two devices to one Job. Every Job receives exactly ONE device. Display a small clear note "1 Job = 1 device" at bottom right. The fast row permits M OR L, not S, and neither one is preferred.
```

### 4. 04-pool-baseline-mix-dflex.png

```text
Use case: infographic-diagram / productivity-visual.
Create ONE standalone slide-ready scientific schematic image, landscape 16:9, high-resolution. Pure WHITE background edge to edge. Extremely clean flat vector-like diagram, no photos, no gradients, no shadows, no textures, no decorative illustrations, no 3D, no watermark. Generous margins and whitespace. Large readable Italian text with correct accents, clean sans-serif font (Inter/Arial-like), dark charcoal #172B3A. Straight orthogonal connectors and thin consistent outlines. Consistent palette across the set: Gold service class warm amber #D6A12D with pale amber fill, Bronze muted copper #A66F49 with pale copper fill. Partitions S light gray with dark outline, M pale blue with blue outline #4274B8, L pale teal with teal outline #22816E. Make text and arrow direction scientifically exact. Use only specified copy, no invented labels, no logos. This is a thesis figure to INSERT in a slide, not a photo of a slide or screen.
Title: "Stessa pool, assegnazione statica o flessibile".
Subtitle: "12 Gold + 2 Bronze · stesse risorse S + M + L".
Main content: two stacked simple horizontal timeline panels sharing the same 0–200 second horizontal scale. Use left lane labels S, M, L, and color GOLD job blocks amber in M and L lanes; BRONZE blocks copper in S lanes. Use blue M lane badge and teal L lane badge, gray S lane badge.
TOP panel heading: "baseline-mix · ripartizione statica 6 / 6".
Top S lane: exactly TWO Bronze blocks, total ends around 107 s.
Top M lane: exactly SIX Gold blocks, total ends at 185 s.
Top L lane: exactly SIX Gold blocks, total ends around 136 s, then a thin gray dashed empty segment to185, labelled "L inattiva".
Vertical dashed makespan marker at185 labelled "185 s".
BOTTOM panel heading: "D-Flex · ripartizione dinamica 5 / 7".
Bottom S lane: exactly TWO Bronze blocks, total ends around107 s.
Bottom M lane: exactly FIVE Gold blocks, total ends around151 s.
Bottom L lane: exactly SEVEN Gold blocks, total ends at158 s.
Vertical dashed makespan marker at158 labelled "158 s".
Mark a single common axis along bottom with ticks 0,50,100,150,200 and unit "tempo (s)". A little white space separates the job blocks. No job IDs are needed. The block counts MUST be exact: top S2/M6/L6, bottom S2/M5/L7. They are schematic aggregated execution sequences, not precise reproduction of each Pod interval.
Bottom concise result: "Makespan −14,6%: 185 s → 158 s".
Footnote in readable size: "Run del 18/08/2026 · sequenza schematica, makespan misurato".
Scientific invariants: static M cannot borrow the freed L, hence its long tail. Flexible Gold receive whichever compatible partition is available. Do NOT imply actual migration of already-running Jobs. D-Flex uses same three partitions as baseline-mix, not more hardware. Keep this extremely schematic.
```

### Rifinitura della quarta immagine

Applicata alla quarta immagine tramite imagegen integrato. Rimuove l'asse numerico per non suggerire una scala temporale esatta.

```text
Edit only the attached scientific schematic. Preserve all the content, layout, colors, white background, title and exact job counts. This must stay a minimal clean slide-ready diagram.
Correct the misleading numerical time axis at the bottom: REMOVE all numeric ticks 0, 50, 100, 150, 200 and all tick marks, and REMOVE the label "tempo (s)". Keep just the plain horizontal right-pointing arrow without ticks and label it "Avanzamento della run (schema non in scala)".
Change the bottom footnote to exactly: "Run del 18/08/2026 · sequenza non in scala · makespan misurato".
All other content must remain unchanged: title, 12 Gold + 2 Bronze, baseline-mix 6 / 6, D-Flex 5 / 7, S/M/L lanes, exactly 2/6/6 job rectangles in top lanes and exactly 2/5/7 in lower lanes, L inattiva, the two measured makespan markers 185 s and 158 s, and result "Makespan −14,6%: 185 s → 158 s".
Do not add new charts, text, or decoration. This figure illustrates processing sequence, not an exact scaled Gantt chart. White background.
```

