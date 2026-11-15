# 第三方组件与许可证通知

AStock 0.6.1 使用 Python、Qt/PySide6 和下表组件。本页按 2026-11-15 构建环境中实际安装的 metadata 记录版本与上游声明；`third-party-licenses/` 原样保留安装包附带的许可证、版权、AUTHORS 和 NOTICE，并补充 Qt 官方开源许可全文。目录中的开发工具只是构建来源记录，不表示它们全部进入最终 EXE。最终二进制收集范围以交付包为准。

这些第三方条款不构成对 AStock 自身代码的统一授权；本次没有给项目添加 MIT 或其他项目许可证。各组件仍适用各自的原始条款。完整机器可读清单、原始 metadata 许可字段与文本 SHA256 见 [manifest.json](third-party-licenses/manifest.json)。

## Qt、PySide6 与 Shiboken6

本机 PySide6、PySide6 Essentials/Addons 和 Shiboken6 为 6.12.0。它们的 metadata 声明 `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`。wheel 只附 `LicenseRef-Qt-Commercial.txt`，本目录保留这一上游文件，同时补入官方 v6.12.0 仓库的 [LGPLv3](third-party-licenses/qt-open-source/LGPL-3.0-only.txt)、[GPLv2](third-party-licenses/qt-open-source/GPL-2.0-only.txt) 和 [GPLv3](third-party-licenses/qt-open-source/GPL-3.0-only.txt) 全文；commercial 文本不代表本项目持有 Qt 商业许可。原始文件来源和 Git blob 摘要见 [SOURCES.json](third-party-licenses/qt-open-source/SOURCES.json)。

版本对应源码入口：

