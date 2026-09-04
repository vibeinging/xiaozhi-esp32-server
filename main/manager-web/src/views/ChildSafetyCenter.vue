<template>
  <div class="safety-page">
    <HeaderBar />
    <main class="safety-shell">
      <section class="hero-card">
        <div>
          <span class="eyebrow">PARENT SAFETY CENTER</span>
          <h1>{{ $t('childSafety.title') }}</h1>
          <p>{{ $t('childSafety.subtitle') }}</p>
        </div>
        <div class="privacy-pill">
          <i class="el-icon-lock"></i>
          <span>{{ $t('childSafety.privacyPill') }}</span>
        </div>
      </section>

      <section class="summary-grid">
        <div class="summary-card urgent">
          <span>{{ $t('childSafety.unread') }}</span>
          <strong>{{ dashboard.unreadCount || 0 }}</strong>
        </div>
        <div class="summary-card">
          <span>{{ $t('childSafety.todayEvents') }}</span>
          <strong>{{ todayEventCount }}</strong>
        </div>
        <div class="summary-card">
          <span>{{ $t('childSafety.latestLevel') }}</span>
          <el-tag :type="tagType(latestReview.riskLevel)" effect="dark">
            {{ levelLabel(latestReview.riskLevel) }}
          </el-tag>
        </div>
      </section>

      <section class="content-grid">
        <el-card class="panel settings-panel" shadow="never">
          <div slot="header" class="panel-title">
            <div>
              <h2>{{ $t('childSafety.settingsTitle') }}</h2>
              <p>{{ $t('childSafety.settingsHint') }}</p>
            </div>
          </div>

          <el-form label-position="top" :model="setting">
            <el-form-item :label="$t('childSafety.agent')">
              <el-select v-model="selectedAgentId" filterable @change="loadSetting" style="width: 100%">
                <el-option v-for="agent in agents" :key="agent.id" :label="agent.agentName" :value="agent.id" />
              </el-select>
            </el-form-item>
            <div class="switch-row">
              <div>
                <strong>{{ $t('childSafety.enable') }}</strong>
                <small>{{ $t('childSafety.textOnlyHint') }}</small>
              </div>
              <el-switch v-model="setting.enabled" />
            </div>
            <div class="form-pair">
              <el-form-item :label="$t('childSafety.reviewTime')">
                <el-time-select v-model="setting.reviewTime" :picker-options="timeOptions" style="width: 100%" />
              </el-form-item>
              <el-form-item :label="$t('childSafety.chatRetention')">
                <el-select v-model="setting.chatRetentionDays" style="width: 100%">
                  <el-option :label="$t('childSafety.days', { count: 3 })" :value="3" />
                  <el-option :label="$t('childSafety.days', { count: 7 })" :value="7" />
                  <el-option :label="$t('childSafety.days', { count: 14 })" :value="14" />
                </el-select>
              </el-form-item>
            </div>
            <div class="privacy-note">
              <i class="el-icon-info"></i>
              <span>{{ $t('childSafety.privacyNote') }}</span>
            </div>
            <div class="actions">
              <el-button :loading="reviewing" :disabled="!setting.enabled || !selectedAgentId" @click="runReview">
                {{ $t('childSafety.reviewNow') }}
              </el-button>
              <el-button type="primary" :loading="saving" :disabled="!selectedAgentId" @click="saveSetting">
                {{ $t('childSafety.save') }}
              </el-button>
            </div>
          </el-form>
        </el-card>

        <div class="feed-column">
          <el-card class="panel" shadow="never">
            <div slot="header" class="panel-title">
              <div>
                <h2>{{ $t('childSafety.urgentTitle') }}</h2>
                <p>{{ $t('childSafety.urgentHint') }}</p>
              </div>
            </div>
            <div v-if="!dashboard.events || !dashboard.events.length" class="empty-state">
              <i class="el-icon-circle-check"></i>
              <span>{{ $t('childSafety.noEvents') }}</span>
            </div>
            <button
              v-for="event in dashboard.events"
              :key="event.id"
              class="event-row"
              :class="{ unread: !event.readAt }"
              @click="readEvent(event)"
            >
              <span class="risk-dot" :class="(event.riskLevel || '').toLowerCase()"></span>
              <span class="event-copy">
                <strong>{{ categoryLabel(event.category) }}</strong>
                <small>{{ agentName(event.agentId) }} · {{ formatDate(event.occurredAt) }}</small>
              </span>
              <el-tag size="mini" :type="tagType(event.riskLevel)">{{ levelLabel(event.riskLevel) }}</el-tag>
            </button>
          </el-card>

          <el-card class="panel reports-panel" shadow="never">
            <div slot="header" class="panel-title">
              <div>
                <h2>{{ $t('childSafety.reportsTitle') }}</h2>
                <p>{{ $t('childSafety.reportsHint') }}</p>
              </div>
            </div>
            <div v-if="!dashboard.reviews || !dashboard.reviews.length" class="empty-state compact">
              <span>{{ $t('childSafety.noReports') }}</span>
            </div>
            <article
              v-for="review in dashboard.reviews"
              :key="review.id"
              class="report-card"
              :class="{ unread: !review.readAt && review.status !== 'PROCESSING' }"
              @click="readReview(review)"
            >
              <header>
                <div>
                  <strong>{{ review.reviewDate }} · {{ agentName(review.agentId) }}</strong>
                  <small>{{ $t('childSafety.messageCount', { count: review.messageCount || 0 }) }}</small>
                </div>
                <el-tag :type="tagType(review.riskLevel)" effect="plain">{{ levelLabel(review.riskLevel) }}</el-tag>
              </header>
              <p>{{ review.summary }}</p>
              <ul v-if="review.details && review.details.length">
                <li v-for="(detail, index) in review.details" :key="index">
                  <strong>{{ categoryLabel(detail.category) }}</strong>
                  <span>{{ detail.reason }}</span>
                  <small>{{ detail.action }}</small>
                </li>
              </ul>
              <div v-if="review.parentAdvice" class="parent-advice">
                <i class="el-icon-chat-dot-round"></i>
                <span>{{ review.parentAdvice }}</span>
              </div>
            </article>
          </el-card>
        </div>
      </section>
    </main>
    <el-footer><VersionFooter /></el-footer>
  </div>
