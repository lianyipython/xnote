# -*- coding:utf-8 -*-
# @author xupingmao <578749341@qq.com>
# @since 2018/09/30 20:53:38
# @modified 2022/03/04 23:02:45
import xconfig
import os
import os
import xtemplate
import xutils
import xauth
import xmanager
import web
import copy

from xtemplate import T
from xutils import Storage
from xutils import fsutil
from xutils import logutil
from xutils import textutil, SearchResult, dateutil, dbutil, u
from xutils import attrget
from xutils import mem_util
from xutils.imports import ConfigParser

"""xnote插件模块，由于插件的权限较大，开发权限只开放给管理员，普通用户可以使用

插件的模型：插件包含两部分，程序和数据，程序部分存储在插件目录中的文件，数据存储在数据库或者文件中，使用dbutil/fsutil接口操作数据
- 插件名称、描述、文件名、文件路径
- 插件的主类
- 插件的分类
- 插件的访问权限

插件的生命周期
- 插件的注册：debug模式下实时注册，非debug模式：初始化注册+按需注册
- 插件的卸载：退出应用
- 插件的刷新：刷新系统的时候重新加载
- 插件的删除：删除插件文件

插件日志：
- 日志关系：每个用户保留一个插件访问记录，记录最近访问的时间，访问的总次数
- 日志的创建：访问的时候创建
- 日志的更新：访问的时候更新
- 日志的删除：暂无

"""

PLUGIN_CATEGORY_LIST = list()

CONFIG_TOOLS = list()

PLUGINS_STATUS = "loading"

DEFAULT_PLUGIN_ICON_CLASS = "fa fa-cube"

dbutil.register_table("plugin_visit_log", "插件访问日志", check_user = True)
dbutil.register_table_user_attr("plugin_visit_log", "user")

_log_db = dbutil.get_table("plugin_visit_log")

def get_current_platform():
    return xtemplate.get_device_platform()

class PluginCategory:
    """插件分类"""
    required_roles = None
    icon_class = "fa fa-cube"

    def __init__(self, code, name, url = None, required_roles = None):
        self.code = code
        self.name = name
        self.required_roles = required_roles
        self.platforms = None
        if url is None:
            self.url = "/plugin_list?category=%s" % self.code
        else:
            self.url = url

    def is_visible(self):
        return self.is_visible_by_roles() and self.is_visible_by_platform()

    def is_visible_by_platform(self):
        if self.platforms is None:
            return True
        return get_current_platform() in self.platforms

    def is_visible_by_roles(self):
        if self.required_roles is None:
            return True
        return xauth.current_role() in self.required_roles


def define_plugin_category(code, 
        name, 
        url = None, 
        raise_duplication = True, 
        required_roles = None, 
        platforms = None, 
        icon_class = None):
    global PLUGIN_CATEGORY_LIST
    for item in PLUGIN_CATEGORY_LIST:
        if item.code == code:
            if raise_duplication:
                raise Exception("code: %s is defined" % code)
            else:
                return
        if item.name == name:
            if raise_duplication:
                raise Exception("name: %s is defined" % name)
            else:
                return
    category = PluginCategory(code, name, url, required_roles)
    category.platforms = platforms
    if icon_class != None:
        category.icon_class = icon_class
    PLUGIN_CATEGORY_LIST.append(category)

def get_plugin_category_list():
    global PLUGIN_CATEGORY_LIST
    return PLUGIN_CATEGORY_LIST

def get_category_url_by_code(code):
    if code is None:
        return "/plugin_list?category=all"
    for item in PLUGIN_CATEGORY_LIST:
        if item.code == code:
            return item.url
    return "/plugin_list?category=%s" % code

def get_category_name_by_code(code):
    category = get_category_by_code(code)
    if category != None:
        return category.name

    # 如果没有定义，就返回code
    return code

def get_category_by_code(code):
    for item in PLUGIN_CATEGORY_LIST:
        if item.code == code:
            return item
    return None


def get_category_icon_class_by_code(code):
    category = get_category_by_code(code)
    if category is None:
        return DEFAULT_PLUGIN_ICON_CLASS
    return category.icon_class

