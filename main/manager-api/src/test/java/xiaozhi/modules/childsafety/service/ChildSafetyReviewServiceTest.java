package xiaozhi.modules.childsafety.service;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import xiaozhi.modules.agent.dto.AgentUpdateDTO;
import xiaozhi.modules.agent.entity.AgentChatHistoryEntity;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.agent.service.AgentChatHistoryService;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.agent.vo.AgentInfoVO;
import xiaozhi.modules.childsafety.dao.ChildSafetyEventDao;
import xiaozhi.modules.childsafety.dao.ChildSafetyReviewDao;
import xiaozhi.modules.childsafety.dao.ChildSafetySettingDao;
import xiaozhi.modules.childsafety.dto.ChildSafetySettingDTO;
import xiaozhi.modules.childsafety.entity.ChildSafetyReviewEntity;
import xiaozhi.modules.childsafety.entity.ChildSafetySettingEntity;
import xiaozhi.modules.llm.service.LLMService;

class ChildSafetyReviewServiceTest {
    @Test
    void enablingChildSafetyKeepsMemMeAndForcesTextOnlyHistory() {
        ChildSafetySettingDao settingDao = mock(ChildSafetySettingDao.class);
        AgentService agentService = mock(AgentService.class);
        AgentInfoVO agent = new AgentInfoVO();
        agent.setId("agent-memme");
        agent.setUserId(7L);
        agent.setMemModelId("Memory_memme");
        agent.setChatHistoryConf(2);
        when(agentService.getAgentById("agent-memme", 7L)).thenReturn(agent);
        when(settingDao.selectOne(any())).thenReturn(null);

        ChildSafetyReviewService service = new ChildSafetyReviewService(
                settingDao, mock(ChildSafetyReviewDao.class), mock(ChildSafetyEventDao.class),
                agentService, mock(AgentChatHistoryService.class), mock(LLMService.class));
        ChildSafetySettingDTO setting = new ChildSafetySettingDTO();
        setting.setEnabled(true);

        service.updateSetting("agent-memme", 7L, setting);

        ArgumentCaptor<AgentUpdateDTO> update = ArgumentCaptor.forClass(AgentUpdateDTO.class);
        verify(agentService).updateAgentById(org.mockito.ArgumentMatchers.eq("agent-memme"),
                update.capture(), org.mockito.ArgumentMatchers.eq(7L));
        assertEquals(null, update.getValue().getMemModelId());
        assertEquals(1, update.getValue().getChatHistoryConf());
    }

    @Test
    void redactsPrivateValuesBeforeModelReview() {
        String result = ChildSafetyReviewService.redact(
                "电话13812345678 邮箱 child@example.com 验证码是123456 https://example.com sk-abcdefghijklmnop");

        assertFalse(result.contains("13812345678"));
        assertFalse(result.contains("child@example.com"));
        assertFalse(result.contains("123456"));
        assertFalse(result.contains("https://example.com"));
        assertFalse(result.contains("sk-abcdefghijklmnop"));
        assertTrue(result.contains("已隐藏"));
    }

    @Test
    void createsStructuredDailyReviewWithoutStoringQuotes() {
        ChildSafetyReviewDao reviewDao = mock(ChildSafetyReviewDao.class);
        AgentChatHistoryService historyService = mock(AgentChatHistoryService.class);
        LLMService llmService = mock(LLMService.class);
        when(reviewDao.selectOne(any())).thenReturn(null, null);
        when(reviewDao.insert(any(ChildSafetyReviewEntity.class))).thenAnswer(invocation -> {
            ((ChildSafetyReviewEntity) invocation.getArgument(0)).setId(1L);
            return 1;
        });
        when(historyService.list(any(com.baomidou.mybatisplus.core.conditions.Wrapper.class))).thenReturn(List.of(
                AgentChatHistoryEntity.builder()
                        .agentId("agent-1")
                        .chatType((byte) 1)
                        .content("今天有人在学校欺负我")
                        .createdAt(new Date())
                        .build()));
        when(llmService.generateSummary(anyString(), anyString(), anyString())).thenReturn("""
                {"riskLevel":"MEDIUM","summary":"孩子说今天有人在学校欺负我，需要关注。","items":[
                {"category":"bullying","level":"MEDIUM","timeWindow":"下午","reason":"孩子可能遇到同伴欺凌。","action":"温和询问经过并联系老师。"}],
                "parentAdvice":"先认真倾听孩子。"}
                """);

        ChildSafetyReviewService service = new ChildSafetyReviewService(
                mock(ChildSafetySettingDao.class), reviewDao, mock(ChildSafetyEventDao.class),
                mock(AgentService.class), historyService, llmService);
        AgentEntity agent = new AgentEntity();
        agent.setId("agent-1");
        agent.setUserId(1L);
        agent.setSlmModelId("LLM_AliLLM");
        ChildSafetySettingEntity setting = new ChildSafetySettingEntity();
        setting.setAgentId("agent-1");

        ChildSafetyReviewEntity result = service.reviewAgentDay(
                agent, setting, ZonedDateTime.now(ZoneId.of("Asia/Shanghai")), true);

        assertEquals("COMPLETED", result.getStatus());
        assertEquals("MEDIUM", result.getRiskLevel());
        assertEquals(1, result.getRiskCount());
        assertFalse(result.getSummary().contains("今天有人在学校欺负我"));
        assertFalse(result.getDetailsJson().contains("今天有人在学校欺负我"));
        assertTrue(result.getDetailsJson().contains("bullying"));
    }

