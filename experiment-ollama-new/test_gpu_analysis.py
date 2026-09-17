#!/usr/bin/env python3

import copy
import unittest

import collect_gpu_metrics
import evaluate


TIMESTAMPS = (-5, 0, 5, 10)


def metric_series(metric_name: str, gpu_i_id: str, values: list[float]) -> dict:
    return {
        "metric": {
            "__name__": metric_name,
            "UUID": "GPU-test",
            "gpu": "0",
            "GPU_I_ID": gpu_i_id,
            "GPU_I_PROFILE": "1g.5gb",
            "modelName": "NVIDIA A100-SXM4-40GB",
        },
        "values": [
            [timestamp, str(value)] for timestamp, value in zip(TIMESTAMPS, values)
        ],
    }


class GpuAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        metrics = {}
        metric_values = {
            "DCGM_FI_PROF_GR_ENGINE_ACTIVE": [0.0, 0.0, 0.5, 0.0],
            "DCGM_FI_PROF_DRAM_ACTIVE": [0.0, 0.0, 0.25, 0.0],
            "DCGM_FI_DEV_FB_USED": [1000, 1000, 1000, 1000],
            "DCGM_FI_DEV_FB_FREE": [4000, 4000, 4000, 4000],
            "DCGM_FI_DEV_POWER_USAGE": [100, 100, 160, 100],
        }
        for metric_name, values in metric_values.items():
            second_values = (
                [102, 102, 162, 102]
                if metric_name == "DCGM_FI_DEV_POWER_USAGE"
                else values
            )
            metrics[metric_name] = {
                "series": [
                    metric_series(metric_name, "1", values),
                    metric_series(metric_name, "2", second_values),
                ]
            }

        self.document = {
            "schema_version": 2,
            "query_window": {
                "start_unix_s": -5,
                "end_unix_s": 10,
                "padding_before_seconds": 5,
                "padding_after_seconds": 8,
                "step_seconds": 5,
            },
            "activity_capture": {
                "status": "settled",
                "threshold_pct_per_partition": 0.1,
            },
            "metrics": metrics,
        }
        self.records = [{"start_time": 0, "end_time": 2000, "eval_count": 100}]

    def test_partition_weighting_and_power_deduplication(self) -> None:
        rows = evaluate.build_gpu_rows(self.document, self.records)
        system_active = next(
            row for row in rows["system"] if row["timestamp_unix_s"] == 5
        )
        self.assertAlmostEqual(system_active["sm_configured_pct"], 50.0)
        self.assertAlmostEqual(system_active["sm_physical_pct"], 100.0 / 7.0)
        self.assertAlmostEqual(system_active["dram_configured_pct"], 25.0)
        self.assertAlmostEqual(system_active["dram_physical_pct"], 6.25)
        self.assertAlmostEqual(system_active["fb_used_mib"], 2000.0)
        self.assertAlmostEqual(system_active["power_w"], 161.0)

    def test_delayed_pulse_area_is_normalized_by_workload_duration(self) -> None:
        rows = evaluate.build_gpu_rows(self.document, self.records)
        summary = evaluate.summarize_gpu_metrics(
            self.document, rows, self.records, total_tokens=100
        )

        self.assertEqual(summary["telemetry_episode"]["quality"], "coarse_but_comparable")
        self.assertEqual(summary["telemetry_episode"]["active_sample_count"], 1)
        self.assertAlmostEqual(
            summary["sm_activity"]["capacity_equivalent_active_seconds"],
            5.0 / 7.0,
        )
        self.assertAlmostEqual(
            summary["sm_activity"]["physical_gpu_avg_pct"], 250.0 / 7.0
        )
        self.assertAlmostEqual(
            summary["sm_activity"]["observed_episode_physical_avg_pct"],
            50.0 / 7.0,
        )

    def test_energy_uses_idle_wall_time_plus_delayed_dynamic_area(self) -> None:
        rows = evaluate.build_gpu_rows(self.document, self.records)
        summary = evaluate.summarize_gpu_metrics(
            self.document, rows, self.records, total_tokens=100
        )

        self.assertAlmostEqual(summary["power"]["idle_avg_w"], 101.0)
        self.assertAlmostEqual(summary["power"]["observed_episode_avg_w"], 131.0)
        self.assertAlmostEqual(summary["energy"]["dynamic_above_idle_j"], 300.0)
        self.assertAlmostEqual(summary["energy"]["total_j"], 502.0)
        self.assertAlmostEqual(summary["energy"]["per_generated_token_j"], 5.02)
        self.assertAlmostEqual(summary["energy"]["generated_tokens_per_j"], 100 / 502)

    def test_missing_activity_is_invalid_not_zero(self) -> None:
        document = copy.deepcopy(self.document)
        for series in document["metrics"]["DCGM_FI_PROF_GR_ENGINE_ACTIVE"]["series"]:
            series["values"] = [[timestamp, "0"] for timestamp in TIMESTAMPS]
        document["activity_capture"]["status"] = "activity_not_observed"

        rows = evaluate.build_gpu_rows(document, self.records)
        summary = evaluate.summarize_gpu_metrics(
            document, rows, self.records, total_tokens=100
        )
        self.assertEqual(
            summary["telemetry_episode"]["quality"], "invalid_no_activity_episode"
        )
        self.assertIsNone(summary["sm_activity"]["physical_gpu_avg_pct"])
        self.assertIsNone(summary["energy"]["total_j"])

    def test_collector_waits_for_an_idle_sample_after_activity(self) -> None:
        series = [
            {
                "values": [[0, "0"], [5, "0.4"], [10, "0"]],
            }
        ]
        observed, settled, active_count, idle_count = collect_gpu_metrics.activity_state(
            series, workload_start=0, threshold_fraction=0.001, settle_samples=1
        )
        self.assertTrue(observed)
        self.assertTrue(settled)
        self.assertEqual(active_count, 1)
        self.assertEqual(idle_count, 1)


if __name__ == "__main__":
    unittest.main()