class PluginContext(Storage):
    """插件上下文"""

    def __init__(self):
        self.title         = ""
        self.name          = ""
        self.url           = "" # 这个应该算是基础url，用于匹配访问日志
        self.url_query     = "" # 查询参数部分
        self.link          = "" # URL的别名
        self.description   = ""
        self.fname         = ""
        self.fpath         = ""
        self.category      = None
        self.category_list = []
        self.require_admin = True
        self.required_role = "" 
        self.permitted_role_list = [] # 允许访问的权限列表
        self.atime         = ""
        self.editable      = True
        self.edit_link     = ""
        self.clazz         = None
        self.priority      = 0
        self.icon          = DEFAULT_PLUGIN_ICON_CLASS
        self.author        = None
        self.version       = None
        self.debug         = False

    # sort方法重写__lt__即可
    def __lt__(self, other):
        return self.title < other.title

    # 兼容Python2
    def __cmp__(self, other):
        return cmp(self.title, other.title)

    def load_category_info(self, meta_obj):
        self.category      = meta_obj.get_str_value("category")  # 这里取第一个分类
        self.category_list = meta_obj.get_list_value("category") # 获取分类列表
        self.build_category()

    def load_permission_info(self, meta_obj):
        self.require_admin = meta_obj.get_bool_value("require-admin", True)  # 访问是否要求管理员权限
        self.permitted_role_list = meta_obj.get_list_value("permitted-role") # 允许访问的角色


    def load_from_meta(self, meta_obj):
        self.api_level = meta_obj.get_float_value("api-level", 0.0)

        if self.api_level >= 2.8:
            self.title       = meta_obj.get_str_value("title")
            self.description = meta_obj.get_str_value("description")
            self.author      = meta_obj.get_str_value("author")
            self.version     = meta_obj.get_str_value("version")
            self.icon        = meta_obj.get_str_value("icon-class")
            self.since       = meta_obj.get_str_value("since")
            self.debug       = meta_obj.get_bool_value("debug")
            
            self.load_category_info(meta_obj)
            self.load_permission_info(meta_obj)


    def build_category(self):
        if self.category is None and len(self.category_list) > 0:
            self.category = self.category_list[0]
        
        if self.category != None and self.category not in self.category_list:
            self.category_list.append(self.category)

        if self.category is None and len(self.category_list) == 0:
            self.category = "other"
            self.category_list.append(self.category)

    def build_permission_info(self):
        if self.clazz != None:
            self.clazz.permitted_role_list = self.permitted_role_list

    def build(self):
        """构建完整的对象"""
        self.build_category()
        self.build_permission_info()

        if self.icon is None:
            self.icon = DEFAULT_PLUGIN_ICON_CLASS
            self.icon_class = DEFAULT_PLUGIN_ICON_CLASS



def is_plugin_file(fpath):
    return os.path.isfile(fpath) and fpath.endswith(".py")


@mem_util.log_mem_info_deco("load_plugin_file", log_args = True)
def load_plugin_file(fpath, fname = None):
    if not is_plugin_file(fpath):
        return
    if fname is None:
        fname = os.path.basename(fpath)
    dirname = os.path.dirname(fpath)

    # 相对于插件目录的名称
    plugin_name = fsutil.get_relative_path(fpath, xconfig.PLUGINS_DIR)

    vars = dict()
    vars["script_name"] = plugin_name
    vars["fpath"] = fpath

    try:
        meta    = xutils.load_script_meta(fpath)
        context = PluginContext()
        context.icon_class = DEFAULT_PLUGIN_ICON_CLASS
        # 读取meta信息
        context.load_from_meta(meta)
        context.fpath = fpath

        if meta.has_tag("disabled"):
            return

        # 2.8版本之后从注解中获取插件信息
        module  = xutils.load_script(fname, vars, dirname = dirname)
        main_class = vars.get("Main")
        if main_class != None:
            # 实例化插件
            main_class.fname      = fname
            main_class.fpath      = fpath
            instance              = main_class()
            context.fname         = fname
            context.name          = os.path.splitext(fname)[0]

            if context.api_level < 2.8:
                context.title = getattr(instance, "title", "")
                context.category = attrget(instance, "category")
                context.required_role = attrget(instance, "required_role")
            
            if context.api_level >= 2.8:
                main_class.title = context.title
                main_class.category = context.category
                main_class.required_role = context.required_role

            context.url           = "/plugin/%s" % plugin_name
            context.clazz         = main_class
            context.edit_link     = "code/edit?path=" + fpath
            context.link          = context.url
            context.meta          = meta

            # 初始化插件
            if hasattr(main_class, 'on_init'):
                instance.on_init(context)

            # 注册插件
            xconfig.PLUGINS_DICT[plugin_name] = context
            context.build()
            return context
    except:
        # TODO 增加异常日志
        xutils.print_exc()