    @Test
    void doesNotTreatInconsistentModelResultAsSafe() {
        ChildSafetyReviewDao reviewDao = mock(ChildSafetyReviewDao.class);
        AgentChatHistoryService historyService = mock(AgentChatHistoryService.class);
        LLMService llmService = mock(LLMService.class);
        when(reviewDao.selectOne(any())).thenReturn(null, null);
        when(reviewDao.insert(any(ChildSafetyReviewEntity.class))).thenAnswer(invocation -> {
            ((ChildSafetyReviewEntity) invocation.getArgument(0)).setId(2L);
            return 1;
        });
        when(historyService.list(any(com.baomidou.mybatisplus.core.conditions.Wrapper.class))).thenReturn(List.of(
                AgentChatHistoryEntity.builder()
                        .agentId("agent-2")
                        .chatType((byte) 1)
                        .content("普通聊天")
                        .createdAt(new Date())
                        .build()));
        when(llmService.generateSummary(anyString(), anyString(), anyString())).thenReturn(
                "{\"riskLevel\":\"HIGH\",\"summary\":\"有风险\",\"items\":[],\"parentAdvice\":\"请关注\"}");

        ChildSafetyReviewService service = new ChildSafetyReviewService(
                mock(ChildSafetySettingDao.class), reviewDao, mock(ChildSafetyEventDao.class),
                mock(AgentService.class), historyService, llmService);
        AgentEntity agent = new AgentEntity();
        agent.setId("agent-2");
        agent.setUserId(1L);
        agent.setSlmModelId("LLM_AliLLM");
        ChildSafetySettingEntity setting = new ChildSafetySettingEntity();
        setting.setAgentId("agent-2");

        ChildSafetyReviewEntity result = service.reviewAgentDay(
                agent, setting, ZonedDateTime.now(ZoneId.of("Asia/Shanghai")), true);

        assertEquals("FAILED", result.getStatus());
        assertEquals("UNKNOWN", result.getRiskLevel());
    }

    @Test
    void keepsLatestMessagesWhenConversationExceedsModelLimit() {
        ChildSafetyReviewDao reviewDao = mock(ChildSafetyReviewDao.class);
        AgentChatHistoryService historyService = mock(AgentChatHistoryService.class);
        LLMService llmService = mock(LLMService.class);
        when(reviewDao.selectOne(any())).thenReturn(null, null);
        when(reviewDao.insert(any(ChildSafetyReviewEntity.class))).thenAnswer(invocation -> {
            ((ChildSafetyReviewEntity) invocation.getArgument(0)).setId(3L);
            return 1;
        });
        List<AgentChatHistoryEntity> messages = new ArrayList<>();
        for (int i = 0; i < 15; i++) {
            String marker = i == 0 ? "OLDEST_MARKER" : i == 14 ? "LATEST_MARKER" : "MESSAGE_" + i;
            messages.add(AgentChatHistoryEntity.builder()
                    .agentId("agent-3")
                    .chatType((byte) 1)
                    .content(marker + "字".repeat(1990))
                    .createdAt(new Date(1_000L * (i + 1)))
                    .build());
        }
        when(historyService.list(any(com.baomidou.mybatisplus.core.conditions.Wrapper.class))).thenReturn(messages);
        when(llmService.generateSummary(anyString(), anyString(), anyString())).thenReturn(
                "{\"riskLevel\":\"NONE\",\"summary\":\"无风险\",\"items\":[],\"parentAdvice\":\"无需处理\"}");

        ChildSafetyReviewService service = new ChildSafetyReviewService(
                mock(ChildSafetySettingDao.class), reviewDao, mock(ChildSafetyEventDao.class),
                mock(AgentService.class), historyService, llmService);
        AgentEntity agent = new AgentEntity();
        agent.setId("agent-3");
        agent.setUserId(1L);
        agent.setSlmModelId("LLM_AliLLM");
        ChildSafetySettingEntity setting = new ChildSafetySettingEntity();
        setting.setAgentId("agent-3");

        service.reviewAgentDay(agent, setting, ZonedDateTime.now(ZoneId.of("Asia/Shanghai")), true);

        ArgumentCaptor<String> conversation = ArgumentCaptor.forClass(String.class);
        verify(llmService).generateSummary(conversation.capture(), anyString(), anyString());
        assertTrue(conversation.getValue().contains("LATEST_MARKER"));
        assertFalse(conversation.getValue().contains("OLDEST_MARKER"));
    }
}
