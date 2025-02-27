# -*- coding:utf-8 -*-  
# Created by xupingmao on 2016/10
# @modified 2022/02/26 11:27:37
"""System functions"""
import os
import os

import xconfig
import xtemplate
import xutils
import xauth
import xmanager
import xtables
import web
from xutils import cacheutil
from xutils import Storage
from xtemplate import T

def link(name, url, user = None, icon = "cube"):
    return Storage(name = name, url = url, link = url, user = user, icon = icon)

def admin_link(name, url, icon = "cube"):
    return link(name, url, "admin", icon)

def user_link(name, url, icon = "cube"):
    return Storage(name = name, url = url, link = url, user = None, is_user = True, icon = icon)

def guest_link(name, url, icon = "cube"):
    return Storage(name = name, url = url, link = url, user = None, is_guest = True, icon = icon)

def public_link(name, url, icon = "cube"):
    return Storage(name = name, url = url, link = url, user = None, is_public = True, icon = icon)

SYS_TOOLS = [
    user_link("设置",   "/system/settings", "cog"),
    public_link("关于", "/code/wiki/README.md", "info-circle"),
    user_link("退出", "/logout", "sign-out"),
    guest_link("登录", "/login", "sign-in"),
    admin_link("文件",       "/fs_list", "file"),
    admin_link("脚本",    "/fs_link/scripts"),
    admin_link("定时任务",   "/system/crontab", "clock-o"),
    admin_link("事件注册", "/system/event"),
    admin_link("线程管理", "/system/thread_info"),
    admin_link("Menu_User",   "/system/user/list", "users"),
    admin_link("Menu_Log",    "/system/log"),
    admin_link("Menu_Refresh",  "/system/reload", "refresh"),
    admin_link("Menu_Modules",  "/system/modules_info"),
    admin_link("Menu_Configure", "/code/edit?type=script&path=" + str(xconfig.INIT_SCRIPT)),
    admin_link("Menu_CSS", "/code/edit?type=script&path=user.css"),
    admin_link("Menu_Plugin",   "/plugins_list", "cogs"),
    admin_link("Shell",    "/tools/shell", "terminal")
] 

NOTE_TOOLS = [
    user_link("搜索历史", "/search", "history"),

    # 笔记
    user_link("最近更新",      "/note/recent_edit", "folder"),
    user_link("最近创建",      "/note/recent_created", "folder"),
    user_link("最近查看",       "/note/recent_viewed", "folder"),
    user_link("根目录", "/note/group", "folder"),
    user_link("书架", "/note/category", "book"),
    user_link("标签列表", "/note/taglist", "tags"),
    user_link("时光轴", "/note/timeline"),
    user_link("词典", "/note/dict"),

    # 提醒
    user_link("待办",  "/message?tag=task", "calendar-check-o"),
    user_link("日历", "/message/calendar", "calendar"),
    user_link("上传管理", "/fs_upload", "upload"),
    user_link("数据统计", "/note/stat", "bar-chart"),
    user_link("笔记索引", "/note/index", "th-large"),
] 

DATA_TOOLS = [
    admin_link("数据迁移",  "/system/db_migrate", "database"),
    admin_link("SQLite", "/tools/sql", "database"),
    admin_link("leveldb", "/system/db_scan", "database")
]

# 所有功能配置
xconfig.MENU_LIST = [
    Storage(name = "System", children = SYS_TOOLS, need_login = True),
    Storage(name = "Note", children = NOTE_TOOLS, need_login = True),
    Storage(name = "数据管理", children = DATA_TOOLS, need_login = True),
]

xconfig.NOTE_OPTIONS = [
    link("New_Note", "/note/add"),
    link("Recent Updated", "/note/recent_edit"),
    link("Recent Created", "/note/recent_created"),
    link("Recent View",  "/note/recent_viewed"),
    link("Public",   "/note/public"),
    link("Tag List", "/note/taglist"),
]

@xutils.cache(expire=60)
def get_tools_config(user):
    db  = xtables.get_storage_table()
    user_config = db.select_first(where=dict(key="tools", user=user))
    return user_config


                
class IndexHandler:

    def GET(self):
        user_name = xauth.current_name()
        menu_list = []

        def filter_link_func(link):
            if link.is_guest:
                return user_name is None
            if link.is_user:
                return user_name != None
            if link.user is None:
                return True
            return link.user == user_name

        for category in xconfig.MENU_LIST:
            children = category.children
            if len(children) == 0:
                continue
            children = list(filter(filter_link_func, children))
            menu_list.append(Storage(name = category.name, children = children))

        return xtemplate.render("system/page/system.html",
            html_title       = "系统",
            Storage          = Storage,
            os               = os,
            user             = xauth.get_current_user(),
            menu_list = menu_list,
            customized_items = []
        )

class AdminHandler:

    @xauth.login_required("admin")
    def GET(self):
        return xtemplate.render("system/page/system_admin.html")

class ReloadHandler:

    @xauth.login_required("admin")
    def GET(self):
        # autoreload will load new handlers
        import web

        runtime_id = xutils.get_argument("runtime_id")
        if runtime_id == xconfig.RUNTIME_ID:
            # autoreload.reload()
            xmanager.restart()
            raise web.seeother("/system/index")
        else:
            return dict(code = "success", status = "running")

    def POST(self):
        return self.GET()

class UserCssHandler:

    def GET(self):
        web.header("Content-Type", "text/css")
        environ = web.ctx.environ
        path = os.path.join(xconfig.SCRIPTS_DIR, "user.css")

        if not xconfig.DEBUG:
            web.header("Cache-Control", "max-age=3600")

        if not os.path.exists(path):
            return b''
        
        etag = '"%s"' % os.path.getmtime(path)
        client_etag = environ.get('HTTP_IF_NONE_MATCH')
        web.header("Etag", etag)
        if etag == client_etag:
            web.ctx.status = "304 Not Modified"
            return b'' # 其实webpy已经通过yield空bytes来避免None
        return xutils.readfile(path)
        # return xconfig.get("USER_CSS", "")

class UserJsHandler:

    def GET(self):
        web.header("Content-Type", "application/javascript")
        return xconfig.get("USRE_JS", "")
        
class CacheHandler:

    @xauth.login_required("admin")
    def POST(self):
        key = xutils.get_argument("key", "")
        value = xutils.get_argument("value", "")
        cacheutil.set(key, value)
        return dict(code = "success")

    @xauth.login_required("admin")
    def GET(self):
        key = xutils.get_argument("key", "")
        return dict(code = "success", data = cacheutil.get(key))

xurls = (
    r"/system/sys",   IndexHandler,
    r"/system/index", IndexHandler,
    r"/system/admin", AdminHandler,
    r"/system/system", IndexHandler,
    r"/system/reload", ReloadHandler,
    r"/system/user\.css", UserCssHandler,
    r"/system/user\.js", UserJsHandler,
    r"/system/cache", CacheHandler
)