def check_and_load_class(plugin):
    if plugin.clazz is not None:
        return

    load_plugin_file(plugin.fpath)

def load_inner_plugins():
    for tool in INNER_TOOLS:
        xconfig.PLUGINS_DICT[tool.url] = tool

def load_plugin_dir(dirname = None):
    """加载插件目录"""
    if dirname is None:
        dirname = xconfig.PLUGINS_DIR

    xconfig.PLUGINS_DICT = {}
    for root, dirs, files in os.walk(dirname):
        for fname in files:
            fpath = os.path.join(root, fname)
            load_plugin_file(fpath)

    load_inner_plugins()

def can_visit_by_role(plugin, current_role):
    if current_role == "admin":
        return True

    # permitted_role_list 优先级更高
    if current_role in plugin.permitted_role_list:
        return True

    if plugin.require_admin:
        return False

    if plugin.required_role is None:
        return True

    if plugin.required_role == current_role:
        return True

    return False

@xutils.timeit(logfile=True, logargs=True, name="FindPlugins")
def find_plugins(category, orderby=None):
    current_role = xauth.get_current_role()
    user_name    = xauth.current_name()
    plugins = []

    if current_role is None:
        # not logged in
        return plugins

    if category == "None":
        category = "other"

    for fname in xconfig.PLUGINS_DICT:
        p = xconfig.PLUGINS_DICT.get(fname)
        if p and category in p.category_list:
            if can_visit_by_role(p, current_role):
                plugins.append(p)
    return sorted_plugins(user_name, plugins, orderby)

def inner_plugin(name, url, category = "inner", url_query = "", icon = None):
    context = PluginContext()
    context.name = name
    context.title = name
    context.url   = url
    context.link  = url
    context.url_query = url_query
    context.editable = False
    context.category = category
    context.icon_class = "fa fa-cube"
    context.permitted_role_list = ["admin", "user"]
    context.require_admin = False
    context.icon = icon
    context.icon_class = icon
    context.build()
    return context

def note_plugin(name, url, icon=None, size = None, required_role = "user", url_query = ""):
    context = PluginContext()
    context.name = name
    context.title = name
    context.url   = url
    context.url_query = url_query
    context.link  = url
    context.icon  = icon
    context.icon_class = "fa %s" % icon
    context.size  = size
    context.editable = False
    context.category = "note"
    context.require_admin = False
    context.required_role = required_role
    context.permitted_role_list = ["admin", "user"]
    context.build()
    return context

def index_plugin(name, url, url_query = ""):
    return inner_plugin(name, url, "index", url_query = url_query)

def file_plugin(name, url, icon = None):
    return inner_plugin(name, url, "dir", icon = icon)

def dev_plugin(name, url):
    return inner_plugin(name, url, "develop")

def system_plugin(name, url):
    return inner_plugin(name, url, "system")


def load_inner_tools():
    pass