</template>

<script>
import Api from '@/apis/api';
import HeaderBar from '@/components/HeaderBar.vue';
import VersionFooter from '@/components/VersionFooter.vue';

export default {
  name: 'ChildSafetyCenter',
  components: { HeaderBar, VersionFooter },
  data() {
    return {
      agents: [],
      selectedAgentId: '',
      dashboard: { unreadCount: 0, events: [], reviews: [] },
      setting: this.defaultSetting(),
      saving: false,
      reviewing: false,
      timeOptions: { start: '18:00', step: '00:30', end: '23:30' },
    };
  },
  computed: {
    latestReview() {
      return (this.dashboard.reviews && this.dashboard.reviews[0]) || { riskLevel: 'NONE' };
    },
    todayEventCount() {
      const today = new Date().toDateString();
      return (this.dashboard.events || []).filter((item) => new Date(item.occurredAt).toDateString() === today).length;
    },
  },
  mounted() {
    this.loadAgents();
    this.loadDashboard();
  },
  methods: {
    defaultSetting() {
      return {
        enabled: false,
        reviewTime: '22:00',
        timezone: 'Asia/Shanghai',
        chatRetentionDays: 7,
        reportRetentionDays: 90,
      };
    },
    loadAgents() {
      Api.agent.getAgentList(({ data }) => {
        this.agents = data && data.data ? data.data : [];
        if (!this.selectedAgentId && this.agents.length) {
          this.selectedAgentId = this.agents[0].id;
          this.loadSetting();
        }
      });
    },
    loadDashboard() {
      Api.childSafety.getDashboard(({ data }) => {
        this.dashboard = (data && data.data) || { unreadCount: 0, events: [], reviews: [] };
      });
    },
    loadSetting() {
      if (!this.selectedAgentId) return;
      Api.childSafety.getSetting(this.selectedAgentId, ({ data }) => {
        this.setting = { ...this.defaultSetting(), ...((data && data.data) || {}) };
      });
    },
    saveSetting() {
      this.saving = true;
      Api.childSafety.updateSetting(this.selectedAgentId, this.setting, () => {
        this.saving = false;
        this.$message.success(this.$t('childSafety.saved'));
        this.loadDashboard();
      }, () => {
        this.saving = false;
      });
    },
    runReview() {
      this.reviewing = true;
      Api.childSafety.runReview(this.selectedAgentId, () => {
        this.reviewing = false;
        this.$message.success(this.$t('childSafety.reviewComplete'));
        this.loadDashboard();
      }, () => {
        this.reviewing = false;
      });
    },
    readEvent(event) {
      if (event.readAt) return;
      Api.childSafety.markEventRead(event.id, this.loadDashboard);
    },
    readReview(review) {
      if (review.readAt || review.status === 'PROCESSING') return;
      Api.childSafety.markReviewRead(review.id, this.loadDashboard);
    },
    agentName(agentId) {
      const agent = this.agents.find((item) => item.id === agentId);
      return agent ? agent.agentName : this.$t('childSafety.unknownAgent');
    },
    levelLabel(level) {
      return this.$t(`childSafety.level.${level || 'NONE'}`);
    },
    categoryLabel(category) {
      const key = `childSafety.category.${category || 'other'}`;
      const value = this.$t(key);
      return value === key ? this.$t('childSafety.category.other') : value;
    },
    tagType(level) {
      return { CRITICAL: 'danger', HIGH: 'danger', MEDIUM: 'warning', LOW: 'info', NONE: 'success', UNKNOWN: 'info' }[level] || 'info';
    },
    formatDate(value) {
      return value ? new Date(value).toLocaleString() : '-';
    },
  },
};
</script>

