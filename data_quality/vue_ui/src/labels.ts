export const dimensions = [
  { key: 'normativity', label: '规范性' },
  { key: 'completeness', label: '完整性' },
  { key: 'accuracy', label: '准确性' },
  { key: 'consistency', label: '一致性' },
  { key: 'timeliness', label: '时效性' },
  { key: 'accessibility', label: '可访问性' },
];

export function dimensionName(value?: string) {
  return dimensions.find((item) => item.key === value)?.label || value || '-';
}

export function levelName(value?: string) {
  const map: Record<string, string> = {
    P0_BLOCKING: '强校验',
    P1_WARNING: '提醒校验',
    P2_MONITORING: '监测校验',
  };
  return map[value || ''] || value || '-';
}

export function runStatusName(value?: string) {
  const map: Record<string, string> = {
    success: '已完成',
    warning: '已完成，有问题需处理',
    blocked: '阻断，需先整改',
    failed: '执行失败',
  };
  return map[value || ''] || value || '-';
}

export function issueStatusName(value?: string) {
  const map: Record<string, string> = {
    discovered: '已发现',
    alerted: '已告警',
    ticketed: '已派单',
    remediating: '整改中',
    reviewing: '复核中',
    closed: '已关闭',
    archived: '已归档',
  };
  return map[value || ''] || value || '-';
}
