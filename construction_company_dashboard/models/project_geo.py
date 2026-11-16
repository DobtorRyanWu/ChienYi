# -*- coding: utf-8 -*-
"""標案地圖的定位功能（淞源 2026-11-10 會議 C6；使用者 2026-11-13 決定三件都做）。

現況（2026-11-13 查 dev）：170 個工程只有 1 個有座標——座標只有「手機建工程時按了取得 GPS」才會寫入，
而且工程進入施工中之後，表單上的經緯度是唯讀的。所以地圖幾乎是空的。這裡補三件事：

1. 在地圖上點位置：標案地圖頁對沒座標的工程（與外部標案）按「定位」，在地圖上點一下就存。
   前端直接用 ORM 的 write（有寫入權的人才存得進去）；工程表單另有「在地圖上定位」按鈕開到同一頁。
2. 用地點文字自動定位（action_dash_geocode）：拿「工程地點／履約地點」的文字向外部地理編碼服務查座標。
   * 預設用 OpenStreetMap 的 Nominatim（免金鑰）。只送地點文字，不送工程名稱、編號或任何帳號資訊。
   * 遵守它的使用規則：一秒最多一個請求、帶可辨識的 User-Agent、不大量批次——所以一次最多查 GEOCODE_BATCH_LIMIT 個。
     「一秒一個」要跨呼叫成立（淞源權限審查 low #7）：同一時間只讓一個自動定位在跑（PostgreSQL 交易層級的
     advisory lock，跨請求、跨 worker；別人正在查就回「請稍候」，不排隊卡住 worker），而且每個請求「之前」都等
     GEOCODE_MIN_INTERVAL_SECONDS——鎖保證上一次的交易已經結束，但它的最後一個請求可能才剛送出。
     鎖只在同一個資料庫內有效：同一台主機上好幾個庫同時按，仍可能同時送（沒處理）。
   * 查到的座標標成「地點文字自動定位（請確認）」：地址定位不一定準，地圖上可以再點一次修正。
   * 這個服務查不到臺灣的門牌（2026-11-13 實測：「…市府路1號」查不到，「…市府路」「…信義區」查得到），
     所以整段文字查不到時會退一級再查：先拿掉門牌只留到路段，再不行只查行政區（geocode_candidates）。
     退一級查到的只是大概位置，回傳時標 approx，畫面會提醒。
   * 系統參數 construction_company_dashboard.geocode_url 可以換成自架或其他相容的服務；設成 off 就停用。
3. 外部標案圖層的資料（get_dash_map_extras）：見 external_tender.py。

兩支方法列在 method_gate.DASHBOARD_METHODS（前端呼叫的方法都要在那張表上）；
自動定位是寫入：受限帳號（營造方、角色帳號、控台讀取）在方法裡直接拒絕。
"""
import logging
import re
import time
import zlib

import requests

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .external_tender import GEO_SOURCE_GEOCODED, GEO_SOURCE_SELECTION, MAP_STAGES

_logger = logging.getLogger(__name__)

TENDER_MODEL = 'construction.external.tender'
GEOCODE_PARAM = 'construction_company_dashboard.geocode_url'
GEOCODE_DEFAULT_URL = 'https://nominatim.openstreetmap.org/search'
GEOCODE_OFF = 'off'
GEOCODE_USER_AGENT = 'odoo-construction-site-map/18.0'      # 不帶任何公司、個人或站台資訊
GEOCODE_TIMEOUT_SECONDS = 10
GEOCODE_MIN_INTERVAL_SECONDS = 1.1          # Nominatim 的使用規則：每秒最多一個請求
# 「同一時間只讓一個自動定位在跑」的 advisory lock 鍵（固定值：同一個庫的每個 worker 都要算出同一個）
GEOCODE_LOCK_KEY = zlib.crc32(b'construction_company_dashboard.geocode')
GEOCODE_BATCH_LIMIT = 10                    # 一次最多查幾個（一個請求大約十幾秒內做完；也避免變成大量批次）
GEOCODE_COUNTRY = 'tw'
GEOCODE_LANGUAGE = 'zh-TW'
# 查回來的座標要落在臺灣附近（含離島），不然多半是同名的外國地點
TAIWAN_LATITUDE_RANGE = (21.5, 26.5)
TAIWAN_LONGITUDE_RANGE = (117.5, 123.0)
EXTERNAL_MAP_LIMIT = 500                    # 地圖上最多畫幾個外部標案
# 地址退一級的切法：①門牌（數字＋號／巷／弄／樓／之）以後拿掉，只留到路段；②只留「縣市＋鄉鎮區」
STREET_PART = re.compile(r'^(.*?[路街道段])\s*[0-9０-９一二三四五六七八九十百]+\s*(?:號|巷|弄|樓|之).*$')
DISTRICT_PART = re.compile(r'(?:[\u4e00-\u9fff]{1,4}[縣市])?[\u4e00-\u9fff]{1,4}[鄉鎮區]')
KIND_PROJECT = 'project'
KIND_TENDER = 'tender'
MAP_PAGE_TAG = 'company_dashboard_map'      # 同 static/src/dashboard_page/dash_common.js 的 MAP_PAGE_TAG


