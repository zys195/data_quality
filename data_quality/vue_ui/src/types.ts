export interface ApiListResponse<T> {
  total: number;
  [key: string]: any;
  rules?: T[];
}

export interface RuleItem {
  rule_id: string;
  name: string;
  display_name: string;
  dimension: string;
  dimension_zh?: string;
  problem_category: string;
  severity: string;
  validation_level: string;
  source_type: string;
  core_definition: string;
  tags?: string[];
  scripts?: Record<string, { expression: string; language?: string; description?: string }>;
  parameters?: Record<string, any>;
  threshold?: Record<string, any>;
  responsible_role?: string;
  remediation_suggestion?: string;
  issue_strategy?: string;
  status?: string;
  reuse_count?: number;
}

export interface DimensionMeta {
  display_name: string;
  weight: number;
  description: string;
  examples: string[];
}