<style lang="scss" scoped>
.safety-page { min-height: 100vh; background: #f6f1ea; color: #342a26; }
.safety-shell { width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 32px 0 48px; text-align: left; }
.hero-card { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; padding: 30px 34px; border-radius: 26px; background: linear-gradient(135deg, #3e2f36, #6f4c65); color: white; box-shadow: 0 18px 44px rgba(69, 44, 58, .18); }
.eyebrow { font-size: 12px; letter-spacing: .18em; color: #efc9dc; }
.hero-card h1 { margin: 9px 0 7px; font-size: 32px; }
.hero-card p { margin: 0; color: rgba(255,255,255,.78); }
.privacy-pill { display: flex; align-items: center; gap: 9px; padding: 10px 14px; border: 1px solid rgba(255,255,255,.18); border-radius: 999px; background: rgba(255,255,255,.09); white-space: nowrap; }
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 18px 0; }
.summary-card { min-height: 92px; padding: 18px 20px; border-radius: 18px; background: #fffdf9; border: 1px solid rgba(91,65,54,.1); display: flex; flex-direction: column; justify-content: space-between; }
.summary-card span { color: #887770; font-size: 13px; }
.summary-card strong { font-size: 28px; }
.summary-card.urgent { background: #fff5f3; }
.content-grid { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 18px; align-items: start; }
.panel { border: 0; border-radius: 20px; overflow: hidden; background: #fffdf9; }
.panel-title h2 { margin: 0 0 5px; font-size: 19px; }
.panel-title p { margin: 0; color: #96867e; font-size: 13px; }
.switch-row { display: flex; align-items: center; justify-content: space-between; padding: 15px; margin-bottom: 18px; border-radius: 14px; background: #f8f3ee; }
.switch-row strong, .switch-row small { display: block; }
.switch-row small { margin-top: 4px; color: #9a8980; }
.form-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.privacy-note { display: flex; gap: 8px; padding: 12px; border-radius: 12px; background: #f2edf5; color: #6e5a6e; font-size: 12px; line-height: 1.6; }
.actions { display: flex; justify-content: flex-end; margin-top: 18px; }
.feed-column { display: grid; gap: 18px; }
.empty-state { display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 112px; color: #8f9a89; }
.empty-state i { font-size: 25px; color: #7da272; }
.empty-state.compact { min-height: 74px; }
.event-row { width: 100%; border: 0; border-top: 1px solid #eee6df; background: transparent; display: flex; align-items: center; gap: 12px; padding: 14px 2px; text-align: left; cursor: pointer; }
.event-row.unread { background: linear-gradient(90deg, rgba(154,73,95,.07), transparent); }
.risk-dot { width: 9px; height: 9px; border-radius: 50%; background: #8d9b88; flex: none; }
.risk-dot.critical, .risk-dot.high { background: #d95c63; box-shadow: 0 0 0 5px rgba(217,92,99,.1); }
.risk-dot.medium { background: #dc9b4a; }
.event-copy { min-width: 0; flex: 1; }
.event-copy strong, .event-copy small { display: block; }
.event-copy small { margin-top: 4px; color: #9a8980; }
.report-card { padding: 18px 0; border-top: 1px solid #eee6df; cursor: pointer; }
.report-card.unread { border-left: 3px solid #a15c78; padding-left: 14px; }
.report-card header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.report-card header strong, .report-card header small { display: block; }
.report-card header small { margin-top: 5px; color: #9a8980; }
.report-card > p { line-height: 1.7; color: #5e504a; }
.report-card ul { padding: 0; margin: 12px 0; list-style: none; display: grid; gap: 9px; }
.report-card li { padding: 12px; border-radius: 12px; background: #faf5ef; }
.report-card li strong, .report-card li span, .report-card li small { display: block; }
.report-card li span { margin: 5px 0; color: #685a54; }
.report-card li small { color: #8b786f; line-height: 1.5; }
.parent-advice { display: flex; gap: 8px; padding: 11px 12px; border-radius: 11px; background: #eef3ea; color: #596c52; line-height: 1.55; }
@media (max-width: 900px) { .content-grid { grid-template-columns: 1fr; } .hero-card { align-items: flex-start; flex-direction: column; } }
@media (max-width: 620px) { .safety-shell { width: min(100% - 24px, 1180px); padding-top: 18px; } .summary-grid { grid-template-columns: 1fr; } .form-pair { grid-template-columns: 1fr; } .hero-card { padding: 24px; } }
</style>
