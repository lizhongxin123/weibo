# -*- coding: utf-8 -*-
import base64
import json
import random
import re
import urllib.parse

import binascii

import math
import requests
import rsa
import scrapy
import time

from weiboSpider.items import WeibospiderItem
from weiboSpider.YDMH import YDMHttp

class WeiboSpider(scrapy.Spider):
    name = 'weibo'
    allowed_domains = ['weibo.com']
    start_urls = ['http://weibo.com/']

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36"}
    username = "18650716462"
    password = "lzx1314541"
    filename = 'captcha1.jpg'
    login_url = 'https://login.sina.com.cn/sso/login.php?client=ssologin.js(v1.4.19)'


    # 1.重写入口函数,获取账号密文,发起预登陆
    def start_requests(self):
        # 账号
        su = self.get_su(self.username)
        # 时间
        td = str(int(time.time() * 1000))
        # 预登陆url
        prelogin_url = "http://login.sina.com.cn/sso/prelogin.php?entry=weibo&callback=sinaSSOController.preloginCallBack&su={0}&rsakt=mod&checkpin=1&client=ssologin.js(v1.4.19)&_={1}".format(su,td)
        yield scrapy.Request(prelogin_url, meta={"su": su},callback=self.prelogin_request)


    # 2.得到nonce、rsakv等参数,获取密码密文,发起登录请求
    def prelogin_request(self,response):

        # 2.1 提取关键参数
        try:
            serverData = eval(response.text.replace("sinaSSOController.preloginCallBack", ''))
            nonce = serverData["nonce"]
            servertime = serverData['servertime']
            rsakv = serverData['rsakv']
            pubkey = serverData['pubkey']
            pcid = serverData['pcid']
        except:
            print("第二步提取关键参数出错",response.url)

        # 2.2 密码
        sp = self.get_pass(self.password, servertime, nonce, pubkey)

        # 2.3 构建请求数据,formdata 的参数必须是字符串
        postdata = {
            'entry': 'weibo',
            'gateway': '1',
            'from': '',
            'savestate': '7',
            'useticket': '1',
            'pagerefer': "http://login.sina.com.cn/sso/logout.php?entry=miniblog&r=http%3A%2F%2Fweibo.com%2Flogout.php%3Fbackurl",
            'vsnf': '1',
            'su': response.meta.get("su"),
            'service': 'miniblog',
            'servertime': str(servertime),
            'nonce': nonce,
            'pwencode': "rsa2",
            'rsakv': rsakv,
            'sp': sp,
            'sr': '1366*768',
            'encoding': 'UTF-8',
            'prelt': "115",
            'url': 'http://weibo.com/ajaxlogin.php?framelogin=1&callback=parent.sinaSSOController.feedBackUrlCallBack',
            'returntype': "META",
        }

        # 2.4判断是否有验证码
        if serverData['showpin'] == 1:
            # 获取并保存验证码图片
            self.yanzma(pcid, self.filename)
            # 打码平台
            postdata["door"] = self.daMa(self.filename)
        # print(postdata)

        # 2.5 post登录请求
        yield scrapy.FormRequest(url=self.login_url, headers=self.headers, callback=self.login_request, formdata=postdata,meta={"servertime":servertime} ,dont_filter=True)


    # 3.正式登录，并自动跳转跳转url,获取ticket,ssosavestate,并构建uid_url,发起uid请求
    def login_request(self, response):
        try:
            servertime = response.meta.get("servertime")
            ticket, ssosavestate = re.findall(r'ticket=(.*?)&ssosavestate=(.*?)"', response.text)[0]  # 获取ticket和ssosavestate参数
            uid_url = 'https://passport.weibo.com/wbsso/login?ticket={}&ssosavestate={}&callback=sinaSSOController.doCrossDomainCallBack&scriptId=ssoscript0&client=ssologin.js(v1.4.19)&_={}'.format(ticket, ssosavestate,servertime)
        except:
            print("第三步获取uid_url出错",response.url)

        # 请求uid_url
        yield scrapy.Request(url=uid_url,callback=self.uid_request)


    # 4.获取uniqueid,发起主页请求
    def uid_request(self,response):
        try:
            uid = re.findall(r'"uniqueid":"(.*?)"', response.text)[0]
        except:
            print("第四步获取uniqueid出错",response.url)

        # 请求关注主页
        home_url = "https://weibo.com/{}/follow?rightmod=1&wvr=6".format(uid)
        yield scrapy.Request(url=home_url,callback=self.parse,meta={"uid":uid})


    # 5.请求关注主页,获取page_id,发起第1页请求
    def parse(self, response):
        try:
            page_id = re.findall(r"\$CONFIG\['page_id'\]='(.*?)'", response.text)[0]  # 获取page_id
            page_url = "https://weibo.com/p/{}/myfollow?t=1&cfs=&Pl_Official_RelationMyfollow__92_page=1".format(page_id)
        except:
            print("第五步获取page_id出错", response.url)

        yield scrapy.Request(url=page_url, callback=self.page_request,meta={"page_id":page_id})


    # 6.获取总页数，并循环遍历所有关注的页面
    def page_request(self,resopnse):
        try:
            page_num = int(re.findall(r"Pl_Official_RelationMyfollow__92_page=(.*?)#", resopnse.text)[-2])  # 获取page_num
            page_id = resopnse.meta.get("page_id")
        except:
            print("第六步获取page_num出错",resopnse.url)

        # 对每页发起请求
        p1 = "https://weibo.com/p/{}/myfollow?t=1&cfs=&Pl_Official_RelationMyfollow__92_page={}"
        for i in range(1, page_num + 1):
            p1_url = p1.format(page_id, i)
            yield scrapy.Request(url=p1.format(page_id, i),callback=self.detail_request)


    # 7.保存详情页信息,title,link
    def detail_request(self,response):
        weibo_item = WeibospiderItem()
        member_wrap = re.findall(r'title W_fb W_autocut[\s\S]*?href=([\s\S].*?)class[\s\S]*?title=([\s\S].*?)usercard', response.text)

        for item in member_wrap:
            link = item[0].strip()[4:-2]
            if "u" in link:
                link = link[2:]
            weibo_item["link"] = "https://weibo.com/" + link
            weibo_item["title"] = item[1].strip()[2:-2]
            print(weibo_item)
            yield weibo_item


    # 转码账号
    def get_su(self,username):
        username = urllib.parse.quote_plus(username)
        username = base64.b64encode(username.encode('utf-8'))
        return username.decode('utf-8')

    # 转换密码
    def get_pass(self,password, servertime, nonce, pubkey):
        # 获取公钥
        publicKey = int(pubkey, 16)  # 指定16进制
        key = rsa.PublicKey(publicKey, 65537)
        # 明文
        message = str(servertime) + '\t' + str(nonce) + '\n' + str(password)
        message = message.encode('utf-8')
        # 公钥加密
        password = rsa.encrypt(message, key)
        password = binascii.b2a_hex(password)  # 二进制转十六进制
        return password

    # 保存验证码图片
    def yanzma(self,pcid, filename):
        size = 0
        url = "http://login.sina.com.cn/cgi/pin.php"
        img_url = "{}?r={}&s={}&p={}".format(url, math.floor(random.random() * 100000000), size, pcid)
        resp = requests.get(img_url, headers=self.header, stream=True)
        with open(filename, 'wb') as f:
            for chunk in resp.iter_content():
                f.write(chunk)


    # 打码平台
    def daMa(self,filename):
        # 用户名
        username = 'lizhongxin123'

        # 密码
        password = 'lzx1314541'

        # 软件ＩＤ，开发者分成必要参数。登录开发者后台【我的软件】获得！
        appid = 5938

        # 软件密钥，开发者分成必要参数。登录开发者后台【我的软件】获得！
        appkey = '1f37b7f2b77cec58f18f5cf687122a8b'

        # 图片文件
        filename = filename

        # 验证码类型，# 例：1004表示4位字母数字，不同类型收费不同。请准确填写，否则影响识别率。在此查询所有类型 http://www.yundama.com/price.html
        codetype = 1005

        # 超时时间，秒
        timeout = 60

        # 初始化
        yundama = YDMHttp(username, password, appid, appkey)
        # 登陆云打码
        uid = yundama.login()
        print('uid: %s' % uid)
        # # 查询余额
        # balance = yundama.balance()
        # print('balance: %s' % balance)
        # 开始识别，图片路径，验证码类型ID，超时时间（秒），识别结果
        cid, result = yundama.decode(filename, codetype, timeout)
        return result


