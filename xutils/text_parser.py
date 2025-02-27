# -*- coding:utf-8 -*-
# @author xupingmao <578749341@qq.com>
# @since 2021/01/10 14:36:09
# @modified 2022/04/09 13:42:24

"""标记文本解析

类
- 文本解析器的基类      TextParserBase(text:str)
- 文本解析器           TextParser

函数
- HTML转义            escape_html(text:str)

"""
import os
from urllib.parse import quote, unquote

IMG_EXT_SET = set([".png", ".jpg", ".gif"])

def invoke_deco(prefix = ""):
    """日志装饰器"""
    def deco(func):
        def handle(*args, **kw):
            try:
                result = func(*args, **kw)
                print(prefix, args, kw, result)
                return result
            except Exception as e:
                print("exception occurs", prefix, args, kw)
                raise e
        return handle
    return deco

def is_img_file(filename):
    """根据文件后缀判断是否是图片"""
    name, ext = os.path.splitext(filename)
    return ext.lower() in IMG_EXT_SET

def set_img_file_ext(img_set):
    global IMG_EXT_SET
    IMG_EXT_SET = img_set

def escape_html(text):
    # 必须先处理&
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace(" ", "&nbsp;")
    text = text.replace("'", "&#39;")
    text = text.replace("\n", "<br/>")
    return text

class TextParserBase(object):

    """文本解析工具, 有这些规则
    - 下标默认从0开始
    - read_till_XXX 指从当前字符读取到目标字符，读完后下标{i}位于目标字符之后的一个字符
    - read_before_XXX 从当前字符读取到目标字符之前的一个字符，读完后下标{i}位于目标字符


    index   value    Description
    -------------------------------
   -1       None  
    0       i        -> 开始的下标
    1       n        
    2       p        -> current 当前字符 (self.i = 2)
    3       u        -> next    下一个字符
    4       t
    5       None

    """


    # 调试的开关
    debug_flag = False

    def init(self, text):
        text = text.replace("\r", "")
        text = text.replace(u'\xad', '\n')

        self.text = text
        self.str_token = ""
        self.tokens = []
        # 当前读取的字符下标，默认初始化为第一个字符
        self.i = 0
        self.length = len(text)
        self.max_index = self.length - 1

        # 循环分析
        self.profile_dict = dict()

    def current(self):
        """当前的字符，如果越界了，返回None"""
        if self.i < self.length:
            return self.text[self.i]
        return None

    def read_next(self):
        """往后读取一个字符，返回读取的字符，如果已经读完了，返回None，改变索引下标"""
        if self.i < self.max_index:
            self.i += 1
            return self.text[self.i]
        elif self.i == self.max_index:
            self.i += 1
        return None

    def next(self):
        """读取下一个字符，如果没有返回None，不改变当前索引下标"""
        if self.i < self.max_index:
            return self.text[self.i+1]
        return None

    def get(self, index):
        if index < self.max_index:
            return self.text[index]
        return None

    def startswith(self, target):
        """当前字符是否以{target}开头"""
        length = len(target)
        return self.text[self.i:self.i+length] == target

    def find(self, target):
        """以{self.i}作为开始下标，寻找目标字符串
        @param {string} target 
        @return 目标字符串的索引下标，如果找不到返回-1
        """
        return self.text.find(target, self.i)

    def find_blank(self):
        """找到一个空白字符
        @return 第一个空白字符的索引，如果找不到返回-1
        """
        i = self.i
        for i in range(self.i, self.length):
            c = self.text[i]
            if c in " \t\n\r":
                return i

        return -1

    def stash_char(self, c):
        """暂存一个字符"""
        self.str_token += c

    def save_str_token(self):
        if self.str_token != "":
            token = self.str_token
            token = escape_html(token)
            self.tokens.append(token)
        self.str_token = ""

    def read_before_blank(self):
        """从当前字符开始，找到空白字符为止，返回内容不包含空白字符,读取后{i}位于第一个空白字符"""
        end = self.find_blank()
        if end < 0:
            found = self.text[self.i:]
            # 全部读完，当前索引处于有效范围外
            self.i = self.length
        else:
            found = self.text[self.i:end]
            # 位于第一个空白字符
            self.i = end
        return found

    def read_till_any(self, any_char_list, start_index = None):
        """包含目标{any_char_list},读取后索引{i}位于any之后的字符"""
        if start_index is None:
            start_index = self.i

        for i in range(start_index, self.max_index+1):
            c = self.text[i]
            if c in any_char_list:
                self.i = i + 1
                return self.text[start_index:i]
        # 没找到，下标移动到最后
        self.i = self.length
        return self.text[start_index:]

    def read_till_index(self, index):
        """包含目标索引，读取后{i}=index+1"""
        start_index = self.i
        self.i = min(self.length, index+1)
        return self.text[start_index:self.i]

    def read_before_index(self, index):
        """不包含目标索引，读取后{i}=index"""
        start_index = self.i
        self.i = min(self.length, index)
        return self.text[start_index:self.i]

    def read_number(self):
        """读取后{i}位于第一个非数字位"""
        for i in range(self.i, self.length):
            c = self.text[i]
            if not c.isdigit():
                token = self.text[self.i:i]
                # 当前处于数字后的第一个字符
                self.i = i
                return token
        token = self.text[self.i:]
        self.i = i + 1
        return token

    def read_rest(self):
        return self.read_till_index(self.max_index)

    def profile(self, name):
        if not self.debug_flag:
            return

        visit_cnt = self.profile_dict.get(name, 0) + 1
        if visit_cnt >= 1000:
            print("there maybe dead loops in [%s]" % name)
        self.profile_dict[name] = visit_cnt

    def parse(self, text):
        raise Exception("parse() must be implemented by child class")


