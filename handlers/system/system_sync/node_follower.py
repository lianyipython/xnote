# -*- coding:utf-8 -*-
# @author xupingmao
# @since 2022/02/12 18:13:41
# @modified 2022/02/26 18:55:14
# @filename node_follower.py

"""从节点管理"""

import time
import logging
import xconfig

from xutils import Storage
from xutils import textutil
from xutils import dbutil
from xutils import netutil
import xutils
from xutils.db.binlog import BinLog
from .node_base import NodeManagerBase
from .node_base import convert_follower_dict_to_list
from .node_base import CONFIG
from .system_sync_client import HttpClient


def filter_result(result, offset):
    data = []
    offset = "fs_sync_index:" + offset
    for item in result.data:
        if item.get("_key", "") == offset:
            # logging.debug("跳过offset:%s", offset)
            continue
        data.append(item)

    result.data = data
    return result


class Follower(NodeManagerBase):

    # PING的时间间隔，单位是秒
    # Leader侧的失效时间是1小时
    PING_INTERVAL = 600

    def __init__(self):
        self.follower_list = []
        self.leader_info = None
        self.ping_error = None
        self.ping_result = None
        self.admin_token = None
        self.last_ping_time = -1
        self.fs_index_count = -1
        # 同步完成的时间
        self.fs_sync_done_time = -1
        self._debug = False
        self.db_syncer = DBSyncer()

    def get_client(self):
        leader_host = self.get_leader_url()
        leader_token = self.get_leader_token()
        return HttpClient(leader_host, leader_token, self.admin_token)

    def get_node_id(self):
        return xconfig.get_global_config("system.node_id", "unknown_node_id")

    def get_leader_node_id(self):
        if self.leader_info != None:
            return self.leader_info.get("node_id")
        return "<unknown>"

    def get_current_port(self):
        return xconfig.get_global_config("system.port")
    
    def is_token_active(self):
        now = time.time()
        is_active = (now - self.last_ping_time) < self.PING_INTERVAL
        return self.admin_token != None and is_active

    def ping_leader(self):
        if self.is_token_active():
            return self.ping_result

        port = self.get_current_port()

        fs_sync_offset = CONFIG.get("fs_sync_offset", "")

        leader_host = self.get_leader_url()
        if leader_host != None:
            client = self.get_client()
            params = dict(port=port, fs_sync_offset=fs_sync_offset,
                          node_id=self.get_node_id())
            result_obj = client.get_stat(params)

            self.update_ping_result(result_obj)
            return result_obj

        return None

    def update_ping_result(self, result0):
        if result0 is None:
            logging.error("PING主节点:返回None")
            return

        result = Storage(**result0)
        if result.code != "success":
            self.ping_error = result.message
            logging.error("PING主节点失败:%s", self.ping_error)
            return

        logging.debug("PING主节点成功")

        self.ping_error = None
        self.ping_result = result
        follower_dict = result.get("follower_dict", {})
        self.follower_list = convert_follower_dict_to_list(follower_dict)
        self.leader_info = result.get("leader")
        self.last_ping_time = time.time()

        if len(self.follower_list) > 0:
            item = self.follower_list[0]
            self.admin_token = item.admin_token
            self.fs_index_count = item.fs_index_count

    def get_follower_list(self):
        return self.follower_list

    def get_leader_url(self):
        return CONFIG.get("leader.host")
    
    def get_leader_info(self):
        if self.ping_result != None:
            return self.ping_result.get("leader")
        return None

    def get_ping_error(self):
        return self.ping_error

    def need_sync(self):
        if self.fs_sync_done_time < 0:
            return True

        last_sync = time.time() - self.fs_sync_done_time
        return last_sync >= self.PING_INTERVAL

    def sync_files_from_leader(self):
        result = self.ping_leader()
        if result == None:
            logging.error("ping_leader结果为空")
            return

        if not self.need_sync():
            # logging.debug("没到SYNC时间")
            return

        client = self.get_client()
        # 先重试失败的任务
        client.retry_failed()

        offset = CONFIG.get("fs_sync_offset", "")
        offset = textutil.remove_head(offset, "fs_sync_index:")

        logging.debug("offset:%s", offset)
        result = client.list_files(offset)

        if result is None:
            logging.error("返回结果为空")
            return

        # 不需要包含offset的结果
        result = filter_result(result, offset)
        if len(result.data) == 0:
            logging.debug("返回文件列表为空")
            self.fs_sync_done_time = time.time()
            return

        max_offset = offset
        for item in result.data:
            item = Storage(**item)
            key = item._key
            key = textutil.remove_head(key, "fs_sync_index:")
            max_offset = max(max_offset, key)

        # logging.debug("result:%s", result)
        client.download_files(result)

        # offset可能不变
        logging.debug("result.sync_offset:%s", result.sync_offset)
        logging.debug("max_offset:%s", max_offset)

        if max_offset != offset:
            CONFIG.put("fs_sync_offset", max_offset)

        return result

    def get_sync_process(self):
        if self.fs_index_count < 0:
            return "-1"

        count = self.count_sync_done()
        if count == 0:
            return "0%"
        return "%.2f%%" % (count / self.fs_index_count * 100.0)

    def sync_for_home_page(self):
        return self.ping_leader() != None

    def get_fs_index_count(self):
        return self.fs_index_count

    def count_sync_done(self):
        return dbutil.count_table("fs_sync_index_copy")

    def count_sync_failed(self):
        return dbutil.count_table("fs_sync_index_failed")

    def reset_sync(self):
        CONFIG.put("fs_sync_offset", "")
        CONFIG.put("db_sync_offset", "")
        CONFIG.put("follower_db_sync_state", "full")
        self.fs_sync_done_time = -1

        db = dbutil.get_hash_table("fs_sync_index_copy")
        for key, value in db.iter(limit=-1):
            db.delete(key)

    def _sync_db_by_binlog(self, leader_host, leader_token, last_seq):
        assert isinstance(last_seq, int)
        params = dict(last_seq=str(last_seq))
        url = "{host}/system/sync/leader?p=list_binlog&token={token}".format(
            host=leader_host, token=leader_token)
        result = netutil.http_get(url, params=params)
        try:
            result_obj = textutil.parse_json(result)
        except:
            logging.error("解析json失败:%s", result)
            return
        message = self.db_syncer.sync_by_binlog(result_obj)
        assert message in ("sync_by_full", None)
        if message == "sync_by_full":
            self._sync_db_full(leader_host, leader_token, "")

    def _sync_db_full(self, leader_host, leader_token, last_key):
        params = dict(last_key=last_key, token=leader_token)
        url = "{host}/system/sync/leader?p=list_db".format(host=leader_host)
        result = netutil.http_get(url, params=params)

        if self._debug:
            print("\n\n_sync_db_full -------------\nresp:%s\n\n" % result)

        result_obj = textutil.parse_json(result)

        self.db_syncer.sync_by_full(result_obj, last_key)

    def sync_db_from_leader(self):
        leader_host = self.get_leader_url()
        if leader_host == None:
            return

        ping_result = self.ping_leader()
        if ping_result == None:
            logging.debug("ping_leader为空")
            return

        leader_token = self.get_leader_token()
        if leader_token == "":
            logging.debug("leader_token为空")
            return

        sync_state = self.db_syncer.get_db_sync_state()
        if sync_state == "binlog":
            last_seq = self.db_syncer.get_binlog_last_seq()
            self._sync_db_by_binlog(leader_host, leader_token, last_seq)
        else:
            last_key = self.db_syncer.get_db_last_key()
            self._sync_db_full(leader_host, leader_token, last_key)
    
    def is_at_full_sync(self):
        return self.db_syncer.get_db_sync_state() == "full"


