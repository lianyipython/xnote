# -*- coding:utf-8 -*-
# @author xupingmao
# @since 2021/12/04 15:35:23
# @modified 2022/04/05 21:15:18
# @filename dbutil_hash.py

from xutils import Storage
from xutils.db.dbutil_base import *
from xutils.db.encode import encode_str, decode_str

class LdbHashTable:
    """基于leveldb的哈希表结构
    注: LdbTable可以覆盖LdbHashTable的功能, 如果不考虑极致的性能, 建议使用LdbTable+索引的方式
    put -> LdbTable.update_by_id
    get -> LdbTable.get_by_id
    """

    def __init__(self, table_name, user_name = None, key_name = "_key"):
        check_table_name(table_name)

        self.table_name = table_name
        self.key_name = key_name

        self.prefix = table_name
        if user_name != None and user_name != "":
            self.prefix += ":" + user_name

        if self.prefix[-1] != ":":
            self.prefix += ":"

    def _check_key(self, key):
        if not isinstance(key, str):
            raise Exception("LdbHashTable_param_error: expect str key")

    def _check_value(self, obj):
        pass

    def build_key(self, key):
        return self.prefix + encode_str(key)

    def put(self, key, value, batch = None):
        """通过key来设置value，这个key是hash的key，不是ldb的key
        @param {string} key hash的key
        @param {object} value hash的value
        """
        self._check_key(key)
        self._check_value(value)

        row_key = self.build_key(key)
        
        if batch != None:
            batch.put(row_key, value)
        else:
            put(row_key, value)

    def get(self, key, default_value = None):
        """通过key来查询value，这个key是hash的key，不是ldb的key
        @param {string} key hash的key
        @param {object} default_value 如果值不存在，返回默认值
        """
        row_key = self.build_key(key)
        return get(row_key, default_value)

    def iter(self, offset = 0, limit = 20, reverse = False, filter_func = None):
        """hash表的迭代器
        @yield key, value
        """
        prefix_len = len(self.prefix)
        for key, value in prefix_iter(self.prefix, filter_func = filter_func, 
                offset = offset, limit = limit, reverse = reverse, include_key = True):
            yield decode_str(key[prefix_len:]), value

    def list(self, *args, **kw):
        return list(self.iter(*args, **kw))

    def dict(self, *args, **kw):
        result = Storage()
        for key, value in self.iter(*args, **kw):
            result[key] = value
        return result

    def delete(self, key, batch = None):
        row_key = self.build_key(key)

        if batch != None:
            batch.delete(row_key)
        else:
            delete(row_key)

    def count(self, prefix = None):
        if prefix != None:
            key_prefix = self.prefix + encode_str(prefix)
        else:
            key_prefix = self.prefix

        return count_table(key_prefix)
    
    def last(self):
        records = self.list(limit = 1, reverse = True)
        if len(records) > 0:
            return records[0]
        else:
            return None, None

