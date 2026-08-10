# -*- coding: utf-8 -*-
"""匯出時的記錄篩選條件。

專案層級的彙總樣板（缺失／自主檢查／檢試驗／送審管制表）原本一律列出該專案
「全部」記錄——工程案件表單上的匯出按鈕就是這個語意。批次下載中心要能限定
期間（例如只要這個月的缺失管制表），但又不能改變既有按鈕的輸出。

作法是讓呼叫端用 context 帶日期區間，對照表在 search 時把這裡組出來的 domain
片段接上去。context 沒帶時回空 list，既有按鈕的行為與輸出完全不變。

## 日期空白的記錄一律列入

有些日期本來就不一定要填（例如非廠驗案件不會有廠驗日期），把它們排除等於
「使用者看不到、也不知道自己少了東西」。所以日期區間**不排除**日期空白的
記錄，改由 undated_warning() 明講有哪幾筆，讓人自己判斷要不要去補資料。
"""

CTX_FROM = 'export_date_from'
CTX_TO = 'export_date_to'

# 提醒訊息最多列幾筆記錄名稱，其餘用「等 N 筆」帶過
_PREVIEW_LIMIT = 8


def has_range(env):
    """呼叫端有沒有指定日期區間"""
    return bool(env.context.get(CTX_FROM) or env.context.get(CTX_TO))


def date_domain(env, field):
    """依 context 的匯出日期區間組出 domain 片段。

    :param env: 記錄集的 environment（context 從這裡讀）
    :param field: 要比對的日期欄位名稱，各報表不同（通知日／檢查日／進場日…）
    :return: domain 片段 list，context 沒帶日期時為 []

    日期空白的記錄一律通過（見模組說明）。
    """
    if not has_range(env):
        return []

    ranged = []
    if env.context.get(CTX_FROM):
        ranged.append((field, '>=', env.context[CTX_FROM]))
    if env.context.get(CTX_TO):
        ranged.append((field, '<=', env.context[CTX_TO]))

    # 前綴式（波蘭式）domain：'|' 吃後面兩個條件，兩個區間條件先用 '&' 併成一個
    return ['|', (field, '=', False)] + ['&'] * (len(ranged) - 1) + ranged


def undated_records(env, model_name, field, project_id):
    """日期區間生效時，該日期欄位空白的記錄（它們會被一併列入匯出）"""
    if not has_range(env):
        return env[model_name].browse()
    domain = [(field, '=', False)]
    if project_id:
        domain.append(('project_id', '=', project_id))
    return env[model_name].search(domain)


def undated_warning(env, model_name, field, label, project_id=None):
    """回報「有幾筆沒填日期、已一併列入」，格式與 mapping 的 WARNINGS 相同。

    :param label: 給人看的日期欄位名稱，例如「進場日期」
    :return: 訊息 list（沒有要提醒的事就是空 list）
    """
    records = undated_records(env, model_name, field, project_id)
    if not records:
        return []
    names = records[:_PREVIEW_LIMIT].mapped('display_name')
    more = ('等 %s 筆' % len(records)) if len(records) > _PREVIEW_LIMIT else ''
    return ['有 %s 筆沒有填「%s」。這些記錄**已一併列入**本次匯出（日期區間不會'
            '排除它們），但如果你要的是「這段期間」的資料，請確認是否該補上日期：\n'
            '%s%s' % (len(records), label, '、'.join(names), more)]


def project_warning(project, model_name, field, label):
    """專案層級對照表用的 WARNINGS 捷徑"""
    return undated_warning(project.env, model_name, field, label, project.id)
