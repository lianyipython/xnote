# -*- coding:utf-8 -*-
# @author xupingmao
# @since 2021/12/04 21:22:40
# @modified 2022/04/16 08:53:11
# @filename dbutil_table.py

import time
from urllib.parse import quote
from xutils import Storage
from xutils.db.dbutil_base import *
from xutils.db.dbutil_table_index import TableIndex
from xutils.db.encode import decode_str, encode_index_value, encode_str, clean_value_before_update
from xutils.db.binlog import BinLog

register_table("_id", "系统ID表")
MAX_ID_KEY = "_id:max_id"

register_table("_index", "通用索引")
register_table("_meta", "表元信息")


class TableValidator:

    def __init__(self, table_name, has_user_name=False):
        pass

    def validate_key(self, key, user_name=None):
        pass


class LdbTable:
    """基于leveldb的表, 比较常见的是以下2种
    * key = prefix:record_id           全局数据库
    * key = prefix:user_name:record_id 用户维度数据

    字段说明: 
    * prefix    代表的是功能类型，比如猫和狗是两种不同的动物，锤子和手机是两种
                不同的工具
    * user_name 代表用户名，比如张三和李四，也可以是其他类型的对象ID，比如笔记ID
    * record_id 代表一条记录的ID，从属于user_name

    注: record_id建议使用全局ID，尽量避免多级主键，如果使用多级主键，移动记录会
        比较麻烦，要重新构建主键
    """

    def __init__(self, table_name, user_name=None):
        # 参数检查
        check_table_name(table_name)
        table_info = get_table_info(table_name)
        assert table_info != None

        self.table_name = table_name
        self.key_name = "_key"
        self.id_name = "_id"
        self.prefix = table_name
        self.user_name = user_name
        self.index_names = table_info.get_index_names()
        self._need_check_user = table_info.check_user
        self.user_attr = None
        if table_info.check_user:
            if table_info.user_attr == None:
                raise Exception("table({table_name}).user_attr can not be None".format(
                    table_name=table_name))
            self.user_attr = table_info.user_attr

        self.binlog = BinLog.get_instance()
        self.binlog_enabled = True
        self.indexes = self._build_indexes(table_info)

        if user_name != None:
            assert user_name != ""
            self.prefix += ":" + user_name

        if self.prefix[-1] != ":":
            self.prefix += ":"
    
    def _build_indexes(self, table_info):
        indexes = []
        index_dict = IndexInfo.get_table_index_dict(self.table_name)
        if index_dict != None:
            for index_name in index_dict:
                index_info = index_dict[index_name]
                indexes.append(TableIndex(self.table_name, index_info.index_name, table_info.user_attr,
                                        check_user=table_info.check_user,
                                        index_type=index_info.index_type))
        return indexes

    def set_binlog_enabled(self, enabled=True):
        self.binlog_enabled = enabled

    def _build_key(self, *argv):
        return self.prefix + self._build_key_no_prefix(*argv)

    def _build_key_no_prefix(self, *argv):
        return ":".join(filter(None, argv))

    def _get_key_from_obj(self, obj):
        validate_dict(obj, "obj is not dict")
        return obj.get(self.key_name)

    def _get_id_from_obj(self, obj):
        key = self._get_key_from_obj(obj)
        return key.rsplit(":", 1)[-1]

    def _get_id_from_key(self, key):
        return decode_str(key.rsplit(":", 1)[-1])

    def _get_user_from_key(self, key):
        parts = key.split(":")
        assert len(parts) == 3, parts
        return parts[1]

    def _format_value(self, key, value):
        if not isinstance(value, dict):
            value = Storage(_raw=value)

        value[self.key_name] = key
        value[self.id_name] = self._get_id_from_key(key)
        if self.user_attr != None:
            user = value.get(self.user_attr)
            parts = key.split(":")
            if user == None and len(parts) == 3:
                value[self.user_attr] = parts[1]
        return value

    def _convert_to_db_row(self, obj):
        obj_copy = dict(**obj)
        clean_value_before_update(obj_copy)
        return obj_copy

    def _create_increment_id(self, start_id=None):
        if start_id != None:
            assert start_id > 0

        with get_write_lock():
            last_id = get(MAX_ID_KEY)
            if last_id is None:
                if start_id != None:
                    last_id = start_id - 1
                else:
                    last_id = int(time.time() * 1000)
            else:
                last_id += 1
            put(MAX_ID_KEY, last_id)
            return str(last_id)

    def _create_new_id(self, id_type="uuid", id_value=None):
        if id_type == "uuid":
            validate_none(id_value, "invalid id_value")
            return xutils.create_uuid()

        if id_type == "timeseq":
            validate_none(id_value, "invalid id_value")
            return timeseq()

        if id_type == "auto_increment":
            validate_none(id_value, "invalid id_value")
            return self._create_increment_id()

        if id_value != None:
            validate_none(id_type, "invalid id_type")
            return id_value

        raise Exception("unknown id_type:%s" % id_type)

    def _check_before_delete(self, key):
        if not key.startswith(self.prefix):
            raise Exception("invalid key:%s" % key)

    def _check_value(self, obj):
        if not isinstance(obj, dict):
            raise Exception("invalid obj:%r, expected dict" % obj)

    def _check_key(self, key):
        if not key.startswith(self.prefix):
            raise Exception("invalid key:(%s), prefix:(%s)" %
                            (key, self.prefix))

    def _check_index_name(self, index_name):
        validate_str(index_name, "invalid index_name:%r" % index_name)
        if index_name not in self.index_names:
            raise Exception("invalid index_name:%r" % index_name)

    def _check_user_name(self, user_name):
        user_name = self.user_name or user_name
        if self._need_check_user:
            validate_str(user_name, "invalid user_name:{!r}", user_name)

    def _get_prefix(self, user_name=None):
        user_name = self.user_name or user_name
        if user_name is None:
            return self.table_name + ":"
        else:
            return self.table_name + ":" + user_name + ":"

    def _get_index_prefix(self, index_name, user_name=None):
        self._check_index_name(index_name)
        self._check_user_name(user_name)

        index_prefix = "_index$%s$%s" % (self.table_name, index_name)
        return self._build_key_no_prefix(index_prefix, self.user_name or user_name)

    def _update_index(self, old_obj, new_obj, batch, force_update=False):
        for index in self.indexes:
            index.update_index(old_obj, new_obj, batch, force_update)

    def _delete_index(self, old_obj, batch):
        for index in self.indexes:
            index.delete_index(old_obj, batch)

    def _put_obj(self, key, obj, sync=False):
        # ~~写redo-log，启动的时候要先锁定检查redo-log，恢复异常关闭的数据~~
        # 不需要重新实现redo-log，直接用leveldb的批量处理功能即可
        # 使用leveldb的批量操作可以确保不会读到未提交的数据
        batch = create_write_batch()
        with get_write_lock(key):
            old_obj = get(key)
            self._format_value(key, obj)
            batch.put(key, self._convert_to_db_row(obj))
            self._update_index(old_obj, obj, batch)
            if self.binlog_enabled:
                self.binlog.add_log("put", key, obj, batch=batch)
            # 更新批量操作
            batch.commit(sync)

    def is_valid_key(self, key=None, user_name=None):
        if user_name is None:
            return key.startswith(self.prefix)
        else:
            return key.startswith(self.prefix + user_name)

    def get_by_id(self, row_id, default_value=None, user_name=None):
        validate_str(row_id, "invalid row_id:{!r}", row_id)
        self._check_user_name(user_name)
        row_id = encode_str(row_id)
        key = self._build_key(user_name, row_id)
        return self.get_by_key(key, default_value)

    def get_by_key(self, key, default_value=None):
        if key == "":
            return None
        self._check_key(key)
        value = get(key, default_value)
        if value is None:
            return None

        return self._format_value(key, value)

    def insert(self, obj, id_type="timeseq", id_value=None):
        """插入新数据
        @param {object} obj 插入的对象
        @param {string} id_type id类型
        """
        self._check_value(obj)
        id_value = self._create_new_id(id_type, id_value)

        user_name = None
        if self._need_check_user:
            user_name = obj.get(self.user_attr)

        key = self._build_key(user_name, id_value)

        obj[self.key_name] = key
        obj[self.id_name] = id_value

        self._put_obj(key, obj)
        return key

    def insert_by_user(self, user_name, obj, id_type="timeseq"):
        """@deprecated 定义user_attr之后使用insert即可满足
        指定用户名插入数据
        """
        validate_str(user_name, "invalid user_name")
        self._check_value(obj)

        id_value = self._create_new_id(id_type)
        key = self._build_key(user_name, id_value)
        self._put_obj(key, obj)
        return key

    def update(self, obj):
        """从`obj`中获取主键`key`进行更新"""
        self._check_value(obj)

        obj_key = self._get_key_from_obj(obj)
        self._check_key(obj_key)

        update_obj = self._convert_to_db_row(obj)

        self._put_obj(obj_key, update_obj)

    def update_by_id(self, id, obj, user_name=None):
        """通过ID进行更新，如果key包含用户，必须有user_name(初始化定义或者传入参数)"""
        assert xutils.is_str(id)
        id = encode_str(id)
        self._check_user_name(user_name)
        key = self._build_key(user_name, id)
        self.update_by_key(key, obj)

    def update_by_key(self, key, obj):
        """直接通过`key`进行更新"""
        self._check_key(key)
        self._check_value(obj)

        update_obj = self._convert_to_db_row(obj)
        self._put_obj(key, update_obj)

    def rebuild_single_index(self, obj, user_name=None):
        self._check_value(obj)
        self._check_user_name(user_name)

        key = self._get_key_from_obj(obj)
        batch = create_write_batch()
        with get_write_lock(key):
            old_obj = get(key)
            self._format_value(key, obj)
            self._update_index(old_obj, obj, batch,
                               force_update=True)
            # 更新批量操作
            batch.commit()

    def repair_index(self):
        repair = TableIndexRepair(self)
        repair.repair_index()

    def delete(self, obj):
        obj_key = self._get_key_from_obj(obj)
        self.delete_by_key(obj_key)

    def delete_by_id(self, id, user_name = None):
        validate_str(id, "delete_by_id: id is not str")
        key = self._build_key(user_name, id)
        self.delete_by_key(key)

    def delete_by_key(self, key, user_name=None):
        validate_str(key, "delete_by_key: invalid key")
        self._check_before_delete(key)

        old_obj = get(key)
        if old_obj is None:
            return

        self._format_value(key, old_obj)
        with get_write_lock(key):
            batch = create_write_batch()
            self._delete_index(old_obj, batch)
            # 更新批量操作
            batch.delete(key)
            if self.binlog_enabled:
                self.binlog.add_log("delete", key, old_obj, batch=batch)
            batch.commit()

    def iter(self, offset=0, limit=20, reverse=False, key_from=None,
             filter_func=None, fill_cache=False, user_name=None):
        """返回一个遍历的迭代器
        @param {int} offset 返回结果下标开始
        @param {int} limit  返回结果最大数量
        @param {bool} reverse 返回结果是否逆序
        @param {str} key_from 开始的key，这里是相对的key，也就是不包含table_name
        @param {func} filter_func 过滤函数
        """
        if key_from == "":
            key_from = None

        if key_from != None:
            key_from = self._build_key(key_from)

        if user_name != None:
            prefix = self.table_name + ":" + user_name
        else:
            prefix = self.prefix

        for key, value in prefix_iter(prefix, filter_func, offset, limit,
                                      reverse=reverse, include_key=True, key_from=key_from,
                                      fill_cache=fill_cache):
            yield self._format_value(key, value)

    def list(self, *args, **kw):
        result = []
        for value in self.iter(*args, **kw):
            result.append(value)
        return result

    def get_first(self, filter_func=None):
        """读取第一个满足条件的数据"""
        result = self.list(limit=1, filter_func=filter_func)
        if len(result) > 0:
            return result[0]
        else:
            return None

    def get_last(self, filter_func=None):
        """读取最后一个满足条件的数据"""
        result = self.list(limit=1, reverse=True, filter_func=filter_func)
        if len(result) > 0:
            return result[0]
        else:
            return None

    def list_by_user(self, user_name, offset=0, limit=20, reverse=False):
        return self.list(offset=offset, limit=limit, reverse=reverse, user_name=user_name)

    def list_by_func(self, user_name, filter_func=None,
                     offset=0, limit=20, reverse=False):
        return self.list(offset=offset, limit=limit, reverse=reverse,
                         filter_func=filter_func, user_name=user_name)

    def create_index_map_func(self, filter_func, index_type="ref"):
        def map_func_for_copy(key, value):
            obj_key = value.get("key")
            obj_value = value.get("value")
            self._format_value(obj_key, obj_value)
            if isinstance(obj_value, dict):
                obj_value = Storage(**obj_value)

            if filter_func is None:
                return obj_value
            else:
                # 这里应该是使用obj参数来过滤
                is_match = filter_func(obj_key, obj_value)
                if is_match:
                    return obj_value
                return None
    
        def map_func_for_ref(key, value):
            # 先判断实例是否存在
            # 普通的引用索引
            obj = self.get_by_key(value)
        
            if obj is None:
                # 异步 delete(key)
                logging.warning("invalid key:(%s)", key)
                return None

            # 检查key是否匹配
            obj_id = key.rsplit(":", 1)[-1]
            key_obj_id_temp = self._get_id_from_obj(obj)
            key_obj_id = quote(key_obj_id_temp)
            if obj_id != key_obj_id:
                logging.warning(
                    "invalid obj_id:(%s), obj_id:(%s)", obj_id, key_obj_id)
                return None

            # 用于调试
            # setattr(obj, "_idx_key", key)

            if filter_func is None:
                return obj
            else:
                # 这里应该是使用obj参数来过滤
                is_match = filter_func(key, obj)
                if is_match:
                    return obj
                return None
        
        if index_type == "copy":
            return map_func_for_copy
        
        return map_func_for_ref
        

    def count_by_index(self, index_name, filter_func=None, index_value=None):
        validate_str(index_name, "index_name can not be empty")
        index_info = IndexInfo.get_table_index_info(self.table_name, index_name)
        if index_info == None:
            raise Exception("index not found: %s", index_name)

        if index_value != None:
            index_value = encode_index_value(index_value)
            prefix = self._get_index_prefix(index_name) + ":" + index_value
        else:
            prefix = self._get_index_prefix(index_name)

        map_func = self.create_index_map_func(filter_func, index_type = index_info.index_type)
        return prefix_count(prefix, map_func=map_func)

    def list_by_index(self, index_name, filter_func=None,
                      offset=0, limit=20, reverse=False,
                      index_value=None):
        """通过索引查询结果列表
        @param {str}  index_name 索引名称
        @param {func} filter_func 过滤函数
        @param {int}  offset 开始索引
        @param {int}  limit  返回记录限制
        @param {bool} reverse 是否逆向查询
        """
        validate_str(index_name, "index_name can not be empty")
        index_info = IndexInfo.get_table_index_info(self.table_name, index_name)
        if index_info == None:
            raise Exception("index not found: %s", index_name)

        if isinstance(index_value, dict):
            # TODO: 参考 mongodb 的 {$gt: 20} 这种格式的
            raise NotImplementedError("暂未实现")
        elif index_value != None:
            index_value = encode_index_value(index_value)
            prefix = self._get_index_prefix(
                index_name) + ":" + index_value + ":"
        else:
            prefix = self._get_index_prefix(index_name)

        map_func = self.create_index_map_func(filter_func, index_type = index_info.index_type)
        return list(prefix_iter(prefix, offset=offset, limit=limit,
                                map_func=map_func,
                                reverse=reverse, include_key=False))

    def first_by_index(self, *args, **kw):
        kw["limit"] = 1
        result = self.list_by_index(*args, **kw)
        if len(result) > 0:
            return result[0]
        return None

    def count(self, filter_func=None, user_name=None, id_prefix=None):
        if filter_func is None:
            prefix = self._get_prefix(user_name=user_name)
        else:
            prefix = self._get_prefix(user_name=user_name)

        if id_prefix != None:
            prefix += encode_str(id_prefix)

        return prefix_count(prefix, filter_func)

    def count_by_user(self, user_name):
        return self.count(user_name=user_name)

    def count_by_func(self, user_name, filter_func):
        assert filter_func != None, "[count_by_func.assert] filter_func != None"
        return self.count(user_name=user_name, filter_func=filter_func)
    
    def drop_index(self, index_name):
        for index in self.indexes:
            if index.index_name == index_name:
                index.drop()