- [PySide6 / Shiboken6 6.12.0 官方源码目录](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/)，文件为 `pyside-setup-everywhere-src-6.12.0.zip` 或 `.tar.xz`。
- [PySide 官方 v6.12.0 源码](https://github.com/pyside/pyside-setup/tree/v6.12.0)，包含 Shiboken。
- [Qt 6.12.0 官方完整源码 ZIP](https://download.qt.io/official_releases/qt/6.12/6.12.0/single/qt-everywhere-src-6.12.0.zip)；[Qt 官方下载说明](https://www.qt.io/development/offline-installers)。
- [Qt 许可与第三方组件说明](https://doc.qt.io/qt-6/licensing.html)；[PySide 第三方通知](https://doc.qt.io/qtforpython-6/licenses.html)。

程序以独立 DLL/扩展模块加载 Qt、PySide 和 Shiboken；保留便携包 `_internal` 目录结构，用户可在副本中替换兼容库。本项目没有修改这些库，也不额外限制针对库修改的调试或替换。Qt 内嵌组件有各自条款，不能用 LGPL 一项代替它们的通知；版本对应的版权和许可索引见 [QtBase v6.12.0 第三方目录](https://github.com/qt/qtbase/tree/v6.12.0/src/3rdparty)。本记录保存已安装发行物随附的文本和快速核实的官方来源，不声明已独立审计全部原生库的传递许可。WebEngine、PDF、Multimedia 和 QML/Quick 等模块在本项目构建配置中排除；环境清单仍保留它们已安装的 metadata，不能据此推断程序使用了这些模块。

## 组件清单

| 组件 | 版本 | 上游许可声明 | 范围与来源 |
|---|---|---|---|
| akshare | 1.20.42 | MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/akshare/1.20.42/)；[原始字段](third-party-licenses/akshare-1.20.42/METADATA-LICENSE.json) |
| altgraph | 0.17.5 | MIT | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/altgraph/0.17.5/)；[原始字段](third-party-licenses/altgraph-0.17.5/METADATA-LICENSE.json) |
| baostock | 0.9.4 | BSD License | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/baostock/0.9.4/)；[原始字段](third-party-licenses/baostock-0.9.4/METADATA-LICENSE.json) |
| beautifulsoup4 | 4.15.0 | MIT License | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/beautifulsoup4/4.15.0/)；[原始字段](third-party-licenses/beautifulsoup4-4.15.0/METADATA-LICENSE.json) |
| certifi | 2026.10.23 | MPL-2.0 | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/certifi/2026.10.23/)；[原始字段](third-party-licenses/certifi-2026.10.23/METADATA-LICENSE.json) |
| cffi | 2.1.1 | MIT-0 | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/cffi/2.1.1/)；[原始字段](third-party-licenses/cffi-2.1.1/METADATA-LICENSE.json) |
| charset-normalizer | 3.5.2 | MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/charset-normalizer/3.5.2/)；[原始字段](third-party-licenses/charset-normalizer-3.5.2/METADATA-LICENSE.json) |
| colorama | 0.4.6 | 见随附原文/metadata | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/colorama/0.4.6/)；[原始字段](third-party-licenses/colorama-0.4.6/METADATA-LICENSE.json) |
| curl_cffi | 0.17.0 | MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/curl-cffi/0.17.0/)；[原始字段](third-party-licenses/curl-cffi-0.17.0/METADATA-LICENSE.json) |
| et_xmlfile | 2.0.0 | MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/et-xmlfile/2.0.0/)；[原始字段](third-party-licenses/et-xmlfile-2.0.0/METADATA-LICENSE.json) |
| html5lib | 1.1 | MIT License | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/html5lib/1.1/)；[原始字段](third-party-licenses/html5lib-1.1/METADATA-LICENSE.json) |
| idna | 3.20 | BSD-3-Clause | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/idna/3.20/)；[原始字段](third-party-licenses/idna-3.20/METADATA-LICENSE.json) |
| iniconfig | 2.3.1 | MIT | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/iniconfig/2.3.1/)；[原始字段](third-party-licenses/iniconfig-2.3.1/METADATA-LICENSE.json) |
| lxml | 6.1.3 | BSD-3-Clause | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/lxml/6.1.3/)；[原始字段](third-party-licenses/lxml-6.1.3/METADATA-LICENSE.json) |
| mini-racer | 0.14.1 | ISC | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/mini-racer/0.14.1/)；[原始字段](third-party-licenses/mini-racer-0.14.1/METADATA-LICENSE.json) |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/numpy/2.5.4/)；[原始字段](third-party-licenses/numpy-2.5.4/METADATA-LICENSE.json) |
| openpyxl | 3.1.5 | MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/openpyxl/3.1.5/)；[原始字段](third-party-licenses/openpyxl-3.1.5/METADATA-LICENSE.json) |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/packaging/26.3/)；[原始字段](third-party-licenses/packaging-26.3/METADATA-LICENSE.json) |
| pandas | 2.3.3 | BSD-3-Clause（完整声明见原文） | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/pandas/2.3.3/)；[原始字段](third-party-licenses/pandas-2.3.3/METADATA-LICENSE.json) |
| pefile | 2024.8.26 | MIT | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/pefile/2024.8.26/)；[原始字段](third-party-licenses/pefile-2024.8.26/METADATA-LICENSE.json) |
| pluggy | 1.7.0 | MIT | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/pluggy/1.7.0/)；[原始字段](third-party-licenses/pluggy-1.7.0/METADATA-LICENSE.json) |
| pyarrow | 23.0.1 | Apache-2.0 | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/pyarrow/23.0.1/)；[原始字段](third-party-licenses/pyarrow-23.0.1/METADATA-LICENSE.json) |
| pycparser | 3.12 | BSD-3-Clause | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/pycparser/3.12/)；[原始字段](third-party-licenses/pycparser-3.12/METADATA-LICENSE.json) |
| Pygments | 2.21.0 | BSD-2-Clause | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/pygments/2.21.0/)；[原始字段](third-party-licenses/pygments-2.21.0/METADATA-LICENSE.json) |
| pyinstaller | 6.22.3 | GPL-2.0-or-later + bootloader exception（见原文） | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/pyinstaller/6.22.3/)；[原始字段](third-party-licenses/pyinstaller-6.22.3/METADATA-LICENSE.json) |
| pyinstaller-hooks-contrib | 2026.10 | 见随附原文/metadata | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/pyinstaller-hooks-contrib/2026.10/)；[原始字段](third-party-licenses/pyinstaller-hooks-contrib-2026.10/METADATA-LICENSE.json) |
| pyqtgraph | 0.14.0 | MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/pyqtgraph/0.14.0/)；[原始字段](third-party-licenses/pyqtgraph-0.14.0/METADATA-LICENSE.json) |
| PySide6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/pyside6/6.12.0/)；[原始字段](third-party-licenses/pyside6-6.12.0/METADATA-LICENSE.json) |
| PySide6_Addons | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/pyside6-addons/6.12.0/)；[原始字段](third-party-licenses/pyside6-addons-6.12.0/METADATA-LICENSE.json) |
| PySide6_Essentials | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/pyside6-essentials/6.12.0/)；[原始字段](third-party-licenses/pyside6-essentials-6.12.0/METADATA-LICENSE.json) |
| PySide6_Pdf | 6.12.0.140 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 已安装；构建配置排除对应 Qt 模块；[来源](https://pypi.org/project/pyside6-pdf/6.12.0.140/)；[原始字段](third-party-licenses/pyside6-pdf-6.12.0.140/METADATA-LICENSE.json) |
| PySide6_WebEngine | 6.12.0.140 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 已安装；构建配置排除对应 Qt 模块；[来源](https://pypi.org/project/pyside6-webengine/6.12.0.140/)；[原始字段](third-party-licenses/pyside6-webengine-6.12.0.140/METADATA-LICENSE.json) |
| pytest | 9.2.0 | MIT | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/pytest/9.2.0/)；[原始字段](third-party-licenses/pytest-9.2.0/METADATA-LICENSE.json) |
| pytest-qt | 4.5.0 | MIT | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/pytest-qt/4.5.0/)；[原始字段](third-party-licenses/pytest-qt-4.5.0/METADATA-LICENSE.json) |
| python-dateutil | 4.0.0 | BSD-3-Clause | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/python-dateutil/4.0.0/)；[原始字段](third-party-licenses/python-dateutil-4.0.0/METADATA-LICENSE.json) |
| pytz | 2026.6 | MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/pytz/2026.6/)；[原始字段](third-party-licenses/pytz-2026.6/METADATA-LICENSE.json) |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/pywin32-ctypes/0.2.3/)；[原始字段](third-party-licenses/pywin32-ctypes-0.2.3/METADATA-LICENSE.json) |
| requests | 2.34.2 | Apache-2.0 | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/requests/2.34.2/)；[原始字段](third-party-licenses/requests-2.34.2/METADATA-LICENSE.json) |
| ruff | 0.17.5 | MIT | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/ruff/0.17.5/)；[原始字段](third-party-licenses/ruff-0.17.5/METADATA-LICENSE.json) |
| setuptools | 84.2.1 | MIT | 构建/检查环境依赖；不等于随程序分发；[来源](https://pypi.org/project/setuptools/84.2.1/)；[原始字段](third-party-licenses/setuptools-84.2.1/METADATA-LICENSE.json) |
| shiboken6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/shiboken6/6.12.0/)；[原始字段](third-party-licenses/shiboken6-6.12.0/METADATA-LICENSE.json) |
| six | 1.17.0 | MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/six/1.17.0/)；[原始字段](third-party-licenses/six-1.17.0/METADATA-LICENSE.json) |
| soupsieve | 4.1 | MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/soupsieve/4.1/)；[原始字段](third-party-licenses/soupsieve-4.1/METADATA-LICENSE.json) |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/tqdm/4.70.1/)；[原始字段](third-party-licenses/tqdm-4.70.1/METADATA-LICENSE.json) |
| typing_extensions | 4.16.0 | PSF-2.0 | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/typing-extensions/4.16.0/)；[原始字段](third-party-licenses/typing-extensions-4.16.0/METADATA-LICENSE.json) |
| tzdata | 2026.6 | Apache-2.0 | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/tzdata/2026.6/)；[原始字段](third-party-licenses/tzdata-2026.6/METADATA-LICENSE.json) |
| urllib3 | 2.8.0 | MIT | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/urllib3/2.8.0/)；[原始字段](third-party-licenses/urllib3-2.8.0/METADATA-LICENSE.json) |
| webencodings | 0.6.1 | 见随附原文/metadata | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/webencodings/0.6.1/)；[原始字段](third-party-licenses/webencodings-0.6.1/METADATA-LICENSE.json) |
| xlrd | 2.0.2 | BSD | 运行依赖（最终收集范围以程序包为准）；[来源](https://pypi.org/project/xlrd/2.0.2/)；[原始字段](third-party-licenses/xlrd-2.0.2/METADATA-LICENSE.json) |

CPython 3.12.15 的原始许可历史和版权条款随附在 [LICENSE.txt](third-party-licenses/cpython-3.12.15/LICENSE.txt)。NumPy、PyArrow、lxml 等包中随附的第三方许可和 NOTICE 也保留在各自目录，不能只按表内顶层许可理解。PyInstaller bootloader 的特殊例外以其原始 COPYING 文本为准。

## 上游资料缺口

baostock 0.9.4 的 wheel 和官方 sdist 只有笼统 `BSD License` 声明，没有独立许可原文。本目录保留真实 metadata 和 [核查记录](third-party-licenses/baostock-0.9.4/UPSTREAM-STATUS.md)，没有将它自行改写成某种 BSD 许可，也不声明已获得上游未提供的额外授权。

数据接口的代码许可不等同于行情数据的再分发许可。公开包不携带本机 72 组真实行情验收资料；用户自行下载的数据仍受相应服务和数据来源条款约束。
