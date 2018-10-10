# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://doc.scrapy.org/en/latest/topics/item-pipeline.html



import pymysql
from twisted.enterprise import adbapi


# 方式一：　这是一种同步操作，会因为数据写入的速度慢于数据爬取的速度，导致整个程序执行变慢.
class MysqlPiple(object):
    # 采用同步的机制写入mysql
    def __init__(self):
        self.conn = pymysql.connect('localhost', 'root', 'lizhongxin', 'weibo', charset="utf8",use_unicode=True)
        self.cursor = self.conn.cursor()

    def process_item(self, item, spider):
        insert_sql = """insert into weibo_tb(link,title) VALUES (%s, %s)"""
        self.cursor.execute(insert_sql, (item["link"], item["title"]))
        self.conn.commit()
        print("保存一条数据成功")


# 方式二：这是一种异步操作，适用于大量数据
class WeibospiderPipeline(object):
    def __init__(self, dbpool):
        self.dbpool = dbpool

    # 类方法，读取setting.py文件里的mysql配置
    @classmethod
    def from_settings(cls, settings):
        dbparms = dict(
            host = settings["MYSQL_HOST"],
            db = settings["MYSQL_DBNAME"],
            user = settings["MYSQL_USER"],
            passwd = settings["MYSQL_PASSWORD"],
            cursorclass= pymysql.cursors.DictCursor,
            charset="utf8",
            use_unicode=True,
        )
        # adbapi.ConnectionPool 异步连接
        dbpool = adbapi.ConnectionPool("MySQLdb", **dbparms)
        return cls(dbpool)

    def process_item(self, item, spider):
        # 使用twisted将mysql插入变成异步执行
        query = self.dbpool.runInteraction(self.do_insert, item)
        query.addErrback(self.handle_error, item, spider)  # 处理异常

    def handle_error(self, failure, item, spider):
        # 处理异步插入的异常
        print(failure)

    def do_insert(self, cursor, item):
        # 执行具体的插入
        # 根据不同的item 构建不同的sql语句并插入到mysql中
        insert_sql = """insert into weibo_tb(link,title) VALUES (%s, %s)"""
        params = (item["link"], item['title'])
        cursor.execute(insert_sql, params)