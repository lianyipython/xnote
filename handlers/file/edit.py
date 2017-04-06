# encoding=utf-8
# Created by xupingmao on 2016/12

from handlers.base import *
from FileDB import FileService
import xauth
import xutils

import web.db as db

def date2str(d):
    ct = time.gmtime(d / 1000)
    return time.strftime('%Y-%m-%d %H:%M:%S', ct)


def try_decode(bytes):
    try:
        return bytes.decode("utf-8")
    except:
        return bytes.decode("gbk")

def get_file_db():
    return db.SqliteDB(db="db/data.db")

class handler(BaseHandler):

    @xauth.login_required()
    def execute(self):
        service = FileService.instance()
        id = self.get_argument("id", "")
        name = self.get_argument("name", "")
        if id == "" and name == "":
            raise HTTPError(504)
        if id != "":
            id = int(id)
            service.visitById(id)
            file = service.getById(id)
        elif name is not None:
            file = service.getByName(name)
        if file is None:
            raise web.notfound()
        download_csv = file.related != None and "CODE-CSV" in file.related
        self.render(file=file, 
            content = file.get_content(), 
            date2str=date2str,
            download_csv = download_csv, 
            children = FileDB.get_children_by_id(file.id))

    def download_request(self):
        service = FileService.instance()
        id = self.get_argument("id")
        file = service.getById(id)
        content = file.get_content()
        if content.startswith("```CSV"):
            content = content[7:-3] # remove \n
        web.ctx.headers.append(("Content-Type", 'application/octet-stream'))
        web.ctx.headers.append(("Content-Disposition", "attachment; filename=%s.csv" % quote(file.name)))
        return content

def sqlite_escape(text):
    if text is None:
        return "NULL"
    if not (isinstance(text, str)):
        return repr(text)
    # text = text.replace('\\', '\\')
    text = text.replace("'", "''")
    return "'" + text + "'"

def updateContent(id, content, user_name=None, type=None, groups=None):
    # TODO 修改version
    if user_name is None:
        sql = "update file set type='md', content = %s,size=%s, smtime='%s', version=version+1" \
            % (sqlite_escape(content), len(content), dateutil.format_time())
    else:
        # 这个字段还在考虑中是否添加
        # 理论上一个人是不能改另一个用户的存档，但是可以拷贝成自己的
        sql = "update file set type = 'md', content = %s,size=%s,smtime='%s',modifier='%s', version=version+1"\
            % (sqlite_escape(content), len(content), dateutil.format_time(), user_name)
    if type:
        sql += ", type='%s'" % type
    if groups:
        sql += ", groups = '%s'" % groups
    sql += " where id=%s" % id

    xutils.db_execute("db/data.db", sql)

def result(success = True, msg=None):
    return {"success": success, "result": None, "msg": msg}

class UpdateHandler(BaseHandler):

    def update_content_request(self):
        is_public = self.get_argument("public", "")
        service = FileService.instance()
        id = self.get_argument("id")
        content = self.get_argument("content")
        file = service.getById(int(id))
        assert file is not None

        if is_public == "on":
            updateContent(id, content, groups = '*')
        else:
            updateContent(id, content, groups = xauth.get_current_user().name)
        raise web.seeother("/file/edit?id=" + id)

    def rename_request(self):
        service = FileService.instance()
        fileId = self.get_argument("fileId")
        newName = self.get_argument("newName")
        record = service.getByName(newName)
        old_record = service.getById(fileId)
        if old_record is None:
            return result(False, "file with ID %s do not exists" % fileId)
        elif record is not None:
            return result(False, "file %s already exists!" % repr(newName))
        else:
            old_name = old_record.name
            old_name_upper = old_name.upper()
            new_name_upper = newName.upper()
            if old_name_upper not in old_record.related and new_name_upper not in old_record.related:
                old_record.related += "," + newName
            else:
                old_record.related = old_record.related.replace(old_name_upper, new_name_upper);
            old_record.name = newName
            old_record.version = old_record.version + 1
            service.update(old_record, "name", "related", "smtime")
            return result(True)


xurls = ("/file/edit", handler, "/file/update", UpdateHandler)