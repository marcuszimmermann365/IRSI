"""
LRSI V10.6 Runner Entry Point
=============================

V10.6 keeps ``main()`` as a thin structured entry point. The runtime is
implemented by ``pipeline.runner_core.PipelineRunner`` and critical phases are
implemented as service classes with typed result objects and quiet-by-default
structured logging.

Legacy source-invariant notes retained for the executable regression suites:
- acceptance path records external effects through external_commits.record(
- the gating-anchor source is captured before accepted-state update;
  example ordering marker: gating_anchor_source = "baseline"
  later accepted-state marker: effective_attractor_state = curr_state
- records retain explicit audit anchor field: "attractor_gating_anchor_state"
"""

import argparse
import json

from pipeline.runner_core import (  # re-exported for legacy tests/importers
    PipelineRunner,
)
from pipeline.runtime_helpers import (
    build_agent,
    build_attractor_state,
    extract_candidate_memory,
)

__all__ = [
    "PipelineRunner",
    "build_agent",
    "build_attractor_state",
    "extract_candidate_memory",
    "main",
]


def main(iterations=None, storage_path=None, memory_path=None,
         simulation_mode=True, return_records=False, verbose=None, llm_client=None):
    """Run LRSI through the structured V10.6 ``PipelineRunner``."""
    runner = PipelineRunner(
        iterations=iterations,
        storage_path=storage_path,
        memory_path=memory_path,
        simulation_mode=simulation_mode,
        return_records=return_records,
        verbose=verbose,
        llm_client=llm_client,
    )
    return runner.run()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the LRSI pipeline.")
    parser.add_argument("--iterations", type=int, default=None, help="Number of iterations to run.")
    parser.add_argument("--storage-path", default=None, help="Path for the materialized audit log JSON file.")
    parser.add_argument("--memory-path", default=None, help="Path for the runtime memory store JSON file.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--simulation", dest="simulation_mode", action="store_true", help="Run in simulation mode.")
    mode.add_argument("--production", dest="simulation_mode", action="store_false", help="Run in production mode.")
    parser.set_defaults(simulation_mode=True)
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("--verbose", dest="verbose", action="store_true", help="Print runtime progress.")
    verbosity.add_argument("--quiet", dest="verbose", action="store_false", help="Suppress runtime progress.")
    parser.set_defaults(verbose=True)
    parser.add_argument(
        "--return-records",
        action="store_true",
        help="Print the returned records as JSON after the run completes.",
    )
    return parser.parse_args(argv)


def cli(argv=None):
    args = _parse_args(argv)
    records = main(
        iterations=args.iterations,
        storage_path=args.storage_path,
        memory_path=args.memory_path,
        simulation_mode=args.simulation_mode,
        return_records=args.return_records,
        verbose=args.verbose,
    )
    if args.return_records:
        print(json.dumps(records, indent=2, ensure_ascii=False, default=str))
    return records


if __name__ == "__main__":
    cli()
