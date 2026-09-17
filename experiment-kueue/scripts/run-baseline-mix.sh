#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
MANIFEST_DIR="${BENCHMARK_DIR}/manifests"
RESULTS_DIR="${BENCHMARK_DIR}/results"
NAMESPACE="${NAMESPACE:-experiment}"
TIMEOUT="${TIMEOUT:-20m}"
EXPECTED_NODE="${EXPECTED_NODE:-ai-lab-a100-2}"
GOLD_MEDIUM_JOBS="${GOLD_MEDIUM_JOBS:-6}"
GOLD_LARGE_JOBS="${GOLD_LARGE_JOBS:-6}"
BRONZE_JOBS="${BRONZE_JOBS:-2}"
EXPERIMENT="baseline-mix"
LOCAL_QUEUE="baseline-mix-uq"
CLUSTER_QUEUE="baseline-mix-cq"
SELECTOR="benchmark.thesis/experiment=${EXPERIMENT}"
TEMPLATE="${MANIFEST_DIR}/pool-job-template.yaml"

KUBECTL=(kubectl)
if [[ -n "${KUBE_CONTEXT:-}" ]]; then
  KUBECTL+=(--context "${KUBE_CONTEXT}")
fi

die() {
  echo "ERROR: $*" >&2
  exit 1
}

is_positive_integer() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

is_positive_integer "${GOLD_MEDIUM_JOBS}" \
  || die "GOLD_MEDIUM_JOBS must be a positive integer"
is_positive_integer "${GOLD_LARGE_JOBS}" \
  || die "GOLD_LARGE_JOBS must be a positive integer"
is_positive_integer "${BRONZE_JOBS}" \
  || die "BRONZE_JOBS must be a positive integer"
command -v kubectl >/dev/null || die "kubectl is not available"
command -v python3 >/dev/null || die "python3 is not available"

context="$("${KUBECTL[@]}" config current-context)"
echo "Kubernetes context: ${context}"
echo "Kubeconfig: ${KUBECONFIG:-<kubectl default>}"
echo "Expected node: ${EXPECTED_NODE}"
"${KUBECTL[@]}" get node "${EXPECTED_NODE}" >/dev/null \
  || die "the selected cluster does not contain node ${EXPECTED_NODE}"
"${KUBECTL[@]}" get localqueue "${LOCAL_QUEUE}" -n "${NAMESPACE}" >/dev/null \
  || die "LocalQueue ${LOCAL_QUEUE} is not available in namespace ${NAMESPACE}; apply manifests/baseline-mix-queues.yaml first"
"${KUBECTL[@]}" get clusterqueue "${CLUSTER_QUEUE}" >/dev/null \
  || die "ClusterQueue ${CLUSTER_QUEUE} is not available; apply manifests/baseline-mix-queues.yaml first"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_dir="${RESULTS_DIR}/${timestamp}-${EXPERIMENT}"
rendered_manifest="${run_dir}/pool.yaml"
mkdir -p "${run_dir}/logs"

render_job() {
  local job_name="$1"
  local service_class="$2"
  local profile_label="$3"
  local priority_class="$4"
  local claim_template="$5"
  local expected_profile="$6"
  local expected_sms="$7"

  sed \
    -e "s/@@JOB_NAME@@/${job_name}/g" \
    -e "s/@@EXPERIMENT@@/${EXPERIMENT}/g" \
    -e "s/@@LOCAL_QUEUE@@/${LOCAL_QUEUE}/g" \
    -e "s/@@SERVICE_CLASS@@/${service_class}/g" \
    -e "s/@@PROFILE_LABEL@@/${profile_label}/g" \
    -e "s/@@PRIORITY_CLASS@@/${priority_class}/g" \
    -e "s/@@CLAIM_TEMPLATE@@/${claim_template}/g" \
    -e "s/@@EXPECTED_PROFILE@@/${expected_profile}/g" \
    -e "s/@@EXPECTED_SMS@@/${expected_sms}/g" \
    "${TEMPLATE}"
  echo "---"
}

