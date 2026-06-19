<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-title">质量评价模块</div>
        <div class="brand-sub">Vue + JSON Spec + OM 对齐</div>
      </div>
      <nav class="nav">
        <RouterLink
          v-for="item in items"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          active-class="active"
        >
          <component :is="item.icon" :size="16" />
          <span>
            <strong>{{ item.label }}</strong>
            <small>{{ item.hint }}</small>
          </span>
        </RouterLink>
      </nav>
    </aside>
    <main class="main">
      <header class="topbar">
        <div>
          <div class="page-title">{{ pageTitle }}</div>
          <div class="page-hint">{{ pageHint }}</div>
        </div>
        <div class="topbar-right">
          <a class="ghost-link" href="http://127.0.0.1:8765/api/rules/spec" target="_blank">JSON Spec</a>
          <a class="ghost-link" href="http://127.0.0.1:8765/api/workflow/overview" target="_blank">API</a>
        </div>
      </header>
      <section class="workspace">
        <slot />
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, RouterLink } from 'vue-router';
import {
  Activity,
  BarChart3,
  ClipboardCheck,
  Database,
  FileJson,
  GitBranch,
  ListChecks,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-vue-next';

const route = useRoute();

const items = [
  { path: '/import', label: '数据导入', hint: '测试/真实数据', icon: Database },
  { path: '/rules', label: '规则库', hint: '六维规则管理', icon: FileJson },
  { path: '/recommend', label: '智能推荐', hint: '自动匹配规则', icon: Sparkles },
  { path: '/parameters', label: '规则参数', hint: '业务化配置', icon: SlidersHorizontal },
  { path: '/execution', label: '评价实施', hint: '任务执行', icon: ClipboardCheck },
  { path: '/dashboard', label: '六维看板', hint: '评价结果', icon: BarChart3 },
  { path: '/issues', label: '问题分析', hint: '闭环处理', icon: ListChecks },
  { path: '/scoring', label: '计分规则', hint: '得分归档', icon: Activity },
  { path: '/lineage', label: '问题溯源', hint: '真实血缘', icon: GitBranch },
];

const pageTitle = computed(() => String(route.meta.title || '质量评价模块'));
const pageHint = computed(() => String(route.meta.hint || ''));
</script>
