"""Reader transforms and deterministic checks, independent of Qt and trading state."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation


def sections(markdown, show_answers=False):
    """Add stable heading anchors; withhold answer sections without changing source."""
    lines, headings, hidden, in_code = [], [], False, False
    for line in markdown.splitlines():
        if line.startswith('```'):
            in_code = not in_code
        match = None if in_code else re.match(r'^(#{1,6})\s+(.+)$', line)
        if match:
            title = match.group(2)
            hidden = not show_answers and any(word in title for word in ('答案', '解析', '参考解答'))
            anchor = 'section-' + str(len(headings))
            headings.append((title, anchor))
            lines.append(line)
            if hidden:
                lines.append('勾选「显示练习答案」后阅读本节。先自行完成练习，再对照解析。')
        elif not hidden:
            lines.append(line)
    return '\n'.join(lines), headings


def normalize_answer(value):
    return ''.join(unicodedata.normalize('NFKC', str(value)).casefold().split()).rstrip('。.')


def check_answer(check, answer):
    candidate = normalize_answer(answer)
    if not candidate:
        return False
    accepted = {normalize_answer(v) for v in check['answers']}
    if candidate in accepted:
        return True
    try:
        value = Decimal(candidate)
        return value.is_finite() and any(value == Decimal(other) for other in accepted
                                        if re.fullmatch(r'[-+]?\d+(?:\.\d*)?(?:e[-+]?\d+)?', other))
    except InvalidOperation:
        return False
