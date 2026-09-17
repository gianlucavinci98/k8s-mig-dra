#!/usr/bin/env python3

import unittest

import evaluate


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
        "values": [[timestamp, str(value)] for timestamp, value in zip((0, 5, 10), values)],
    }


class GpuAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        metrics = {}
        for metric_name, values in {
            "DCGM_FI_PROF_GR_ENGINE_ACTIVE": [0.5, 0.5, 0.5],
            "DCGM_FI_PROF_DRAM_ACTIVE": [0.25, 0.25, 0.25],
            "DCGM_FI_DEV_FB_USED": [1000, 1000, 1000],
            "DCGM_FI_DEV_FB_FREE": [4000, 4000, 4000],
            "DCGM_FI_DEV_POWER_USAGE": [100, 100, 100],
        }.items():
            second_values = (
                [102, 102, 102]
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
            "query_window": {
                "start_unix_s": 0,
                "end_unix_s": 10,
                "padding_before_seconds": 0,
                "padding_after_seconds": 0,
                "step_seconds": 5,
            },
            "metrics": metrics,
        }
        self.records = [
            {
                "start_time": 0,
                "end_time": 10000,
                "eval_count": 100,
            }
        ]

    def test_partition_weighting_and_power_deduplication(self) -> None:
        rows = evaluate.build_gpu_rows(self.document, self.records)
        system_middle = next(
            row for row in rows["system"] if row["timestamp_unix_s"] == 5
        )

        self.assertAlmostEqual(system_middle["sm_configured_pct"], 50.0)
        self.assertAlmostEqual(system_middle["sm_physical_pct"], 100.0 / 7.0)
        self.assertAlmostEqual(system_middle["dram_configured_pct"], 25.0)
        self.assertAlmostEqual(system_middle["dram_physical_pct"], 6.25)
        self.assertAlmostEqual(system_middle["fb_used_mib"], 2000.0)
        self.assertAlmostEqual(system_middle["power_w"], 101.0)

    def test_energy_integrates_deduplicated_board_power(self) -> None:
        rows = evaluate.build_gpu_rows(self.document, self.records)
        summary = evaluate.summarize_gpu_metrics(
            self.document, rows, self.records, total_tokens=100
        )

        self.assertAlmostEqual(summary["power"]["avg_w"], 101.0)
        self.assertAlmostEqual(summary["energy"]["total_j"], 1010.0)
        self.assertAlmostEqual(summary["energy"]["per_generated_token_j"], 10.1)
        self.assertAlmostEqual(summary["energy"]["generated_tokens_per_j"], 100 / 1010)


if __name__ == "__main__":
    unittest.main()
