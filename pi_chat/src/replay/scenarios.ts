import { DisplayEvent, SCHEMA } from '../contract/display'
import type { Questionnaire } from '../projection/transcript'

export interface ReplayScenario {
  id: string
  title: string
  description: string
  events: DisplayEvent[]
  actions?: string[]
}

function makeRun(runId: string, startTs = Date.now()) {
  let seq = 0
  return (type: string, fields: Record<string, unknown> = {}): DisplayEvent =>
    ({
      schema: SCHEMA,
      schema_version: 1,
      type,
      run_id: runId,
      seq: seq++,
      ts: startTs + seq,
      ...fields,
    }) as DisplayEvent
}

const questionnaire: Questionnaire = {
  id: 'qst_replay_1',
  pending_id: 'qst_replay_1',
  title: '退款信息',
  description: '继续处理前，Agent 需要确认三项信息。',
  questions: [
    {
      id: 'order',
      header: '订单',
      question: '要退款的是哪个订单？',
      type: 'single',
      required: true,
      options: [
        { id: 'a1042', label: '订单 A-1042', description: '12 天前下单' },
        { id: 'b2099', label: '订单 B-2099', description: '45 天前下单' },
      ],
    },
    {
      id: 'reasons',
      question: '退款原因有哪些？',
      type: 'multi',
      required: true,
      min_selections: 1,
      max_selections: 2,
      options: [
        { id: 'damaged', label: '到货损坏' },
        { id: 'wrong', label: '商品错误' },
        { id: 'late', label: '到货延迟' },
      ],
    },
    {
      id: 'notes',
      question: '还有其他需要 Agent 知道的信息吗？',
      type: 'text',
      required: false,
      placeholder: '选填备注',
      max_length: 500,
    },
  ],
}

