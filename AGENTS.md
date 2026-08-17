# Contesto condiviso — Tesi: Design and Implementation of a Cloud-AI-Native Cost-Energy Efficient Platform for Optimized GPU Resource Management (Titolo tesi è provvisorio)

## Obiettivo della tesi

Valutare come **NVIDIA Multi-Instance GPU (MIG)** e **Kubernetes Dynamic Resource Allocation (DRA)** possano ottimizzare l'inferenza AI su Kubernetes, con particolare attenzione a:

- throughput e latenza dell'inferenza;
- utilizzo effettivo della GPU;
- efficienza energetica e consumo di risorse;
- flessibilità dell'allocazione delle risorse acceleratrici;
- complessità operativa e limiti dell'approccio.

L'obiettivo non è dimostrare che MIG o DRA siano sempre preferibili: occorre individuare le condizioni in cui ciascuna tecnologia produce un beneficio misurabile e ripetibile rispetto a una baseline appropriata.

## Concetti chiave

### NVIDIA MIG

MIG suddivide una GPU fisica compatibile in istanze isolate, ciascuna con una porzione di risorse di calcolo e memoria. È particolarmente adatto a carichi di inferenza che non richiedono l'intera GPU e che possono quindi essere consolidati senza una penalizzazione rilevante.

Ipotesi di lavoro:

- MIG è vantaggioso quando il workload non è troppo esoso di risorse GPU;
- il carico deve mantenere prestazioni accettabili all'interno di una partizione più piccola;
- il consolidamento di più workload può migliorare l'utilizzo globale della GPU e il throughput complessivo.

### Kubernetes DRA

DRA permette di richiedere e allocare risorse tramite oggetti Kubernetes e driver dedicati, separando la richiesta di capacità dalla tradizionale allocazione statica di device plugin.

Ipotesi di lavoro:

- DRA mostra il suo valore soprattutto quando il fabbisogno di GPU non può essere fissato a priori;
- una semplice assegnazione della GPU/partizione al bootstrap del Pod non costituisce, da sola, un vantaggio prestazionale di DRA;
- lo scenario sperimentale deve permettere una decisione o un riassetto dell'allocazione tra esecuzioni successive, in funzione delle caratteristiche del job, della coda o dello stato del cluster.

## Risultati e osservazioni già ottenuti

È stato sperimentato il deployment di più istanze di **Ollama**, ciascuna associata a una partizione MIG diversa.

Osservazioni:

- l'utilizzo della GPU è aumentato;
- il throughput complessivo, misurato in token al secondo (tok/s), è migliorato;
- DRA è stato usato per assegnare una partizione MIG al momento dell'avvio del Pod;
- una volta avviato, il Pod Ollama resta attivo e non effettua ulteriori richieste di GPU.

Conclusione provvisoria: in questo assetto DRA agisce come meccanismo di provisioning iniziale. Il miglioramento osservato è attribuibile principalmente al partizionamento MIG e al consolidamento dei workload, non a una capacità dinamica di DRA sfruttata durante il ciclo di vita del carico.

## Problema di ricerca aperto

Definire uno scenario in cui DRA produca un vantaggio dimostrabile rispetto a un'allocazione GPU statica.

Il caso d'uso deve soddisfare questi requisiti:

1. il fabbisogno di accelerazione varia tra job o tra esecuzioni successive;
2. l'allocazione non deve poter essere decisa una volta per tutte al bootstrap di un servizio long-running;
3. l'uso di DRA deve influire concretamente su almeno una metrica: throughput, tempo di completamento, latenza di attesa, utilizzo GPU, energia/consumi o densità di consolidamento;
4. deve essere disponibile una baseline credibile e confrontabile.

## Direzione sperimentale: Kueue e workload batch

Kueue è una direzione promettente perché orchestra workload in coda, tipicamente Job che terminano e vengono nuovamente sottomessi. Questa natura ciclica rende possibile richiedere risorse GPU diverse a ogni esecuzione e confrontare politiche di allocazione.

Idea centrale:

- classificare o caratterizzare i job di inferenza prima della sottomissione (ad esempio per modello, lunghezza del prompt, batch size, contesto o SLO);
- richiedere dinamicamente la risorsa GPU/MIG più adatta tramite DRA;
- lasciare che Kueue ammetta i job in base alla disponibilità e alle quote;
- rilasciare la risorsa alla terminazione del Job, così da poterla riassegnare a un job con esigenze differenti.

L'adattamento può avvenire **tra job** o **tra tentativi/esecuzioni**. Non assumere, senza verificarlo, che DRA possa ridimensionare in-place una GPU già assegnata a un container in esecuzione: il disegno sperimentale deve rispettare la semantica effettivamente supportata dalla versione di Kubernetes, dal driver DRA NVIDIA e dal runtime usati.

## Stato attuale

La parte MIG ha già una prima evidenza: più istanze Ollama su partizioni MIG hanno migliorato utilizzo GPU e throughput aggregato per un carico compatibile con il partizionamento.

La prossima priorità è progettare e validare un workflow batch con Kueue in cui job con profili eterogenei ricevano, a ogni esecuzione, una richiesta DRA proporzionata al loro fabbisogno. Il risultato atteso da verificare è un vantaggio misurabile rispetto a un'assegnazione GPU/MIG statica.