class DBSyncer:

    def __init__(self):
        self._binlog = BinLog.get_instance()
    
    def get_table_by_key(self, key):
        table_name = key.split(":")[0]
        if dbutil.TableInfo.is_registered(table_name):
            return dbutil.get_table(table_name)
        return None
    
    def get_binlog_last_seq(self):
        return CONFIG.get("follower_binlog_last_seq", 0)

    def put_binlog_last_seq(self, last_seq):
        return CONFIG.put("follower_binlog_last_seq", last_seq)

    def get_db_sync_state(self):
        return CONFIG.get("follower_db_sync_state", "full")

    def put_db_sync_state(self, state):
        assert state in ("full", "binlog")
        CONFIG.put("follower_db_sync_state", state)
    

    def get_db_last_key(self):
        return CONFIG.get("follower_db_last_key", "")

    def put_db_last_key(self, last_key):
        CONFIG.put("follower_db_last_key", last_key)
    
    def put_and_log(self, key, value):
        assert key != None
        assert value != None
        done = False
        try:
            table = self.get_table_by_key(key)
            if table != None:
                table.update_by_key(key, value)
                done = True
        except:
            xutils.print_exc()
        
        if not done:
            batch = dbutil.create_write_batch()
            batch.put(key, value, check_table=False)
            self._binlog.add_log("put", key, value, batch = batch)
            batch.commit()
    
    def delete_and_log(self, key):
        assert key != None
        done = False
        try:
            table = self.get_table_by_key(key)
            if table != None:
                table.delete_by_key(key)
                done = True
        except:
            xutils.print_exc()

        if not done:
            batch = dbutil.create_write_batch()
            batch.delete(key)
            self._binlog.add_log("delete", key, None, batch = batch)
            batch.commit()

    def sync_by_binlog(self, result_obj):
        code = result_obj.get("code")

        if code == "success":
            self.handle_binlog(result_obj)
        elif code == "sync_broken":
            logging.error("同步binlog异常, 重新全量同步...")
            self.put_binlog_last_seq(0)
            self.put_db_sync_state("full")
            self.put_db_last_key("")
            return "sync_by_full"
        else:
            raise Exception("未知的code:%s" % code)


    def handle_binlog(self, result_obj):
        last_seq = self.get_binlog_last_seq()
        max_seq = last_seq
        data_list = result_obj.get("data")
        for data in data_list:
            seq = data.get("seq")
            assert isinstance(seq, int)

            if seq == last_seq:
                continue

            optype = data.get("optype")
            key = data.get("key")
            value = data.get("value")
            assert key != None
            if value == None:
                optype = "delete"

            if optype == "put":
                self.put_and_log(key, value)
            elif optype == "delete":
                self.delete_and_log(key)
            else:
                logging.error("未知的optype:%s", optype)

            max_seq = max(max_seq, seq)
        if max_seq != last_seq:
            self.put_binlog_last_seq(max_seq)
        else:
            logging.info("已经保持同步")

    def sync_by_full(self, result_obj, last_key):
        code = result_obj.get("code")
        if code == "success":
            data = result_obj.get("data")
            assert data != None, "data不能为空"
            if last_key == "":
                binlog_last_seq = data.get("binlog_last_seq")
                assert isinstance(binlog_last_seq, int)
                self.put_binlog_last_seq(binlog_last_seq)

            rows = data.get("rows")
            if not isinstance(rows, list):
                logging.error("resp:%s", result_obj)
                raise Exception("data.rows必须为list,当前类型(%s)" % type(rows))

            new_last_key = last_key
            for row in rows:
                key = row.get("key")
                value = row.get("value")
                assert key != None
                assert value != None
                if key == last_key:
                    continue
                
                self.put_and_log(key, value)
                new_last_key = key

            if new_last_key == last_key:
                self.put_db_sync_state("binlog")
            else:
                self.put_db_last_key(new_last_key)