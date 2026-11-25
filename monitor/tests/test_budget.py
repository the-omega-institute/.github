import datetime as dt
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import monitor_budget as b
import monitor as m

NOW = dt.datetime(2026, 11, 26, 12, tzinfo=dt.timezone.utc)
EMPTY = {'schema': b.SCHEMA, 'reservations': []}
OBSERVATION = {'schema': m.SCHEMA, 'repository': 'org/pages', 'state': 'anomaly', 'fingerprint': 'a'*20}


class ReservationTests(unittest.TestCase):
    def test_failed_runs_and_different_source_commits_cannot_repeat_the_same_incident(self):
        first = b.reserve(OBSERVATION, EMPTY, 10, 1, True, NOW)
        self.assertTrue(first['model_allowed'])
        changed = {**OBSERVATION, 'head_sha': 'new source revision'}
        again = b.reserve(changed, first['model_budget'], 11, 1, True, NOW+dt.timedelta(days=1))
        self.assertFalse(again['model_allowed'])
        self.assertEqual(again['model_budget'], first['model_budget'])
        later = b.reserve(changed, again['model_budget'], 12, 1, True, NOW+dt.timedelta(days=8))
        self.assertTrue(later['model_allowed'])

    def test_different_incidents_and_manual_acceptance_share_the_daily_limit(self):
        first = b.reserve(OBSERVATION, EMPTY, 10, 1, True, NOW)
        second = b.reserve({**OBSERVATION, 'state':'healthy'}, first['model_budget'], 11, 1, True, NOW)
        self.assertTrue(second['model_allowed'])
        third = b.reserve({**OBSERVATION, 'fingerprint':'b'*20}, second['model_budget'], 12, 1, True, NOW)
        self.assertFalse(third['model_allowed'])

    def test_healthy_runs_do_not_spend_or_reset_reservations(self):
        first = b.reserve(OBSERVATION, EMPTY, 10, 1, True, NOW)
        healthy = b.reserve({**OBSERVATION, 'state':'healthy'}, first['model_budget'], 11, 1, False, NOW)
        self.assertFalse(healthy['model_allowed'])
        self.assertEqual(healthy['model_budget'], first['model_budget'])

    def test_missing_corrupt_future_history_and_workflow_reruns_cannot_open_paid_work(self):
        self.assertFalse(b.reserve(OBSERVATION, None, 10, 1, True, NOW)['model_allowed'])
        self.assertFalse(b.reserve(OBSERVATION, EMPTY, 10, 2, True, NOW)['model_allowed'])
        for previous in ({'schema':'wrong','reservations':[]},
                         {'schema':b.SCHEMA,'reservations':[{'at':(NOW+dt.timedelta(days=1)).isoformat()}]}):
            with self.assertRaises(ValueError): b.reserve(OBSERVATION, previous, 10, 1, True, NOW)

    def test_repair_rerun_cannot_reuse_the_original_inspect_reservation(self):
        first = b.reserve(OBSERVATION, EMPTY, 10, 1, True, NOW)
        b.validate_reservation(first, 10, 1)
        for run, attempt in [(10,2),(11,1)]:
            with self.assertRaises(ValueError): b.validate_reservation(first, run, attempt)

    def test_history_must_exist_even_when_prior_repair_failed_or_asset_expired(self):
        class API:
            def __init__(self, expired=False, missing=False):self.expired,self.missing=expired,missing
            def call(self, method, path):
                if '/workflows/' in path:return {'workflow_runs':[{'id':9,'run_attempt':1,'status':'completed','conclusion':'failure'}]}
                if '/artifacts?' in path:return {'artifacts':[] if self.missing else [{'name':'monitor-input-9-1','id':1,'expired':self.expired}]}
                if '/jobs?' in path:return {'jobs':[{'name':'monitor / repair','conclusion':'failure'}]}
                raise AssertionError(path)
            def observation(self, _identity):
                return {**OBSERVATION, 'model_budget':b.reserve(OBSERVATION, EMPTY, 9, 1, True, NOW)['model_budget']}
        with patch.dict(os.environ, {'GITHUB_RUN_ID':'10','GITHUB_RUN_ATTEMPT':'1'}):
            self.assertEqual(len(m.model_history(API(), 'org/pages')['reservations']),1)
            for api in [API(expired=True),API(missing=True)]:
                with self.assertRaises(ValueError): m.model_history(api, 'org/pages')


