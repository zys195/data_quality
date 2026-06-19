import { createRouter, createWebHistory } from 'vue-router';
import ImportPage from './pages/ImportPage.vue';
import RulesPage from './pages/RulesPage.vue';
import RecommendPage from './pages/RecommendPage.vue';
import ParametersPage from './pages/ParametersPage.vue';
import ExecutionPage from './pages/ExecutionPage.vue';
import DashboardPage from './pages/DashboardPage.vue';
import IssuesPage from './pages/IssuesPage.vue';
import ScoringPage from './pages/ScoringPage.vue';
import LineagePage from './pages/LineagePage.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/import' },
    { path: '/import', component: ImportPage, meta: { title: '数据导入', hint: '导入测试或真实数据' } },
    { path: '/rules', component: RulesPage, meta: { title: '规则库', hint: '六维质量规则管理' } },
    { path: '/recommend', component: RecommendPage, meta: { title: '智能推荐', hint: '根据元数据自动推荐规则' } },
    { path: '/parameters', component: ParametersPage, meta: { title: '规则参数', hint: '业务化调整规则要求' } },
    { path: '/execution', component: ExecutionPage, meta: { title: '评价实施', hint: '创建并执行质量评价任务' } },
    { path: '/dashboard', component: DashboardPage, meta: { title: '六维看板', hint: '按六个维度查看评价结果' } },
    { path: '/issues', component: IssuesPage, meta: { title: '问题分析', hint: '质量问题闭环处理' } },
    { path: '/scoring', component: ScoringPage, meta: { title: '计分规则', hint: '评价得分和归档' } },
    { path: '/lineage', component: LineagePage, meta: { title: '问题溯源', hint: '接入真实血缘后定位来源' } },
  ],
});

export default router;
