from Conduit.sync import Model, Prompt, Conduit, Verbosity
from contextlib import contextmanager
from rich.console import Console
import pandas as pd
import signal
import time

# Set console
console = Console()
Model._console = console


# Our context manager for handling timeouts
class Timeout:
    def __init__(self, seconds: int):
        self.seconds = seconds

    def _handle_timeout(self, signum, frame):
        raise TimeoutError(f"Operation timed out after {self.seconds} seconds")

    def __enter__(self):
        # Register the handler and start the alarm
        signal.signal(signal.SIGALRM, self._handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Cancel the alarm no matter what
        signal.alarm(0)
        return False  # don’t suppress exceptions


# Our chain function
def test_model(model_str: str) -> tuple:
    model = Model(model_str)

    # Cold boot -- loading the model for the first time
    cold_prompt = Prompt("Tell me a joke.")
    cold_chain = Conduit(prompt=cold_prompt, model=model)
    cold_boot_start = time.time()
    try:
        print("Cold boot:")
        with Timeout(180):  # Set timeout to 10 seconds
            response = cold_chain.run(cache=False, verbose=Verbosity.COMPLETE)
    except TimeoutError as e:
        print(f"\t\tTimeoutError for {model_str}: {e}")
    except Exception as e:
        print(f"\t\tAn error occurred for {model_str}: {e}")
    cold_boot_end = time.time()
    cold_boot_duration = cold_boot_end - cold_boot_start

    # Warm boot -- model should already be loaded -- this is what we care about
    warm_prompt = Prompt("Name three North american birds.")
    warm_chain = Conduit(prompt=warm_prompt, model=model)
    warm_boot_start = time.time()
    try:
        print("Warm boot:")
        with Timeout(180):  # Set timeout to 10 seconds
            response = warm_chain.run(cache=False, verbose=Verbosity.COMPLETE)
    except TimeoutError as e:
        print(f"\t\tTimeoutError for {model_str}: {e}")
    except Exception as e:
        print(f"\t\tAn error occurred for {model_str}: {e}")
    warm_boot_end = time.time()
    warm_boot_duration = warm_boot_end - warm_boot_start
    return cold_boot_duration, warm_boot_duration


if __name__ == "__main__":
    # Get models
    models = Model.models()["ollama"]
    timings = []
    for index, model_str in enumerate(models):
        print(f"Testing model {index + 1}/{len(models)}: {model_str}")
        cold_boot_duration, warm_boot_duration = test_model(model_str)
        data_dict = {
            "model": model_str,
            "cold_boot_duration": cold_boot_duration,
            "warm_boot_duration": warm_boot_duration,
        }
        timings.append(data_dict)
        print("-" * 40)
    df = pd.DataFrame(timings)
    df.to_csv("timings.csv", index=False)