INNER_TOOLS = [
    # 工具集/插件集
    # index_plugin("笔记工具", "/plugin_list?category=note", url_query = "&show_back=true"),
    # index_plugin("文件工具", "/plugin_list?category=dir" , url_query = "&show_back=true"),
    # index_plugin("开发工具", "/plugin_list?category=develop", url_query = "&show_back=true"),
    # index_plugin("网络工具", "/plugin_list?category=network", url_query = "&show_back=true"),
    # index_plugin("系统工具", "/plugin_list?category=system" , url_query = "&show_back=true"),

    # 开发工具
    dev_plugin("浏览器信息", "/tools/browser_info"),

    # 文本
    dev_plugin("文本对比", "/tools/text_diff"),
    dev_plugin("文本转换", "/tools/text_convert"),
    dev_plugin("随机字符串", "/tools/random_string"),

    # 图片
    dev_plugin("图片合并", "/tools/img_merge"),
    dev_plugin("图片拆分", "/tools/img_split"),
    dev_plugin("图像灰度化", "/tools/img2gray"),

    # 编解码
    dev_plugin("base64", "/tools/base64"),
    dev_plugin("HEX转换", "/tools/hex"),
    dev_plugin("md5签名", "/tools/md5"),
    dev_plugin("sha1签名", "/tools/sha1"),
    dev_plugin("URL编解码", "/tools/urlcoder"),
    dev_plugin("条形码", "/tools/barcode"),
    dev_plugin("二维码", "/tools/qrcode"),
    
    # 其他工具
    inner_plugin("分屏模式", "/tools/multi_win"),
    inner_plugin("RunJS", "/tools/runjs"),
    inner_plugin("摄像头", "/tools/camera"),

    # 笔记工具
    note_plugin("新建笔记", "/note/create", "fa-plus-square"),
    note_plugin("我的置顶", "/note/sticky", "fa-thumb-tack"),
    note_plugin("搜索历史", "/search/history", "fa-search"),
    note_plugin("导入笔记", "/note/html_importer", "fa-internet-explorer", required_role = "admin"),
    note_plugin("时间视图", "/note/date", "fa-clock-o", url_query = "?show_back=true"),
    note_plugin("数据统计", "/note/stat", "fa-bar-chart"),
    note_plugin("上传管理", "/fs_upload", "fa-upload"),
    note_plugin("笔记批量管理", "/note/management", "fa-gear"),
    note_plugin("回收站", "/note/removed", "fa-trash"),
    note_plugin("笔记本", "/note/group", "fa-th-large"),
    note_plugin("待办任务", "/message?tag=task", "fa-calendar-check-o"),
    note_plugin("随手记", "/message?tag=log", "fa-file-text-o"),
    note_plugin("我的相册", "/note/gallery", "fa-photo"),
    note_plugin("我的清单", "/note/list", "fa-list"),
    note_plugin("我的日志", "/note/log", "fa-file-text-o"),
    note_plugin("我的评论", "/note/comment/mine", "fa-comments"),
    note_plugin("标签列表", "/note/taglist", "fa-tags"),
    note_plugin("常用笔记", "/note/recent?orderby=hot", "fa-file-text-o"),
    note_plugin("词典", "/note/dict", "icon-dict"),

    # 文件工具
    file_plugin("文件索引", "/fs_index"),
    file_plugin("我的收藏夹", "/fs_bookmark", icon = "fa fa-folder"),

    # 系统工具
    system_plugin("系统日志", "/system/log"),
]

def get_inner_tool_name(url):
    for tool in INNER_TOOLS:
        if tool.url == url:
            return tool.name
    return url

def build_inner_tools(user_name = None):
    if user_name is None:
        user_name = xauth.current_name()
    tools_copy = copy.copy(INNER_TOOLS)
    sort_plugins(user_name, tools_copy)
    return tools_copy

def convert_plugins_to_links(plugins):
    return plugins

def get_plugin_values():
    values = xconfig.PLUGINS_DICT.values()
    return list(values)

class PluginSort:

    def __init__(self, user_name):
        self.user_name = user_name
        self.logs = list_visit_logs(user_name)

    def get_log_by_url(self, url):
        for log in self.logs:
            if log.url == url:
                return log
        return None

    def sort_by_visit_cnt_desc(self, plugins):
        for p in plugins:
            log = self.get_log_by_url(p.url)
            if log:
                p.visit_cnt = log.visit_cnt
            
            if p.visit_cnt is None:
                p.visit_cnt = 0

        plugins.sort(key = lambda x:x.visit_cnt, reverse = True)

    def sort_by_recent(self, plugins):
        for p in plugins:
            log = self.get_log_by_url(p.url)
            if log:
                p.visit_time = log.time
            
            if p.visit_time is None:
                p.visit_time = ""

        plugins.sort(key = lambda x:x.visit_time, reverse = True)