export const REPLAY_SCENARIOS: ReplayScenario[] = [
  {
    id: 'process',
    title: '工具、技能与压缩',
    description: '完整回放：思考、Dify 工具、技能激活、受限资料读取和真实压缩活动。',
    events: (() => {
      const run = makeRun('run_replay_process', 1_700_000_000_000)
      return [
        run('run.start', { conversation_id: 'replay-conv' }),
        run('message.user', { message_id: 'u1', text: '汇总订单 A-1042，并检查退款政策。' }),
        run('reasoning.delta', { reasoning_id: 'r1', delta: '应用政策前，我需要先确认订单状态。' }),
        run('reasoning.end', { reasoning_id: 'r1' }),
        run('message.start', { message_id: 'a1' }),
        run('message.delta', { message_id: 'a1', delta: '我先查询订单，再读取退款技能。' }),
        run('message.end', { message_id: 'a1', text: '我先查询订单，再读取退款技能。', stop_reason: 'toolUse', has_tool_calls: true }),
        run('tool.start', { tool_call_id: 'call_lookup', name: 'lookup_order', arguments: { order_id: 'A-1042' } }),
        run('tool.update', { tool_call_id: 'call_lookup', text: '已找到订单 A-1042' }),
        run('tool.end', {
          tool_call_id: 'call_lookup',
          name: 'lookup_order',
          status: 'ok',
          result: '订单 A-1042 · 已支付 · 12 天前下单',
          duration_ms: 840,
          artifacts: [{ id: 'art_1', name: 'order-summary.txt', mime_type: 'text/plain', size: 132, source: 'dify' }],
          execution_outcome: 'executed',
        }),
        run('skill.activate', { tool_call_id: 'call_skill', skill: 'refund-policy', source: 'app', activated_by: 'model' }),
        run('skill.read', { tool_call_id: 'call_skill', skill: 'refund-policy', path: 'guide.md', offset: 0, total_chars: 188, next_offset: null }),
        run('compaction.start', { tokens_before: 48_210, messages_kept: 4 }),
        run('compaction.end', { tokens_before: 48_210, summary_chars: 612, first_kept_entry_id: 'a1' }),
        run('message.start', { message_id: 'a2' }),
        run('message.delta', { message_id: 'a2', delta: '订单在 12 天前下单，仍在 30 天退款窗口内。' }),
        run('message.delta', { message_id: 'a2', delta: '政策要求商品未使用；退款前请先让用户确认。' }),
        run('message.end', {
          message_id: 'a2',
          text: [
            '订单在 12 天前下单，仍在 30 天退款窗口内。政策要求商品未使用，退款前请先让用户确认。',
            '',
            '**处理要点**',
            '',
            '- 已核对订单状态与下单时间',
            '- 已比对退款政策的 30 天窗口条款',
            '',
            '| 项目 | 值 |',
            '| --- | --- |',
            '| 订单 | A-1042 |',
            '| 窗口 | 30 天 |',
            '',
            '```bash',
            'refund --order A-1042 --dry-run',
            '```',
          ].join('\n'),
          stop_reason: 'stop',
          has_tool_calls: false,
        }),
        run('run.state', {
          status: 'completed',
          answer: '订单在 12 天前下单，仍在 30 天退款窗口内。政策要求商品未使用，退款前请先让用户确认。',
          stats: { model_requests: 3, tool_calls: 2, usage: { reported: { total_tokens: 6_240 }, estimated_tokens: 700, unknown_usage_requests: 0 } },
          state_ref: { revision: 7, delivery_status: 'encoded' },
        }),
        run('run.done', { status: 'completed' }),
      ]
    })(),
  },
  {
    id: 'questionnaire',
    title: '问卷暂停与答复',
    description: 'Agent 提出多题问卷，确定性暂停，并在下一轮收到答复后继续。',
    events: (() => {
      const run = makeRun('run_replay_question', 1_700_000_100_000)
      return [
        run('run.start', { conversation_id: 'replay-conv' }),
        run('message.user', { message_id: 'qu1', text: '请帮我发起退款。' }),
        run('message.start', { message_id: 'qa1' }),
        run('message.end', { message_id: 'qa1', text: '我先确认几项信息。', stop_reason: 'toolUse', has_tool_calls: true }),
        run('tool.start', { tool_call_id: 'call_ask', name: 'ask_user', arguments: { title: '退款信息' } }),
        run('question.asked', { questionnaire }),
        run('tool.end', { tool_call_id: 'call_ask', name: 'ask_user', status: 'awaiting_user', result: '问卷已展示。', execution_outcome: 'executed' }),
        run('run.state', { status: 'awaiting_user', answer: 'Agent 正在等待你的回答。', pending: { kind: 'ask_user', questionnaire } }),
        run('run.done', { status: 'awaiting_user' }),
      ]
    })(),
    actions: ['questionnaire'],
  },
  {
    id: 'multi',
    title: '多回合与折叠',
    description: '三个回合：前两回合完成态折叠进终态头，第三回合停在问卷等待。',
    events: (() => {
      const run = makeRun('run_replay_multi', 1_700_000_300_000)
      return [
        run('run.start', { conversation_id: 'replay-conv' }),
        // 第一回合：思考 + 工具 + 回答，完成折叠
        run('message.user', { message_id: 'mu1', text: '用 python 写一个快排完看看。' }),
        run('reasoning.delta', { reasoning_id: 'mr1', delta: '写一个带测试的快排。' }),
        run('reasoning.end', { reasoning_id: 'mr1' }),
        run('tool.start', { tool_call_id: 'mcall_write', name: 'write_file', arguments: { path: 'quicksort.py' } }),
        run('tool.end', { tool_call_id: 'mcall_write', name: 'write_file', status: 'ok', result: '已写入 quicksort.py', duration_ms: 420, execution_outcome: 'executed' }),
        run('tool.start', { tool_call_id: 'mcall_run', name: 'run_code', arguments: { cmd: 'python3 quicksort.py' } }),
        run('tool.end', { tool_call_id: 'mcall_run', name: 'run_code', status: 'ok', result: 'OK 20 万随机整数 → 通过', duration_ms: 1500, execution_outcome: 'executed' }),
        run('message.start', { message_id: 'ma1' }),
        run('message.end', {
          message_id: 'ma1',
          text: [
            '跑通了：`quicksort.py`。',
            '',
            '实现上做了三件事：',
            '',
            '1. **Hoare 分区 + 三数取中** — 全等值输入也保持 O(n log n)。',
            '2. **只递归较小的一侧** — 栈深度压到 O(log n)。',
            '3. **≤16 元素切插入排序** — 少一堆递归调用。',
          ].join('\n'),
          stop_reason: 'stop',
          has_tool_calls: false,
        }),
        run('run.state', { status: 'completed', answer: '跑通了。', stats: {}, state_ref: { revision: 2, delivery_status: 'encoded' } }),
        run('run.done', { status: 'completed' }),
        // 第二回合：纯文本回答，完成折叠
        run('message.user', { message_id: 'mu2', text: '复杂度分析再展开讲讲。' }),
        run('message.start', { message_id: 'ma2' }),
        run('message.end', { message_id: 'ma2', text: '平均 O(n log n)；三数取中把最坏退化压到近似 O(n log n)。', stop_reason: 'stop', has_tool_calls: false }),
        run('run.state', { status: 'completed', answer: '平均 O(n log n)。', stats: {}, state_ref: { revision: 3, delivery_status: 'encoded' } }),
        run('run.done', { status: 'completed' }),
        // 第三回合：停在问卷等待（不折叠）
        run('message.user', { message_id: 'mu3', text: '帮我顺手跑一个基准测试。' }),
        run('message.start', { message_id: 'ma3' }),
        run('message.end', { message_id: 'ma3', text: '我先确认几项信息。', stop_reason: 'toolUse', has_tool_calls: true }),
        run('tool.start', { tool_call_id: 'mcall_ask', name: 'ask_user', arguments: { title: '基准参数' } }),
        run('question.asked', { questionnaire }),
        run('tool.end', { tool_call_id: 'mcall_ask', name: 'ask_user', status: 'awaiting_user', result: '问卷已展示。', execution_outcome: 'executed' }),
        run('run.state', { status: 'awaiting_user', answer: 'Agent 正在等待你的回答。', pending: { kind: 'ask_user', questionnaire } }),
        run('run.done', { status: 'awaiting_user' }),
      ]
    })(),
    actions: ['questionnaire'],
  },
  {
    id: 'visualize',
    title: '可视化卡片',
    description: 'visualize 工具渲染沙箱交互卡：内联 SVG 排序可视化（零网络片段）。',
    events: (() => {
      const run = makeRun('run_replay_visualize', 1_700_000_400_000)
      const fragment = [
        '<div id="sort-viz">',
        '<div class="viz-controls">',
        '<button class="btn" id="shuffle-btn" type="button">打乱</button>',
        '<button class="btn btn-primary" id="play-btn" type="button">播放快排</button>',
        '<span class="viz-badge" id="sort-status">就绪</span>',
        '</div>',
        '<svg id="sort-svg" viewBox="0 0 400 160" width="100%" role="img" aria-label="数组柱状图"></svg>',
        '<style>#sort-viz .bar { fill: var(--viz-series-1); } #sort-viz .bar.pivot { fill: var(--viz-series-2); } #sort-viz .bar.done { fill: var(--viz-series-3); }</style>',
        '<script>',
        '(function () {',
        '  var root = document.getElementById("sort-viz");',
        '  var svg = root.querySelector("#sort-svg");',
        '  var status = root.querySelector("#sort-status");',
        '  var data = [];',
        '  function shuffle() {',
        '    data = Array.from({ length: 16 }, function (_, i) { return i + 1; });',
        '    for (var i = data.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = data[i]; data[i] = data[j]; data[j] = t; }',
        '    status.textContent = "就绪";',
        '    render(data, []);',
        '  }',
        '  function render(values, highlight) {',
        '    var width = 400 / values.length;',
        '    var parts = "";',
        '    for (var i = 0; i < values.length; i++) {',
        '      var h = values[i] / 17 * 150 + 8;',
        '      var cls = "bar" + (highlight.indexOf(i) >= 0 ? " pivot" : "");',
        '      parts += \'<rect class="\' + cls + \'" x="\' + (i * width + 1) + \'" y="\' + (160 - h) + \'" width="\' + (width - 2) + \'" height="\' + h + \'" rx="2"></rect>\';',
        '    }',
        '    svg.innerHTML = parts;',
        '  }',
        '  async function quicksort(lo, hi) {',
        '    if (lo >= hi) return;',
        '    var pivot = data[hi];',
        '    render(data, [hi]);',
        '    status.textContent = "分区中：枢轴 " + pivot;',
        '    var i = lo;',
        '    for (var j = lo; j < hi; j++) {',
        '      if (data[j] < pivot) { var t = data[i]; data[i] = data[j]; data[j] = t; i++; render(data, [hi]); await wait(120); }',
        '    }',
        '    var t2 = data[i]; data[i] = data[hi]; data[hi] = t2;',
        '    render(data, [i]);',
        '    await wait(160);',
        '    await quicksort(lo, i - 1);',
        '    await quicksort(i + 1, hi);',
        '  }',
        '  function wait(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }',
        '  root.querySelector("#shuffle-btn").addEventListener("click", shuffle);',
        '  root.querySelector("#play-btn").addEventListener("click", function () { quicksort(0, data.length - 1).then(function () { status.textContent = "完成"; }); });',
        '  shuffle();',
        '})();',
        '</script>',
        '</div>',
      ].join('\n')
      return [
        run('run.start', { conversation_id: 'replay-conv' }),
        run('message.user', { message_id: 'vu1', text: '做一个能调参数的排序算法可视化。' }),
        run('tool.start', { tool_call_id: 'call_viz1', name: 'visualize', arguments: { title: '快排演示', mode: 'inline' } }),
        run('tool.end', {
          tool_call_id: 'call_viz1',
          name: 'visualize',
          status: 'ok',
          result: 'Rendered "快排演示" as an inline card (1900 chars). The user sees the interactive card in the conversation.',
          duration_ms: 12,
          execution_outcome: 'executed',
          visual: { fragment, title: '快排演示', mode: 'inline', size_bytes: fragment.length },
        }),
        run('message.start', { message_id: 'va1' }),
        run('message.end', { message_id: 'va1', text: '卡片已生成：点「播放快排」看分区过程，「打乱」重置数组。', stop_reason: 'stop', has_tool_calls: false }),
        run('run.state', { status: 'completed', answer: '卡片已生成。', stats: {}, state_ref: { revision: 1, delivery_status: 'encoded' } }),
        run('run.done', { status: 'completed' }),
      ]
    })(),
  },
  {
    id: 'approval',
    title: '工具审批与未知写操作',
    description: '写工具需要单独审批；可批准、拒绝，或模拟远程结果未知。',
    events: (() => {
      const run = makeRun('run_replay_approval', 1_700_000_200_000)
      return [
        run('run.start', { conversation_id: 'replay-conv' }),
        run('message.user', { message_id: 'au1', text: '删除过期记录。' }),
        run('message.start', { message_id: 'aa1' }),
        run('message.end', { message_id: 'aa1', text: '该操作需要你的批准。', stop_reason: 'toolUse', has_tool_calls: true }),
        run('tool.start', { tool_call_id: 'call_delete', name: 'delete_record', arguments: { record: 'stale-14' } }),
        run('tool.end', { tool_call_id: 'call_delete', name: 'delete_record', status: 'awaiting_approval', result: '需要审批。', execution_outcome: 'not_executed' }),
        run('approval.requested', {
          approval: {
            pending_id: 'apv_replay_1',
            action_id: 'act_replay_1',
            tool_call_id: 'call_delete',
            tool: 'delete_record',
            arguments: { record: 'stale-14' },
            source: 'mcp',
            scope_options: ['once', 'session'],
          },
        }),
        run('run.state', { status: 'awaiting_approval', answer: 'Agent 正在等待你的批准。', pending: { kind: 'approval' } }),
        run('run.done', { status: 'awaiting_approval' }),
      ]
    })(),
    actions: ['approval'],
  },
]

export function scenarioById(id: string): ReplayScenario | null {
  return REPLAY_SCENARIOS.find((scenario) => scenario.id === id) || null
}