class RequestBudgetTests(unittest.TestCase):
    def request(self, **values):
        return json.dumps({'model':'gpt-6.1-sol', 'input':'bounded task', **values}).encode()

    def test_restart_cannot_reset_turn_limit_or_increase_output_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'budget.json'
            for _ in range(b.MAX_REQUESTS):
                payload=json.loads(b.RequestBudget(path).reserve(self.request(max_output_tokens=999999), 'gpt-6.1-sol'))
                self.assertEqual(payload['max_output_tokens'],b.MAX_OUTPUT_TOKENS)
                self.assertFalse(payload['store'])
            with self.assertRaises(ValueError): b.RequestBudget(path).reserve(self.request(), 'gpt-6.1-sol')

    def test_context_growth_hidden_history_and_paid_tools_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            budget=b.RequestBudget(Path(d)/'budget.json')
            for values in [{'model':'more-expensive-model'}, {'previous_response_id':'hidden-history'},
                           {'conversation':'growing-thread'}, {'tools':[{'type':'web_search'}]},
                           {'input':'x'*b.MAX_REQUEST_BYTES}]:
                with self.assertRaises(ValueError):budget.reserve(self.request(**values),'gpt-6.1-sol')
            for _ in range(4):budget.reserve(self.request(input='x'*100000),'gpt-6.1-sol')
            budget.reserve(self.request(input='x'*100000),'gpt-6.1-sol')
            with self.assertRaises(ValueError):budget.reserve(self.request(input='x'*100000),'gpt-6.1-sol')

    def test_concurrent_requests_cannot_overspend_shared_budget(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'budget.json';accepted=[]
            def reserve():
                try:b.RequestBudget(path).reserve(self.request(),'gpt-6.1-sol');accepted.append(True)
                except ValueError:pass
            threads=[threading.Thread(target=reserve) for _ in range(30)]
            for t in threads:t.start()
            for t in threads:t.join()
            self.assertEqual(len(accepted),b.MAX_REQUESTS)

    def test_gateway_denials_never_reach_upstream_and_lost_responses_spend_once(self):
        calls=[]
        def opener(req,timeout):
            calls.append(req)
            self.assertEqual(req.full_url,b.UPSTREAM)
            self.assertEqual(req.headers['Authorization'],'Bearer real-key-never-forwarded-to-codex')
            if len(calls)==1:raise TimeoutError('uncertain charge')
            response=io.BytesIO(b'data: {"type":"response.completed"}\n\n')
            response.headers={'Content-Type':'text/event-stream'}
            return response
        with tempfile.TemporaryDirectory() as d:
            budget=b.RequestBudget(Path(d)/'budget.json')
            with b.gateway(budget,'real-key-never-forwarded-to-codex','gpt-6.1-sol',opener) as (url,token):
                def post(body=None, path='/responses', auth=token):
                    req=urllib.request.Request(url+path,data=body or self.request(),headers={
                        'Authorization':'Bearer '+auth,'Content-Type':'application/json'})
                    return urllib.request.urlopen(req,timeout=5)
                for values in [{'path':'/other'},{'auth':'wrong'},{'body':self.request(previous_response_id='old')}]:
                    with self.assertRaises(urllib.error.HTTPError):post(**values)
                self.assertEqual(calls,[])
                with self.assertRaises(urllib.error.HTTPError):post()
                with post() as response:self.assertIn(b'response.completed',response.read())
                self.assertEqual(len(calls),2)
                self.assertEqual(json.loads(budget.path.read_text())['requests'],2)


if __name__=='__main__':unittest.main()