def sort_plugins(user_name, plugins, orderby = None):
    sort_obj = PluginSort(user_name)
    if orderby is None or orderby == "":
        sort_obj.sort_by_visit_cnt_desc(plugins)
    elif orderby == "recent":
        sort_obj.sort_by_recent(plugins)
    else:
        raise Exception("invalid orderby:%s" % orderby)

    return plugins

def sorted_plugins(user_name, plugins, orderby=None):
    sort_plugins(user_name, plugins, orderby)
    return plugins

def debug_print_plugins(plugins, ctx = None):
    if False:
        print("\n" * 5)
        print(ctx)
        for p in plugins:
            print(p)

@logutil.timeit_deco(name = "list_all_plugins")
def list_all_plugins(user_name, sort = True, orderby = None):
    links = get_plugin_values()
    
    if sort:
        return sorted_plugins(user_name, links, orderby)

    return links

def list_other_plugins(user_name, sort = True):
    return find_plugins("other")


@logutil.timeit_deco(name = "list_plugins")
def list_plugins(category, sort = True, orderby = None):
    user_name = xauth.current_name()

    if category == "other":
        plugins = list_other_plugins(user_name)
    elif category and category != "all":
        # 某个分类的插件
        plugins = find_plugins(category)
    else:
        # 所有插件
        plugins = list_all_plugins(user_name)

    links = convert_plugins_to_links(plugins)
    if sort:
        return sorted_plugins(user_name, links, orderby = orderby)
    return links

def find_plugin_by_url(url, plugins):
    for p in plugins:
        if u(p.url) == u(url):
            return p
    return None

@logutil.timeit_deco(name = "list_recent_plugins")
def list_recent_plugins():
    user_name = xauth.current_name()
    plugins   = list_all_plugins(user_name, sort = False)
    links = convert_plugins_to_links(plugins)

    sort_plugins(user_name, links, "recent")
    return links

def list_visit_logs(user_name, offset = 0, limit = -1):
    logs = _log_db.list(user_name = user_name, offset = offset, limit = limit, reverse = True)
    logs.sort(key = lambda x: x.time, reverse = True)
    return logs

def find_visit_log(user_name, url):
    for log in _log_db.iter(user_name = user_name, limit = -1):
        if log.url == url:
            log.key = log._key
            return log
    return None

def update_visit_log(log, name):
    log.name = name
    log.time = dateutil.format_datetime()
    if log.visit_cnt is None:
        log.visit_cnt = 1
    log.visit_cnt += 1
    _log_db.update(log)

def add_visit_log(user_name, url, name = None, args = None):
    if user_name == None:
        user_name = "guest"
        
    exist_log = find_visit_log(user_name, url)
    if exist_log != None:
        exist_log.user = user_name
        update_visit_log(exist_log, name)
        return

    log = Storage()
    log.name = name
    log.url  = url
    log.args = args
    log.time = dateutil.format_datetime()
    log.user = user_name

    _log_db.insert_by_user(user_name, log)

def delete_visit_log(user_name, name, url):
    exist_log = find_visit_log(user_name, url)
    if exist_log != None:
        _log_db.delete_by_key(exist_log.key, user_name)

def load_plugin(name):
    user_name = xauth.current_name()
    context   = xconfig.PLUGINS_DICT.get(name)

    # DEBUG模式下始终重新加载插件
    if xconfig.DEBUG or context is None or context.debug is True:
        fpath = os.path.join(xconfig.PLUGINS_DIR, name)
        fpath = xutils.get_real_path(fpath)
        if not os.path.exists(fpath):
            return None
        # 发现了新的插件，重新加载一下
        plugin = load_plugin_file(fpath)
        if plugin:
            return plugin
        else:
            return None
    else:
        return context

