#!/usr/bin/env python
# -*- coding:utf-8 -*-
# outhor:李仲新 time:18-9-22
"""
调试文件
"""
from scrapy.cmdline import execute

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
execute(['scrapy', 'crawl', 'weibo'])