class TextParser(TextParserBase):

    # 是否标记单书名号<书籍名>
    mark_book_single_flag = False

    # 是否标记数字
    mark_number_flag = False

    # 是否记录关键字，关键字包括话题、书籍、@值等等
    record_keyword_flag = True

    # 话题的长度限制
    topic_len_limit = 100

    # 话题转换器
    topic_translator = None

    # 搜索转换器
    search_translator = None

    def init2(self, text):
        self.keywords = set()

    def set_topic_marker(self, topic_marker):
        self.topic_translator = topic_marker

    def set_topic_translator(self, topic_translator):
        self.topic_translator = topic_translator

    def set_search_translator(self, translator):
        self.search_translator = translator

    def record_keyword(self, keyword):
        self.keywords.add(keyword)

    def read_till_target(self, target):
        """返回值包含target，索引{i}移动到target之后"""
        end = self.text.find(target, self.i+1)
        if end < 0:
            key = self.text[self.i:]
            self.i = self.max_index
        else:
            key = self.text[self.i:end+1]
            # 包含 target
            self.i = end + len(target)
        return key

    def build_search_link(self, keyword):
        if self.search_translator != None:
            return self.search_translator(self, keyword)
        key = quote(keyword)
        value = escape_html(keyword)
        return "<a class=\"link\" href=\"/message?category=message&key=%s\">%s</a>" % (key, value)

    def translate_topic(self, key0):
        if self.topic_translator != None:
            return self.topic_translator(self, key0)
        key = key0.lstrip("#\n")
        key = key.rstrip("#\n")
        quoted_key = quote(key)
        value = escape_html(key0)
        return "<a class=\"link\" href=\"/message?category=message&key=%s\">%s</a>" % (quoted_key, value)

    def mark_topic(self):
        """话题转为搜索关键字的时候去掉前后的#符号"""
        self.profile("mark_topic")

        start_index = self.i
        self.save_str_token()
        end_tuple = ("#", "\n")
        key0 = None
        for i in range(self.i+1, self.length):
            c = self.text[i]
            if c == '#':
                key0 = self.read_till_index(i)
                break
            elif c == '\n':
                key0 = self.read_before_index(i)
                break

        if key0 is None:
            key0 = self.read_rest()

        if len(key0) > self.topic_len_limit:
            # 超过限制，不认为是话题
            self.stash_char('#')
            self.i = start_index + 1
            return
        # 记录关键字
        self.record_keyword(key0)
        # 处理转换逻辑
        token = self.translate_topic(key0)
        self.tokens.append(token)


    def mark_http(self):
        self.profile("mark_http")

        self.save_str_token()
        link  = self.read_before_blank()
        token = '<a target="_blank" href="%s">%s</a>' % (link, link)
        self.tokens.append(token)

    def mark_https(self):
        return self.mark_http()

    def mark_book(self):
        return self.mark_tag_single("》")

    def mark_at(self):
        self.profile("mark_at")
        self.save_str_token()
        
        word  = self.read_before_blank()
        token = self.build_search_link(word)
        self.tokens.append(token)

        # 记录关键字
        self.record_keyword(word)

    def mark_book_single(self):
        return self.mark_tag_single(">")

    def mark_number(self):
        self.profile("mark_number")

        self.save_str_token()
        number = self.read_number()
        token  = self.build_search_link(number)
        self.tokens.append(token)
        return token

    def mark_tag_single(self, end_char):
        self.profile("mark_tag_single")

        self.save_str_token()
        
        key   = self.read_till_target(end_char)
        token = self.build_search_link(key)
        self.tokens.append(token)

        # 记录关键字
        self.record_keyword(key)


    def mark_file(self):
        self.profile("mark_file")

        self.save_str_token()
        href = self.read_before_blank()
        href = href[7:]
        if is_img_file(href):
            token = '<div class="msg-img-box"><img class="msg-img x-photo" alt="%s" src="%s"></div>' % (href, href)
            self.tokens.append(token)
        else:
            name = href[href.rfind("/")+1:]
            # 尝试urldecode名称
            name = unquote(name)
            token = '<a href="%s">%s</a>' % (href, name)
            self.tokens.append(token)

    def parse(self, text):
        self.init(text)
        self.init2(text)

        c = self.current()
        while c != None:
            if c == '#':
                self.mark_topic()
            elif c == '《':
                self.mark_book()
            elif c == '@':
                self.mark_at()
            elif self.mark_book_single_flag and c == '<':
                self.mark_book_single()
            elif self.mark_number_flag and c.isdigit():
                self.mark_number()
            elif self.startswith("http://"):
                self.mark_http()
            elif self.startswith("https://"):
                self.mark_https()
            elif self.startswith("file://"):
                self.mark_file()
            elif c == '\n':
                self.stash_char(c)
                self.save_str_token()
                self.read_next()
            else:
                # 未命中规则，保存并且往下读取一个字符
                self.stash_char(c)
                self.read_next()

            # 再读取一个字符
            # c = self.read_next()
            c = self.current()

        self.save_str_token()
        return self.tokens

