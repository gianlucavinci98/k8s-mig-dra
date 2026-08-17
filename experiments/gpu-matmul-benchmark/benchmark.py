#!/usr/bin/env python3
"""Deterministic CUDA matrix-multiplication benchmark for MIG/DRA experiments."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

import torch


SCHEMA_VERSION = "1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def emit(event: str, **fields: Any) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "event": event,
        "timestamp_utc": utc_now(),
        **fields,
    }
    print(f"BENCHMARK_JSON {json.dumps(payload, sort_keys=True, default=str)}", flush=True)


def info(message: str) -> None:
    print(f"[{utc_now()}] INFO {message}", flush=True)


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def env_bool(name: str, default: bool) -> bool:
    return parse_bool(os.getenv(name, str(default)))


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("cannot compute a percentile of an empty list")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a fixed amount of CUDA matrix multiplication work, or an optional "
            "duration-based stress test, and emit machine-readable JSON metrics."
        )
    )
    parser.add_argument("--matrix-size", type=int, default=env_int("MATRIX_SIZE", 8192))
    parser.add_argument("--iterations", type=int, default=env_int("ITERATIONS", 100))
    parser.add_argument(
        "--warmup-iterations",
        type=int,
        default=env_int("WARMUP_ITERATIONS", 5),
    )
    parser.add_argument("--trials", type=int, default=env_int("TRIALS", 1))
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=env_float("DURATION_SECONDS", 0.0),
        help="If greater than zero, overrides --iterations and runs each trial for at least this duration.",
    )
    parser.add_argument(
        "--duration-check-interval",
        type=int,
        default=env_int("DURATION_CHECK_INTERVAL", 5),
        help="Synchronize and check elapsed time every N iterations in duration mode.",
    )
    parser.add_argument(
        "--dtype",
        choices=("float32", "float16", "bfloat16"),
        default=os.getenv("DTYPE", "float32"),
    )
    parser.add_argument("--seed", type=int, default=env_int("SEED", 42))
    parser.add_argument(
        "--allow-tf32",
        type=parse_bool,
        default=env_bool("ALLOW_TF32", False),
    )
    parser.add_argument(
        "--expected-multiprocessors",
        type=int,
        default=env_int("EXPECTED_MULTIPROCESSORS", 0),
        help="Expected visible SM count; zero disables the check.",
    )
    parser.add_argument(
        "--strict-device-check",
        type=parse_bool,
        default=env_bool("STRICT_DEVICE_CHECK", True),
        help="Fail when the visible SM count differs from --expected-multiprocessors.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    positive = {
        "matrix-size": args.matrix_size,
        "iterations": args.iterations,
        "trials": args.trials,
        "duration-check-interval": args.duration_check_interval,
    }
    for name, value in positive.items():
        if value <= 0:
            raise ValueError(f"--{name} must be greater than zero")
    if args.warmup_iterations < 0:
        raise ValueError("--warmup-iterations must be zero or greater")
    if args.duration_seconds < 0:
        raise ValueError("--duration-seconds must be zero or greater")


def run_command(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return {
            "command": command,
            "return_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:  # Diagnostic command failure must not abort the benchmark.
        return {"command": command, "error": repr(exc)}


def collect_nvidia_smi() -> dict[str, Any]:
    if shutil.which("nvidia-smi") is None:
        return {"available": False, "reason": "nvidia-smi not found"}
    return {
        "available": True,
        "list": run_command(["nvidia-smi", "-L"]),
        "query": run_command(
            [
                "nvidia-smi",
                "--query-gpu=name,uuid,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ]
        ),
    }


def environment_metadata() -> dict[str, Any]:
    names = (
        "POD_NAME",
        "POD_NAMESPACE",
        "NODE_NAME",
        "JOB_NAME",
        "EXPERIMENT_ARM",
        "EXPECTED_PROFILE",
        "CLAIM_TEMPLATE",
        "NVIDIA_VISIBLE_DEVICES",
        "CUDA_VISIBLE_DEVICES",
    )
    return {name.lower(): os.getenv(name, "") for name in names}


def dtype_from_name(name: str) -> torch.dtype:
    return {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
    }[name]


def run_trial(
    *,
    a: torch.Tensor,
    b: torch.Tensor,
    output: torch.Tensor,
    trial_number: int,
    iterations: int,
    duration_seconds: float,
    duration_check_interval: int,
) -> dict[str, Any]:
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()

    cuda_start = torch.cuda.Event(enable_timing=True)
    cuda_end = torch.cuda.Event(enable_timing=True)
    wall_start = time.perf_counter()
    cuda_start.record()

    completed_iterations = 0
    if duration_seconds > 0:
        while True:
            torch.mm(a, b, out=output)
            completed_iterations += 1
            if completed_iterations % duration_check_interval == 0:
                torch.cuda.synchronize()
                if time.perf_counter() - wall_start >= duration_seconds:
                    break
    else:
        for _ in range(iterations):
            torch.mm(a, b, out=output)
        completed_iterations = iterations

    cuda_end.record()
    cuda_end.synchronize()
    wall_end = time.perf_counter()

    elapsed_wall_seconds = wall_end - wall_start
    elapsed_cuda_seconds = cuda_start.elapsed_time(cuda_end) / 1000.0
    matrix_size = a.shape[0]
    operations = 2 * (matrix_size**3) * completed_iterations
    checksum = float(output[0, 0].float().item())

    result = {
        "trial": trial_number,
        "completed_iterations": completed_iterations,
        "elapsed_wall_seconds": elapsed_wall_seconds,
        "elapsed_cuda_seconds": elapsed_cuda_seconds,
        "average_iteration_ms": (elapsed_cuda_seconds * 1000.0) / completed_iterations,
        "iterations_per_second": completed_iterations / elapsed_cuda_seconds,
        "estimated_tflops": operations / elapsed_cuda_seconds / 1e12,
        "estimated_operations": operations,
        "checksum": checksum,
        "peak_memory_allocated_bytes": torch.cuda.max_memory_allocated(),
        "peak_memory_reserved_bytes": torch.cuda.max_memory_reserved(),
    }
    emit("trial_complete", **result)
    info(
        f"Trial {trial_number}: {completed_iterations} iterations in "
        f"{elapsed_wall_seconds:.3f}s wall / {elapsed_cuda_seconds:.3f}s CUDA, "
        f"{result['iterations_per_second']:.3f} iter/s, "
        f"{result['estimated_tflops']:.3f} estimated TFLOP/s"
    )
    return result


def main() -> int:
    args = parse_args()
    validate_args(args)

    env = environment_metadata()
    mode = "duration" if args.duration_seconds > 0 else "fixed_iterations"
    emit(
        "benchmark_start",
        mode=mode,
        arguments=vars(args),
        environment=env,
        python_version=sys.version,
        platform=platform.platform(),
        torch_version=torch.__version__,
        torch_cuda_version=torch.version.cuda,
        cudnn_version=torch.backends.cudnn.version(),
    )

    if not torch.cuda.is_available():
        emit("benchmark_error", error="CUDA is not available inside the container")
        return 2

    device = torch.device("cuda:0")
    torch.cuda.set_device(device)
    torch.backends.cuda.matmul.allow_tf32 = args.allow_tf32
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)

    properties = torch.cuda.get_device_properties(device)
    gpu = {
        "device_index": 0,
        "name": properties.name,
        "total_memory_bytes": properties.total_memory,
        "total_memory_gib": properties.total_memory / (1024**3),
        "multiprocessor_count": properties.multi_processor_count,
        "compute_capability_major": properties.major,
        "compute_capability_minor": properties.minor,
        "uuid": str(getattr(properties, "uuid", "")),
    }
    print(
        "GPU_ACQUIRED "
        f"name={gpu['name']!r} sm={gpu['multiprocessor_count']} "
        f"memory_gib={gpu['total_memory_gib']:.2f} "
        f"expected_profile={env['expected_profile']!r} "
        f"claim={env['claim_template']!r}",
        flush=True,
    )
    emit("gpu_acquired", gpu=gpu, nvidia_smi=collect_nvidia_smi())

    expected = args.expected_multiprocessors
    matches_expected = expected == 0 or properties.multi_processor_count == expected
    emit(
        "device_validation",
        expected_multiprocessors=expected,
        actual_multiprocessors=properties.multi_processor_count,
        matches=matches_expected,
    )
    if not matches_expected:
        message = (
            f"expected {expected} multiprocessors, but CUDA reports "
            f"{properties.multi_processor_count}"
        )
        if args.strict_device_check:
            emit("benchmark_error", error=message)
            return 3
        info(f"WARNING: {message}")

    dtype = dtype_from_name(args.dtype)
    element_size = torch.empty((), dtype=dtype).element_size()
    estimated_tensor_memory = 3 * (args.matrix_size**2) * element_size
    emit(
        "allocation_plan",
        matrix_size=args.matrix_size,
        dtype=args.dtype,
        tensor_count=3,
        estimated_tensor_memory_bytes=estimated_tensor_memory,
        estimated_tensor_memory_gib=estimated_tensor_memory / (1024**3),
        visible_gpu_memory_bytes=properties.total_memory,
    )
    if estimated_tensor_memory > properties.total_memory * 0.80:
        info(
            "WARNING: input/output tensors alone are estimated to use more than "
            "80% of visible GPU memory; reduce MATRIX_SIZE if allocation fails"
        )

    info(
        f"Allocating three {args.matrix_size}x{args.matrix_size} {args.dtype} matrices "
        f"(~{estimated_tensor_memory / (1024**3):.2f} GiB before library workspace)"
    )
    with torch.inference_mode():
        a = torch.randn((args.matrix_size, args.matrix_size), device=device, dtype=dtype)
        b = torch.randn((args.matrix_size, args.matrix_size), device=device, dtype=dtype)
        output = torch.empty_like(a)

        if args.warmup_iterations:
            info(f"Starting {args.warmup_iterations} warm-up iterations")
            warmup_start = time.perf_counter()
            for _ in range(args.warmup_iterations):
                torch.mm(a, b, out=output)
            torch.cuda.synchronize()
            warmup_seconds = time.perf_counter() - warmup_start
            emit(
                "warmup_complete",
                iterations=args.warmup_iterations,
                elapsed_wall_seconds=warmup_seconds,
            )

        results = []
        for trial_number in range(1, args.trials + 1):
            results.append(
                run_trial(
                    a=a,
                    b=b,
                    output=output,
                    trial_number=trial_number,
                    iterations=args.iterations,
                    duration_seconds=args.duration_seconds,
                    duration_check_interval=args.duration_check_interval,
                )
            )

    wall_times = [result["elapsed_wall_seconds"] for result in results]
    cuda_times = [result["elapsed_cuda_seconds"] for result in results]
    throughputs = [result["iterations_per_second"] for result in results]
    summary = {
        "status": "success",
        "mode": mode,
        "profile": env["expected_profile"],
        "claim_template": env["claim_template"],
        "experiment_arm": env["experiment_arm"],
        "gpu": gpu,
        "matrix_size": args.matrix_size,
        "dtype": args.dtype,
        "allow_tf32": args.allow_tf32,
        "trials": args.trials,
        "iterations_per_trial": args.iterations if mode == "fixed_iterations" else None,
        "duration_seconds_per_trial": args.duration_seconds if mode == "duration" else None,
        "wall_seconds_total": sum(wall_times),
        "wall_seconds_p50": statistics.median(wall_times),
        "wall_seconds_p95": percentile(wall_times, 0.95),
        "cuda_seconds_p50": statistics.median(cuda_times),
        "cuda_seconds_p95": percentile(cuda_times, 0.95),
        "iterations_per_second_p50": statistics.median(throughputs),
        "iterations_per_second_p95": percentile(throughputs, 0.95),
        "trial_results": results,
    }
    emit("benchmark_summary", **summary)
    print(
        "BENCHMARK_COMPLETE "
        f"profile={summary['profile']!r} "
        f"wall_p50_seconds={summary['wall_seconds_p50']:.3f} "
        f"wall_p95_seconds={summary['wall_seconds_p95']:.3f} "
        f"iterations_per_second_p50={summary['iterations_per_second_p50']:.3f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit("benchmark_error", error=repr(exc), error_type=type(exc).__name__)
        raise

