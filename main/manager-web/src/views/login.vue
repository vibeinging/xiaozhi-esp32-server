<template>
  <div class="welcome">
    <div class="ambient ambient-one"></div>
    <div class="ambient ambient-two"></div>

    <header class="brand-bar">
      <div class="brand-lockup" aria-label="YIYI AI">
        <span class="brand-mark">AI</span>
        <span class="brand-name">YIYI AI</span>
        <span class="brand-divider"></span>
        <span class="brand-product">CONTROL CENTER</span>
      </div>

      <el-dropdown trigger="click" class="title-language-dropdown"
        @visible-change="handleLanguageDropdownVisibleChange">
        <span class="el-dropdown-link">
          <i class="el-icon-s-promotion language-icon"></i>
          <span class="current-language-text">{{ currentLanguageText }}</span>
          <i class="el-icon-arrow-down" :class="{ 'rotate-down': languageDropdownVisible }"></i>
        </span>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item @click.native="changeLanguage('zh_CN')">{{ $t("language.zhCN") }}</el-dropdown-item>
          <el-dropdown-item @click.native="changeLanguage('zh_TW')">{{ $t("language.zhTW") }}</el-dropdown-item>
          <el-dropdown-item @click.native="changeLanguage('en')">{{ $t("language.en") }}</el-dropdown-item>
          <el-dropdown-item @click.native="changeLanguage('de')">{{ $t("language.de") }}</el-dropdown-item>
          <el-dropdown-item @click.native="changeLanguage('vi')">{{ $t("language.vi") }}</el-dropdown-item>
          <el-dropdown-item @click.native="changeLanguage('pt_BR')">{{ $t("language.ptBR") }}</el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>
    </header>

    <main class="auth-layout">
      <section class="story-panel" aria-labelledby="brand-story-title">
        <div class="story-copy">
          <div class="eyebrow"><span></span>{{ brandCopy.eyebrow }}</div>
          <h1 id="brand-story-title">{{ brandCopy.title }}</h1>
          <p>{{ brandCopy.subtitle }}</p>
          <div class="feature-row">
            <span><i class="el-icon-microphone"></i>{{ brandCopy.featureOne }}</span>
            <span><i class="el-icon-chat-dot-round"></i>{{ brandCopy.featureTwo }}</span>
            <span><i class="el-icon-s-tools"></i>{{ brandCopy.featureThree }}</span>
          </div>
        </div>

        <div class="companion-scene" aria-hidden="true">
          <div class="orbit orbit-one"></div>
          <div class="orbit orbit-two"></div>
          <div class="orbit-dot dot-one"></div>
          <div class="orbit-dot dot-two"></div>
          <div class="plush">
            <div class="plush-ear plush-ear-left"></div>
            <div class="plush-ear plush-ear-right"></div>
            <div class="plush-face">
              <span class="plush-eye plush-eye-left"></span>
              <span class="plush-eye plush-eye-right"></span>
              <span class="plush-nose"></span>
              <span class="plush-smile"></span>
              <span class="plush-blush plush-blush-left"></span>
              <span class="plush-blush plush-blush-right"></span>
            </div>
            <div class="voice-wave wave-one"></div>
            <div class="voice-wave wave-two"></div>
            <div class="voice-wave wave-three"></div>
          </div>
          <div class="scene-note">
            <strong>{{ brandCopy.noteTitle }}</strong>
            <span>{{ brandCopy.noteBody }}</span>
          </div>
        </div>
      </section>

      <section class="login-box" @keyup.enter="login">
        <div class="login-heading">
          <div>
            <span class="console-label">{{ brandCopy.console }}</span>
            <h2>{{ brandCopy.welcome }}</h2>
            <p>{{ brandCopy.loginHint }}</p>
          </div>
          <div class="security-badge" :title="brandCopy.secure">
            <i class="el-icon-lock"></i>
          </div>
        </div>

        <div class="form-body">
          <template v-if="!isMobileLogin">
            <label class="field-label">{{ brandCopy.usernameLabel }}</label>
            <div class="input-box">
              <i class="el-icon-user input-glyph"></i>
              <el-input v-model="form.username" :placeholder="$t('login.usernamePlaceholder')" autocomplete="username" />
            </div>
          </template>

          <template v-else>
            <label class="field-label">{{ brandCopy.mobileLabel }}</label>
            <div class="input-box mobile-input-box">
              <el-select v-model="form.areaCode" class="area-code-select">
                <el-option v-for="item in mobileAreaList" :key="item.key" :label="`${item.name} (${item.key})`"
                  :value="item.key" />
              </el-select>
              <el-input v-model="form.mobile" :placeholder="$t('login.mobilePlaceholder')" />
            </div>
          </template>

          <label class="field-label">{{ brandCopy.passwordLabel }}</label>
          <div class="input-box">
            <i class="el-icon-lock input-glyph"></i>
            <el-input v-model="form.password" :placeholder="$t('login.passwordPlaceholder')" type="password"
              autocomplete="current-password" show-password />
          </div>

          <label class="field-label">{{ brandCopy.captchaLabel }}</label>
          <div class="captcha-row">
            <div class="input-box captcha-input">
              <i class="el-icon-key input-glyph"></i>
              <el-input v-model="form.captcha" :placeholder="$t('login.captchaPlaceholder')" />
            </div>
            <button v-if="captchaUrl" type="button" class="captcha-button" @click="fetchCaptcha"
              :aria-label="brandCopy.refreshCaptcha">
              <img loading="lazy" :src="captchaUrl" alt="验证码" />
            </button>
          </div>

          <div class="form-links">
            <button v-if="allowUserRegister" type="button" @click="goToRegister">{{ $t("login.register") }}</button>
            <button v-if="enableMobileRegister" type="button" @click="goToForgetPassword">
              {{ $t("login.forgetPassword") }}
            </button>
          </div>

          <button type="button" class="login-btn" @click="login">
            <span>{{ $t("login.login") }}</span>
            <i class="el-icon-right"></i>
          </button>

          <div class="login-type-container" v-if="enableMobileRegister">
            <div class="login-type-switch">
              <el-tooltip :content="$t('login.mobileLogin')" placement="bottom">
                <el-button :type="isMobileLogin ? 'primary' : 'default'" icon="el-icon-mobile" circle
                  @click="switchLoginType('mobile')"></el-button>
              </el-tooltip>
              <el-tooltip :content="$t('login.usernameLogin')" placement="bottom">
                <el-button :type="!isMobileLogin ? 'primary' : 'default'" icon="el-icon-user" circle
                  @click="switchLoginType('username')"></el-button>
              </el-tooltip>
            </div>
          </div>

          <div class="agreement">
            {{ $t("login.agreeTo") }}
            <button type="button" @click="openPage('/user-agreement.html')">{{ $t("login.userAgreement") }}</button>
            {{ $t("login.and") }}
            <button type="button" @click="openPage('/privacy-policy.html')">{{ $t("login.privacyPolicy") }}</button>
          </div>
        </div>
      </section>
    </main>

    <footer class="yiyi-footer">
      <span>YIYI AI</span>
      <span class="footer-dot"></span>
      <span>{{ brandCopy.footer }}</span>
    </footer>
  </div>
