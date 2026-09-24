import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from exchange_bridge import __main__ as bridge


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.ultra=self.config('ultra5060')
        self.pro=self.config('pro360')
        self.commit=patch.object(bridge,'commit',return_value='a'*40)
        self.commit.start();self.addCleanup(self.commit.stop)
        self.space=patch.object(bridge.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(10**12,0,10**12))
        self.space.start();self.addCleanup(self.space.stop)

    def config(self,role):
        root=self.base/role
        root.mkdir()
        return dict(version=1,role=role,project_root=str(root),exchange_root=str(self.base/'exchange'),
                    state_root=str(self.base/(role+'-state')),python='python',auto_git=False,review_debounce_seconds=0)

    def source(self,cfg,name='data/derived/example.csv',content='id,label\n1,0\n'):
        path=Path(cfg['project_root'])/name
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        return path

    def worker(self,cfg):
        bridge.run_worker(cfg,self.base/'unused-config.json')
        return json.loads((Path(cfg['state_root'])/'worker-state.json').read_text())

    def test_paths_reject_traversal_and_windows_special_names(self):
        for name in ('../a','/absolute','data/../secret','data\\file','data/a:stream','data/CON.txt','data/a.','data//a'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                bridge.safe_path(self.base,name)

    def test_only_data_is_exported(self):
        for name in ('configs/local-exchange.json','data/derived/.env','data/external/.cache/token','data/derived/start.ps1'):
            self.assertFalse(bridge.allowed_data(name))

    def test_arbitrary_commands_are_rejected(self):
        job=bridge.publish(self.ultra,'ping')
        job['action']='powershell'
        with self.assertRaises(ValueError):
            bridge.validate_job(job,job['id'],'pro360')
        job['action']='ping';job['command']='whoami'
        with self.assertRaises(ValueError):
            bridge.validate_job(job,job['id'],'pro360')

    def test_missing_payload_waits_then_imports_exact_bytes(self):
        source=self.source(self.ultra)
        job=bridge.publish(self.ultra,'import_bundle',['data/derived/example.csv'])
        inbox=bridge.dirs(self.pro)[1]
        payload=inbox/'bundles'/job['id']/'files/data/derived/example.csv'
        data=payload.read_bytes();payload.unlink()
        self.assertEqual(self.worker(self.pro)['jobs'][job['id']]['status'],'waiting_for_files')
        payload.write_bytes(data)
        self.assertEqual(self.worker(self.pro)['jobs'][job['id']]['status'],'completed')
        self.assertEqual((Path(self.pro['project_root'])/'data/derived/example.csv').read_bytes(),source.read_bytes())

    def test_hash_mismatch_fails_without_import(self):
        self.source(self.ultra)
        job=bridge.publish(self.ultra,'import_bundle',['data/derived/example.csv'])
        payload=bridge.dirs(self.pro)[1]/'bundles'/job['id']/'files/data/derived/example.csv'
        payload.write_bytes(b'x'*payload.stat().st_size)
        state=self.worker(self.pro)
        self.assertEqual(state['jobs'][job['id']]['status'],'failed')
        self.assertFalse((Path(self.pro['project_root'])/'data/derived/example.csv').exists())

    def test_conflict_preserves_all_local_files(self):
        self.source(self.ultra,'data/derived/a.csv')
        self.source(self.ultra,'data/derived/b.csv')
        original=self.source(self.pro,'data/derived/b.csv','human edit')
        job=bridge.publish(self.ultra,'import_bundle',['data/derived'])
        self.assertEqual(self.worker(self.pro)['jobs'][job['id']]['status'],'failed')
        self.assertEqual(original.read_text(),'human edit')
        self.assertFalse((Path(self.pro['project_root'])/'data/derived/a.csv').exists())

    def test_completed_job_is_not_executed_twice(self):
        self.source(self.ultra)
        job=bridge.publish(self.ultra,'import_bundle',['data/derived'])
        self.worker(self.pro)
        self.source(self.pro,content='human edit after import')
        with patch.object(bridge,'import_files',side_effect=AssertionError('re-executed')):
            self.assertEqual(self.worker(self.pro)['jobs'][job['id']]['status'],'completed')

    def test_interrupted_job_requires_new_id(self):
        job=bridge.publish(self.ultra,'ping')
        bridge.atomic_json(Path(self.pro['state_root'])/'worker-state.json',{'jobs':{job['id']:{'status':'running'}},'watch':{}})
        self.assertEqual(self.worker(self.pro)['jobs'][job['id']]['status'],'failed')

    def test_changed_pending_job_is_rejected(self):
        self.source(self.ultra)
        job=bridge.publish(self.ultra,'verify_bundle',['data/derived'])
        inbox=bridge.dirs(self.pro)[1]
        (inbox/'bundles'/job['id']/'files/data/derived/example.csv').unlink()
        self.worker(self.pro)
        job['action']='import_bundle'
        bridge.atomic_json(inbox/'jobs'/(job['id']+'.json'),job)
        self.assertIn('reused',self.worker(self.pro)['jobs'][job['id']]['reason'])

    def test_review_return_is_versioned(self):
        self.source(self.pro,content='reviewed')
        original=self.source(self.ultra,content='original')
        job=bridge.publish(self.pro,'return_reviews',['data/derived'])
        self.assertEqual(self.worker(self.ultra)['jobs'][job['id']]['status'],'completed')
        self.assertEqual(original.read_text(),'original')
        returned=Path(self.ultra['project_root'])/'data/derived/peer_reviews/pro360'/job['id']/'data/derived/example.csv'
        self.assertEqual(returned.read_text(),'reviewed')

    def test_import_does_not_echo_but_human_edit_returns_once(self):
        name=bridge.WATCH[0]
        self.source(self.ultra,name)
        bridge.publish(self.ultra,'import_bundle',[name])
        self.worker(self.pro);self.worker(self.pro)
        outbox=bridge.dirs(self.pro)[0]
        self.assertEqual(list((outbox/'jobs').glob('*.json')),[])
        self.source(self.pro,name,'id,label\n1,reviewed\n')
        self.worker(self.pro);self.worker(self.pro);self.worker(self.pro)
        self.assertEqual(len(list((outbox/'jobs').glob('*.json'))),1)

    def test_cpu_job_waits_for_matching_code(self):
        job=bridge.publish(self.ultra,'run_contract_tests')
        with patch.object(bridge,'commit',return_value='b'*40):
            state=self.worker(self.pro)
        self.assertEqual(state['jobs'][job['id']]['status'],'waiting_for_clean_matching_code')

    def test_worker_lock_prevents_concurrent_execution(self):
        with bridge.worker_lock(self.pro['state_root']):
            with self.assertRaises(RuntimeError):
                with bridge.worker_lock(self.pro['state_root']):
                    self.fail('second worker entered')


if __name__=='__main__':
    unittest.main()