class GeocodeFailed(Exception):
    """查不到或服務不通；訊息是給使用者看的原因。"""


def geocode_text(url, text):
    """地點文字 → (緯度, 經度)。查不到、不在臺灣範圍、服務不通都丟 GeocodeFailed。"""
    try:
        response = requests.get(url, params={
            'q': text, 'format': 'jsonv2', 'limit': 1, 'countrycodes': GEOCODE_COUNTRY,
            'accept-language': GEOCODE_LANGUAGE,
        }, headers={'User-Agent': GEOCODE_USER_AGENT}, timeout=GEOCODE_TIMEOUT_SECONDS)
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError) as exc:
        _logger.warning('地理編碼服務沒有回應：%s', exc)
        raise GeocodeFailed('定位服務沒有回應') from exc
    if not isinstance(results, list) or not results:
        raise GeocodeFailed('查不到這個地點')
    try:
        latitude, longitude = float(results[0]['lat']), float(results[0]['lon'])
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocodeFailed('定位服務回傳的資料看不懂') from exc
    if not (TAIWAN_LATITUDE_RANGE[0] <= latitude <= TAIWAN_LATITUDE_RANGE[1]
            and TAIWAN_LONGITUDE_RANGE[0] <= longitude <= TAIWAN_LONGITUDE_RANGE[1]):
        raise GeocodeFailed('查到的位置不在臺灣範圍內')
    return latitude, longitude


def geocode_candidates(text):
    """要依序試的查詢文字：整段 → 只到路段 → 只到行政區（重複的、空的不列）。"""
    text = ' '.join((text or '').split())
    candidates = [text]
    street = STREET_PART.match(text)
    if street:
        candidates.append(street.group(1).strip())
    district = DISTRICT_PART.search(text)
    if district:
        candidates.append(district.group(0))
    unique = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


