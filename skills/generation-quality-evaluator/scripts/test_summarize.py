#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline calculation/validation tests; assertions are not model quality scores."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import summarize as engine

ROOT = Path(__file__).resolve().parents[1]


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.cases = engine.load_json(ROOT / 'demo/cases.json')
        self.ratings = engine.load_json(ROOT / 'demo/ratings.json')
        self.rubric = engine.load_json(ROOT / 'references/rubric.json')

    def run_batch(self):
        return engine.summarize(self.cases, self.ratings, self.rubric, 'v1', 'v2')

    def record(self, case='G04', version='v2'):
        return next(r for r in self.ratings['records'] if r['case_id'] == case and r['version_id'] == version)

    def result_record(self, result, case='G04', version='v2'):
        return next(r for r in result['records'] if r['case_id'] == case and r['version_id'] == version)

    def comparison(self, result, case):
        return next(r for r in result['comparisons'] if r['case_id'] == case)

    def only(self, ident):
        self.cases['cases'] = [c for c in self.cases['cases'] if c['case_id'] == ident]
        self.ratings['records'] = [r for r in self.ratings['records'] if r['case_id'] == ident]

    def finding(self, severity='major', status='confirmed'):
        return {'issue_id':'stable-test', 'type':'omission', 'status':status,
                'severity':severity, 'claim':'测试评审给定的问题',
                'evidence':[{'ref':'output','quote':'把线缆夹进理线夹','note':'第1句'}],
                'recommendation':'人工复核', 'possible_causes':[]}

    def test_demo_denominators_and_paired_difference(self):
        r = self.run_batch()
        self.assertEqual((r['case_count'], r['paired_rated_cases'], r['score_comparable_pairs']), (4, 4, 3))
        self.assertAlmostEqual(r['paired_mean_delta'], (2 - 0.375 + 0) / 3)
        self.assertEqual(r['paired_delta_denominator'], 3)
        self.assertEqual(r['readiness'], 'needs_revision_and_evidence')

    def test_target_error_removed_and_improved(self):
        c = self.comparison(self.run_batch(), 'G01')
        self.assertEqual(c['verdict'], 'improved')
        self.assertIn('fire-claim', c['resolved_confirmed_issues'])

    def test_unknown_is_null_not_zero(self):
        r = self.result_record(self.run_batch(), 'G02')
        self.assertIsNone(r['full_mean'])
        self.assertIsNone(r['scores']['factual_accuracy']['score'])
        self.assertEqual(r['weight_denominator'], 7)

    def test_known_violation_survives_unknown_total(self):
        self.only('G02')
        r = self.run_batch()
        c = r['comparisons'][0]
        self.assertEqual(c['verdict'], 'inconclusive')
        self.assertTrue(c['known_regression'])
        self.assertIn('effect-number-rule', c['new_confirmed_issues'])
        self.assertEqual(r['readiness'], 'needs_revision_and_evidence')

    def test_golden_case_regression_preserved(self):
        c = self.comparison(self.run_batch(), 'G03')
        self.assertEqual(c['verdict'], 'regressed')
        self.assertEqual(c['dimension_deltas']['production_feasibility'], -3)

    def test_unchanged_case_can_pass_checks(self):
        self.only('G04')
        r = self.run_batch()
        self.assertEqual(r['comparisons'][0]['verdict'], 'unchanged')
        self.assertEqual(r['readiness'], 'send_for_human_review')

    def test_omitted_dimension_is_missing_not_zero(self):
        del self.record()['scores']['naturalness']
        r = self.result_record(self.run_batch())
        self.assertEqual(r['scores']['naturalness']['status'], 'missing')
        self.assertIsNone(r['full_mean'])
        self.assertEqual(r['weight_denominator'], 7)

    def test_missing_record_does_not_create_zero(self):
        self.ratings['records'].remove(self.record())
        r = self.run_batch()
        self.assertEqual(r['versions']['v2']['missing_ratings'], ['G04'])
        self.assertEqual(r['paired_rated_cases'], 3)
        self.assertEqual(r['unpaired_baseline'], ['G04'])

    def test_absent_output_is_unpaired(self):
        case = next(c for c in self.cases['cases'] if c['case_id'] == 'G04')
        del case['outputs']['v1']
        self.ratings['records'].remove(self.record('G04','v1'))
        r = self.run_batch()
        self.assertEqual(r['versions']['v1']['missing_outputs'], ['G04'])
        self.assertEqual(r['unpaired_candidate'], ['G04'])

    def test_duplicate_case_rejected(self):
        self.cases['cases'].append(copy.deepcopy(self.cases['cases'][0]))
        with self.assertRaises(engine.InputError): self.run_batch()

    def test_duplicate_record_rejected(self):
        self.ratings['records'].append(copy.deepcopy(self.record()))
        with self.assertRaises(engine.InputError): self.run_batch()

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'duplicate.json'
            path.write_text('{"a":1,"a":2}',encoding='utf-8')
            with self.assertRaises(engine.InputError): engine.load_json(path)

    def test_critical_blocks_high_mean(self):
        self.only('G04')
        self.record()['findings'] = [self.finding('critical')]
        r = self.run_batch()
        self.assertGreaterEqual(r['versions']['v2']['mean_of_complete_scores'], 2)
        self.assertEqual(r['readiness'], 'blocked_critical')
        self.assertEqual(r['comparisons'][0]['verdict'], 'regressed_critical')

    def test_existing_critical_is_still_blocked(self):
        self.only('G04')
        for v in ('v1','v2'): self.record('G04',v)['findings'] = [self.finding('critical')]
        r = self.run_batch()
        self.assertEqual(r['comparisons'][0]['verdict'], 'blocked_existing_critical')
        self.assertEqual(r['readiness'], 'blocked_critical')

    def test_severity_escalation_detected(self):
        self.only('G04')
        self.record('G04','v1')['findings'] = [self.finding('minor')]
        self.record()['findings'] = [self.finding('major')]
        c = self.run_batch()['comparisons'][0]
        self.assertEqual(c['severity_escalations'], ['stable-test'])
        self.assertEqual(c['verdict'], 'regressed')

    def test_confirmed_to_pending_not_resolved(self):
        self.only('G04')
        self.record('G04','v1')['findings'] = [self.finding()]
        self.record()['findings'] = [self.finding(status='pending')]
        c = self.run_batch()['comparisons'][0]
        self.assertEqual(c['resolved_confirmed_issues'], [])
        self.assertEqual(c['verdict'], 'inconclusive')

    def test_all_not_applicable_has_no_mean(self):
        for item in self.record()['scores'].values():
            item.update(status='not_applicable',score=None,rationale='测试任务不适用')
        r = self.result_record(self.run_batch())
        self.assertIsNone(r['partial_mean'])
        self.assertIsNone(r['full_mean'])
        self.assertEqual(r['weight_denominator'],0)

    def test_different_applicable_sets_not_total_comparable(self):
        self.record()['scores']['oral_fluency'].update(status='not_applicable',score=None,rationale='测试任务不适用')
        c = self.comparison(self.run_batch(),'G04')
        self.assertFalse(c['score_comparable'])
        self.assertIsNone(c['total_delta'])

    def test_invalid_quote_rejected(self):
        self.record()['scores']['topic_relevance']['evidence'][0]['quote'] = '原文里没有的句子'
        with self.assertRaises(engine.InputError): self.run_batch()

    def test_unknown_fact_cannot_be_confirmed(self):
        self.record('G02')['findings'][0]['status'] = 'confirmed'
        with self.assertRaises(engine.InputError): self.run_batch()

    def test_unknown_fact_cannot_be_assessed_score(self):
        self.record('G02')['scores']['factual_accuracy'].update(status='assessed',score=0)
        with self.assertRaises(engine.InputError): self.run_batch()

    def test_boolean_or_out_of_range_scores_rejected(self):
        for score in (True,-1,4,1.5):
            with self.subTest(score=score):
                self.record()['scores']['topic_relevance']['score'] = score
                with self.assertRaises(engine.InputError): self.run_batch()

    def test_invalid_weight_and_rubric_mismatch_rejected(self):
        for weight in (0,-1,float('nan'),float('inf'),True):
            with self.subTest(weight=weight):
                self.rubric['dimensions'][0]['weight'] = weight
                with self.assertRaises(engine.InputError): self.run_batch()
        self.rubric['dimensions'][0]['weight'] = 1
        self.ratings['rubric_id'] = 'different'
        with self.assertRaises(engine.InputError): self.run_batch()

    def test_empty_batch_has_no_mean_or_pair(self):
        self.cases['cases'] = []; self.ratings['records'] = []
        r = self.run_batch()
        self.assertIsNone(r['paired_mean_delta'])
        self.assertEqual(r['readiness'],'needs_more_evidence')

    def test_empty_actual_output_remains_an_output(self):
        self.only('G04')
        self.cases['cases'][0]['outputs']['v2'] = ''
        for item in self.record()['scores'].values():
            item.update(score=0,rationale='按锚点评空输出',evidence=[{'ref':'output','kind':'empty_output','quote':None,'note':'完整输出为空'}])
        r = self.run_batch()
        self.assertEqual(r['versions']['v2']['output_cases'],1)
        self.assertEqual(self.result_record(r)['full_mean'],0)
        self.cases['cases'][0]['outputs']['v2'] = '实际非空'
        with self.assertRaises(engine.InputError): self.run_batch()

    def test_feedback_missing_is_not_false(self):
        self.assertIsNone(self.result_record(self.run_batch())['feedback'])

    def test_issue_id_cannot_change_type(self):
        self.record('G04','v1')['findings']=[self.finding()]
        self.record()['findings']=[self.finding()]
        self.record()['findings'][0]['type']='repetition'
        with self.assertRaises(engine.InputError): self.run_batch()

    def test_average_gain_does_not_hide_dimension_drop(self):
        self.only('G04')
        for item in self.record()['scores'].values(): item['score']=3
        self.record()['scores']['production_feasibility']['score']=1
        c=self.run_batch()['comparisons'][0]
        self.assertGreater(c['total_delta'],0)
        self.assertEqual(c['verdict'],'mixed')

    def test_cli_refuses_overwriting_input(self):
        source=ROOT/'demo/cases.json'
        before=source.read_bytes()
        r=subprocess.run([sys.executable,str(ROOT/'scripts/summarize.py'),'--cases',str(source),'--ratings',str(ROOT/'demo/ratings.json'),'--rubric',str(ROOT/'references/rubric.json'),'--baseline','v1','--candidate','v2','--json-out',str(source)],capture_output=True,text=True)
        self.assertEqual(r.returncode,2)
        self.assertEqual(source.read_bytes(),before)

    def test_cli_is_deterministic_and_read_only_without_targets(self):
        args=[sys.executable,str(ROOT/'scripts/summarize.py'),'--cases',str(ROOT/'demo/cases.json'),'--ratings',str(ROOT/'demo/ratings.json'),'--rubric',str(ROOT/'references/rubric.json'),'--baseline','v1','--candidate','v2']
        outputs=[]
        for seed in ('1','2'):
            r=subprocess.run(args,env=dict(os.environ,PYTHONHASHSEED=seed),capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            outputs.append(json.loads(r.stdout))
        self.assertEqual(outputs[0],outputs[1])


if __name__=='__main__':
    unittest.main(verbosity=2)