@xmanager.searchable()
def on_search_plugins(ctx):
    if not xauth.is_admin():
        return

    if not ctx.search_tool:
        return

    if ctx.search_dict:
        return

    global PLUGINS_STATUS
    if PLUGINS_STATUS == "loading":
        result = Storage()
        result.name = "插件加载中，暂时不可用"
        result.icon = "fa-th-large"
        result.url  = "#"

        ctx.tools.append(result)
        return

    user_name = ctx.user_name
    result_list = []
    temp_result = []

    for plugin in search_plugins(ctx.key):
        result           = SearchResult()
        result.category  = "plugin"
        result.icon      = "fa-cube"
        result.name      = u(plugin.name)
        result.name      = u(plugin.title + "(" + plugin.name + ")")
        result.url       = u(plugin.url)
        result.edit_link = plugin.edit_link
        temp_result.append(result)

    result_count = len(temp_result)
    if ctx.category != "plugin" and len(temp_result) > 0:
        more = SearchResult()
        more.name = u("搜索到[%s]个插件") % result_count
        more.icon = "fa-th-large"
        more.url  = "/plugins_list?category=plugin&key=" + ctx.key
        more.show_more_link = True
        result_list.append(more)

    if xconfig.get_user_config(user_name, "search_plugin_detail_show") == "true":
        result_list += temp_result[:3]

    ctx.tools += result_list

def is_plugin_matched(p, words):
    return textutil.contains_all(p.title, words) \
        or textutil.contains_all(p.url, words) \
        or textutil.contains_all(p.fname, words)


def search_plugins(key):
    from xutils.functions import dictvalues
    user_name = xauth.current_name()
    words   = textutil.split_words(key)
    plugins = list_all_plugins(user_name, True)
    result  = dict()
    for p in plugins:
        if is_plugin_matched(p, words):
            result[p.url] = p
    return dictvalues(result)

def get_template_by_version(version):
    if version == "1":
        return "plugin/page/plugins_v1.html"
    if version == "2":
        return "plugin/page/plugins_v2.html"

    # 最新版本
    return "plugin/page/plugins_v3.html"

def filter_plugins_by_role(plugins, user_role):
    result = []
    for p in plugins:
        if user_role in p.permitted_role_list:
            result.append(p)
    return result

def fill_plugins_badge_info(plugins, orderby):
    if orderby == "" or orderby is None:
        # 默认按热度访问
        for p in plugins:
            p.badge_info = "热度: %s" % p.visit_cnt
    else:
        # 最近访问的
        for p in plugins:
            p.badge_info = dateutil.format_date(p.visit_time)

class PluginListHandler:

    @logutil.timeit_deco(name = "PluginListHandler")
    @xauth.login_required()
    def GET(self):
        global PLUGINS_STATUS
        category = xutils.get_argument("category", "")
        key      = xutils.get_argument("key", "")
        header   = xutils.get_argument("header", "")
        version  = xutils.get_argument("version", "")
        show_back = xutils.get_argument("show_back", "")
        orderby  = xutils.get_argument("orderby", "")

        context = Storage()
        context.category = category
        context.category_name = get_category_name_by_code(category)
        context.html_title = "插件"
        context.header = header
        context.show_back = show_back

        user_name = xauth.current_name()
        xmanager.add_visit_log(user_name, "/plugin_list?category=%s" % category)

        if category == "recent":
            category = "all"
            orderby  = "recent"

        if xauth.is_admin():
            if key != "" and key != None:
                plugins = search_plugins(key)
                context.show_category = False
                context.show_back = "true"
                context.title = T("搜索插件")
            else:
                plugins  = list_plugins(category, orderby = orderby)
        else:
            # 普通用户插件访问
            user_role = xauth.current_role()
            plugins = list_plugins(category)
            plugins = filter_plugins_by_role(plugins, user_role)

        fill_plugins_badge_info(plugins, orderby)

        context.plugins = plugins
        context.plugins_status = PLUGINS_STATUS

        if category == "":
            context.plugin_category = "all"

        template_file = get_template_by_version(version)
        return xtemplate.render(template_file, **context)