class ProjectProjectGeo(models.Model):
    _inherit = 'project.project'

    dash_geo_source = fields.Selection(
        GEO_SOURCE_SELECTION, string='座標來源', readonly=True, copy=False,
        help='座標是在標案地圖上標定的，還是用工程地點文字自動定位的（自動定位不一定準，請在地圖上確認）。'
             '手機建工程時取得的 GPS、匯入或手填的座標沒有這個標記。')

    # ── 地圖頁的額外資料 ──────────────────────────────────────────────────
    @api.model
    def _dash_geocode_url(self):
        """地理編碼服務的網址；停用回 False。"""
        value = (self.env['ir.config_parameter'].sudo().get_param(GEOCODE_PARAM) or GEOCODE_DEFAULT_URL).strip()
        return False if value.lower() == GEOCODE_OFF else value

    @api.model
    def _dash_can_locate(self):
        """目前使用者能不能改工程的座標：受限帳號一律不行，其餘看工程的寫入 ACL。"""
        return bool(not self.env.user._dash_is_restricted() and self.has_access('write'))

    @api.model
    def get_dash_map_extras(self):
        """標案地圖頁的額外資料：能不能定位、有沒有開自動定位、外部標案圖層。

        回傳 {'can_locate', 'geocode_enabled', 'geocode_batch',
              'external': {'status': 'ok'／'no_access', 'can_edit', 'items': [...], 'count'}}
        external.items：id、name、agency、stage、stage_label、deadline（ISO 或 False）、amount、currency、location、
                        lat、lng（沒座標是 False）、geo_source
        """
        result = {'can_locate': False, 'geocode_enabled': False, 'geocode_batch': GEOCODE_BATCH_LIMIT,
                  'external': {'status': 'no_access', 'can_edit': False, 'items': [], 'count': 0}}
        if self._dash_blocked_reason():
            return result
        result['can_locate'] = self._dash_can_locate()
        result['geocode_enabled'] = bool(result['can_locate'] and self._dash_geocode_url())
        Tender = self.env[TENDER_MODEL]
        if self.env.user._dash_is_restricted() or not Tender.has_access('read'):
            return result
        domain = [('stage', 'in', MAP_STAGES)]
        stage_labels = dict(Tender._fields['stage'].selection)
        items = [{
            'id': tender.id,
            'name': tender.name,
            'agency': tender.agency or '',
            'stage': tender.stage,
            'stage_label': stage_labels.get(tender.stage, ''),
            'deadline': fields.Date.to_string(tender.deadline_date) if tender.deadline_date else False,
            'amount': tender.budget_amount or 0.0,
            'currency': tender.currency_id.symbol or '',
            'location': tender.location or '',
            'lat': tender.latitude or False,
            'lng': tender.longitude or False,
            'geo_source': tender.geo_source or False,
        } for tender in Tender.search(domain, limit=EXTERNAL_MAP_LIMIT)]
        result['external'] = {'status': 'ok', 'can_edit': Tender.has_access('write'), 'items': items,
                              'count': Tender.search_count(domain)}
        return result

    # ── 用地點文字自動定位 ────────────────────────────────────────────────
    @api.model
    def _dash_geocode_targets(self, kind):
        """(模型, 還沒座標而且有地點文字的紀錄, 還沒座標但沒有地點文字的筆數)；以呼叫者自己的權限找。"""
        unlocated = ['|', ('latitude', '=', False), ('latitude', '=', 0), '|', ('longitude', '=', False),
                     ('longitude', '=', 0)]
        if kind == KIND_PROJECT:
            Model, scope = self.env['project.project'], [('state', '=', 'construction'), ('active', '=', True)]
        elif kind == KIND_TENDER:
            Model, scope = self.env[TENDER_MODEL], [('stage', 'in', MAP_STAGES)]
        else:
            raise UserError('不認得的定位對象。')
        with_text = Model.search(scope + unlocated + [('location', '!=', False), ('location', '!=', '')], order='id')
        without_text = Model.search_count(scope + unlocated + ['|', ('location', '=', False), ('location', '=', '')])
        return Model, with_text, without_text

    @api.model
    def _dash_geocode_lock(self):
        """同一時間只讓一個自動定位在跑（跨請求、跨 worker）：交易層級的 advisory lock，交易結束（含出錯回滾）自動放開。
        拿不到＝別人正在查 → 請稍候。不排隊等：一次最多要十幾秒，排隊會把 worker 卡住。"""
        self.env.cr.execute('SELECT pg_try_advisory_xact_lock(%s)', [GEOCODE_LOCK_KEY])
        if not self.env.cr.fetchone()[0]:
            raise UserError('別人正在使用自動定位，請稍候幾秒再試。')

    @api.model
    def action_dash_geocode(self, kind=KIND_PROJECT):
        """把還沒座標的工程（或外部標案）用地點文字查座標，一次最多 GEOCODE_BATCH_LIMIT 個。

        回傳 {'located': [{'id', 'name', 'lat', 'lng', 'approx'（退一級才查到：只是路段或行政區的位置）}],
              'failed': [{'id', 'name', 'reason'}],
              'remaining'（這次沒輪到、還可以再查的筆數）, 'no_location'（沒有地點文字、查不了的筆數）}
        """
        if self.env.user._dash_is_restricted():
            raise AccessError('您的帳號是唯讀帳號，不能替工程定位。')
        url = self._dash_geocode_url()
        if not url:
            raise UserError('自動定位已停用（系統參數 %s）。請直接在地圖上點位置。' % GEOCODE_PARAM)
        Model, candidates, no_location = self._dash_geocode_targets(kind)
        Model.check_access('write')
        batch = candidates[:GEOCODE_BATCH_LIMIT]
        if batch:
            self._dash_geocode_lock()
        source_field = 'dash_geo_source' if kind == KIND_PROJECT else 'geo_source'
        located, failed = [], []
        for record in batch:
            found, reason = None, ''
            for level, query in enumerate(geocode_candidates(record.location)):
                # 每個請求之前都等（不只是每筆之間，也含這次的第一個：上一次自動定位的最後一個請求可能才剛送出）
                time.sleep(GEOCODE_MIN_INTERVAL_SECONDS)
                try:
                    found = geocode_text(url, query) + (bool(level),)
                    break
                except GeocodeFailed as exc:
                    reason = reason or str(exc)                     # 回報整段文字那一次的原因
            if not found:
                failed.append({'id': record.id, 'name': record.name, 'reason': reason})
                continue
            latitude, longitude, approx = found
            record.write({'latitude': latitude, 'longitude': longitude, source_field: GEO_SOURCE_GEOCODED})
            located.append({'id': record.id, 'name': record.name, 'lat': latitude, 'lng': longitude, 'approx': approx})
        return {'located': located, 'failed': failed, 'remaining': len(candidates) - len(batch),
                'no_location': no_location}

    # ── 工程表單的「在地圖上定位」 ─────────────────────────────────────────
    def action_dash_locate_on_map(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': MAP_PAGE_TAG, 'name': '標案地圖',
                'params': {'locate_project_id': self.id}}
