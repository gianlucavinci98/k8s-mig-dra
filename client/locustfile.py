import json
import subprocess
import time
from itertools import count
from pathlib import Path
from time import strftime

from locust import HttpUser, task, events


user_id_counter = count(1)
results_dir = Path("results")
results_file = results_dir / "results.jsonl"


def ts_now():
    return strftime("%H:%M:%S")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    results_dir.mkdir(exist_ok=True)
    results_file.write_text("")  # reset file
    
    # Crea metadata.json per evaluate.py (con valori di default)
    metadata = {
        "mig_config": "unknown",
        "ollama_replicas": 0,
        "total_requests": 0,
        "concurrency": 0,
        "num_predict": 400,
    }
    metadata_file = results_dir / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"[{ts_now()}] Test started - results will be saved to {results_file}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print(f"[{ts_now()}] Test stopped - running evaluation...")
    try:
        subprocess.run(
            ["python3", "../scripts/evaluate.py"],
            cwd=".",
            check=True,
            capture_output=False,
        )
    except subprocess.CalledProcessError as e:
        print(f"[{ts_now()}] Evaluation failed: {e}")


class GenerateUser(HttpUser):
    host = "http://10.146.0.55:31134"

    def on_start(self):
        self.user_id = next(user_id_counter)
        self.call_count = 0
        print(f"[{ts_now()}] [spawn] user={self.user_id}")

    @task
    def generate(self):
        self.call_count += 1
        call_no = self.call_count
        print(f"[{ts_now()}] [call] user={self.user_id} call={call_no} POST /api/generate")

        payload = {
            "model": "tinyllama",
            "prompt": "produce a extremely long document",
            "stream": False,
            "options": {"num_predict": 400},
        }

        start_time_ms = int(time.time() * 1000)

        with self.client.post(
            "/api/generate",
            json=payload,
            headers={"Content-Type": "application/json"},
            name=f"LLM generate user={self.user_id}",
            catch_response=True,
        ) as response:
            end_time_ms = int(time.time() * 1000)

            if response.status_code == 200:
                try:
                    data = response.json()

                    # Estrai i campi importanti per la valutazione
                    result = {
                        "created_at": data.get("created_at"),
                        "total_duration": data.get("total_duration"),
                        "load_duration": data.get("load_duration"),
                        "prompt_eval_count": data.get("prompt_eval_count"),
                        "prompt_eval_duration": data.get("prompt_eval_duration"),
                        "eval_count": data.get("eval_count"),
                        "eval_duration": data.get("eval_duration"),
                        "num_predict": payload["options"]["num_predict"],
                        "start_time": start_time_ms,
                        "end_time": end_time_ms,
                    }

                    # Salva in JSONL
                    with open(results_file, "a") as f:
                        f.write(json.dumps(result) + "\n")

                    latency_ms = result.get("total_duration", 0) / 1e6
                    tokens = result.get("eval_count", 0)
                    print(
                        f"[{ts_now()}] [resp] user={self.user_id} call={call_no} "
                        f"status={response.status_code} latency={latency_ms:.0f}ms tokens={tokens}"
                    )
                    response.success()
                except Exception as e:
                    print(
                        f"[{ts_now()}] [resp] user={self.user_id} call={call_no} "
                        f"status={response.status_code} ERROR parsing response: {e}"
                    )
                    response.failure(f"Error parsing response: {e}")
            else:
                print(
                    f"[{ts_now()}] [resp] user={self.user_id} call={call_no} "
                    f"status={response.status_code} ERROR"
                )
                response.failure(f"HTTP {response.status_code}")

