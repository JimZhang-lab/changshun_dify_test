'''
Author: JimZhang
Date: 2026-04-09 01:58:28
LastEditors: JimZhang
LastEditTime: 2026-04-09 13:27:00
FilePath: /changshun_dify_test/config/config.py
'''
import configparser
import os
import logging
from datetime import datetime

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_current_dir)
_config_file = os.path.join(_current_dir, 'conf.ini')

_parser = configparser.ConfigParser()
_parser.optionxform = str
if not _parser.read(_config_file, encoding='utf-8'):
    raise FileNotFoundError(f"配置文件不存在: {_config_file}")


def _resolve_path(path):
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(_project_root, path))


def _get(section, key):
    try:
        return _parser.get(section, key)
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        raise ValueError(f"conf.ini 缺少配置 [{section}] {key}: {e}")


class Config:
    run_timestamp = datetime.now().strftime("%m%d%H%M%S")

    def __init__(self):
        self.api_key = _get('DIFY', 'API_KEY')
        self.base_url = _get('DIFY', 'BASE_URL')
        self.app_type = _parser.get('DIFY', 'APP_TYPE', fallback='chatflow').lower()

        self.test_data_path = _resolve_path(_get('EVALUATE', 'TEST_FILE_PATH'))
        self.result_dir = _resolve_path(_parser.get('EVALUATE', 'RESULT_DIR', fallback='results'))
        self.max_workers = _parser.getint('EVALUATE', 'MAX_WORKERS', fallback=5)

        self.console_level = _parser.get('LOG', 'CONSOLE_LEVEL', fallback='INFO').upper()
        self.file_level = _parser.get('LOG', 'FILE_LEVEL', fallback='DEBUG').upper()
        self.log_target = _parser.get('LOG', 'TARGET', fallback='both').lower()
        log_template = _parser.get('LOG', 'FILE_PATH', fallback='logs/app.log')
        base, ext = os.path.splitext(log_template)
        self.log_file = _resolve_path(f"{base}_{self.run_timestamp}{ext}")

        # eval_llm options
        self.eval_client_method = _parser.get('EVAL_LLM', 'CLIENT_METHOD', fallback='request')
        self.eval_api_key = _parser.get('EVAL_LLM', 'API_KEY', fallback='')
        self.eval_base_url = _parser.get('EVAL_LLM', 'BASE_URL', fallback='')
        self.eval_model_name = _parser.get('EVAL_LLM', 'MODEL_NAME', fallback='')
        self.eval_max_token = _parser.getint('EVAL_LLM', 'MAX_TOKEN', fallback=20480)
        self.eval_temperature = _parser.getfloat('EVAL_LLM', 'TEMPERATURE', fallback=0.0)
        self.eval_enable_thinking = _parser.getboolean('EVAL_LLM', 'ENABLE_THINKING', fallback=False)
        self.eval_timeout = _parser.getfloat('EVAL_LLM', 'TIMEOUT', fallback=1200.0)
        self.eval_max_retries = _parser.getint('EVAL_LLM', 'MAX_RETRIES', fallback=3)

        os.makedirs(self.result_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.test_data_path), exist_ok=True)


cfg = Config()


def _init_logger():
    lg = logging.getLogger('dify_test')
    lg.setLevel(logging.DEBUG)
    lg.handlers.clear()
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    if cfg.log_target in ('console', 'both'):
        ch = logging.StreamHandler()
        ch.setLevel(getattr(logging, cfg.console_level, logging.INFO))
        ch.setFormatter(fmt)
        lg.addHandler(ch)

    if cfg.log_target in ('file', 'both'):
        fh = logging.FileHandler(cfg.log_file, encoding='utf-8')
        fh.setLevel(getattr(logging, cfg.file_level, logging.DEBUG))
        fh.setFormatter(fmt)
        lg.addHandler(fh)

    return lg


logger = _init_logger()