class PrefixedDb(LdbTable):
    """plyvel中叫做prefixed_db"""
    pass


class TableIndexRepair:
    """表索引修复工具，不是标准功能，所以抽象到一个新的类里面"""

    def __init__(self, db):
        assert isinstance(db, LdbTable)
        self.db = db

    def repair_index(self):
        db = self.db

        # 先删除无效的索引，这样速度更快
        for name in db.index_names:
            self.delete_invalid_index(name)

        for value in db.iter(limit=-1):
            if db._need_check_user:
                key = value._key
                assert xutils.is_str(key)
                try:
                    table_name, user_name, id = key.split(":")
                    user_name = decode_str(user_name)
                except ValueError:
                    logging.error("invalid record key: %s", key)
                    continue
                db.rebuild_single_index(value, user_name=user_name)
            else:
                db.rebuild_single_index(value)

    def do_delete(self, key):
        logging.info("Delete {%s}", key)

        if not key.startswith("_index$"):
            logging.warning("Invalid index key:(%s)", key)
            return
        delete(key)

    def delete_invalid_index(self, index_name):
        db = self.db
        index_prefix = "_index$%s$%s" % (db.table_name, index_name)

        for old_key, record_key in prefix_iter(index_prefix, include_key=True):
            record = get(record_key)
            if record is None:
                logging.debug("empty record, key:(%s), record_id:(%s)",
                              old_key, record_key)
                self.do_delete(old_key)
                continue

            user_name = None
            index_value = getattr(record, index_name)
            record_id = db._get_id_from_key(record_key)

            if db._need_check_user:
                try:
                    table_name, user_name, id = record_key.split(":")
                    user_name = decode_str(user_name)
                except:
                    logging.error("invalid key: (%s)", record_key)
                    continue

            prefix = db._get_index_prefix(index_name, user_name)
            new_key = db._build_key_no_prefix(
                prefix, encode_index_value(index_value), record_id)

            if new_key != old_key:
                logging.debug("index dismatch, key:(%s), record_id:(%s), correct_key:(%s)",
                              old_key, record_key, new_key)
                self.do_delete(old_key)


def insert(table_name, obj_value, sync=False):
    """往指定表里面插入一条新记录"""
    db = LdbTable(table_name)
    with get_write_lock(table_name):
        for i in range(10):
            new_id = db._create_increment_id(start_id=1)
            old_value = db.get_by_id(new_id)
            if old_value != None:
                logging.warning("id conflict, table:%s, id:%s",
                                table_name, new_id)
                continue
            db.update_by_id(new_id, obj_value)
            return new_id
        raise DBException("insert conflict")