def runtest_head(message):
    width  = 60
    length = len(message)
    left  = (width - length) // 2
    right = width - length - left
    print("-" * left, message, "-" * right)

def runtest_topic1():
    runtest_head("Topic Test 1")
    text = "#Topic1# Text"
    parser = TextParser()
    tokens = parser.parse(text)
    print("text=%r" % text)
    print(tokens)

def runtest_topic2():
    runtest_head("Topic Test 2")
    text = "#Topic2 Bank# Text"
    parser = TextParser()
    tokens = parser.parse(text)
    print("text=%r" % text)
    print(tokens)

def runtest_topic3():
    runtest_head("Topic Test 3")
    text = "#NewLineTopic \nBank# Text"
    parser = TextParser()
    tokens = parser.parse(text)
    print("text=%r" % text)
    print(tokens)
    print("keywords=%s" % parser.keywords)


def runtest():
    runtest_topic1()
    runtest_topic2()
    runtest_topic3()

    runtest_head("Other Test")
    text   = """#Topic1# #Topic2 Test#
    #中文话题#
    This is a new line
    图片file:///data/temp/1.png
    文件file:///data/temp/1.zip
    link1:http://abc.com/test?name=1
    link2:https://abc.com/test?name=1&age=2 text after link
    数字123456END
    <code>test</code>
    """

    parser = TextParser()
    tokens = parser.parse(text)
    # print(tokens)
    print("input: %s" % text)
    print("output:")
    result = "".join(tokens)
    result = result.replace("<br/>", "\n<br/>\n")
    print(result)

if __name__ == '__main__':
    runtest()

