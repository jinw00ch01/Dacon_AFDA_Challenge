"""Range correctness matters: reject wrong bytes before accepting video assets."""
import io
import re
import unittest
from unittest.mock import patch
import zipfile

from scripts import fetch_comma_subset as module


class Response(io.BytesIO):
    status=206

    def __init__(self,data,header):
        super().__init__(data)
        self.headers={'Content-Range':header}


class RemoteZipTests(unittest.TestCase):
    def setUp(self):
        self.previous=module.RemoteZip.transferred
        module.RemoteZip.transferred=0

    def tearDown(self):
        module.RemoteZip.transferred=self.previous

    def test_zip_members_across_range_boundaries(self):
        buffer=io.BytesIO()
        content=bytes(range(256))*9
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('video.hevc',content)
        data=buffer.getvalue()
        def request(url,headers):
            start,end=map(int,re.search(r'bytes=(\d+)-(\d+)',headers['Range']).groups())
            return Response(data[start:end+1],f'bytes {start}-{end}/{len(data)}')
        with patch.object(module,'request',request):
            remote=module.RemoteZip({'path':'test.zip','size':len(data)})
            remote.block_size=64
            with zipfile.ZipFile(remote) as z:
                self.assertEqual(z.read('video.hevc'),content)

    def test_wrong_range_is_rejected(self):
        with patch.object(module,'request',lambda *args:Response(b'bad','bytes 1-3/4')),patch.object(module.time,'sleep'):
            remote=module.RemoteZip({'path':'test.zip','size':4})
            with self.assertRaisesRegex(ValueError,'exact requested range'):
                remote.read(4)

    def test_budget_stops_before_network_request(self):
        remote=module.RemoteZip({'path':'test.zip','size':100})
        remote.max_transfer=1
        with patch.object(module,'request') as request:
            with self.assertRaisesRegex(RuntimeError,'budget'):
                remote.read(10)
            request.assert_not_called()


if __name__=='__main__':
    unittest.main()
