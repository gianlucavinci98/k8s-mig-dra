#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
MANIFEST_DIR="${BENCHMARK_DIR}/manifests"
RESULTS_DIR="${BENCHMARK_DIR}/results"
NAMESPACE="${NAMESPACE:-experiment}"
TIMEOUT="${TIMEOUT:-30m}"

mkdir -p "${RESULTS_DIR}"
kubectl apply -f "${MANIFEST_DIR}/benchmark-config.yaml"

run_profile() {
  local profile="$1"
  local job="gpu-calibration-${profile}"
  local manifest="${MANIFEST_DIR}/calibration-${profile}.yaml"
  local timestamp
  local run_dir

  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  run_dir="${RESULTS_DIR}/${timestamp}-${profile}"
  mkdir -p "${run_dir}"

  echo "Running ${job}; results will be stored in ${run_dir}"
  kubectl delete job "${job}" -n "${NAMESPACE}" --ignore-not-found --wait=true
  kubectl apply -f "${manifest}"

  if ! kubectl wait --for=condition=complete "job/${job}" -n "${NAMESPACE}" --timeout="${TIMEOUT}"; then
    kubectl describe "job/${job}" -n "${NAMESPACE}" > "${run_dir}/job-describe.txt" || true
    kubectl get pods -n "${NAMESPACE}" -l "job-name=${job}" -o yaml > "${run_dir}/pods.yaml" || true
    kubectl logs -n "${NAMESPACE}" "job/${job}" > "${run_dir}/benchmark.log" 2>&1 || true
    echo "${job} did not complete successfully; diagnostics saved in ${run_dir}" >&2
    return 1
  fi

  kubectl logs -n "${NAMESPACE}" "job/${job}" | tee "${run_dir}/benchmark.log"
  kubectl get "job/${job}" -n "${NAMESPACE}" -o yaml > "${run_dir}/job.yaml"
  kubectl get pods -n "${NAMESPACE}" -l "job-name=${job}" -o yaml > "${run_dir}/pods.yaml"
  kubectl get workloads.kueue.x-k8s.io -n "${NAMESPACE}" -o yaml > "${run_dir}/workloads.yaml"
  kubectl get resourceclaims.resource.k8s.io -n "${NAMESPACE}" -o yaml > "${run_dir}/resourceclaims.yaml"

  grep '^BENCHMARK_JSON ' "${run_dir}/benchmark.log" \
    | sed 's/^BENCHMARK_JSON //' > "${run_dir}/metrics.jsonl"
}

requested_profile="${1:-all}"
case "${requested_profile}" in
  small|medium|large)
    run_profile "${requested_profile}"
    ;;
  all)
    run_profile small
    run_profile medium
    run_profile large
    ;;
  *)
    echo "Usage: $0 [small|medium|large|all]" >&2
    exit 2
    ;;
esac

