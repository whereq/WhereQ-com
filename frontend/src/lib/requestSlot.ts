/**
 * One in-flight request slot.
 *
 * The map layers fire a request whenever the viewport settles. Without this,
 * a superseded request still runs to completion: it still downloads its body
 * and still pays `res.json()` on the main thread, and the answer is then
 * thrown away by the request-id guard. Measured on PROD, `/places/map`
 * answers a downtown viewport in **37 ms** with a **239 KB** JSON body, so a
 * user who pans five times pays for five full bodies and parses five
 * payloads, four of which are discarded.
 *
 * A slot holds one request. Starting a new one **cancels** the previous one:
 * the browser tears down the connection, so the body is never downloaded and
 * never parsed.
 *
 * The request-id guard stays. Cancellation saves bandwidth; the guard is what
 * makes the answer correct, and a response that was already in flight when
 * the abort landed still has to be recognised as stale.
 */
export class RequestSlot {
  private controller: AbortController | null = null

  /**
   * Start a request, cancelling the one this slot was holding.
   *
   * Returns the signal to hand to `fetch`. The caller is responsible for
   * attaching it — `api.get(path, { signal })`.
   */
  begin(): AbortSignal {
    this.controller?.abort()
    this.controller = new AbortController()
    return this.controller.signal
  }

  /** Cancel whatever is in flight. Safe to call when nothing is. */
  cancel(): void {
    this.controller?.abort()
    this.controller = null
  }
}

/**
 * True when a rejection is an abort rather than a failure.
 *
 * `fetch` rejects with a `DOMException` named `AbortError` when the signal
 * fires. A superseded request is not an error the user should hear about —
 * it is the app tidying up after itself.
 */
export function isAbortError(err: unknown): boolean {
  return (
    !!err &&
    typeof err === 'object' &&
    (err as { name?: unknown }).name === 'AbortError'
  )
}
