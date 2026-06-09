/**
 * NL2DSL v2 前端类型声明。
 *
 * 这个文件用于约束问数链路中的 DSL 资产引用结构。当前项目主体仍是 JS，
 * 先以 d.ts 形式同步后端协议，后续组件迁移 TS 时可直接复用。
 */

export type DslAssetType = 'term' | 'metric' | 'dimension' | 'column' | 'field' | 'blueprint';

export interface DslAssetRef {
  name: string;
  asset_type: DslAssetType;
  asset_id?: number | null;
  display_name?: string | null;
  matched_text?: string | null;
  confidence?: number | null;
  reason?: string | null;
  [key: string]: unknown;
}

export interface DslAmbiguity {
  text?: string | null;
  reason?: string | null;
  candidates: DslAssetRef[];
  resolution_hint?: string | null;
  [key: string]: unknown;
}

export interface DslFilter {
  field: string | DslAssetRef;
  op: 'eq' | 'in' | 'gt' | 'gte' | 'lt' | 'lte' | 'between' | 'neq';
  values: unknown[];
  confidence?: number | null;
  ambiguities?: DslAmbiguity[];
  [key: string]: unknown;
}

export interface DslOrderBy {
  field: string | DslAssetRef;
  direction: 'ASC' | 'DESC';
  [key: string]: unknown;
}

export interface Nl2Dsl {
  version?: '2.0' | string;
  metrics?: DslAssetRef[];
  dimensions?: DslAssetRef[];
  fields?: DslAssetRef[];
  terms?: DslAssetRef[];
  blueprints?: DslAssetRef[];
  filters?: DslFilter[];
  time_range?: Record<string, unknown> | null;
  order_by?: DslOrderBy[];
  limit?: number | null;
  confidence?: number | null;
  ambiguities?: DslAmbiguity[];
  direct_sql?: string | null;
  inferred?: boolean;
  [key: string]: unknown;
}
