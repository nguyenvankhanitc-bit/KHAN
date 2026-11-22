"""Gửi thẻ thông báo vào Lark.

Cấu hình ở Thiết lập > Kỹ thuật > Tham số hệ thống, nhóm nhận thông báo Checklist GS dùng 1 trong 2 cách:
  1) Custom Bot (webhook) của nhóm - dùng được cả với nhóm "Bên ngoài" như BÁO CÁO GIÁM SÁT:
    store_checklist.lark_gs_webhook          Webhook URL của Custom Bot trong nhóm
    store_checklist.lark_gs_webhook_secret   (tuỳ chọn) khóa ký nếu bật "Xác minh chữ ký" cho Custom Bot
  2) App "Bot Odoo" (Lark Open Platform) - chỉ nhóm nội bộ (cùng tổ chức):
    store_checklist.lark_app_id / store_checklist.lark_app_secret / store_checklist.lark_gs_chat_id
Tuỳ chọn:
    store_checklist.lark_api_base     mặc định https://open.larksuite.com
    store_checklist.lark_link_base    địa chỉ Odoo cho nút "Xem chi tiết", mặc định web.base.url
Chưa cấu hình thì bỏ qua, không báo lỗi khi lưu phiếu.
"""
import base64
import hashlib
import hmac
import json
import logging
import threading
import time

import requests

_logger = logging.getLogger(__name__)

_TOKEN = {'key': None, 'value': None, 'exp': 0.0}
_TOKEN_LOCK = threading.Lock()
# Mã lỗi Lark khi token hết hạn / không hợp lệ -> xin token mới rồi gửi lại 1 lần
_TOKEN_ERRORS = {99991661, 99991663, 99991664, 99991668}


def lark_config(env):
    icp = env['ir.config_parameter'].sudo()
    link_base = icp.get_param('store_checklist.lark_link_base') or icp.get_param('web.base.url') or ''
    return {
        'app_id': (icp.get_param('store_checklist.lark_app_id') or '').strip(),
        'app_secret': (icp.get_param('store_checklist.lark_app_secret') or '').strip(),
        'gs_chat_id': (icp.get_param('store_checklist.lark_gs_chat_id') or '').strip(),
        'gs_webhook': (icp.get_param('store_checklist.lark_gs_webhook') or '').strip(),
        'gs_webhook_secret': (icp.get_param('store_checklist.lark_gs_webhook_secret') or '').strip(),
        'base': (icp.get_param('store_checklist.lark_api_base') or 'https://open.larksuite.com').strip().rstrip('/'),
        'link_base': link_base.strip().rstrip('/'),
    }


def _get_token(cfg, force=False):
    key = (cfg['base'], cfg['app_id'], cfg['app_secret'])
    with _TOKEN_LOCK:
        if not force and _TOKEN['key'] == key and _TOKEN['value'] and _TOKEN['exp'] > time.time() + 60:
            return _TOKEN['value']
        resp = requests.post(
            cfg['base'] + '/open-apis/auth/v3/tenant_access_token/internal',
            json={'app_id': cfg['app_id'], 'app_secret': cfg['app_secret']}, timeout=10)
        data = resp.json()
        if data.get('code') != 0:
            raise RuntimeError('Lark token: code=%s msg=%s' % (data.get('code'), data.get('msg')))
        _TOKEN.update(key=key, value=data['tenant_access_token'], exp=time.time() + int(data.get('expire') or 0))
        return _TOKEN['value']


def lark_call(cfg, method, path, what, **kwargs):
    """Gọi Open API của Lark kèm token; token hết hạn thì xin lại và gọi lại 1 lần. Lỗi thì raise RuntimeError."""
    for attempt in (1, 2):
        token = _get_token(cfg, force=attempt == 2)
        resp = requests.request(method, cfg['base'] + path, headers={'Authorization': 'Bearer ' + token},
                                timeout=10, **kwargs)
        try:
            data = resp.json()
        except ValueError:
            data = {'code': resp.status_code, 'msg': resp.text[:200]}
        if data.get('code') == 0:
            return data
        if attempt == 1 and data.get('code') in _TOKEN_ERRORS:
            continue
        raise RuntimeError('Lark %s: code=%s msg=%s' % (what, data.get('code'), data.get('msg')))


def lark_send_card(cfg, receive_id, card, id_type='chat_id'):
    """Gửi thẻ (interactive) tới nhóm (chat_id) hoặc người (open_id/email)."""
    return lark_call(cfg, 'POST', '/open-apis/im/v1/messages', 'gửi tin', params={'receive_id_type': id_type},
                     json={'receive_id': receive_id, 'msg_type': 'interactive',
                           'content': json.dumps(card, ensure_ascii=False)})


_SIGN_FAIL = 19021  # Lark: chữ ký sai / hết hạn


def _post_webhook(url, card, secret):
    payload = {'msg_type': 'interactive', 'card': card}
    if secret:
        ts = str(int(time.time()))
        sign = hmac.new(('%s\n%s' % (ts, secret)).encode('utf-8'), b'', digestmod=hashlib.sha256).digest()
        payload.update(timestamp=ts, sign=base64.b64encode(sign).decode('utf-8'))
    resp = requests.post(url, json=payload, timeout=10)
    try:
        data = resp.json()
    except ValueError:
        data = {'code': resp.status_code, 'msg': resp.text[:200]}
    return data.get('code', data.get('StatusCode')), data


def lark_send_webhook(url, card, secret=None):
    """Gửi thẻ qua Custom Bot (webhook) của nhóm; có secret thì ký theo quy định của Lark.
    Lark báo sai chữ ký (vd tham số secret nhập nhầm trong khi bot không bật xác nhận chữ ký) thì gửi lại không ký:
    bot có bật chữ ký thật thì lần gửi không ký cũng bị từ chối, nên không làm giảm bảo mật."""
    code, data = _post_webhook(url, card, secret)
    if code == _SIGN_FAIL and secret:
        _logger.warning('store_checklist: Lark báo sai chữ ký webhook, gửi lại không ký '
                        '(kiểm tra tham số store_checklist.lark_gs_webhook_secret)')
        code, data = _post_webhook(url, card, None)
    if code != 0:
        raise RuntimeError('Lark webhook: code=%s msg=%s' % (code, data.get('msg') or data.get('StatusMessage')))
    return data


def lark_card(title, rows, url=None, label='Xem chi tiết', template='purple', extra_md=None, note=None):
    """Thẻ Lark: tiêu đề màu, các dòng "Nhãn: giá trị", phần chi tiết thêm (markdown) và nút mở Odoo."""
    body = '\n'.join('**%s:** %s' % (key, value if value not in (None, False, '') else '—') for key, value in rows)
    elements = [{'tag': 'div', 'text': {'tag': 'lark_md', 'content': body}}]
    if extra_md:
        elements += [{'tag': 'hr'}, {'tag': 'div', 'text': {'tag': 'lark_md', 'content': extra_md}}]
    if url:
        elements.append({'tag': 'action', 'actions': [{
            'tag': 'button', 'type': 'primary', 'url': url,
            'text': {'tag': 'plain_text', 'content': label}}]})
    if note:
        elements.append({'tag': 'note', 'elements': [{'tag': 'plain_text', 'content': note}]})
    return {
        'config': {'wide_screen_mode': True},
        'header': {'template': template, 'title': {'tag': 'plain_text', 'content': title}},
        'elements': elements,
    }
