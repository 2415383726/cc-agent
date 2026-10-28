export type RunStatus = 'completed' | 'awaiting_user' | 'failed' | 'budget_exhausted' | 'unknown'

export function runStatusFromMetadata(metadata: Record<string, any> = {}): RunStatus {
  const explicit = metadata.run_status
  if (['completed', 'awaiting_user', 'failed', 'budget_exhausted', 'unknown'].includes(explicit)) return explicit
  const reason = String(metadata.finish_reason || metadata.finishReason || '')
  if (reason === 'awaiting_user') return 'awaiting_user'
  if (['max_iterations', 'budget_exhausted', 'length', 'max_tokens', 'max_output_tokens', 'token_limit'].includes(reason)) return 'budget_exhausted'
  if (metadata.error_code || reason === 'context_overflow' || reason.endsWith('_error')) return 'failed'
  return 'completed'
}