</template>

<script>
import Api from "@/apis/api";
import i18n, { changeLanguage } from "@/i18n";
import { getUUID, goToPage, showDanger, showSuccess, sm2Encrypt, validateMobile } from "@/utils";
import { mapState } from "vuex";
import featureManager from "@/utils/featureManager";

export default {
  name: "login",
  components: {},
  computed: {
    ...mapState({
      allowUserRegister: (state) => state.pubConfig.allowUserRegister,
      enableMobileRegister: (state) => state.pubConfig.enableMobileRegister,
      mobileAreaList: (state) => state.pubConfig.mobileAreaList,
      sm2PublicKey: (state) => state.pubConfig.sm2PublicKey,
    }),
    // 获取当前语言
    currentLanguage() {
      return i18n.locale || "zh_CN";
    },
    // 获取当前语言显示文本
    currentLanguageText() {
      const currentLang = this.currentLanguage;
      switch (currentLang) {
        case "zh_CN":
          return this.$t("language.zhCN");
        case "zh_TW":
          return this.$t("language.zhTW");
        case "en":
          return this.$t("language.en");
        case "de":
          return this.$t("language.de");
        case "vi":
          return this.$t("language.vi");
        case "pt_BR":
          return this.$t("language.ptBR");
        default:
          return this.$t("language.zhCN");
      }
    },
    brandCopy() {
      const copy = {
        zh_CN: {
          eyebrow: "AI 陪伴玩偶控制中心",
          title: "让每一次回应，都更懂陪伴。",
          subtitle: "在这里管理声音、记忆、模型与设备，让玩偶保持温暖、稳定的表达。",
          featureOne: "语音",
          featureTwo: "记忆",
          featureThree: "设备",
          noteTitle: "正在倾听",
          noteBody: "一个更懂陪伴的智能玩偶",
          console: "管理控制台",
          welcome: "欢迎回来",
          loginHint: "登录后继续管理设备与服务",
          usernameLabel: "管理员账号",
          mobileLabel: "手机号",
          passwordLabel: "登录密码",
          captchaLabel: "安全验证",
          refreshCaptcha: "点击刷新验证码",
          secure: "HTTPS 安全连接",
          footer: "让科技更有温度",
        },
        zh_TW: {
          eyebrow: "AI 陪伴玩偶控制中心",
          title: "讓每一次回應，都更懂陪伴。",
          subtitle: "在這裡管理聲音、記憶、模型與設備。",
          featureOne: "語音", featureTwo: "記憶", featureThree: "設備",
          noteTitle: "正在傾聽", noteBody: "一個更懂陪伴的智能玩偶",
          console: "管理控制台", welcome: "歡迎回來", loginHint: "登入後繼續管理設備與服務",
          usernameLabel: "管理員帳號", mobileLabel: "手機號", passwordLabel: "登入密碼", captchaLabel: "安全驗證",
          refreshCaptcha: "點擊更新驗證碼", secure: "HTTPS 安全連線", footer: "讓科技更有溫度",
        },
        en: {
          eyebrow: "AI COMPANION CONTROL CENTER",
          title: "Make every response feel more caring.",
          subtitle: "Manage YIYI AI voices, memory, models and devices in one calm, secure place.",
          featureOne: "Voice", featureTwo: "Memory", featureThree: "Devices",
          noteTitle: "Listening", noteBody: "A companion designed to understand",
          console: "ADMIN CONSOLE", welcome: "Welcome back", loginHint: "Sign in to manage your YIYI AI",
          usernameLabel: "Admin account", mobileLabel: "Mobile number", passwordLabel: "Password", captchaLabel: "Security check",
          refreshCaptcha: "Refresh captcha", secure: "Secure HTTPS connection", footer: "Technology with a warmer touch",
        },
      };
      return copy[this.currentLanguage] || copy.en;
    },
  },
  data() {
    return {
      activeName: "username",
      form: {
        username: "",
        password: "",
        captcha: "",
        captchaId: "",
        areaCode: "+86",
        mobile: "",
      },
      captchaUuid: "",
      captchaUrl: "",
      isMobileLogin: false,
      languageDropdownVisible: false,
    };
  },
  mounted() {
    this.fetchCaptcha();
    this.$store.dispatch("fetchPubConfig").then(() => {
      // 根据配置决定默认登录方式
      this.isMobileLogin = this.enableMobileRegister;
    });
  },
  methods: {
    openPage(url) {
      const lang = this.$i18n ? this.$i18n.locale : 'zh_CN';
      if (!lang.startsWith('zh')) {
        url = url.replace('.html', '-en.html');
      }
      window.open(url, '_blank');
    },
    fetchCaptcha() {
      // 处理手动清空localstorage导致无法获取验证码的问题
      const token = localStorage.getItem('token')
      if (token) {
        if (this.$route.path !== "/home") {
          this.$router.push("/home");
        }
      } else {
        this.captchaUuid = getUUID();

        Api.user.getCaptcha(this.captchaUuid, (res) => {
          if (res.status === 200) {
            const blob = new Blob([res.data], { type: res.data.type });
            this.captchaUrl = URL.createObjectURL(blob);
          } else {
            showDanger("验证码加载失败，点击刷新");
          }
        });
      }
    },

    // 切换语言下拉菜单的可见状态变化
    handleLanguageDropdownVisibleChange(visible) {
      this.languageDropdownVisible = visible;
    },

    // 切换语言
    changeLanguage(lang) {
      changeLanguage(lang);
      this.languageDropdownVisible = false;
      this.$message.success({
        message: this.$t("message.success"),
        showClose: true,
      });
    },

    // 切换登录方式
    switchLoginType(type) {
      this.isMobileLogin = type === "mobile";
      // 清空表单
      this.form.username = "";
      this.form.mobile = "";
      this.form.password = "";
      this.form.captcha = "";
      this.fetchCaptcha();
    },

    // 封装输入验证逻辑
    validateInput(input, messageKey) {
      if (!input.trim()) {
        showDanger(this.$t(messageKey));
        return false;
      }
      return true;
    },
    
    getUserInfo() {
      Api.user.getUserInfo(({ data }) => {
        if (data.code === 0) {
          this.$store.commit("setUserInfo", data.data);
          goToPage("/home");
        } else {
          showDanger("用户信息获取失败");
        }
      });
    },

    async login() {
      if (this.isMobileLogin) {
        // 手机号登录验证
        if (!validateMobile(this.form.mobile, this.form.areaCode)) {
          showDanger(this.$t('login.requiredMobile'));
          return;
        }
        // 拼接手机号作为用户名
        this.form.username = this.form.areaCode + this.form.mobile;
      } else {
        // 用户名登录验证
        if (!this.validateInput(this.form.username, 'login.requiredUsername')) {
          return;
        }
      }

      // 验证密码
      if (!this.validateInput(this.form.password, 'login.requiredPassword')) {
        return;
      }
      // 验证验证码
      if (!this.validateInput(this.form.captcha, 'login.requiredCaptcha')) {
        return;
      }
      // 加密密码
      let encryptedPassword;
      try {
        // 拼接验证码和密码
        const captchaAndPassword = this.form.captcha + this.form.password;
        encryptedPassword = sm2Encrypt(this.sm2PublicKey, captchaAndPassword);
      } catch (error) {
        console.error("密码加密失败:", error);
        showDanger(this.$t('sm2.encryptionFailed'));
        return;
      }

      const plainUsername = this.form.username;

      this.form.captchaId = this.captchaUuid;

      // 加密
      const loginData = {
        username: plainUsername,
        password: encryptedPassword,
        captchaId: this.form.captchaId
      };

      Api.user.login(
        loginData,
        ({ data }) => {
          showSuccess(this.$t('login.loginSuccess'));
          this.$store.commit("setToken", JSON.stringify(data.data));
          this.getUserInfo();
        },
        (err) => {
          // 直接使用后端返回的国际化消息
          let errorMessage = err.data.msg || "登录失败";

          showDanger(errorMessage);
        }
      );

      // 重新获取验证码
      setTimeout(() => {
        this.fetchCaptcha();
      }, 1000);
    },

    goToRegister() {
      goToPage("/register");
    },
    goToForgetPassword() {
      goToPage("/retrieve-password");
    }
  },
};
</script>
<style lang="scss" scoped>
@import "./auth.scss";

.login-type-container {
  margin: 2px 0 12px;
  display: flex;
  justify-content: center;
}

.login-type-switch {
  display: flex;
  gap: 10px;
}

.title-language-dropdown {
  position: relative;
  z-index: 6;
  cursor: pointer;
}

.el-dropdown-link {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 12px;
  border: 1px solid rgba(113, 89, 79, 0.12);
  border-radius: 999px;
  color: #6f625e;
  background: rgba(255, 253, 249, 0.68);
  backdrop-filter: blur(10px);
}

.language-icon {
  color: #d76752;
}

.current-language-text {
  font-size: 12px;
  color: #5e514d;
}

.rotate-down {
  transform: rotate(180deg);
  transition: transform 0.3s ease;
}

.el-icon-arrow-down {
  transition: transform 0.3s ease;
}

:deep(.el-button--primary) {
  background-color: #e96f58;
  border-color: #e96f58;

  &:hover,
  &:focus {
    background-color: #d85a45;
    border-color: #d85a45;
  }

  &:active {
    background-color: #c44d3b;
    border-color: #c44d3b;
  }
}
</style>
