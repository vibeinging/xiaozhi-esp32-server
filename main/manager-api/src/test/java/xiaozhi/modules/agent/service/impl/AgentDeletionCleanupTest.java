package xiaozhi.modules.agent.service.impl;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import xiaozhi.modules.agent.dao.AgentDao;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.agent.service.AgentChatHistoryService;
import xiaozhi.modules.agent.service.AgentContextProviderService;
import xiaozhi.modules.agent.service.AgentPluginMappingService;
import xiaozhi.modules.agent.service.AgentSnapshotService;
import xiaozhi.modules.agent.service.AgentTagService;
import xiaozhi.modules.correctword.service.CorrectWordFileService;
import xiaozhi.modules.device.service.DeviceService;

class AgentDeletionCleanupTest {
    @Test
    void deletingAgentAlsoDeletesChildSafetyData() {
        AgentDao agentDao = mock(AgentDao.class);
        DeviceService deviceService = mock(DeviceService.class);
        AgentChatHistoryService historyService = mock(AgentChatHistoryService.class);
        AgentPluginMappingService pluginService = mock(AgentPluginMappingService.class);
        AgentContextProviderService contextService = mock(AgentContextProviderService.class);
        CorrectWordFileService correctWordService = mock(CorrectWordFileService.class);
        AgentTagService tagService = mock(AgentTagService.class);
        AgentSnapshotService snapshotService = mock(AgentSnapshotService.class);
        AgentServiceImpl service = new AgentServiceImpl(
                agentDao, null, null, null, null, deviceService, pluginService,
                historyService, null, null, contextService, tagService,
                correctWordService, snapshotService);
        ReflectionTestUtils.setField(service, "baseDao", agentDao);
        AgentEntity agent = new AgentEntity();
        agent.setId("agent-1");
        when(agentDao.selectByIdForUpdate("agent-1")).thenReturn(agent);

        service.deleteAgent("agent-1");

        verify(agentDao).deleteChildSafetyEventsByAgentId("agent-1");
        verify(agentDao).deleteChildSafetyReviewsByAgentId("agent-1");
        verify(agentDao).deleteChildSafetySettingByAgentId("agent-1");
        verify(historyService).deleteByAgentId("agent-1", true, true);
        verify(agentDao).deleteById("agent-1");
    }
}
