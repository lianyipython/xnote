# -*- coding:utf-8 -*-
"""
@Author       : xupingmao
@email        : 578749341@qq.com
@Date         : 2022-06-26 10:49:13
@LastEditors  : xupingmao
@LastEditTime : 2022-06-26 11:24:39
@FilePath     : /xnote/handlers/note/note_checklist.py
@Description  : 清单列表
"""
import xauth
import xtemplate
import xutils
from xutils.base import Storage

from .dao import get_by_id as get_note_by_id
from .dao import list_path


class ChecklistSearchHandler:

    @xauth.login_required()
    def GET(self):
        note_id = xutils.get_argument("note_id", "")
        note_detail = get_note_by_id(note_id)
        user_name = xauth.current_name()

        if note_detail == None:
            raise Exception("笔记不存在")
        if note_detail.creator != user_name and not note_detail.is_public:
            raise Exception("无访问权限")

        kw = Storage()
        kw.search_type = "checklist"
        kw.search_ext_dict = dict(note_id = note_id)
        kw.comment_list_type = "search"
        kw.pathlist = list_path(note_detail)
        kw.file = note_detail
        kw.show_checklist_search = True

        return xtemplate.render("note/page/detail/checklist_detail.html", **kw)


xurls = (
    r"/note/checklist/search", ChecklistSearchHandler,
)