{
  for ((index = 1; index <= GOLD_MEDIUM_JOBS; index++)); do
    printf -v suffix "%02d" "${index}"
    render_job \
      "baseline-mix-gold-medium-${suffix}" gold medium \
      gold-priority claim-medium medium-2g 28
  done
  for ((index = 1; index <= GOLD_LARGE_JOBS; index++)); do
    printf -v suffix "%02d" "${index}"
    render_job \
      "baseline-mix-gold-large-${suffix}" gold large \
      gold-priority claim-large large-3g 42
  done
  for ((index = 1; index <= BRONZE_JOBS; index++)); do
    printf -v suffix "%02d" "${index}"
    render_job \
      "baseline-mix-bronze-${suffix}" bronze small \
      bronze-priority claim-small small-1g 14
  done
} > "${rendered_manifest}"

gold_jobs="$((GOLD_MEDIUM_JOBS + GOLD_LARGE_JOBS))"
expected_jobs="$((gold_jobs + BRONZE_JOBS))"

echo "Experiment arm: ${EXPERIMENT}"
echo "Pool: ${GOLD_MEDIUM_JOBS} Gold statically on M, ${GOLD_LARGE_JOBS} Gold statically on L, ${BRONZE_JOBS} Bronze on S"
echo "Queue: ${LOCAL_QUEUE} -> ${CLUSTER_QUEUE}"
echo "Results: ${run_dir}"
echo "Removing jobs left by a previous ${EXPERIMENT} run..."
"${KUBECTL[@]}" delete jobs -n "${NAMESPACE}" -l "${SELECTOR}" \
  --ignore-not-found --wait=true

"${KUBECTL[@]}" apply -f "${MANIFEST_DIR}/benchmark-config.yaml"
date -u +%Y-%m-%dT%H:%M:%S.%NZ > "${run_dir}/client-submit-start.txt"
"${KUBECTL[@]}" apply -f "${rendered_manifest}"
date -u +%Y-%m-%dT%H:%M:%S.%NZ > "${run_dir}/client-submit-end.txt"

actual_jobs="$("${KUBECTL[@]}" get jobs -n "${NAMESPACE}" -l "${SELECTOR}" \
  -o name | wc -l | tr -d ' ')"
[[ "${actual_jobs}" == "${expected_jobs}" ]] \
  || die "expected ${expected_jobs} jobs after apply, found ${actual_jobs}"

echo "Submitted ${actual_jobs} jobs. Waiting up to ${TIMEOUT} for the complete pool..."
wait_status=0
if ! "${KUBECTL[@]}" wait --for=condition=complete jobs \
  -n "${NAMESPACE}" -l "${SELECTOR}" --timeout="${TIMEOUT}"; then
  wait_status=1
  echo "The pool did not complete successfully; collecting diagnostics." >&2
fi
date -u +%Y-%m-%dT%H:%M:%S.%NZ > "${run_dir}/client-wait-end.txt"

"${KUBECTL[@]}" get jobs -n "${NAMESPACE}" -l "${SELECTOR}" -o json \
  > "${run_dir}/jobs.json"
"${KUBECTL[@]}" get pods -n "${NAMESPACE}" -l "${SELECTOR}" -o json \
  > "${run_dir}/pods.json"
"${KUBECTL[@]}" get workloads.kueue.x-k8s.io -n "${NAMESPACE}" -o json \
  > "${run_dir}/workloads.json"
"${KUBECTL[@]}" get resourceclaims.resource.k8s.io -n "${NAMESPACE}" -o json \
  > "${run_dir}/resourceclaims.json"
"${KUBECTL[@]}" get clusterqueue "${CLUSTER_QUEUE}" -o yaml \
  > "${run_dir}/clusterqueue.yaml"
"${KUBECTL[@]}" get localqueue "${LOCAL_QUEUE}" -n "${NAMESPACE}" -o yaml \
  > "${run_dir}/localqueue.yaml"

while IFS= read -r job_name; do
  "${KUBECTL[@]}" logs -n "${NAMESPACE}" "job/${job_name}" \
    > "${run_dir}/logs/${job_name}.log" 2>&1 || true
done < <("${KUBECTL[@]}" get jobs -n "${NAMESPACE}" -l "${SELECTOR}" \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')

analysis_status=0
if ! python3 "${SCRIPT_DIR}/analyze-pool.py" "${run_dir}" \
  --experiment "${EXPERIMENT}" | tee "${run_dir}/summary.txt"; then
  analysis_status=1
fi

echo
echo "Machine-readable summary: ${run_dir}/summary.json"
echo "Per-job table:           ${run_dir}/jobs.csv"
echo "Raw logs:                ${run_dir}/logs/"

if ((wait_status != 0 || analysis_status != 0)); then
  exit 1
fi
