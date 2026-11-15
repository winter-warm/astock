"""QMT migration lessons: separate reading/quiz state from engine practice evidence."""

SOURCES = (
    ("迅投新手教程", "https://knowledge.thinktrader.net/docs/freshman/rookie.html"),
    ("迅投运行机制", "https://dict.thinktrader.net/innerApi/start_now.html"),
    ("迅投界面操作", "https://dict.thinktrader.net/innerApi/interface_operation.html"),
)

# Original teaching text, with explicit distinctions from the local simulator.
COURSES = [
    dict(id="orientation", title="01 认识完整终端", action="home", target="打开我的主页",
         body="""<h2>先记住四个工作区</h2><p>行情用于看证券和报价；模型研究用于管理、编辑和回测策略；
         模型交易用于配置策略运行；账户区域用于检查资金、持仓、委托和成交。学习中心是本软件额外提供的练习入口。</p>
         <p>在本软件依次打开这些入口，再回到模型研究找到策略编辑器。顶部的运行模式决定本次运行方式，
         切换页面只是查看内容，不会替你启动或停止策略。</p>
         <h3>换到 QMT</h3><p>使用完整客户端而非极简模式。行情连接、交易账户连接和策略运行是不同状态，
         不能因看到报价就认为交易账户已连接。本软件不登录券商账户。</p>""",
         question="切换到模型交易页面，会自动开始交易吗？", choices=["不会，页面与运行状态分开", "会自动运行当前代码"], answer=0),
    dict(id="data", title="02 行情与数据准备", action="data", target="打开数据中心",
         body="""<h2>先选证券、周期和数据范围</h2><ol><li>在行情中搜索证券，加入关注列表。</li>
         <li>打开数据中心，先用教学日线熟悉流程，再下载真实历史。</li><li>核对来源、起止日期、周期、缺口和权益资料。</li></ol>
         <p>分钟周期不是界面的刷新间隔。订阅到当前报价也不意味着历史 K 线已经下载。</p>
         <h3>换到 QMT</h3><p>先检查行情连接，再下载对应证券和周期的数据。回测日期必须有实际历史覆盖。
         主图证券、周期和复权设置也要核对。这里的教学数据为合成数据，不可当作真实收益证据。</p>""",
         question="已显示最新报价，能否据此确认三年历史已准备好？", choices=["可以", "不能，必须检查历史数据范围"], answer=1),
    dict(id="model", title="03 新建与编辑模型", action="research", target="进入模型研究",
         body="""<h2>把策略作为可保存的模型管理</h2><ol><li>模型研究中选择模板或新建模型，命名后打开策略编辑器。</li>
         <li>修改 PARAMETERS 声明后检查参数，参数表填写本次值。</li><li>保存，再打开回测设置。</li></ol>
         <p>导入自己的代码前先确认接口。AStock 使用 initialize / on_bar / on_quote / on_order，
         QMT 内置 Python 常用 init(ContextInfo) / handlebar(ContextInfo)。仅改函数名不能完成迁移。</p>
         <h3>换到 QMT</h3><p>在模型研究中创建 Python 模型，进入策略编辑器，配置基本信息、参数及回测参数。
         QMT 的 Python 库由客户端管理，与本项目的 uv 环境不同。</p>""",
         question="本项目策略能原样粘贴到 QMT 执行吗？", choices=["能，都是 Python", "不能，需要改写接口并重新验证"], answer=1),
    dict(id="backtest", title="04 配置与执行回测", action="setup", target="打开回测设置",
         body="""<h2>一次回测应能说明运行依据</h2><p>确认证券、数据周期、起止日期、初始资金、费用、滑点与基准，
         保存参数再运行。在历史回测查看运行依据，确认实际用到的数据和设置。</p>
         <p>先用同一数据只改变一个参数，保留两次结果，再做运行对比。收益比较必须同时查看最大回撤和费用。</p>
         <h3>换到 QMT</h3><p>策略编辑器提供回测参数。运行与回测有不同用途，不要把行情图上运行模型产生的信号当成成交。
         本软件采用下一根 K 线开盘的保守撮合，QMT 回测有自己的撮合机制；相同代码思想不保证相同收益。</p>""",
         question="两个平台收益不同，首先应该检查什么？", choices=["只看哪个收益更高", "数据、复权、参数、费用及撮合时点"], answer=1),
    dict(id="review", title="05 委托、成交与复盘", action="results", target="查看历史回测",
         body="""<h2>沿着一笔交易往回查</h2><ol><li>打开委托，检查方向、数量、状态和原因。</li>
         <li>打开成交，点击一笔记录定位图表。</li><li>看解释日志，核对信号出现时已知的数据。</li>
         <li>检查持仓、可卖数量和权益流水，最后导出报告。</li></ol>
         <p>已提交、部分成交和全部成交是不同状态；撤单只撤未成交部分，不能撤销已经发生的成交。</p>
         <h3>换到 QMT</h3><p>分别查看策略信号、委托和成交；出错时先查看消息与日志。
         将本地回测报告和 QMT 结果逐笔核对，先定位第一笔差异，再解释最终收益。</p>""",
         question="有买入信号是否代表已买入成功？", choices=["是", "不是，还要检查委托与成交回报"], answer=1),
    dict(id="execution", title="06 模型交易与停止", action="trading", target="进入模型交易",
         body="""<h2>把研究模型放进持续运行的账户</h2><p>本软件先连接行情，再启动策略仿真；手动练习建立独立账户。
         从左侧运行记录选择账户后，检查顶部账户标识，再执行暂停、继续或停止并撤单。</p>
         <p>历史回测暂停保留挂单；实时仿真暂停会撤单。关闭本软件会结束本地策略，不会后台继续。</p>
         <h3>换到 QMT</h3><p>模型交易中新建策略交易，选择模型、证券、周期、资金账号及运行模式。
         QMT 的模拟信号模式与模拟柜台账户不是同一概念：是否发委托和委托送往哪种柜台要分别确认。
         本软件的虚拟账户不是 QMT 模拟柜台。</p>""",
         question="QMT 运行模式写着“模拟”，就能说明用了模拟柜台吗？",
         choices=["不能，需要分别核对运行模式与资金账号", "可以，只看模式名称"], answer=0),
    dict(id="api", title="07 Python 接口迁移", action="api", target="查看本地策略接口",
         body="""<h2>按职责迁移，不机械替换函数名</h2><table border="1" cellpadding="6">
         <tr><th>职责</th><th>AStock</th><th>QMT 内置 Python</th></tr>
         <tr><td>初始化</td><td>initialize(ctx)</td><td>init(ContextInfo)</td></tr>
         <tr><td>观察行情</td><td>on_bar / on_quote</td><td>handlebar 或订阅回调</td></tr>
         <tr><td>读取历史</td><td>ctx.history</td><td>ContextInfo 的行情读取接口</td></tr>
         <tr><td>委托</td><td>ctx.order</td><td>passorder 等接口</td></tr></table>
         <p>QMT 的 handlebar 在盘中可能多次触发同一根 K 线，不等于本项目每根完成柱调用一次。
         迁移时要处理重复信号、订单状态和历史截止时间。quicktrade 参数会影响信号发送时机，必须查官方文档。</p>
         <p>先在 QMT 写只输出日志、不下单的 init / handlebar 模型，检查证券、周期及调用时刻；
         再迁移指标，最后在模拟环境核对订单。本项目暂未实现 QMT API 兼容层。</p>""",
         question="迁移 handlebar 时最容易忽略什么？", choices=["同一根 K 线可能多次回调", "函数名称大小写不影响 Python"], answer=0),
    dict(id="graduation", title="08 独立完成一次练习", action="practice", target="进入四课实作",
         body="""<h2>不用逐步提示，再做一次完整流程</h2><ol><li>选择证券与历史周期，说明数据来源。</li>
         <li>复制一个模型并修改一个参数，保留原模型。</li><li>设置回测，指出一笔成交对应的信号与费用。</li>
         <li>比较两次运行，并说出哪些条件相同。</li><li>启动离线演练或实时仿真，找到账户并停止撤单。</li></ol>
         <p>四课实作由实际引擎回报记录完成证据。本迁移课程的答题通过只表示知识自测，
         不表示已经操作过 QMT，更不表示策略已经可以实盘使用。</p>
         <h3>带到 QMT 的检查单</h3><p>能够找到模型研究、编辑器、历史下载、回测参数、模型交易、账户、委托、成交与日志；
         能解释接口与撮合差异。初次迁移用模拟环境逐项验证。</p>""",
         question="这组自测全部通过，表示什么？", choices=["已通过 QMT 实盘验收", "通过知识自测，仍需实作及 QMT 环境验证"], answer=1),
]