class PluginCategoryListHandler:

    @xauth.login_required()
    def GET(self):
        version  = xutils.get_argument("version", "")
        current_role = xauth.current_role()
        total_count = 0
        count_dict = dict()

        for k in xconfig.PLUGINS_DICT:
            p = xconfig.PLUGINS_DICT[k]
            if not can_visit_by_role(p, current_role):
                continue
            
            total_count += 1
            for category in p.category_list:
                count = count_dict.get(category, 0)
                count += 1
                count_dict[category] = count
        
        sorted_items = sorted(count_dict.items(), key = lambda x:x[1], reverse = True)
        category_keys = list(map(lambda x:x[0], sorted_items))

        plugins = []

        # 全部插件
        root = PluginContext()
        root.title = T("全部")
        root.url   = "/plugin_list?category=all&show_back=true"
        root.link  = root.url
        root.badge_info = total_count
        root.icon_class = DEFAULT_PLUGIN_ICON_CLASS
        plugins.append(root)

        for key in category_keys:
            p = PluginContext()
            p.title = get_category_name_by_code(key)
            url     = get_category_url_by_code(key)
            url     = textutil.add_url_param(url, "show_back", "true")
            p.url   = url
            p.link  = url
            p.icon_class = get_category_icon_class_by_code(key)
            p.badge_info = count_dict[key]
            plugins.append(p)

        template_file = get_template_by_version(version)
        return xtemplate.render(template_file, plugins = plugins, plugin_category = "index")
        

def get_plugin_category(category):
    plugin_categories = []

    recent   = list_recent_plugins()
    plugins  = list_plugins(category)
    note_plugins = list_plugins("note")
    dev_plugins  = list_plugins("develop")
    sys_plugins  = list_plugins("system")
    dir_plugins  = list_plugins("dir")
    net_plugins  = list_plugins("network")
    other_plugins = list(filter(lambda x: x.category not in ("inner", "note", "develop", "system", "dir", "network"), plugins))

    plugin_categories.append(["最近", recent])
    plugin_categories.append(["默认工具", build_inner_tools()])
    plugin_categories.append(["笔记", note_plugins])
    plugin_categories.append(["开发工具", dev_plugins])
    plugin_categories.append(["系统", sys_plugins])
    plugin_categories.append(["文件", dir_plugins])
    plugin_categories.append(["网络", net_plugins])
    plugin_categories.append(["其他", other_plugins])
    return plugin_categories

class PluginGridHandler:

    @xauth.login_required()
    def GET(self):
        category = xutils.get_argument("category", "")
        key      = xutils.get_argument("key", "")
        plugin_categories = []

        if xauth.is_admin():
            if key != None and key != "":
                plugin_categories.append(["搜索", search_plugins(key)])
            else:
                plugin_categories = get_plugin_category(category)
        else:
            plugins = build_inner_tools()
            plugin_categories.append(["默认工具", plugins])

        return xtemplate.render("plugin/page/plugins_v2.html", 
            category = category,
            html_title = "插件",
            plugin_categories = plugin_categories)

class LoadPluginHandler:

    def GET(self, name = ""):
        user_name = xauth.current_name()
        name      = xutils.unquote(name)

        if not name.endswith(".py"):
            name += ".py"
        try:
            url = "/plugin/" + name
            plugin = load_plugin(name)
            if plugin != None:
                # 访问日志
                add_visit_log(user_name, url)
                check_and_load_class(plugin)
                # 渲染页面
                return plugin.clazz().render()
            else:
                # 加载插件失败，删除日志
                delete_visit_log(user_name, name, url)
                return xtemplate.render("error.html", 
                    error = "插件[%s]不存在!" % name)
        except:
            error = xutils.print_exc()
            return xtemplate.render("error.html", error=error)

    def POST(self, name = ""):
        return self.GET(name)

