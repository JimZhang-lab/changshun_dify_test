'''
Author: JimZhang
Date: 2026-04-09 01:58:28
LastEditors: 很拉风的James
LastEditTime: 2026-04-09 02:02:29
FilePath: /changshun_dify_test/config/config.py
Description: 

'''
import configparser
import os
import logging

current_dir = os.path.dirname(os.path.abspath(__file__))
config_file_path = os.path.join(current_dir, 'conf.ini')
project_root = os.path.dirname(current_dir)

config = configparser.ConfigParser()
config.read(config_file_path, encoding='utf-8')

try:
    API_KEY = config.get('Dify', 'api_key')
    BASE_URL = config.get('Dify', 'base_url')
    TEST_DATA_PATH = config.get('test_data', 'file_path')
    
    if not os.path.isabs(TEST_DATA_PATH):
        TEST_DATA_PATH = os.path.abspath(os.path.join(project_root, TEST_DATA_PATH))
except (configparser.NoSectionError, configparser.NoOptionError) as e:
    raise ValueError(f"配置文件解析失败: {e}")

LOG_LEVEL = config.get('log', 'level', fallback='INFO').upper()
LOG_TARGET = config.get('log', 'target', fallback='both').lower()
LOG_FILE = config.get('log', 'file_path', fallback='logs/app.log')

if not os.path.isabs(LOG_FILE):
    LOG_FILE = os.path.abspath(os.path.join(project_root, LOG_FILE))

logger = logging.getLogger('dify_test')
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
logger.handlers.clear()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

if LOG_TARGET in ('console', 'both'):
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

if LOG_TARGET in ('file', 'both'):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)