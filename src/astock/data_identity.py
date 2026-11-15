"""Consistent, explicit data provenance for selections, charts and saved runs."""


def is_index(meta):
    rules = (meta or {}).get('rules') or {}
    return bool(meta and (meta.get('asset_class') == 'index' or
                         rules and all(getattr(rule, 'kind', None) == 'index' for rule in rules.values())))


def origin_label(meta):
    if not meta:
        return '数据来源未记录'
    source = str(meta.get('source', ''))
    if meta.get('demo') or source.startswith(('astock-synthetic', 'astock-equity-lesson')):
        return '合成教学数据'
    if source in ('tencent-recording', 'astock-live-input-v1'):
        return '真实行情录制'
    if source.startswith('akshare-'):
        return '真实历史数据' + (' · 指数（研究用）' if is_index(meta) else '')
    return '导入数据 · 真实性待核对'


def display_name(meta):
    name = (meta or {}).get('name', '未选择数据')
    for prefix in ('合成教学 · ', '真实历史 · ', '教学 · '):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return f'{origin_label(meta)}｜{name}'


def source_summary(meta):
    meta = meta or {}
    return (f"{origin_label(meta)} · 来源：{meta.get('source', '未记录')} · 周期：{meta.get('period', '—')}\n"
            f"实际覆盖：{str(meta.get('start', '未知'))[:19]} 至 {str(meta.get('end', '未知'))[:19]}" +
            ('\n指数点位用于观察和策略信号研究，指数本体不能直接下单。' if is_index(meta) else ''))