class LoadInnerToolHandler:
    
    def GET(self, name):
        user_name = xauth.current_name()
        url  = "/tools/" + name
        fname = xutils.unquote(name)
        if not name.endswith(".html"):
            fname += ".html"
        # Chrome下面 tools/timeline不能正常渲染
        web.header("Content-Type", "text/html")
        fpath = os.path.join(xconfig.HANDLERS_DIR, "tools", fname)
        if os.path.exists(fpath):
            if user_name != None:
                tool_name = get_inner_tool_name(url)
                add_visit_log(user_name, url)
            return xtemplate.render("tools/" + fname, show_aside = False)
        else:
            raise web.notfound()

    def POST(self, name):
        return self.GET(name)

class PluginLogHandler:

    @xauth.login_required()
    def GET(self):
        user_name = xauth.current_name()
        logs = list_visit_logs(user_name)
        return logs

@xmanager.listen("sys.reload")
@mem_util.log_mem_info_deco("reload_plugins")
def reload_plugins(ctx):
    global PLUGINS_STATUS
    PLUGINS_STATUS = "loading"

    reload_plugins_by_config()

    load_plugin_dir()

    PLUGINS_STATUS = "done"

@xutils.log_init_deco("reload_plugins_by_config")
def reload_plugins_by_config(ctx = None):
    global CONFIG_TOOLS
    parser = ConfigParser()

    fpath = "config/plugin/plugins.ini"
    sections = parser.read(fpath, encoding = "utf-8")

    tmp_tools = []
    for section in parser.sections():
        name = parser.get(section, "name", fallback = None)
        icon = parser.get(section, "icon", fallback = None)
        url  = parser.get(section, "url", fallback = None)
        category = parser.get(section, "category", fallback = None)
        editable = parser.getboolean(section, "editable", fallback = False)
    
        # 构建上下文
        context = PluginContext()
        context.name = name
        context.title = name
        context.url   = url
        context.link  = url
        context.editable = editable
        context.category = category

        tmp_tools.append(context)

    CONFIG_TOOLS = tmp_tools



xutils.register_func("plugin.find_plugins", find_plugins)
xutils.register_func("plugin.add_visit_log", add_visit_log)
xutils.register_func("plugin.get_category_list", get_plugin_category_list)
xutils.register_func("plugin.get_category_url_by_code", get_category_url_by_code)
xutils.register_func("plugin.get_category_name_by_code", get_category_name_by_code)
xutils.register_func("plugin.define_category", define_plugin_category)

define_plugin_category("all",      u"全部", icon_class = "fa fa-th-large")
define_plugin_category("recent",   u"最近")
define_plugin_category("note"  ,   u"笔记")
define_plugin_category("dir",      u"文件", required_roles = ["admin"], icon_class="fa fa-folder")
define_plugin_category("system",   u"系统", required_roles = ["admin"], platforms = ["desktop"],  icon_class = "fa fa-gear")
define_plugin_category("network",  u"网络", required_roles = ["admin"], platforms = ["desktop"], icon_class = "icon-network-14px")
define_plugin_category("develop",  u"开发", required_roles = ["admin", "user"], platforms = ["desktop"])
define_plugin_category("datetime", u"日期和时间", platforms = [], icon_class = "fa fa-clock-o")
define_plugin_category("work",     u"工作", platforms = ["desktop"], icon_class = "icon-work")
define_plugin_category("index",    u"分类", url = "/plugin_category_list?category=index", icon_class = "fa fa-th-large")
define_plugin_category("inner",    u"内置工具", platforms = [])
define_plugin_category("money",    u"理财", platforms = ["desktop"])
define_plugin_category("test",     u"测试", platforms = [])
define_plugin_category("other",    u"其他", platforms = [])

xurls = (
    r"/plugin/(.+)", LoadPluginHandler,
    r"/plugin_list", PluginListHandler,
    r"/plugin_category_list", PluginCategoryListHandler,
    
    r"/plugins_list_new", PluginGridHandler,
    r"/plugins_list", PluginListHandler,
    r"/plugins_log", PluginLogHandler,
    r"/plugins/(.+)", LoadPluginHandler,
    r"/tools/(.+)", LoadInnerToolHandler,
)
