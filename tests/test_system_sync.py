# -*- coding:utf-8 -*-
"""
@Author       : xupingmao
@email        : 578749341@qq.com
@Date         : 2022-05-28 22:28:31
@LastEditors  : xupingmao
@LastEditTime : 2022-07-02 11:16:24
@FilePath     : /xnote/tests/test_system_sync.py
@Description  : 描述
"""

from .a import *
import os
import xauth
from xutils import dbutil, fsutil
from xutils import textutil
from xutils import netutil
import xconfig

from . import test_base

app = test_base.init()
json_request = test_base.json_request
request_html = test_base.request_html
BaseTestCase = test_base.BaseTestCase

_config_db = dbutil.get_table("cluster_config", type="hash")


class LeaderNetMock:

    def http_get(self, url, charset=None, params=None):
        print("url:{url}, params:{params}".format(**locals()))

        if "get_stat" in url:
            return self.http_get_stat()

        if "list_db" in url:
            return self.http_list_db(url)

        if "list_binlog" in url:
            return self.http_list_binlog(url)

        raise Exception("unsupported url:%s" % url)

    def http_get_stat(self):
        result = dict(code="success",
                      leader=dict(
                          node_id="master",
                          fs_index_count=666,
                          binlog_last_seq=333))
        return textutil.tojson(result)

    def http_list_db(self, url):
        from urllib.parse import urlparse, parse_qs, unquote

        result = urlparse(url)
        params = parse_qs(result.query)
        last_key = params.get("last_key")

        if last_key != None:
            last_key = last_key[0]
            last_key == unquote(last_key)

        if last_key == "my_config:test:key2":
            result = dict(code="success",
                          data=dict(
                              binlog_last_seq=2345,
                              rows=[]
                          ))
        else:
            result = dict(code="success",
                          data=dict(
                              binlog_last_seq=1234,
                              rows=[
                                  {
                                      "key": "my_config:test:key1",
                                      "value": "value1"
                                  },
                                  {
                                      "key": "my_config:test:key2",
                                      "value": "value2"
                                  }
                              ]))
        return textutil.tojson(result)

    def http_list_binlog(self, url):
        return """
        {
            "code": "success",
            "data": [
                {
                    "optype": "delete",
                    "seq": 2345,
                    "key": "my_table:2"
                },
                {
                    "optype": "put",
                    "seq": 2346,
                    "key": "my_table:1",
                    "value": {"name":"Ada", "age":20}
                }
            ]
        }
        """


class TestSystemSync(BaseTestCase):

    def test_system_sync(self):
        admin_token = xauth.get_user_by_name("admin").token
        _config_db.put("leader.token", admin_token)
        self.check_OK("/system/sync?p=home")
        self.check_OK("/system/sync?p=get_stat&token=" + admin_token)

    def test_system_get_stat(self):
        admin_token = xauth.get_user_by_name("admin").token
        _config_db.put("leader.token", admin_token)
        _config_db.put("leader.host", "http://127.0.0.1:3333")
        resp = json_request("/system/sync?p=get_stat&token=" + admin_token)

        print("get_stat resp:{resp}".format(resp=resp))
        self.assertEqual("success", resp["code"])
        self.assertIsNotNone(resp["leader"])
        self.assertIsNotNone(resp["follower_dict"])

    def test_system_ping(self):
        netutil.set_net_mock(LeaderNetMock())
        try:
            admin_token = xauth.get_user_by_name("admin").token
            _config_db.put("leader.token", admin_token)
            _config_db.put("leader.host", "http://127.0.0.1:3333")
            resp = json_request("/system/sync?p=ping&token=" + admin_token)
            print("ping resp:{resp}".format(resp=resp))
            self.assertEqual("success", resp["code"])
            self.assertIsNotNone(resp["data"])
        finally:
            netutil.set_net_mock(None)

    def test_system_sync_db_from_leader(self):
        netutil.set_net_mock(LeaderNetMock())

        try:
            from handlers.system.system_sync.system_sync_controller import FOLLOWER
            admin_token = xauth.get_user_by_name("admin").token
            _config_db.put("leader.token", admin_token)
            _config_db.put("leader.host", "http://127.0.0.1:3333")

            FOLLOWER._debug = True

            FOLLOWER.sync_db_from_leader()

            db_syncer = FOLLOWER.db_syncer

            self.assertEqual(db_syncer.get_binlog_last_seq(), 1234)

            FOLLOWER.sync_db_from_leader()
            self.assertEqual(db_syncer.get_db_sync_state(), "binlog")
            self.assertEqual(db_syncer.get_binlog_last_seq(), 1234)

            # 同步binlog
            FOLLOWER.sync_db_from_leader()
            self.assertEqual(db_syncer.get_binlog_last_seq(), 2346)
        finally:
            netutil.set_net_mock(None)



    def test_system_sync_db_broken(self):
        from handlers.system.system_sync.system_sync_controller import FOLLOWER
        admin_token = xauth.get_user_by_name("admin").token
        _config_db.put("leader.token", admin_token)
        _config_db.put("leader.host", "http://127.0.0.1:3333")

        FOLLOWER._debug = True
        FOLLOWER.db_syncer.put_db_sync_state("binlog")
        result = """
        {
            "code": "sync_broken"
        }
        """
        result_obj = textutil.parse_json(result)
        FOLLOWER.db_syncer.sync_by_binlog(result_obj)
    
    def test_is_token_active(self):
        from handlers.system.system_sync.system_sync_controller import FOLLOWER
        result = """
        {
            "code": "success",
            "timestamp": 1654227462,
            "system_version": "v2.9-dev-2022.06.03",
            "admin_token": "fake-token",
            "fs_index_count": 10960,
            "follower_dict": {
                "127.0.0.1:2222#follower": {
                    "ping_time_ts": 1654227411.8821118,
                    "client_id": "127.0.0.1:2222#follower",
                    "connected_time": "2022-06-03 11:20:16",
                    "connected_time_ts": 1654226416.2453492,
                    "ping_time": "2022-06-03 11:36:51",
                    "fs_sync_offset": "00000001654174803260#/data/path/to/file.txt",
                    "fs_index_count": 10960,
                    "admin_token": "fake-token",
                    "node_id": "follower",
                    "url": "127.0.0.1:2222#follower"
                }
            }
        }
        """
        result_obj = textutil.parse_json(result)
        FOLLOWER.update_ping_result(result_obj)
        self.assertTrue(FOLLOWER.is_token_active())

    def test_build_fs_sync_index(self):
        self.check_OK("/system/sync?p=build_index")
    
    def test_list_files(self):
        from handlers.system.system_sync import system_sync_indexer

        testfile_1 = os.path.join(xconfig.UPLOAD_DIR, "fs_sync_test_01.txt")
        testfile_2 = os.path.join(xconfig.UPLOAD_DIR, "fs_sync_test_02.txt")
        fsutil.touch(testfile_1)
        fsutil.touch(testfile_2)

        manager = system_sync_indexer.FileSyncIndexManager()
        manager.build_full_index()
        result = manager.list_files(None)
        self.assertTrue(len(result) > 0)