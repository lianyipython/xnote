# -*- coding:utf-8 -*-
"""
@Author       : xupingmao
@email        : 578749341@qq.com
@Date         : 2022-07-15 23:08:49
@LastEditors  : xupingmao
@LastEditTime : 2022-07-18 22:47:25
@FilePath     : /xnote/handlers/note/dao_category.py
@Description  : 描述
"""

from xutils import Storage, dateutil
from xutils import fsutil
from xutils import dbutil
import xutils

from .dao import list_group

dbutil.register_table("note_category", "笔记类目", category="note",
                      check_user=True, user_attr="user_name")

_db = dbutil.get_table("note_category")
_cat_config = fsutil.load_prop_config("config/note/category.properties")


def upsert_category(user_name, category):
    assert user_name != None
    assert category != None
    assert category.user_name != None

    category.mtime = dateutil.format_datetime()

    if category._id == None:
        category.ctime = dateutil.format_datetime()

    return _db.update_by_id(category.code, category, user_name=user_name)


def list_category(user_name):
    assert user_name != None
    assert isinstance(user_name, str)

    cat_dict = dict()
    for key in _cat_config:
        value = _cat_config[key]
        cat_dict[key] = Storage(code=key, name=value,
                                user_name=user_name, group_count=0)

    group_count = 0
    for item in _db.list(user_name=user_name, offset=0, limit=-1):
        cat_dict[item.code] = item
        group_count += (item.group_count or 0)

    result = [Storage(code="all", name="全部", group_count=group_count)]
    for key in sorted(cat_dict.keys()):
        item = cat_dict.get(key)
        result.append(item)
    return result


def get_category_by_code(user_name, code):
    assert user_name != None
    assert code != None
    for item in list_category(user_name):
        if item.code == code:
            return item
    return None


@xutils.async_func_deco()
def refresh_category_count(user_name, code):
    if code == "all":
        return

    with dbutil.get_write_lock(user_name):
        cat = get_category_by_code(user_name, code)
        if cat != None:
            cat.group_count = list_group(
                user_name, category=code, count_only=True)
            upsert_category(user_name, cat)


xutils.register_func("note.list_category", list_category)
