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
  title: 'Refund details',
  description: 'The agent needs three details before it can continue.',
  questions: [
    {
      id: 'order',
      header: 'Order',
      question: 'Which order should be refunded?',
      type: 'single',
      required: true,
      options: [
        { id: 'a1042', label: 'Order A-1042', description: 'Placed 12 days ago' },
        { id: 'b2099', label: 'Order B-2099', description: 'Placed 45 days ago' },
      ],
    },
    {
      id: 'reasons',
      question: 'What are the reasons?',
      type: 'multi',
      required: true,
      min_selections: 1,
      max_selections: 2,
      options: [
        { id: 'damaged', label: 'Damaged on arrival' },
        { id: 'wrong', label: 'Wrong item' },
        { id: 'late', label: 'Arrived late' },
      ],
    },
    {
      id: 'notes',
      question: 'Anything else the agent should know?',
      type: 'text',
      required: false,
      placeholder: 'Optional notes',
      max_length: 500,
    },
  ],
}

export const REPLAY_SCENARIOS: ReplayScenario[] = [
  {
    id: 'process',
    title: 'Tool, skill and compaction',
    description: 'A complete run with reasoning, a Dify tool, a skill activation, a bounded resource read and real compaction activity.',
    events: (() => {
      const run = makeRun('run_replay_process', 1_700_000_000_000)
      return [
        run('run.start', { conversation_id: 'replay-conv' }),
        run('message.user', { message_id: 'u1', text: 'Summarize order A-1042 and check the refund policy.' }),
        run('reasoning.delta', { reasoning_id: 'r1', delta: 'I need the order state before applying the policy.' }),
        run('reasoning.end', { reasoning_id: 'r1' }),
        run('message.start', { message_id: 'a1' }),
        run('message.delta', { message_id: 'a1', delta: 'I will look up the order first, then read the refund skill.' }),
        run('message.end', { message_id: 'a1', text: 'I will look up the order first, then read the refund skill.', stop_reason: 'toolUse', has_tool_calls: true }),
        run('tool.start', { tool_call_id: 'call_lookup', name: 'lookup_order', arguments: { order_id: 'A-1042' } }),
        run('tool.update', { tool_call_id: 'call_lookup', text: 'found order A-1042' }),
        run('tool.end', {
          tool_call_id: 'call_lookup',
          name: 'lookup_order',
          status: 'ok',
          result: 'Order A-1042 · paid · placed 12 days ago',
          duration_ms: 840,
          artifacts: [{ id: 'art_1', name: 'order-summary.txt', mime_type: 'text/plain', size: 132, source: 'dify' }],
          execution_outcome: 'executed',
        }),
        run('skill.activate', { tool_call_id: 'call_skill', skill: 'refund-policy', source: 'app', activated_by: 'model' }),
        run('skill.read', { tool_call_id: 'call_skill', skill: 'refund-policy', path: 'guide.md', offset: 0, total_chars: 188, next_offset: null }),
        run('compaction.start', { tokens_before: 48_210, messages_kept: 4 }),
        run('compaction.end', { tokens_before: 48_210, summary_chars: 612, first_kept_entry_id: 'a1' }),
        run('message.start', { message_id: 'a2' }),
        run('message.delta', { message_id: 'a2', delta: 'The order was placed 12 days ago, so it is inside the 30-day refund window. ' }),
        run('message.delta', { message_id: 'a2', delta: 'The policy requires the item to be unused; ask the user to confirm that before issuing a refund.' }),
        run('message.end', {
          message_id: 'a2',
          text: 'The order was placed 12 days ago, so it is inside the 30-day refund window. The policy requires the item to be unused; ask the user to confirm that before issuing a refund.',
          stop_reason: 'stop',
          has_tool_calls: false,
        }),
        run('run.state', {
          status: 'completed',
          answer: 'The order was placed 12 days ago, so it is inside the 30-day refund window. The policy requires the item to be unused; ask the user to confirm that before issuing a refund.',
          stats: { model_requests: 3, tool_calls: 2, usage: { reported: { total_tokens: 6_240 }, estimated_tokens: 700, unknown_usage_requests: 0 } },
          state_ref: { revision: 7, delivery_status: 'encoded' },
        }),
        run('run.done', { status: 'completed' }),
      ]
    })(),
  },
  {
    id: 'questionnaire',
    title: 'Questionnaire pause and answer',
    description: 'The agent asks a multi-question questionnaire, stops deterministically, and resumes in the next turn after answers.',
    events: (() => {
      const run = makeRun('run_replay_question', 1_700_000_100_000)
      return [
        run('run.start', { conversation_id: 'replay-conv' }),
        run('message.user', { message_id: 'qu1', text: 'Please start a refund.' }),
        run('message.start', { message_id: 'qa1' }),
        run('message.end', { message_id: 'qa1', text: 'I need a few details first.', stop_reason: 'toolUse', has_tool_calls: true }),
        run('tool.start', { tool_call_id: 'call_ask', name: 'ask_user', arguments: { title: 'Refund details' } }),
        run('question.asked', { questionnaire }),
        run('tool.end', { tool_call_id: 'call_ask', name: 'ask_user', status: 'awaiting_user', result: 'Questionnaire presented.', execution_outcome: 'executed' }),
        run('run.state', { status: 'awaiting_user', answer: 'The agent is waiting for your answers.', pending: { kind: 'ask_user', questionnaire } }),
        run('run.done', { status: 'awaiting_user' }),
      ]
    })(),
    actions: ['questionnaire'],
  },
  {
    id: 'approval',
    title: 'Tool approval and unknown write',
    description: 'A write tool waits for a separate approval. The replay can approve it, reject it, or show an unknown remote outcome.',
    events: (() => {
      const run = makeRun('run_replay_approval', 1_700_000_200_000)
      return [
        run('run.start', { conversation_id: 'replay-conv' }),
        run('message.user', { message_id: 'au1', text: 'Delete the stale record.' }),
        run('message.start', { message_id: 'aa1' }),
        run('message.end', { message_id: 'aa1', text: 'This operation needs your approval.', stop_reason: 'toolUse', has_tool_calls: true }),
        run('tool.start', { tool_call_id: 'call_delete', name: 'delete_record', arguments: { record: 'stale-14' } }),
        run('tool.end', { tool_call_id: 'call_delete', name: 'delete_record', status: 'awaiting_approval', result: 'Approval required.', execution_outcome: 'not_executed' }),
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
        run('run.state', { status: 'awaiting_approval', answer: 'The agent is waiting for your approval.', pending: { kind: 'approval' } }),
        run('run.done', { status: 'awaiting_approval' }),
      ]
    })(),
    actions: ['approval'],
  },
]

export function scenarioById(id: string): ReplayScenario | null {
  return REPLAY_SCENARIOS.find((scenario) => scenario.id === id) || null
}
