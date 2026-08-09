/**
 * takeTurnStream() unit tests (issue #20).
 *
 * VITE_USE_MOCK is a build-time env var and is not injected at test time (see
 * client.test.ts's note), so importing client.ts directly here exercises the
 * REAL fetch()-based SSE parsing — exactly the code path production runs,
 * with `global.fetch` mocked to return a hand-built streaming Response.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../src/types'
import { takeTurnStream } from '../../../src/api/client'

function sseResponse(chunks: string[], opts: { status?: number } = {}): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
  return new Response(body, {
    status: opts.status ?? 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function jsonErrorResponse(status: number, code: string, message: string): Response {
  return new Response(JSON.stringify({ error: { code, message } }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('takeTurnStream', () => {
  it('calls onDelta for each delta event, in order, and resolves on done', async () => {
    const events = [
      'event: delta\ndata: {"text":"You step "}\n\n',
      'event: delta\ndata: {"text":"into the pass."}\n\n',
      'event: done\ndata: {"scene":{"narrative":"You step into the pass.","choices":[{"id":"1","label":"Go"}],"terminal":false},"status":"active"}\n\n',
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(events)))

    const deltas: string[] = []
    const result = await takeTurnStream({ choice: 'go' }, (text) => deltas.push(text))

    expect(deltas).toEqual(['You step ', 'into the pass.'])
    expect(result.scene.narrative).toBe('You step into the pass.')
    expect(result.status).toBe('active')

    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/me/game/turn/stream')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ choice: 'go' })
  })

  it('handles an SSE event split across multiple stream chunks', async () => {
    // Simulates a real network delivering one logical event across several reads.
    const events = [
      'event: delta\ndata: {"tex',
      't":"partial"}\n\n',
      'event: done\ndata: {"scene":{"narrative":"partial","choices":[],"terminal":true},"status":"ended"}\n\n',
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(events)))

    const deltas: string[] = []
    const result = await takeTurnStream({}, (text) => deltas.push(text))

    expect(deltas).toEqual(['partial'])
    expect(result.status).toBe('ended')
  })

  it('rejects with an ApiError carrying the standard error envelope on an error event', async () => {
    const events = [
      'event: delta\ndata: {"text":"almost there"}\n\n',
      'event: error\ndata: {"error":{"code":"stream_failed","message":"Narrator failed to produce a valid scene"}}\n\n',
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(events)))

    await expect(takeTurnStream({}, () => {})).rejects.toMatchObject({
      code: 'stream_failed',
      message: 'Narrator failed to produce a valid scene',
    })
  })

  it('rejects with ApiError for a pre-stream HTTP error (same shape as takeTurn)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonErrorResponse(404, 'no_active_campaign', 'No active game found'))
    )

    await expect(takeTurnStream({}, () => {})).rejects.toMatchObject({
      status: 404,
      code: 'no_active_campaign',
    })
  })

  it('rejects if the stream ends without a done event', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(sseResponse(['event: delta\ndata: {"text":"cut off"}\n\n']))
    )

    await expect(takeTurnStream({}, () => {})).rejects.toBeInstanceOf(ApiError)
  })

  it('rejects with a network ApiError if fetch itself throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(takeTurnStream({}, () => {})).rejects.toMatchObject({ code: 'unknown' })
  })
})
