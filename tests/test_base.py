# encoding=utf-8
from .a import *
import os
import time
import unittest
import xconfig
import xutils
import xtables
import xmanager
import xtemplate
import xtables_new
import web
import six
import json
import xauth
from xutils import dbutil
from handlers.fs.fs_upload import get_upload_file_path
from xutils.db.driver_sqlite import SqliteKV

config = xconfig
date = time.strftime("%Y/%m")

APP: web.application = None

DEFAULT_HEADERS = dict()


def init():
    global APP
    if APP is not None:
        return APP
    xconfig.init("./config/boot/boot.test.properties")
    xconfig.IS_TEST = True
    xconfig.port = "1234"
    xconfig.DEV_MODE = True
    var_env = dict()
    xutils.remove_file("./testdata/data.db", hard=True)
    xtables.init()

    db_file = os.path.join(xconfig.DB_DIR, "sqlite", "test.db")
    db_instance = SqliteKV(db_file)
    dbutil.init(xconfig.DB_DIR, db_instance=db_instance, binlog_max_size=1000)
    xtables_new.init()

    xutils.init(xconfig)
    xauth.init()
    xutils.cacheutil.init(xconfig.STORAGE_DIR)

    APP = web.application(list(), var_env, autoreload=False)
    last_mapping = (r"/tools/(.*)", "handlers.tools.tools.handler")
    mgr = xmanager.init(APP, var_env, last_mapping=last_mapping)
    mgr.reload()
    # 加载template
    xtemplate.reload()

    xauth.create_user("test2", "123456")

    # 发送启动消息
    xmanager.fire("sys.reload")

    return APP

APP = init()

def get_test_file_path(path):
    return os.path.join("./testdata", path)

def logout_test_user():
    xconfig.IS_TEST = False


def login_test_user():
    xconfig.IS_TEST = True


def json_request(*args, **kw):
    global APP
    if "data" in kw:
        # 对于POST请求设置无效
        kw["data"]["_format"] = "json"
    else:
        kw["data"] = dict(_format="json")
    kw["_format"] = "json"
    kw["headers"] = DEFAULT_HEADERS

    ret = APP.request(*args, **kw)
    if ret.status == "303 See Other":
        return
    assert ret.status == "200 OK"
    data = ret.data
    if six.PY2:
        return json.loads(data)
    return json.loads(data.decode("utf-8"))


def request_html(*args, **kw):
    ret = APP.request(*args, **kw)
    return ret.data


def create_tmp_file(name):
    path = os.path.join(xconfig.DATA_DIR, "files", "user",
                        "upload", time.strftime("%Y/%m"), name)
    xutils.touch(path)


def remove_tmp_file(name):
    path = os.path.join(xconfig.DATA_DIR, "files", "user",
                        "upload", time.strftime("%Y/%m"), name)
    if os.path.exists(path):
        os.remove(path)


class BaseTestCase(unittest.TestCase):

    def request_app(self, *args, **kw):
        return APP.request(*args, **kw)

    def check_OK(self, *args, **kw):
        response = APP.request(*args, **kw)
        status = response.status
        print(status)
        self.assertEqual(True, status == "200 OK" or status ==
                         "303 See Other" or status == "302 Found")

    def check_200(self, *args, **kw):
        response = APP.request(*args, **kw)
        self.assertEqual("200 OK", response.status)

    def check_200_debug(self, *args, **kw):
        response = APP.request(*args, **kw)
        print(args, kw, response)
        print(APP.mapping)
        self.assertEqual("200 OK", response.status)

    def check_303(self, *args, **kw):
        response = APP.request(*args, **kw)
        self.assertEqual("303 See Other", response.status)

    def check_404(self, url):
        response = APP.request(url)
        self.assertEqual("404 Not Found", response.status)

    def check_status(self, status, *args, **kw):
        response = APP.request(*args, **kw)
        self.assertEqual(status, response.status)

    def json_request(self, *args, **kw):
        return json_request(*args, **kw)


class BaseTestMain(unittest.TestCase):

    def test_get_upload_file_path(self):
        remove_tmp_file("test.txt")
        path, webpath = get_upload_file_path("user", "test.txt")
        print()
        print(path)
        print(webpath)
        self.assertEqual(os.path.abspath(config.DATA_PATH +
                         "/files/user/upload/%s/test.txt" % date), path)
        self.assertEqual("/data/files/user/upload/%s/test.txt" % date, webpath)

    def test_get_upload_file_path_1(self):
        remove_tmp_file("test_1.txt")
        create_tmp_file("test.txt")
        path, webpath = get_upload_file_path("user", "test.txt")
        print()
        print(path)
        print(webpath)
        self.assertEqual(os.path.abspath(config.DATA_PATH +
                         "/files/user/upload/%s/test_1.txt" % date), path)
        self.assertEqual(
            "/data/files/user/upload/%s/test_1.txt" % date, webpath)
        remove_tmp_file("test.txt")

    def test_get_upload_file_path_2(self):
        create_tmp_file("test.txt")
        create_tmp_file("test_1.txt")
        remove_tmp_file("test_2.txt")
        path, webpath = get_upload_file_path("user", "test.txt")
        print()
        print(path)
        print(webpath)
        self.assertEqual(os.path.abspath(config.DATA_PATH +
                         "/files/user/upload/%s/test_2.txt" % date), path)
        self.assertEqual(
            "/data/files/user/upload/%s/test_2.txt" % date, webpath)
        remove_tmp_file("test.txt")
        remove_tmp_file("test_1.txt")


class ResponseWrapper:

    def __init__(self, resp: web.Storage) -> None:
        self.resp = resp
    
    def get_header(self, header: str):
        header = header.lower()
        headers = self.resp.header_items
        for key, value in headers:
            if key.lower() == header:
                return value
        return value
