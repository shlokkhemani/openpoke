from __future__ import annotations

import unittest

from evals.ui.server import _expected_cells


class EvalUiProgressTests(unittest.TestCase):
    def test_scenario_runs_have_one_configured_size_per_case(self) -> None:
        data = {
            "mode": "scenario",
            "sizes": [0, 16_000, 80_000],
            "strategies": ["budgeted", "legacy"],
        }
        runs = [{"case_id": "a"}, {"case_id": "b"}]

        self.assertEqual(_expected_cells(data, runs), 4)

    def test_sweep_runs_cross_cases_sizes_and_strategies(self) -> None:
        data = {
            "mode": "sweep",
            "sizes": [0, 16_000, 80_000],
            "strategies": ["budgeted", "legacy"],
        }
        runs = [{"case_id": "a"}, {"case_id": "b"}]

        self.assertEqual(_expected_cells(data, runs), 12)


if __name__ == "__main__":
    unittest.main()
