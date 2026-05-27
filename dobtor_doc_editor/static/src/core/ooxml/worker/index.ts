/**
 * Phase 7 Worker parse — barrel export（Sprint 292 spike）。
 *
 * 紀律 #18 scope-down：本 spike 為 API contract design + MainThreadDispatcher
 * fallback；真實 Worker（browser Worker / node:worker_threads）實作為未來
 * polish sprint 範圍。
 */
export type {
  ParseWorkerRequest,
  ParseWorkerResponse,
  ParseHarnessResult,
  ParseWorkerDispatcher,
} from './parse_worker_protocol';
export { ParseWorkerHarness } from './ParseWorkerHarness';
export type { ParseHarnessOptions } from './ParseWorkerHarness';
export { MainThreadDispatcher } from './MainThreadDispatcher';
export type { MainThreadDispatcherOptions, SyncParseFn } from './MainThreadDispatcher';
// Sprint 294：node:worker_threads 真實 dispatcher
export { NodeWorkerThreadDispatcher } from './NodeWorkerThreadDispatcher';
export type {
  NodeWorkerThreadDispatcherOptions,
  ParseStub,
} from './NodeWorkerThreadDispatcher';
// Sprint 299：browser Worker API 真實 dispatcher
export { BrowserWorkerDispatcher } from './BrowserWorkerDispatcher';
export type { BrowserWorkerDispatcherOptions } from './BrowserWorkerDispatcher';
// Sprint 307：worker pool round-robin（compose existing dispatchers）
export { WorkerPoolDispatcher } from './WorkerPoolDispatcher';
export type { WorkerPoolDispatcherOptions } from './WorkerPoolDispatcher';
