"""Regression checks for calendar, workload and planning behavior."""
from copy import deepcopy
import unittest

import simpy

from migration_sim import (
    BASE_CONFIG, UsageTracker, hypercare_process, preview_plan,
    run_full_program, within_business, work_timeout_tracked,
)


class MigrationTests(unittest.TestCase):
    def config(self, **overrides):
        cfg = deepcopy(BASE_CONFIG)
        cfg.update(TOTAL_REPOS=12, TOTAL_PIPES=6, WAVES=2, COHORTS_PER_WAVE=2,
                   TEMPLATES_READY_DAY=0)
        cfg.update(overrides)
        return cfg

    def test_plan_exposes_single_cohort_and_even_distribution(self):
        cfg = self.config()
        self.assertEqual(int(preview_plan(cfg).Active.sum()), 1)
        cfg['ALLOCATION_MODE'] = 'even'
        plan = preview_plan(cfg)
        self.assertEqual(int(plan.Active.sum()), 4)
        self.assertEqual(plan.Repos.sum(), 12)
        self.assertEqual(plan.Pipelines.sum(), 6)

    def test_invalid_config_fails_before_running(self):
        for overrides in ({'TOTAL_REPOS': 10000}, {'WORKDAY_END_HOUR': 9},
                          {'CI_ENGINEERS_PER_COHORT': 0}, {'ALLOCATION_MODE': 'typo'},
                          {'REPO_DIST': {'simple': .5}}, {'HYPERCARE_HOURS_PER_DAY': 9}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                run_full_program(self.config(**overrides))

    def test_empty_program(self):
        out = run_full_program(self.config(TOTAL_REPOS=0, TOTAL_PIPES=0))
        self.assertEqual(out['overall_finish_days'], 0)
        self.assertEqual(out['peak_engineers'], 0)
        self.assertTrue(out['usage_load_df'].empty)

    def test_hypercare_has_five_separate_workdays_and_releases_engineer(self):
        cfg = self.config()
        env = simpy.Environment(initial_time=4 * 24 + 9)  # Friday 09:00
        pool = simpy.Store(env, capacity=1)
        pool.items.append('Triage:1')
        tracker = UsageTracker()
        env.process(hypercare_process(env, pool, env.now, 5, 2, cfg, tracker))
        env.run()
        segments = tracker.segments_df()
        days = (segments['Start(h)'] // 24).astype(int).tolist()
        self.assertEqual(days, [4, 7, 8, 9, 10])
        self.assertEqual(segments.Hours.sum(), 10)
        self.assertEqual(pool.items, ['Triage:1'])

    def test_continuous_calendar_crosses_midnight(self):
        cfg = self.config(BUSINESS_HOURS_ONLY=False)
        env = simpy.Environment()
        tracker = UsageTracker()
        env.process(work_timeout_tracked(env, 50, cfg, tracker, 'Repo', 'Repo_1.1:1'))
        env.run()
        self.assertEqual(env.now, 50)
        self.assertEqual(tracker.segments_df().Hours.sum(), 50)

    def test_workload_balances_and_start_matches_calendar(self):
        cfg = self.config(REPO_REWORK_PROB=1, PIPE_REWORK_PROB=1,
                          REWORK_SCALER_REPO=1, REWORK_SCALER_PIPE=1)
        out = run_full_program(cfg)
        expected = sum(stats[key] for stats in out['rework_stats'].values()
                       for key in ('main_hours', 'rework_hours', 'triage_hours', 'swat_hours')) + 10
        self.assertAlmostEqual(out['usage_df'].Hours.sum(), expected)
        self.assertAlmostEqual(out['usage_totals_df'].PersonDays.sum(), expected / 8)
        self.assertEqual(out['program_start_hour'], 9)
        self.assertEqual(out['processed_repos'], 12)
        self.assertEqual(out['processed_pipes'], 6)
        self.assertTrue((out['usage_load_df'].LoadPct <= 100 + 1e-8).all())
        self.assertTrue(all(within_business(t, cfg) for t in out['usage_df']['Start(h)']))
        self.assertEqual(out['peak_engineers'], 4 + 2 + 3 + 2)

    def test_overlapping_waves_count_all_crews(self):
        cfg = self.config(ALLOCATION_MODE='even', HYPERCARE_ENABLED=False)
        out = run_full_program(cfg)
        self.assertEqual(out['peak_engineers'], 4 * (4 + 2) + 3 + 2)

    def test_same_seed_reproduces_results(self):
        cfg = self.config(ALLOCATION_MODE='even')
        first, second = run_full_program(cfg), run_full_program(cfg)
        self.assertEqual(first['overall_finish_days'], second['overall_finish_days'])
        self.assertTrue(first['usage_df'].equals(second['usage_df']))


if __name__ == '__main__':
    unittest.main()
