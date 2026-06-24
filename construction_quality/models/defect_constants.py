# -*- coding: utf-8 -*-
"""缺失改善：檢查類型(check_type) 與 缺失類別(defect_category) 的共用對應表

後台正向篩選（檢查類型 → 缺失類別選項）與 portal 反向反推（缺失類別 → 檢查類型）
共用同一份來源，避免規則散落各檔造成不一致。

放在 construction_quality（一般式/預約式/portal 的最小共同依賴），
不放最基礎的 construction_supervision_base，避免缺失改善規則污染基礎模組。
"""

# 檢查類型首字（缺失編號用，取代 general/reservation 各自重複的對照）
CHECK_TYPE_PREFIX = {
    'construction': '施',
    'safety_env': '安',
}

# 檢查類型 -> 該類型允許的缺失類別（順序即下拉顯示順序）
CHECK_TYPE_TO_CATEGORIES = {
    'construction': ['material', 'workmanship', 'dimension', 'document', 'other'],
    'safety_env': ['safety', 'environment'],
}

# 缺失類別 -> 檢查類型（portal 反推用：選類別自動決定檢查類型）
CATEGORY_TO_CHECK_TYPE = {
    cat: check_type
    for check_type, cats in CHECK_TYPE_TO_CATEGORIES.items()
    for cat in cats
}

# 各檢查類型的預設缺失類別（後台切換檢查類型時的兜底重設值）
CHECK_TYPE_DEFAULT_CATEGORY = {
    'construction': 'workmanship',
    'safety_env': 'safety',
}
